import io
import asyncio
import logging
import httpx
import exifread
import numpy as np
import cv2
import json

# Import existing ML models
from app import ml
from app.config import settings

logger = logging.getLogger(__name__)

async def download_image(url: str) -> bytes:
    """Download an image robustly using httpx."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=30.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.content

def download_image_sync(url: str) -> bytes:
    """Synchronous version for easier notebook usage without await."""
    import requests
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    response = requests.get(url, headers=headers, timeout=30.0, allow_redirects=True)
    response.raise_for_status()
    return response.content

def extract_exif(image_bytes: bytes) -> dict:
    """
    Extracts EXIF metadata from an image. 
    Returns a dictionary of relevant tags. Will highlight Software or Generator tags.
    """
    try:
        tags = exifread.process_file(io.BytesIO(image_bytes), details=False)
        result = {}
        for tag, value in tags.items():
            if tag not in ('JPEGThumbnail', 'TIFFThumbnail', 'Filename', 'EXIF MakerNote'):
                result[tag] = str(value)
        return result
    except Exception as e:
        logger.error(f"Error extracting EXIF: {e}")
        return {"error": str(e)}

def detect_faces(image_bytes: bytes) -> int:
    """
    Uses OpenCV to quickly detect the number of human faces in an image.
    Useful for deciding whether to run GAN face deepfake detectors.
    """
    try:
        # Convert bytes to cv2 image
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return 0
            
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Load the pre-trained Haar cascade for frontal face
        # We need to use the default xml path from opencv package
        import os
        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        if not os.path.exists(cascade_path):
            return -1 # Cascade not found
            
        face_cascade = cv2.CascadeClassifier(cascade_path)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        
        return len(faces)
    except Exception as e:
        logger.error(f"Face detection failed: {e}")
        return -1

def run_diffusion_detector(image_bytes: bytes) -> dict:
    """Run Stable Diffusion / Flux / Midjourney detector."""
    return ml.score_sdxl(image_bytes)

def run_gan_detector(image_bytes: bytes) -> dict:
    """Run GAN face deepfake detector."""
    return ml.score_gan_face(image_bytes)

def analyze_image_orchestrated(image_url: str) -> dict:
    """
    An example utility showing how an orchestrated check could be run.
    Sphinx might call this directly or recreate this logic itself.
    """
    results = {}
    try:
        image_bytes = download_image_sync(image_url)
        results["image_downloaded"] = True
        
        # 1. EXIF Data Check
        exif_data = extract_exif(image_bytes)
        results["exif_data"] = exif_data
        
        # 2. Diffusion Check
        diffusion_res = run_diffusion_detector(image_bytes)
        results["diffusion_score"] = diffusion_res.get("fake_prob", 0.0)
        
        # 3. Face Check -> GAN Check
        num_faces = detect_faces(image_bytes)
        results["num_faces"] = num_faces
        if num_faces > 0:
            gan_res = run_gan_detector(image_bytes)
            results["gan_score"] = gan_res.get("fake_prob", 0.0)
        else:
            results["gan_score"] = 0.0 # No faces, no gan score
            
        return results
    except Exception as e:
        return {"error": str(e)}

def extract_image_context_gemini(image_bytes: bytes, tweet_text: str = "") -> str:
    """
    Uses Gemini 2.5 Flash Lite to extract rich semantic context from the image.
    Transcribes text within the image and notes suspicious flags or contradictions.
    """
    if not settings.gemini_api_key:
        return "Gemini API key not configured. Visual context extraction skipped."
        
    try:
        from google import genai
        from google.genai import types
        
        client = genai.Client(api_key=settings.gemini_api_key)
        
        prompt = (
            "You are an elite Trust & Safety forensic analyst. Describe the contents of this image concisely. "
            "1. Identify key subjects (people, logos, objects). "
            "2. Transcribe any visible text inside the image. "
            "3. If context text was provided, note if the image obviously contradicts it. "
            f"Context text provided by the user: '{tweet_text}'"
        )
        
        # We must construct a 'Part' object for the image bytes to send to Gemini
        img_part = types.Part.from_bytes(
            data=image_bytes,
            mime_type="image/jpeg" # Assume JPEG/PNG, the model is somewhat robust
        )
        
        # gemini-2.5-flash-lite is the recommended lightweight fast multimodal model
        response = client.models.generate_content(
            model='gemini-2.5-flash-lite',
            contents=[prompt, img_part],
        )
        return response.text
    except Exception as e:
        logger.error(f"Gemini VLM extraction failed: {e}")
        return f"VLM Context Extraction Failed: {e}"


async def analyze_image_parallel(image_bytes: bytes, tweet_text: str = "") -> dict:
    """
    Runs EXIF extraction, diffusion detection, and face/GAN detection concurrently.
    Uses asyncio.to_thread for CPU-bound ML model calls so they don't block the event loop.
    The image bytes are passed in directly — caller is responsible for the download.

    Returns a dict with keys:
        exif_data, diffusion_score, diffusion_label, gan_score, num_faces
    """

    # Define each synchronous task as a callable for asyncio.to_thread
    def _exif():
        return extract_exif(image_bytes)

    def _diffusion():
        return run_diffusion_detector(image_bytes)

    def _faces():
        return detect_faces(image_bytes)

    # Fire EXIF and diffusion detection in parallel immediately
    exif_task = asyncio.to_thread(_exif)
    diffusion_task = asyncio.to_thread(_diffusion)
    faces_task = asyncio.to_thread(_faces)

    exif_data, diffusion_result, num_faces = await asyncio.gather(
        exif_task, diffusion_task, faces_task
    )

    diffusion_score = diffusion_result.get("fake_prob", 0.0)
    diffusion_label = diffusion_result.get("label", "unknown")

    gan_score = 0.0
    if isinstance(num_faces, int) and num_faces > 0:
        gan_result = await asyncio.to_thread(lambda: run_gan_detector(image_bytes))
        gan_score = gan_result.get("fake_prob", 0.0)

    # 4. Optional: Gemini Context Extraction (runs after Exif/Diffusion/Faces)
    # Ideally this would also be in the initial gather block, but for simplicity of the return struct right now,
    # we run it here if an api key is present.
    image_context = ""
    if settings.gemini_api_key:
        image_context = await asyncio.to_thread(extract_image_context_gemini, image_bytes, tweet_text)

    return {
        "exif_data": exif_data,
        "diffusion_score": round(diffusion_score, 4),
        "diffusion_label": diffusion_label,
        "gan_score": round(gan_score, 4),
        "num_faces": num_faces,
        "image_context": image_context
    }

