import os
import re
import time
import json
import cv2
import logging
import base64
import hashlib
import urllib.parse
import google.generativeai as genai
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import List, Optional
import numpy as np
import asyncio
import httpx

# 🔑 Load API keys
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
POLLINATIONS_API_KEY = os.getenv("POLLINATIONS_API_KEY", "")

# ✅ Gemini Model
model = genai.GenerativeModel("gemini-2.5-flash")

# 🌸 Pollinations official OpenAI-compatible API
POLLINATIONS_API_URL = "https://gen.pollinations.ai/v1/images/generations"

# Best models for avatar generation (tried in priority order)
AVATAR_MODELS = [
    "klein",          # Artistic quality, good for avatars
    "flux",           # Best quality
    "nanobanana-pro", # Great cartoon style
    "seedream-pro",   # Artistic quality
    "gptimage",       # Good prompt accuracy
    "seedream",       # Fast fallback
    "nanobanana",     # Stylized fallback
    "nanobanana-2",   # Extra fallback
    "seedream5",      # Extra fallback
]

# ✅ Valid image magic bytes — use tuple for startswith()
VALID_IMAGE_MAGIC = (
    b'\xFF\xD8\xFF',  # JPEG
    b'\x89PNG',       # PNG
    b'GIF8',          # GIF
    b'RIFF',          # WebP
    b'BM',            # BMP
)

# ═══════════════════════════════════════════════════════
# ⚡ IN-MEMORY CACHE — avoid re-analyzing the same image
# ═══════════════════════════════════════════════════════
ANALYSIS_CACHE: dict = {}
CACHE_MAX_SIZE = 50
CACHE_TTL_SECONDS = 3600  # 1 hour


def _cache_key(image_bytes: bytes) -> str:
    return hashlib.md5(image_bytes).hexdigest()


def _cache_get(key: str):
    entry = ANALYSIS_CACHE.get(key)
    if not entry:
        return None
    if time.time() - entry["cached_at"] > CACHE_TTL_SECONDS:
        del ANALYSIS_CACHE[key]
        return None
    return entry["features"]


def _cache_set(key: str, features: dict):
    if len(ANALYSIS_CACHE) >= CACHE_MAX_SIZE:
        oldest_key = min(ANALYSIS_CACHE, key=lambda k: ANALYSIS_CACHE[k]["cached_at"])
        del ANALYSIS_CACHE[oldest_key]
        print(f"🗑️  Cache full — evicted oldest entry")
    ANALYSIS_CACHE[key] = {"features": features, "cached_at": time.time()}
    print(f"💾 Cached analysis | total entries: {len(ANALYSIS_CACHE)}")


# 🔷 Logging setup
logging.basicConfig(
    filename="ai_log.txt",
    level=logging.INFO,
    format="%(asctime)s - %(message)s"
)

# 🔷 Parser
class QueryParser:
    def parse(self, query: str):
        query = query.strip().lower()

        if not query:
            return "INVALID"

        if all(not c.isalnum() for c in query):
            return "NOISE"

        if re.match(r"^\d+e\d+$", query):
            return "NOISE"

        if query.isnumeric():
            return "NOISE"

        keywords = [
            "image", "picture", "photo", "show", "see",
            "animal", "person", "object", "car", "dog", "cat",
            "what", "describe", "who", "where", "color", "happening"
        ]

        greetings = ["hi", "hello", "hey", "morning", "evening", "how are you", "help", "who are you", "exit", "quit"]

        if any(word in query for word in keywords):
            return "VALID"

        if any(word in query for word in greetings):
            return "GREETING"

        return "NON_IMAGE"

parser = QueryParser()

app = FastAPI()

# 🔷 CORS Setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔷 Safety
def safety_check(query):
    blocked = ["who is this person", "identify person"]
    return not any(b in query.lower() for b in blocked)


def is_blurry(image_bytes, threshold=15):
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)   # ⚡ skip color decode

        if image is None:
            return False

        h, w = image.shape[:2]
        if h < 100 or w < 100:
            return False

        variance = cv2.Laplacian(image, cv2.CV_64F).var()
        return variance < threshold
    except Exception as e:
        print(f"Error in blur detection: {e}")
        return False


# ⚡ Image Compression
def compress_image(image_bytes, max_dim=800):
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        h, w = image.shape[:2]

        if max(h, w) > max_dim:
            scale = max_dim / float(max(h, w))
            image = cv2.resize(image, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

        _, compressed = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 75])
        return compressed.tobytes()
    except Exception as e:
        print(f"Error compressing image: {e}")
        return image_bytes


# 🔷 Gemini Vision  (runs in thread — never blocks the event loop)
MAX_RETRIES = 3

async def ask_gemini(question, images_data):
    images = [{"mime_type": "image/jpeg", "data": d} for d in images_data]

    prompt = [
        "You are VisionAI. Answer the user's question based on the image(s). "
        "Use plain text with emojis. No asterisks or markdown. Keep it concise.",
        f"User: {question}"
    ]

    def _call():
        for attempt in range(MAX_RETRIES):
            try:
                response = model.generate_content(prompt + images)
                answer = response.text.strip()
                answer = answer.replace("**", "").replace("* ", "• ")
                return answer
            except Exception as e:
                if "429" in str(e) and attempt < MAX_RETRIES - 1:
                    wait = (attempt + 1) * 10  # 10s, 20s backoff
                    print(f"⚠️  Rate limited (attempt {attempt+1}/{MAX_RETRIES}), retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    raise

    return await asyncio.to_thread(_call)   # ⚡ off the event loop


@app.post("/ask")
async def ask_endpoint(
    question: str = Form(...),
    images: List[UploadFile] = File(default=[])
):
    result = parser.parse(question)

    if result == "INVALID":
        return {"answer": "❌ Empty question"}
    elif result == "NOISE":
        return {"answer": "❌ Noise detected (invalid input)"}
    elif result == "NON_IMAGE" and not images:
        return {"answer": "❌ Please upload an image or ask a vision-related question."}

    if not safety_check(question):
        return {"answer": "❌ Safety check failed: Not allowed"}

    try:
        start = time.time()

        valid_images_data = []
        if images and len(images) > 0:
            for img in images:
                if img.size == 0: continue

                content = await img.read()
                if is_blurry(content):
                    logging.warning(f"Rejected blurry image: {img.filename}")
                    return {
                        "answer": f"❌ The image '{img.filename}' appears to be blurry. Please provide a clearer image.",
                        "status": "error"
                    }

                fast_content = compress_image(content, max_dim=768)   # ⚡ was 800
                valid_images_data.append(fast_content)

        answer = await ask_gemini(question, valid_images_data)

        end = time.time()
        response_time = round(end - start, 2)
        logging.info(f"Query: {question} | Answer: {answer}")

        try:
            with open("response_times.log", "a", encoding="utf-8") as f:
                timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
                f.write(f"[{timestamp}] Response Time: {response_time}s | Query: {question}\n")
        except Exception as log_err:
            print(f"Failed to write performance log: {log_err}")

        return {"answer": answer, "response_time": response_time, "status": "success"}

    except Exception as e:
        logging.error(f"Error for query '{question}': {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════
# 🎨 AVATAR / BITMOJI GENERATOR ENDPOINTS
# ═══════════════════════════════════════════════════════

# ⚡ TRIMMED prompt — fewer tokens = faster Gemini response
FACE_ANALYSIS_PROMPT = """Analyze this face and return ONLY valid JSON, no extra text:
{
  "gender": "male/female/non-binary",
  "facial_expression": "specific emotion: happy/sad/serious/excited/neutral/smirking/surprised/angry/playful/shy/confident",
  "emotional_intensity": "1-10",
  "hairstyle": "exact description e.g. short wavy, long straight, bald, tight bun",
  "hair_color": "e.g. dark brown, blonde, jet black",
  "eye_color": "color",
  "skin_tone": "fair/light/medium/olive/brown/dark",
  "face_shape": "round/oval/square/heart/oblong",
  "facial_hair": "none/stubble/beard/mustache with detail",
  "accessories": "glasses/earrings/hat/none",
  "clothing_style": "brief description",
  "age_range": "e.g. 20-25",
  "distinguishing_features": "dimples/freckles/moles/none"
}"""

async def analyze_face_with_gemini(image_bytes):
    """Use Gemini to analyze facial features — runs off-thread to avoid blocking."""
    # ⚡ smaller image = faster upload to Gemini + faster token processing
    compressed = compress_image(image_bytes, max_dim=512)

    image_part = {"mime_type": "image/jpeg", "data": compressed}

    def _call():
        response = model.generate_content([FACE_ANALYSIS_PROMPT, image_part])
        text = response.text.strip()
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        return {"error": "Could not parse facial analysis"}

    return await asyncio.to_thread(_call)   # ⚡ off the event loop


# ═══════════════════════════════════════════════════════
# 🎨 STYLE DEFINITIONS — each style has unique visual DNA
# ═══════════════════════════════════════════════════════

STYLE_PROMPTS = {
    "modern 3d cartoon": {
        "description": "modern 3D cartoon render, Bitmoji/Snapchat style, smooth plastic shading, rounded friendly features, vibrant saturated colors, clean topology",
        "quality_tags": "3D rendered, subsurface scattering, soft rim lighting, clean smooth surfaces, Bitmoji aesthetic, high quality render"
    },
    "pixar style": {
        "description": "Pixar/Disney 3D animation style, expressive oversized eyes, warm cinematic lighting, exaggerated but charming proportions, like a character from Inside Out or Coco",
        "quality_tags": "Pixar CGI render, global illumination, SSS skin shader, film-quality 3D, cinematic color grading, Disney Pixar aesthetic"
    },
    "anime": {
        "description": "Japanese anime illustration style, 2D hand-drawn look, large glossy expressive eyes, clean sharp line art, cel shading with flat color fills, Studio Ghibli or modern anime aesthetic",
        "quality_tags": "anime art style, cel shaded, clean ink linework, manga inspired, flat color fills, glossy eye highlights, 2D illustration"
    },
    "chibi": {
        "description": "Chibi super-deformed style, giant oversized head (60% of body), tiny stubby body, huge sparkling doe eyes, ultra-kawaii cute proportions, pastel palette",
        "quality_tags": "chibi character design, super deformed SD style, kawaii aesthetic, oversized head tiny body, cute cartoon, pastel colors"
    },
    "realistic": {
        "description": "semi-realistic digital portrait art, photorealistic skin with pores and texture, detailed hair strands, professional concept art quality, like a high-end character sheet",
        "quality_tags": "hyperrealistic digital painting, 8k detail, ZBrush quality, professional concept art, detailed skin texture, realistic hair simulation"
    },
    "comic book": {
        "description": "American comic book art style, bold thick ink outlines, halftone dot shading, flat bold primary colors, dynamic Marvel/DC comics illustration style",
        "quality_tags": "comic book art, bold ink outlines, halftone dots, flat colors, Ben-Day dots, Marvel DC style, graphic novel illustration"
    },
    "watercolor": {
        "description": "artistic watercolor painting style, soft wet-on-wet edges, translucent color washes, visible brush texture, dreamy painterly illustration, loose expressive strokes",
        "quality_tags": "watercolor art, soft bleeding edges, painted paper texture, transparent washes, artistic brush strokes, impressionistic painting style"
    },
}


# ═══════════════════════════════════════════════════════
# 🧍 POSE DEFINITIONS — body positioning for avatar
# ═══════════════════════════════════════════════════════

POSE_PROMPTS = {
    "standing neutral": "standing upright, relaxed neutral pose, arms at sides, weight evenly balanced, full body visible from head to feet",
    "confident arms crossed": "standing with arms confidently crossed over chest, slight forward lean, strong assertive posture, full body shot",
    "hands on hips": "standing with both hands on hips, elbows out, power pose, confident and energetic stance, full body visible",
    "casual leaning": "casually leaning against a wall with one shoulder, arms loosely crossed or one hand in pocket, relaxed cool vibe, full body shot",
    "walking forward": "mid-stride walking pose, one foot forward, arms in natural swing, dynamic movement, full body visible",
    "sitting relaxed": "seated comfortably on an invisible surface, legs slightly apart, hands resting on knees, upper body upright and relaxed",
    "pointing forward": "one arm extended forward pointing directly at viewer, other hand on hip, confident engaging pose, full body shot",
    "peace sign": "standing upright, one hand raised making a peace/victory sign gesture, other arm at side, cheerful friendly pose, full body visible",
    "superhero": "heroic superhero landing pose, one knee slightly bent, fists on hips, chest out, cape-ready stance, empowering full body shot",
    "thinking pose": "standing with one hand raised to chin in thoughtful thinking pose, weight shifted to one leg, contemplative expression, full body visible",
    "waving": "standing upright with one arm raised high, hand open in friendly wave gesture, slight lean forward, full body shot",
    "jumping": "mid-air jumping pose, knees slightly bent upward, arms raised in excitement or spread wide, dynamic energy, full body visible",
}


def build_avatar_prompt(features, customizations=None):
    """Build a style-specific image generation prompt from analyzed features."""
    if customizations is None:
        customizations = {}

    style_key          = customizations.get("style", "modern 3d cartoon").lower()
    expression_override = customizations.get("expression", "")
    background         = customizations.get("background", "clean light gray studio")
    pose_key           = customizations.get("pose", "standing neutral").lower()

    style_data        = STYLE_PROMPTS.get(style_key, STYLE_PROMPTS["modern 3d cartoon"])
    pose_instruction  = POSE_PROMPTS.get(pose_key, POSE_PROMPTS["standing neutral"])

    gender     = features.get("gender", "person")
    expression = expression_override if expression_override else features.get("facial_expression", "neutral")
    intensity  = features.get("emotional_intensity", 5)

    prompt = f"""Create a {style_data['description']} avatar with these exact features:

SUBJECT: {gender} character

FACE & FEATURES:
- Hair Style: MUST BE EXACTLY {features.get('hairstyle', 'short')}
- Hair Color: {features.get('hair_color', 'brown')}
- Eyes: {features.get('eye_color', 'brown')} colored eyes
- Skin tone: {features.get('skin_tone', 'medium')}
- Face shape: {features.get('face_shape', 'oval')}
- Facial hair: {features.get('facial_hair', 'none')}
- Expression: {expression} (intensity: {intensity}/10)
- Age appearance: {features.get('age_range', '25-30')}
- Accessories: {features.get('accessories', 'none')}
- Distinguishing features: {features.get('distinguishing_features', 'none')}

OUTFIT:
- {features.get('clothing_style', 'casual modern outfit')}

POSE & COMPOSITION:
- {pose_instruction}

TECHNICAL REQUIREMENTS:
- {style_data['quality_tags']}
- Background: {background}
- Full body shot from head to feet, centered
- High quality, professional render
- Vibrant colors with clean composition"""

    return prompt


@app.post("/analyze-face")
async def analyze_face_endpoint(image: UploadFile = File(...)):
    """Analyze a face image and return detected features."""
    try:
        if not image or image.size is None:
            raise HTTPException(status_code=400, detail="No file provided.")

        content = await image.read()

        if not content or len(content) == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        if not content[:4].startswith(VALID_IMAGE_MAGIC):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid image format (magic bytes: {content[:4].hex()}). Upload a JPEG or PNG."
            )

        # ⚡ Cache check BEFORE blur detection + compression
        cache_key = _cache_key(content)
        cached = _cache_get(cache_key)
        if cached:
            print(f"⚡ Cache HIT — returning stored analysis instantly")
            return {"features": cached, "status": "success", "cached": True}

        # Blur check only on cache miss
        if is_blurry(content, threshold=15):
            return JSONResponse(
                status_code=400,
                content={"error": "Image appears blurry. Please upload a clearer photo."}
            )

        print(f"🔍 Cache MISS — calling Gemini for analysis")
        features = await analyze_face_with_gemini(content)   # ⚡ async + off-thread

        if "error" in features:
            raise HTTPException(status_code=500, detail=features["error"])

        _cache_set(cache_key, features)

        return {"features": features, "status": "success", "cached": False}

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Face analysis error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Face analysis failed: {str(e)}")


# ═══════════════════════════════════════════════════════
# 🌸 POLLINATIONS OFFICIAL API — IMAGE GENERATION
# ═══════════════════════════════════════════════════════

async def generate_with_pollinations_api(prompt: str, width: int = 768, height: int = 1024) -> tuple:
    if not POLLINATIONS_API_KEY:
        print("⚠️  POLLINATIONS_API_KEY not set in .env — cannot generate avatar")
        return None, ""

    headers = {
        "Authorization": f"Bearer {POLLINATIONS_API_KEY}",
        "Content-Type":  "application/json",
    }

    for avatar_model in AVATAR_MODELS:
        print(f"🌸 Trying Pollinations model: {avatar_model}")

        payload = {
            "model":  avatar_model,
            "prompt": prompt,
            "size":   f"{width}x{height}",
            "n":      1,
        }

        try:
            async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
                response = await client.post(POLLINATIONS_API_URL, headers=headers, json=payload)

                if response.status_code == 200:
                    data   = response.json()
                    images = data.get("data", [])

                    if not images:
                        print(f"⚠️  {avatar_model}: empty data, trying next…")
                        continue

                    item = images[0]

                    if item.get("b64_json"):
                        image_bytes = base64.b64decode(item["b64_json"])
                        print(f"✅ Pollinations success → {avatar_model} ({len(image_bytes)//1024} KB)")
                        logging.info(f"Avatar generated: {avatar_model}")
                        return image_bytes, avatar_model

                    elif item.get("url"):
                        img_r = await client.get(item["url"])
                        if img_r.status_code == 200:
                            print(f"✅ Pollinations success → {avatar_model} (via URL)")
                            logging.info(f"Avatar generated: {avatar_model}")
                            return img_r.content, avatar_model

                    print(f"⚠️  {avatar_model}: no image data, trying next…")
                    continue

                elif response.status_code == 429:
                    print(f"⚠️  {avatar_model}: rate limited (429), trying next…")
                    await asyncio.sleep(2)
                    continue

                elif response.status_code == 401:
                    print("❌ API key invalid")
                    logging.error("Pollinations 401: invalid API key")
                    return None, ""

                elif response.status_code in (402, 403):
                    print(f"⚠️  {avatar_model}: HTTP {response.status_code}, trying next…")
                    continue

                else:
                    print(f"⚠️  {avatar_model}: HTTP {response.status_code} — {response.text[:100]}, trying next…")
                    continue

        except httpx.ConnectError as e:
            print(f"❌ Connection error: {e}")
            logging.error(f"Pollinations ConnectError: {e}")
            return None, ""

        except httpx.TimeoutException:
            print(f"⚠️  {avatar_model}: timed out, trying next…")
            continue

        except Exception as e:
            print(f"❌ {avatar_model} unexpected error: {e}")
            logging.warning(f"{avatar_model} error: {e}")
            continue

    print("❌ All Pollinations models exhausted")
    return None, ""


@app.post("/generate-avatar")
async def generate_avatar_endpoint(
    features: str = Form(...),
    style: str = Form(default="modern 3d cartoon"),
    expression: str = Form(default=""),
    background: str = Form(default="clean light gray studio"),
    pose: str = Form(default="standing neutral"),
):
    if not POLLINATIONS_API_KEY:
        raise HTTPException(
            status_code=503,
            detail=(
                "POLLINATIONS_API_KEY not configured. "
                "Get your free key at enter.pollinations.ai → API Keys, "
                "add POLLINATIONS_API_KEY=sk_xxx to your .env and restart."
            )
        )

    try:
        parsed_features = json.loads(features)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid features JSON")

    try:
        customizations = {"style": style, "expression": expression, "background": background, "pose": pose}
        prompt = build_avatar_prompt(parsed_features, customizations)

        print(f"\n🎨 Generating avatar | style={style} | expression={expression or 'auto'} | pose={pose}")
        print(f"📝 Prompt preview: {prompt[:200]}...")

        image_bytes, model_used = await generate_with_pollinations_api(prompt=prompt, width=768, height=1024)

        if not image_bytes:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Avatar generation failed. Possible causes: "
                    "(1) API key invalid — check POLLINATIONS_API_KEY  "
                    "(2) All models busy — wait and retry  "
                    "(3) Insufficient credits — visit enter.pollinations.ai"
                )
            )

        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        data_uri  = f"data:image/jpeg;base64,{b64_image}"

        return {"avatar_url": data_uri, "prompt_used": prompt, "model_used": model_used, "status": "success"}

    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e) or repr(e)
        if "429" in error_msg:
            error_msg = "Service is busy. Please wait a moment and try again."
        elif "401" in error_msg:
            error_msg = "Invalid API key. Check POLLINATIONS_API_KEY in .env."
        elif "getaddrinfo" in error_msg or "ConnectError" in error_msg:
            error_msg = "Network error: Could not reach Pollinations API."
        elif "timeout" in error_msg.lower():
            error_msg = "Request timed out. Please try again."
        logging.error(f"Avatar generation error: {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg)


# ══════════════════════════════════════════════════════
# 🔍 UTILITY ENDPOINTS
# ══════════════════════════════════════════════════════

@app.get("/models")
async def get_available_models():
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get("https://gen.pollinations.ai/image/models")
            if r.status_code == 200:
                raw = r.json()
                if raw and isinstance(raw[0], dict):
                    model_names = [item.get("name") or item.get("id") or str(item) for item in raw]
                else:
                    model_names = [str(m) for m in raw]
                return {
                    "all_models":            model_names,
                    "total":                 len(model_names),
                    "avatar_priority_order": AVATAR_MODELS,
                    "api_key_configured":    bool(POLLINATIONS_API_KEY),
                    "status":                "success"
                }
            raise HTTPException(status_code=500, detail=f"Pollinations returned {r.status_code}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/cache-stats")
async def cache_stats():
    now = time.time()
    entries = [
        {
            "key":        k[:8] + "...",
            "age_seconds": round(now - v["cached_at"]),
            "expires_in":  round(CACHE_TTL_SECONDS - (now - v["cached_at"]))
        }
        for k, v in ANALYSIS_CACHE.items()
    ]
    return {
        "total_cached": len(ANALYSIS_CACHE),
        "max_size":     CACHE_MAX_SIZE,
        "ttl_seconds":  CACHE_TTL_SECONDS,
        "entries":      entries,
        "status":       "success"
    }


@app.delete("/cache-clear")
async def cache_clear():
    count = len(ANALYSIS_CACHE)
    ANALYSIS_CACHE.clear()
    return {"cleared": count, "status": "success"}


@app.get("/")
async def root():
    return {
        "message":          "Vision AI + Avatar Generator API is running",
        "pollinations_key": "configured ✅" if POLLINATIONS_API_KEY else "NOT SET ❌ — add to .env",
        "avatar_models":    AVATAR_MODELS,
        "available_styles": list(STYLE_PROMPTS.keys()),
        "available_poses":  list(POSE_PROMPTS.keys()),
    }


if __name__ == "__main__":
    import uvicorn, requests

    W = 60
    print("\n" + "═"*W)
    print("   🤖  VisionAI + Avatar Generator  —  STARTUP")
    print("═"*W)

    if os.getenv("GEMINI_API_KEY"):
        print("✅ Gemini API key        : configured")
    else:
        print("❌ Gemini API key        : MISSING — add GEMINI_API_KEY to .env")

    print()

    if POLLINATIONS_API_KEY:
        print("✅ Pollinations API key  : configured")
        print(f"   Avatar model order   : {' → '.join(AVATAR_MODELS)}")
    else:
        print("❌ Pollinations API key  : NOT SET")
        print()
        print("   ── Get your FREE Pollinations API key ──────────────")
        print("   1. Visit  https://enter.pollinations.ai")
        print("   2. Sign in with GitHub or Google")
        print("   3. Go to  API Keys → Create New Key")
        print("   4. Copy key (starts with sk_)")
        print("   5. Add to .env:  POLLINATIONS_API_KEY=sk_xxxxxxxxxxxx")
        print("   6. Restart the server")
        print("   ─────────────────────────────────────────────────────")

    print()
    print(f"   Available styles     : {', '.join(STYLE_PROMPTS.keys())}")
    print(f"   Available poses      : {', '.join(POSE_PROMPTS.keys())}")
    print()
    print("🔍 Checking Pollinations models...")
    try:
        r = requests.get("https://gen.pollinations.ai/image/models", timeout=10)
        if r.status_code == 200:
            raw = r.json()
            if raw and isinstance(raw[0], dict):
                model_names = [item.get("name") or item.get("id") or str(item) for item in raw]
            else:
                model_names = [str(m) for m in raw]

            print(f"✅ {len(model_names)} models available")
            print("   All available models:")
            for name in model_names:
                print(f"     • {name}")
            print()
            print("   Avatar priority models status:")
            for m in AVATAR_MODELS:
                tag = "✅" if m in model_names else "⚠️  name mismatch"
                print(f"     {tag}  {m}")

            mismatched = [m for m in AVATAR_MODELS if m not in model_names]
            if mismatched:
                print()
                print("   ℹ️  Mismatched models will still be tried via API.")
                print("   ℹ️  Update AVATAR_MODELS if they consistently fail.")
        else:
            print(f"⚠️  Could not fetch models (HTTP {r.status_code})")
    except Exception as e:
        print(f"⚠️  Could not check models: {e}")

    print()
    print(f"   Docs    →  http://localhost:8000/docs")
    print(f"   Models  →  http://localhost:8000/models")
    print("═"*W + "\n")

    uvicorn.run(app, host="0.0.0.0", port=8000)
