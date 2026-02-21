import io
import warnings
import httpx
import numpy as np
from PIL import Image
from sentence_transformers import SentenceTransformer
from transformers import pipeline
import logging

logger = logging.getLogger(__name__)

# Suppress Hugging Face warnings for cleaner logs
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*resume_download.*")

# --- Config ---
CLIP_MODEL_NAME = "sentence-transformers/clip-ViT-B-32"

# Model 1: Best at detecting Stable Diffusion, Flux, Midjourney (the dominant AI content on Twitter)
SDXL_DETECTOR_MODEL = "Organika/sdxl-detector"

# Model 2: Best at detecting GAN-faces (StyleGAN, etc.)
GAN_FACE_DETECTOR_MODEL = "dima806/deepfake_vs_real_image_detection"

# --- Globals for lazy loading ---
_clip_model = None
_sdxl_pipeline = None
_gan_pipeline = None


def get_clip_model():
    global _clip_model
    if _clip_model is None:
        logger.info(f"Loading CLIP model: {CLIP_MODEL_NAME}")
        _clip_model = SentenceTransformer(CLIP_MODEL_NAME)
    return _clip_model


def get_sdxl_pipeline():
    """Lazy-load the SDXL/diffusion AI-image detector."""
    global _sdxl_pipeline
    if _sdxl_pipeline is None:
        logger.info(f"Loading diffusion detector model: {SDXL_DETECTOR_MODEL}")
        _sdxl_pipeline = pipeline(
            "image-classification",
            model=SDXL_DETECTOR_MODEL,
        )
    return _sdxl_pipeline


def get_gan_pipeline():
    """Lazy-load the GAN face deepfake detector."""
    global _gan_pipeline
    if _gan_pipeline is None:
        logger.info(f"Loading GAN face detector model: {GAN_FACE_DETECTOR_MODEL}")
        _gan_pipeline = pipeline(
            "image-classification",
            model=GAN_FACE_DETECTOR_MODEL,
        )
    return _gan_pipeline


async def fetch_image(url: str) -> bytes:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=30.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.content


def get_clip_vector(image_bytes: bytes) -> list[float]:
    """Generates a normalized CLIP embedding for Actian DB."""
    model = get_clip_model()
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    embedding = model.encode(image, normalize_embeddings=True)
    return embedding.tolist()


def _extract_fake_prob_from_results(results: list, fake_labels: list[str]) -> float:
    """Extracts the probability of 'fake' from a transformers pipeline result list."""
    for item in results:
        label = item.get("label", "").lower()
        if any(fl in label for fl in fake_labels):
            return float(item["score"])
    return 0.0


def score_sdxl(image_bytes: bytes) -> dict:
    """
    Run Organika/sdxl-detector.
    Labels: 'artificial' (AI-generated) vs 'real'.
    """
    try:
        pipe = get_sdxl_pipeline()
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        results = pipe(image)
        logger.info(f"[SDXL] raw output: {results}")
        fake_prob = _extract_fake_prob_from_results(results, fake_labels=["artificial", "fake", "ai"])
        logger.info(f"[SDXL] fake_prob extracted: {fake_prob:.4f}")
        return {"fake_prob": fake_prob, "raw": results}
    except Exception as e:
        logger.error(f"SDXL detector failed: {e}")
        return {"fake_prob": 0.5, "error": str(e)}


def score_gan_face(image_bytes: bytes) -> dict:
    """
    Run dima806/deepfake_vs_real_image_detection.
    Labels: 'FAKE' vs 'REAL'.
    """
    try:
        pipe = get_gan_pipeline()
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        results = pipe(image)
        logger.info(f"[GAN] raw output: {results}")
        fake_prob = _extract_fake_prob_from_results(results, fake_labels=["fake", "artificial", "generated"])
        logger.info(f"[GAN] fake_prob extracted: {fake_prob:.4f}")
        return {"fake_prob": fake_prob, "raw": results}
    except Exception as e:
        logger.error(f"GAN face detector failed: {e}")
        return {"fake_prob": 0.5, "error": str(e)}
