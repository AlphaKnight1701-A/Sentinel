import logging
from fastapi import FastAPI
from pydantic import BaseModel, HttpUrl

from .config import settings

# Configure logging
logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Sentinel Backend",
    version="0.1.0",
    description="AI Content & Fake Account Detection Backend",
)

# Log startup info
logger.info(f"Starting backend - Environment: {settings.environment}")
if settings.actian_vectorai_url:
    logger.info("✓ Actian VectorAI configured")
if settings.sphinx_api_key:
    logger.info("✓ Sphinx API key loaded")
if settings.safetykit_api_key:
    logger.info("✓ SafetyKit API key loaded")


class AnalyzePayload(BaseModel):
    image_url: HttpUrl | None = None
    profile_text: str | None = None
    post_text: str | None = None


@app.get("/health")
def health_check() -> dict:
    return {
        "status": "ok",
        "service": "sentinel-backend",
        "environment": settings.environment,
        "integrations_configured": {
            "actian": bool(settings.actian_vectorai_url),
            "sphinx": bool(settings.sphinx_api_key),
            "safetykit": bool(settings.safetykit_api_key),
            "hive": bool(settings.hive_api_key),
        },
    }


@app.post("/analyze")
def analyze(payload: AnalyzePayload) -> dict:
    logger.debug(f"Analyze request received: image_url={payload.image_url}")
    return {
        "risk_score": 0,
        "trust_signal": "analysis_not_implemented",
        "summary": "Dockerized backend running. Integrate CLIP + Actian + Sphinx pipeline here.",
        "input_received": payload.model_dump(mode="json"),
    }
