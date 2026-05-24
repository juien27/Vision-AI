import { useState, useRef, useEffect } from "react";
import {
  Send,
  Image as ImageIcon,
  Upload,
  Loader2,
  Sparkles,
  Trash2,
  Plus,
  Cpu,
  ShieldCheck,
  Eye,
  User,
  Download,
  RefreshCw,
  Wand2,
  Camera,
  Palette,
  CheckCircle2
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

const API_BASE = "http://localhost:8000";

// ═══════════════════════════════════════
// VISION AI TAB COMPONENT
// ═══════════════════════════════════════
function VisionTab() {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [images, setImages] = useState([]);
  const [previews, setPreviews] = useState([]);
  const [chatHistory, setChatHistory] = useState([]);
  const fileInputRef = useRef(null);
  const chatEndRef = useRef(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatHistory, loading]);

  const handleImageUpload = (e) => {
    const files = Array.from(e.target.files);
    setImages((prev) => [...prev, ...files]);
    const newPreviews = files.map((file) => URL.createObjectURL(file));
    setPreviews((prev) => [...prev, ...newPreviews]);
  };

  const removeImage = (index) => {
    setImages(images.filter((_, i) => i !== index));
    setPreviews(previews.filter((_, i) => i !== index));
  };

  const askQuestion = async () => {
    if (!question.trim()) return;
    const currentQuestion = question;
    const currentImages = [...images];

    setQuestion("");
    setLoading(true);

    setChatHistory((prev) => [
      ...prev,
      { type: "user", content: currentQuestion, images: previews },
    ]);

    const formData = new FormData();
    formData.append("question", currentQuestion);
    currentImages.forEach((img) => formData.append("images", img));

    try {
      const res = await fetch(`${API_BASE}/ask`, {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      setChatHistory((prev) => [
        ...prev,
        { type: "ai", content: data.answer, status: "success" },
      ]);
    } catch (err) {
      setChatHistory((prev) => [
        ...prev,
        {
          type: "ai",
          content:
            "I encountered an error connecting to the vision engine. Please ensure the backend is running and try again.",
          status: "error",
        },
      ]);
    }

    setLoading(false);
  };

  const handleKeyPress = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      askQuestion();
    }
  };

  return (
    <div className="vision-layout fade-in">
      {/* Sidebar */}
      <aside className="sidebar">
        <div
          className="glass"
          style={{
            padding: "1rem",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <div className="stat-item">
            <span className="stat-label">Model</span>
            <span className="stat-value">Gemini Flash</span>
          </div>
          <button
            onClick={() => {
              setImages([]);
              setPreviews([]);
              setChatHistory([]);
              setQuestion("");
            }}
            className="send-btn"
            style={{
              background: "rgba(239, 68, 68, 0.12)",
              color: "#ef4444",
              padding: "6px 12px",
              fontSize: "0.72rem",
              gap: "4px",
              border: "1px solid rgba(239, 68, 68, 0.15)",
            }}
            title="Clear session"
          >
            <Trash2 size={13} />
            Reset
          </button>
        </div>

        <div
          className="glass image-gallery"
          style={{ display: "flex", flexDirection: "column" }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "0.75rem",
            }}
          >
            <h3
              style={{
                fontSize: "0.78rem",
                color: "var(--text-secondary)",
                fontWeight: 600,
              }}
            >
              Reference Images
            </h3>
            <button
              onClick={() => fileInputRef.current.click()}
              className="send-btn"
              style={{
                width: "28px",
                height: "28px",
                padding: 0,
                borderRadius: "8px",
              }}
            >
              <Plus size={16} />
            </button>
          </div>

          <input
            type="file"
            multiple
            hidden
            ref={fileInputRef}
            onChange={handleImageUpload}
            accept="image/*"
          />

          {previews.length === 0 ? (
            <div
              style={{
                flex: 1,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--text-muted)",
                gap: "0.5rem",
                border: "2px dashed var(--glass-border)",
                borderRadius: "12px",
                padding: "2rem",
              }}
            >
              <ImageIcon size={28} opacity={0.25} />
              <p style={{ fontSize: "0.75rem" }}>No images uploaded</p>
            </div>
          ) : (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "0.6rem",
              }}
            >
              <AnimatePresence>
                {previews.map((src, idx) => (
                  <motion.div
                    key={src}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    className="image-card"
                  >
                    <img src={src} alt={`Upload ${idx}`} />
                    <span className="image-badge badge-valid">
                      <ShieldCheck
                        size={9}
                        style={{ marginRight: "2px" }}
                      />
                      OK
                    </span>
                    <button
                      onClick={() => removeImage(idx)}
                      style={{
                        position: "absolute",
                        bottom: "6px",
                        right: "6px",
                        background: "rgba(239, 68, 68, 0.85)",
                        border: "none",
                        borderRadius: "6px",
                        padding: "3px",
                        color: "white",
                        cursor: "pointer",
                      }}
                    >
                      <Trash2 size={11} />
                    </button>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          )}
        </div>
      </aside>

      {/* Chat */}
      <main className="main-content">
        <div className="glass chat-container">
          <div className="chat-messages">
            {chatHistory.length === 0 && !loading && (
              <div
                style={{
                  height: "100%",
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: "center",
                  textAlign: "center",
                  gap: "1rem",
                  opacity: 0.7,
                }}
              >
                <div
                  style={{
                    width: "60px",
                    height: "60px",
                    background: "var(--bg-accent)",
                    borderRadius: "50%",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    boxShadow: "0 0 30px var(--accent-glow)",
                  }}
                >
                  <Cpu size={28} color="var(--accent-secondary)" />
                </div>
                <div>
                  <h2
                    style={{
                      fontSize: "1.35rem",
                      fontWeight: 700,
                      marginBottom: "0.4rem",
                    }}
                  >
                    How can I help you today?
                  </h2>
                  <p
                    style={{
                      color: "var(--text-secondary)",
                      fontSize: "0.85rem",
                      lineHeight: 1.6,
                    }}
                  >
                    Upload images and ask questions about them.
                    <br />I can detect objects, read text, or describe scenes.
                  </p>
                </div>
              </div>
            )}

            {chatHistory.map((msg, idx) => (
              <motion.div
                key={idx}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className={`message ${msg.type === "user" ? "message-user" : "message-ai"
                  }`}
              >
                {msg.type === "user" &&
                  msg.images &&
                  msg.images.length > 0 && (
                    <div
                      style={{
                        display: "flex",
                        gap: "4px",
                        marginBottom: "6px",
                        flexWrap: "wrap",
                      }}
                    >
                      {msg.images.map((img, i) => (
                        <img
                          key={i}
                          src={img}
                          alt="ref"
                          style={{
                            width: "36px",
                            height: "36px",
                            borderRadius: "4px",
                            objectFit: "cover",
                            border: "1px solid rgba(255,255,255,0.2)",
                          }}
                        />
                      ))}
                    </div>
                  )}
                {msg.type === "ai" && typeof msg.content === "string"
                  ? msg.content
                    .replace(/\*\*/g, "")
                    .replace(/(^|\n)\s*\*\s/g, "$1• ")
                    .replace(/\*/g, "")
                  : msg.content}
                {msg.status === "error" && (
                  <div
                    style={{
                      fontSize: "0.65rem",
                      color: "#ffbaba",
                      marginTop: "4px",
                    }}
                  >
                    ⚠ Connection Error
                  </div>
                )}
              </motion.div>
            ))}

            {loading && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="message message-ai"
              >
                <div className="typing-dots">
                  <div className="dot"></div>
                  <div className="dot"></div>
                  <div className="dot"></div>
                </div>
              </motion.div>
            )}
            <div ref={chatEndRef} />
          </div>

          <div className="chat-input-area">
            <button
              onClick={() => fileInputRef.current.click()}
              className="send-btn"
              style={{
                background: "var(--bg-accent)",
                color: "var(--text-secondary)",
              }}
              title="Upload Image"
            >
              <Upload size={18} />
            </button>
            <input
              type="text"
              className="chat-input"
              placeholder={
                images.length > 0
                  ? "Ask about selected images..."
                  : "Upload images or ask a question..."
              }
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyPress={handleKeyPress}
            />
            <button
              onClick={askQuestion}
              className="send-btn"
              disabled={loading || !question.trim()}
            >
              {loading ? (
                <Loader2 size={18} className="animate-spin" />
              ) : (
                <Send size={18} />
              )}
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}

// ═══════════════════════════════════════
// AVATAR CREATOR TAB COMPONENT
// ═══════════════════════════════════════
function AvatarTab() {
  const [selectedFile, setSelectedFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [features, setFeatures] = useState(null);
  const [avatarUrl, setAvatarUrl] = useState(null);
  const [customizations, setCustomizations] = useState({
    style: "modern 3D cartoon",
    expression: "",
    background: "clean light gray studio",
  });
  const [isWebcamActive, setIsWebcamActive] = useState(false);
  const fileInputRef = useRef(null);
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);

  useEffect(() => {
    return () => {
      stopWebcam();
    };
  }, []);

  useEffect(() => {
    if (isWebcamActive && videoRef.current && streamRef.current) {
      videoRef.current.srcObject = streamRef.current;
    }
  }, [isWebcamActive]);

  const startWebcam = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true });
      streamRef.current = stream;
      setIsWebcamActive(true);
      setSelectedFile(null);
      setPreviewUrl(null);
      setFeatures(null);
      setAvatarUrl(null);
    } catch (err) {
      console.error("Error accessing webcam:", err);
      alert("Could not access the webcam. Please ensure you have given permission.");
    }
  };

  const stopWebcam = () => {
    if (streamRef.current) {
      const tracks = streamRef.current.getTracks();
      tracks.forEach(track => track.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setIsWebcamActive(false);
  };

  const captureImage = () => {
    if (videoRef.current && canvasRef.current) {
      const video = videoRef.current;
      const canvas = canvasRef.current;
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const context = canvas.getContext("2d");
      context.drawImage(video, 0, 0, canvas.width, canvas.height);
      
      canvas.toBlob(async (blob) => {
        if (blob) {
          const file = new File([blob], "webcam-capture.jpg", { type: "image/jpeg" });
          setSelectedFile(file);
          setPreviewUrl(URL.createObjectURL(file));
          stopWebcam();
          
          // Auto-generate avatar after capturing
          const detectedFeatures = await analyzeFace(file);
          if (detectedFeatures) {
            await generateAvatar(detectedFeatures);
          }
        }
      }, "image/jpeg");
    }
  };

  const handleFileSelect = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setSelectedFile(file);
    setPreviewUrl(URL.createObjectURL(file));
    setFeatures(null);
    setAvatarUrl(null);

    // Auto-generate avatar after uploading
    const detectedFeatures = await analyzeFace(file);
    if (detectedFeatures) {
      await generateAvatar(detectedFeatures);
    }
  };

  const analyzeFace = async (overrideFile = null) => {
    const targetFile = overrideFile || selectedFile;
    if (!targetFile) {
      alert("Please select or capture an image first.");
      return null;
    }
    
    // Validate file
    if (!(targetFile instanceof File) && !(targetFile instanceof Blob)) {
      console.error("Invalid file object:", targetFile);
      alert("Invalid file format. Please select a valid image.");
      return null;
    }
    
    if (targetFile.size === 0) {
      alert("File is empty. Please select a valid image.");
      return null;
    }
    
    setAnalyzing(true);
    setFeatures(null);

    const formData = new FormData();
    formData.append("image", targetFile);

    try {
      const res = await fetch(`${API_BASE}/analyze-face`, {
        method: "POST",
        body: formData,
      });
      
      const data = await res.json();

      if (!res.ok) {
        const errorMsg = data.error || data.detail || `Error: ${res.status} ${res.statusText}`;
        console.error("Analysis failed:", errorMsg);
        alert(errorMsg);
        setAnalyzing(false);
        return null;
      } else if (data.features) {
        setFeatures(data.features);
        setAnalyzing(false);
        return data.features;
      }
    } catch (err) {
      console.error("Analysis error:", err);
      alert("Failed to connect to the analysis engine. Make sure the backend is running.");
      setAnalyzing(false);
      return null;
    }
    setAnalyzing(false);
    return null;
  };

  const generateAvatar = async (overrideFeatures = null) => {
    const targetFeatures = overrideFeatures || features;
    if (!targetFeatures) return;
    setGenerating(true);
    setAvatarUrl(null);

    const formData = new FormData();
    formData.append("features", JSON.stringify(targetFeatures));
    formData.append("style", customizations.style);
    formData.append("expression", customizations.expression);
    formData.append("background", customizations.background);

    try {
      const res = await fetch(`${API_BASE}/generate-avatar`, {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) {
        alert(data.detail || "An error occurred during generation.");
        setGenerating(false);
      } else if (data.avatar_url) {
        setAvatarUrl(data.avatar_url);
        // Do NOT setGenerating(false) here, we will wait for the image to load
      } else {
        setGenerating(false);
      }
    } catch (err) {
      console.error("Generation error:", err);
      alert("Failed to connect to the backend generation service.");
      setGenerating(false);
    }
  };

  const downloadAvatar = () => {
    if (!avatarUrl) return;
    const link = document.createElement("a");
    link.href = avatarUrl;
    link.download = "my-avatar.png";
    link.target = "_blank";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const resetAll = () => {
    setSelectedFile(null);
    setPreviewUrl(null);
    setFeatures(null);
    setAvatarUrl(null);
    setCustomizations({
      style: "modern 3D cartoon",
      expression: "",
      background: "clean light gray studio",
    });
    stopWebcam();
  };

  const featureEntries = features
    ? Object.entries(features).filter(
      ([key]) => key !== "error"
    )
    : [];

  const genderClass = features
    ? features.gender?.toLowerCase().includes("female")
      ? "female"
      : features.gender?.toLowerCase().includes("male")
        ? "male"
        : "other"
    : "";

  return (
    <div className="avatar-layout fade-in">
      {/* Left Panel: Upload + Analysis */}
      <div className="avatar-panel">
        <span className="avatar-panel-title">📸 Input & Analysis</span>

        {/* Upload/Webcam Actions */}
        {!previewUrl && !isWebcamActive && (
          <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.5rem" }}>
             <button className="btn-primary" onClick={() => fileInputRef.current.click()} style={{ flex: 1 }}>
                <Upload size={16} /> Upload Image
             </button>
             <button className="btn-primary" onClick={startWebcam} style={{ flex: 1, background: "var(--bg-accent)", border: "1px solid var(--glass-border)" }}>
                <Camera size={16} /> Use Camera
             </button>
          </div>
        )}

        {/* Upload Zone / Webcam View */}
        {isWebcamActive ? (
          <div className="upload-zone" style={{ padding: "0.5rem", cursor: "default" }}>
             <video ref={videoRef} autoPlay playsInline style={{ width: "100%", borderRadius: "8px", background: "#000" }} />
             <canvas ref={canvasRef} style={{ display: "none" }} />
             <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.5rem", width: "100%" }}>
                <button className="btn-primary" onClick={captureImage} style={{ flex: 1 }}>
                  📸 Capture
                </button>
                <button className="btn-primary" onClick={stopWebcam} style={{ flex: 1, background: "rgba(239, 68, 68, 0.12)", color: "#ef4444", border: "1px solid rgba(239, 68, 68, 0.15)" }}>
                  Cancel
                </button>
             </div>
          </div>
        ) : (
          <div
            className={`upload-zone ${previewUrl ? "has-image" : ""}`}
            onClick={!previewUrl ? () => fileInputRef.current.click() : undefined}
          >
            <input
              type="file"
              hidden
              ref={fileInputRef}
              onChange={handleFileSelect}
              accept="image/*"
            />
            {previewUrl ? (
              <img src={previewUrl} alt="Your photo" />
            ) : (
              <>
                <div className="upload-icon-wrapper">
                  <Camera size={24} color="var(--accent-secondary)" />
                </div>
                <p className="upload-text">
                  <strong>Click to upload</strong> your photo
                </p>
                <p className="upload-hint">
                  JPG, PNG • Clear face photo recommended
                </p>
              </>
            )}
          </div>
        )}

        {/* Action Buttons */}
        {previewUrl && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            style={{ display: "flex", gap: "0.5rem" }}
          >
            <button
              className="btn-primary"
              onClick={async () => {
                const detectedFeatures = await analyzeFace();
                if (detectedFeatures) {
                  await generateAvatar(detectedFeatures);
                }
              }}
              disabled={analyzing}
              style={{ flex: 1 }}
            >
              {analyzing ? (
                <>
                  <Loader2 size={16} className="animate-spin" /> Analyzing...
                </>
              ) : (
                <>
                  <Eye size={16} /> Analyze Face
                </>
              )}
            </button>
            <button
              className="btn-primary"
              onClick={resetAll}
              style={{
                background: "rgba(239, 68, 68, 0.12)",
                color: "#ef4444",
                border: "1px solid rgba(239, 68, 68, 0.15)",
              }}
            >
              <RefreshCw size={16} />
            </button>
          </motion.div>
        )}

        {/* Detected Features */}
        {features && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="glass"
            style={{ padding: "1rem" }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: "0.75rem",
              }}
            >
              <h3
                style={{
                  fontSize: "0.82rem",
                  fontWeight: 700,
                  color: "var(--text-primary)",
                }}
              >
                <CheckCircle2
                  size={14}
                  style={{
                    display: "inline",
                    marginRight: "6px",
                    color: "var(--success-color)",
                  }}
                />
                Biometric Analysis
              </h3>
              {features.gender && (
                <span className={`gender-badge ${genderClass}`}>
                  {features.gender}
                </span>
              )}
            </div>
            <div className="features-grid">
              {featureEntries.map(([key, value]) => (
                <div className="feature-tag" key={key}>
                  <span className="feature-tag-label">
                    {key.replace(/_/g, " ")}
                  </span>
                  <span className="feature-tag-value">
                    {String(value)}
                  </span>
                </div>
              ))}
            </div>
          </motion.div>
        )}

        {/* Customization */}
        {features && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="glass custom-controls"
          >
            <h3
              style={{
                fontSize: "0.82rem",
                fontWeight: 700,
                color: "var(--text-primary)",
                display: "flex",
                alignItems: "center",
                gap: "0.4rem",
              }}
            >
              <Palette size={14} color="var(--accent-secondary)" />
              Customization
            </h3>

            <div className="control-group">
              <label className="control-label">Avatar Style</label>
              <select
                className="control-select"
                value={customizations.style}
                onChange={(e) =>
                  setCustomizations({ ...customizations, style: e.target.value })
                }
              >
                <option value="modern 3D cartoon">🎨 Modern 3D Cartoon</option>
                <option value="Pixar-style 3D animation">🎬 Pixar Style</option>
                <option value="anime style">🌸 Anime</option>
                <option value="chibi kawaii style">🍡 Chibi</option>
                <option value="realistic digital art">🖼️ Realistic</option>
                <option value="comic book style">💥 Comic Book</option>
                <option value="watercolor illustration">🎨 Watercolor</option>
              </select>
            </div>

            <div className="control-group">
              <label className="control-label">Expression Override</label>
              <select
                className="control-select"
                value={customizations.expression}
                onChange={(e) =>
                  setCustomizations({
                    ...customizations,
                    expression: e.target.value,
                  })
                }
              >
                <option value="">🤖 Auto-Detect (AI)</option>
                <option value="genuinely happy, big smile">😊 Happy</option>
                <option value="sad, melancholic look">😢 Sad</option>
                <option value="angry, intense expression">😡 Angry</option>
                <option value="surprised, eyes wide open">😲 Surprised</option>
                <option value="cool and confident">😎 Confident</option>
                <option value="playful wink">😜 Playful</option>
                <option value="thoughtful, contemplative">🤔 Thoughtful</option>
                <option value="fearful, worried expression">😰 Fearful</option>
                <option value="neutral, serious">😐 Neutral</option>
              </select>
            </div>

            <div className="control-group">
              <label className="control-label">Background</label>
              <select
                className="control-select"
                value={customizations.background}
                onChange={(e) =>
                  setCustomizations({
                    ...customizations,
                    background: e.target.value,
                  })
                }
              >
                <option value="clean light gray studio">⬜ Studio Gray</option>
                <option value="vibrant gradient background">🌈 Gradient</option>
                <option value="futuristic neon city">🌃 Neon City</option>
                <option value="nature park with trees">🌳 Nature</option>
                <option value="abstract colorful geometric">🔶 Abstract</option>
                <option value="transparent background">🏁 Transparent</option>
              </select>
            </div>

            <button
              className="btn-primary"
              onClick={() => generateAvatar()}
              disabled={generating}
              style={{ marginTop: "0.25rem" }}
            >
              {generating ? (
                <>
                  <Loader2 size={16} className="animate-spin" /> Generating
                  Avatar...
                </>
              ) : (
                <>
                  <Wand2 size={16} /> Generate Avatar
                </>
              )}
            </button>
          </motion.div>
        )}
      </div>

      {/* Right Panel: Avatar Result */}
      <div className="avatar-panel">
        <span className="avatar-panel-title">✨ Generated Avatar</span>

        <div className="avatar-result-wrapper" style={{ flex: 1 }}>
          {generating && (
            <div className="loading-overlay">
              <div className="loading-spinner"></div>
              <span className="loading-text">
                Creating your avatar with AI...
              </span>
            </div>
          )}

          {avatarUrl ? (
            <motion.img
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              src={avatarUrl}
              alt="Generated avatar"
              onLoad={() => setGenerating(false)}
              onError={(e) => {
                setGenerating(false);
                setAvatarUrl(null);
                alert("Failed to load avatar image from the generation service. Please try again.");
              }}
              style={{ display: generating ? "none" : "block" }}
            />
          ) : (
            !generating && (
              <div className="avatar-placeholder">
                <div className="avatar-placeholder-icon">
                  <User size={32} color="var(--text-muted)" />
                </div>
                <p style={{ fontSize: "0.9rem", fontWeight: 600 }}>
                  Your avatar will appear here
                </p>
                <p style={{ fontSize: "0.75rem", maxWidth: "260px" }}>
                  Upload a photo → Analyze → Customize → Generate
                </p>
              </div>
            )
          )}
        </div>

        {avatarUrl && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="avatar-actions"
          >
            <button
              className="btn-primary"
              onClick={downloadAvatar}
              style={{ flex: 1 }}
            >
              <Download size={16} /> Download Avatar
            </button>
            <button
              className="btn-primary"
              onClick={generateAvatar}
              disabled={generating}
              style={{
                background: "var(--bg-accent)",
                border: "1px solid var(--glass-border)",
              }}
            >
              <RefreshCw size={16} /> Regenerate
            </button>
          </motion.div>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════
// MAIN APP COMPONENT
// ═══════════════════════════════════════
export default function App() {
  const [activeTab, setActiveTab] = useState("vision");

  return (
    <>
      {/* Top Navigation */}
      <nav className="top-nav">
        <div className="nav-brand">
          <Sparkles size={20} color="var(--accent-secondary)" />
          <span className="nav-brand-text">VisionAI</span>
        </div>

        <div className="nav-tabs">
          <button
            className={`nav-tab ${activeTab === "vision" ? "active" : ""}`}
            onClick={() => setActiveTab("vision")}
          >
            <Eye size={15} />
            Vision Engine
          </button>
          <button
            className={`nav-tab ${activeTab === "avatar" ? "active" : ""}`}
            onClick={() => setActiveTab("avatar")}
          >
            <User size={15} />
            Avatar Creator
          </button>
        </div>

        <div className="nav-status">
          <div className="status-dot"></div>
          <span>System Online</span>
        </div>
      </nav>

      {/* Main Content */}
      <div className="app-container">
        <AnimatePresence mode="wait">
          {activeTab === "vision" ? (
            <motion.div
              key="vision"
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 20 }}
              transition={{ duration: 0.25 }}
              style={{ width: "100%", height: "100%" }}
            >
              <VisionTab />
            </motion.div>
          ) : (
            <motion.div
              key="avatar"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.25 }}
              style={{ width: "100%", height: "100%" }}
            >
              <AvatarTab />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </>
  );
}
