import os
import re
import time
import json
import cv2
import logging
import base64
import urllib.parse
import google.generativeai as genai
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import List, Optional
import numpy as np
import asyncio

# 🔑 Load API key
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# ✅ Model
model = genai.GenerativeModel("gemini-flash-latest")

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

# 🔷 Blur Detection (Optimized for bytes)
def is_blurry(image_bytes, threshold=20):
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        variance = cv2.Laplacian(gray, cv2.CV_64F).var()
        return variance < threshold
    except Exception as e:
        print(f"Error in blur detection: {e}")
        return False

# ⚡ Image Compression (For faster network upload to Gemini)
def compress_image(image_bytes, max_dim=800):
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        h, w = image.shape[:2]
        
        if max(h, w) > max_dim:
            scale = max_dim / float(max(h, w))
            image = cv2.resize(image, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

        _, compressed = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return compressed.tobytes()
    except Exception as e:
        print(f"Error compressing image: {e}")
        return image_bytes

# 🔷 Gemini
async def ask_gemini(question, images_data):
    images = []

    for img_data in images_data:
        images.append({
            "mime_type": "image/jpeg",
            "data": img_data
        })

    prompt = [
        "You are VisionAI, a helpful assistant. "
        "If images are provided, answer the user's question based on the images. "
        "If NO images are provided, reply to the user's greeting or conversation politely. "
        "IMPORTANT: Format your response clearly using plain text with paragraphs and newlines. Include relevant emojis to make the response engaging. Do NOT use any asterisks (*) or markdown for formatting. Keep your response very concise and brief so it can be generated quickly.",
        "If the user says 'exit' or 'quit', say goodbye and suggest they use the 'Reset' button to clear the session. "
        "If the question is completely unrelated to images AND not a greeting, say: 'Please upload an image or ask a vision-related question.'",
        f"User Question: {question}"
    ]

    response = model.generate_content(prompt + images)
    answer = response.text.strip()
    
    # 🧹 Forcefully remove stubborn markdown asterisks if the model still generates them
    answer = answer.replace("**", "")
    answer = answer.replace("* ", "• ")
    
    return answer

# 🔷 Safety
def safety_check(query):
    blocked = ["who is this person", "identify person"]
    return not any(b in query.lower() for b in blocked)

@app.post("/ask")
async def ask_endpoint(
    question: str = Form(...),
    images: List[UploadFile] = File(default=[])
):
    # 🔷 Parse input
    result = parser.parse(question)

    if result == "INVALID":
        return {"answer": "❌ Empty question"}
    elif result == "NOISE":
        return {"answer": "❌ Noise detected (invalid input)"}
    elif result == "NON_IMAGE" and not images:
        return {"answer": "❌ Please upload an image or ask a vision-related question."}

    # 🔒 Safety
    if not safety_check(question):
        return {"answer": "❌ Safety check failed: Not allowed"}

    try:
        start = time.time()
        
        valid_images_data = []
        if images and len(images) > 0:
            for img in images:
                # Check if file is empty
                if img.size == 0: continue
                
                content = await img.read()
                if is_blurry(content):
                    logging.warning(f"Rejected blurry image: {img.filename}")
                    return {
                        "answer": f"❌ The image '{img.filename}' appears to be blurry. Please provide a clearer image for accurate analysis.",
                        "status": "error"
                    }
                
                # Compress image to sharply reduce API upload latency
                fast_content = compress_image(content)
                valid_images_data.append(fast_content)

        # Gemini handles both images and chat automatically
        answer = await ask_gemini(question, valid_images_data)
        
        end = time.time()
        response_time = round(end - start, 2)

        # 🔷 General Logging
        logging.info(f"Query: {question} | Answer: {answer}")
        
        # ⏱️ Separate Performance Log
        try:
            with open("response_times.log", "a", encoding="utf-8") as f:
                timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
                f.write(f"[{timestamp}] Response Time: {response_time}s | Query: {question}\n")
        except Exception as log_err:
            print(f"Failed to write performance log: {log_err}")

        return {
            "answer": answer,
            "response_time": response_time,
            "status": "success"
        }

    except Exception as e:
        logging.error(f"Error for query '{question}': {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ═══════════════════════════════════════════════════════
# 🎨 AVATAR / BITMOJI GENERATOR ENDPOINTS
# ═══════════════════════════════════════════════════════

async def analyze_face_with_gemini(image_bytes):
    """Use Gemini to analyze facial features for avatar generation."""
    compressed = compress_image(image_bytes, max_dim=512)

    image_part = {
        "mime_type": "image/jpeg",
        "data": compressed
    }

    prompt = """Analyze this face image comprehensively for avatar creation. Return ONLY valid JSON:
{
  "gender": "Identify gender with high precision (male/female/non-binary). Look for subtle cues: jawline structure, brow ridge, facial proportions, Adam's apple visibility",
  "facial_expression": "Detect the EXACT emotional state. Don't just say 'neutral'. Options include: genuinely happy, subtle smile, excited, laughing, serious/focused, contemplative, sad, melancholic, angry, frustrated, surprised, shocked, fearful, worried, disgusted, confused, bored, sleepy, confident, smirking, playful, shy. Be as specific as possible.",
  "emotional_intensity": "Rate 1-10 how intense the expression is",
  "hairstyle": "Describe the exact hair styling and length very precisely (e.g., 'tightly pulled back hair with no hair on face', 'long straight hair', 'short curly bob', 'bald'). This is critical for avatar accuracy.",
  "hair_color": "exact shade (e.g., 'dark brown', 'platinum blonde', 'auburn red', 'jet black')",
  "eye_color": "color of eyes",
  "skin_tone": "descriptive skin tone (e.g., 'fair', 'light olive', 'medium brown', 'dark')",
  "face_shape": "round/oval/square/heart/oblong",
  "facial_hair": "For males: stubble/beard/mustache/clean-shaven with detail. For females: none",
  "accessories": "glasses, earrings, piercings, headband, hat, etc.",
  "clothing_style": "What they appear to be wearing",
  "age_range": "estimated age range (e.g., '20-25', '30-35')",
  "distinguishing_features": "any unique features like dimples, freckles, beauty marks, scars"
}
Be extremely accurate. Analyze every detail carefully."""

    response = model.generate_content([prompt, image_part])
    text = response.text.strip()

    # Extract JSON from response
    json_match = re.search(r'\{[\s\S]*\}', text)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    return {"error": "Could not parse facial analysis"}


def build_avatar_prompt(features, customizations=None):
    """Build an image generation prompt from analyzed features."""
    if customizations is None:
        customizations = {}

    style = customizations.get("style", "modern 3D cartoon")
    expression_override = customizations.get("expression", "")
    background = customizations.get("background", "clean light gray studio")

    gender = features.get("gender", "person")
    expression = expression_override if expression_override else features.get("facial_expression", "neutral")
    intensity = features.get("emotional_intensity", 5)

    prompt = f"""Create a professional 3D bitmoji-style avatar with these exact specifications:

SUBJECT: A {gender} character

FACE & FEATURES:
- Hair Style: MUST BE EXACTLY {features.get('hairstyle', 'short')}
- Hair Color: {features.get('hair_color', 'brown')}
- Eyes: {features.get('eye_color', 'brown')} eyes
- Skin tone: {features.get('skin_tone', 'medium')}
- Face shape: {features.get('face_shape', 'oval')}
- Facial hair: {features.get('facial_hair', 'none')}
- Expression: {expression} (intensity: {intensity}/10)
- Age appearance: {features.get('age_range', '25-30')}
- Accessories: {features.get('accessories', 'none')}
- Distinguishing features: {features.get('distinguishing_features', 'none')}

OUTFIT:
- {features.get('clothing_style', 'casual modern outfit')}

VISUAL STYLE:
- Style: {style} (like Snapchat Bitmoji / Pixar character)
- Background: {background}
- Full body shot from head to feet
- High quality, professional render
- Clean lines, smooth shading
- Vibrant but realistic colors"""

    return prompt


@app.post("/analyze-face")
async def analyze_face_endpoint(image: UploadFile = File(...)):
    """Analyze a face image and return detected features."""
    try:
        # Validate that file was provided
        if not image or image.size is None:
            raise HTTPException(
                status_code=400,
                detail="No file provided. Please upload an image file."
            )
        
        # Read and validate file content
        content = await image.read()
        
        if not content or len(content) == 0:
            raise HTTPException(
                status_code=400,
                detail="Uploaded file is empty. Please provide a valid image file."
            )
        
        # Check if file appears to be an image (basic check for common formats)
        if not any(content[:4] == magic for magic in [b'\xFF\xD8\xFF', b'\x89PNG', b'GIF8', b'RIFF']):
            logging.warning(f"Invalid file format. First bytes: {content[:4]}")
            # Don't fail here - let Gemini try to process it

        if is_blurry(content):
            return JSONResponse(
                status_code=400,
                content={"error": "Image appears blurry. Please upload a clearer photo."}
            )

        features = await analyze_face_with_gemini(content)

        if "error" in features:
            raise HTTPException(status_code=500, detail=features["error"])

        return {
            "features": features,
            "status": "success"
        }

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Face analysis error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Face analysis failed: {str(e)}")


import httpx

@app.post("/generate-avatar")
async def generate_avatar_endpoint(
    features: str = Form(...),
    style: str = Form(default="modern 3D cartoon"),
    expression: str = Form(default=""),
    background: str = Form(default="clean light gray studio")
):
    """Generate an avatar image URL using Pollinations.ai (free)."""
    try:
        parsed_features = json.loads(features)
        customizations = {
            "style": style,
            "expression": expression,
            "background": background
        }

        prompt = build_avatar_prompt(parsed_features, customizations)
        # Remove newlines and extra spaces to avoid URL parsing issues on the image service
        clean_prompt = " ".join(prompt.split())
        encoded_prompt = urllib.parse.quote(clean_prompt)

        # Pollinations.ai — free AI image generation. Using turbo model to prevent 429 rate limits.
        avatar_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=768&height=1024&nologo=true&seed={int(time.time())}&model=turbo"

        # Try to fetch the image in the backend first (better for bypassing adblockers/limits)
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                    response = await client.get(avatar_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
                    
                    if response.status_code == 200:
                        image_bytes = response.content
                        b64_image = base64.b64encode(image_bytes).decode("utf-8")
                        data_uri = f"data:image/jpeg;base64,{b64_image}"
                        
                        return {
                            "avatar_url": data_uri,
                            "prompt_used": prompt,
                            "status": "success"
                        }
                    elif response.status_code == 429:
                        if attempt < max_retries:
                            await asyncio.sleep(2)
                            continue
                        raise Exception("429 Too Many Requests")
                    else:
                        raise Exception(f"Service returned status {response.status_code}")
            except (httpx.ConnectError, httpx.ConnectTimeout) as ce:
                logging.warning(f"Connection error on attempt {attempt + 1}: {str(ce)}")
                if attempt < max_retries:
                    await asyncio.sleep(1) # Wait a bit before retry
                    continue
                # If all retries fail, fallback to returning the direct URL (frontend can try to load it)
                logging.info("Backend fetch failed after retries, falling back to direct URL")
                return {
                    "avatar_url": avatar_url,
                    "prompt_used": prompt,
                    "status": "success",
                    "fallback": True
                }
            except Exception as e:
                logging.error(f"Unexpected error on attempt {attempt + 1}: {str(e)}")
                if attempt < max_retries:
                    continue
                raise e

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid features JSON")
    except Exception as e:
        error_msg = str(e)
        if not error_msg:
            error_msg = repr(e)
            
        if "429" in error_msg:
            error_msg = "The free AI generation service is currently busy. Please wait a moment and try again."
        elif "getaddrinfo" in error_msg or "ConnectError" in error_msg:
            error_msg = "Network/DNS error: Could not reach the image generation service. Please check your internet connection."
        elif "Timeout" in error_msg or "timeout" in error_msg.lower():
            error_msg = "The AI generation service took too long to respond. Please try again."
            
        logging.error(f"Avatar generation error: {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg)


# ═══════════════════════════════════════════════════════

@app.get("/")
async def root():
    return {"message": "Vision AI + Avatar Generator API is running"}

if __name__ == "__main__":
    import uvicorn
    print("[OK] UNIFIED AI SYSTEM API STARTED")
    uvicorn.run(app, host="0.0.0.0", port=8000)