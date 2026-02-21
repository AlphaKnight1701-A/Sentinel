import logging
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, HttpUrl

from .config import settings

SPHINX_AVAILABLE = True  # We use httpx for REST API calls

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
    if not SPHINX_AVAILABLE:
        logger.warning("⚠ Sphinx API key set, but sphinxapi not installed")
if settings.safetykit_api_key:
    logger.info("✓ SafetyKit API key loaded")

# Initialize Sphinx client if available
sphinx_api_key = settings.sphinx_api_key
sphinx_enabled = SPHINX_AVAILABLE and sphinx_api_key
if sphinx_enabled:
    logger.info("✓ Sphinx API configured via HTTP/REST")


class AnalyzePayload(BaseModel):
    content_id: str | None = Field(default=None, description="Frontend content identifier")
    content_type: Literal["post", "profile", "image", "video", "dm"] | None = None
    image_url: HttpUrl | None = None
    image_urls: list[HttpUrl] | None = None
    video_url: HttpUrl | None = None
    video_urls: list[HttpUrl] | None = None
    profile_username: str | None = None
    profile_display_name: str | None = None
    profile_bio: str | None = None
    profile_text: str | None = None
    post_text: str | None = None
    dm_text: str | None = None


class PatternMatch(BaseModel):
    match_type: Literal["image", "video", "profile", "text", "cluster"]
    similarity: float = Field(ge=0.0, le=1.0)
    source: str


class SignalFlags(BaseModel):
    similarity: list[str] = Field(default_factory=list)
    linguistic: list[str] = Field(default_factory=list)
    visual: list[str] = Field(default_factory=list)
    metadata: list[str] = Field(default_factory=list)


class TrustSignalResponse(BaseModel):
    risk_level: Literal["low", "medium", "high"] = "low"
    trust_score: int = Field(ge=0, le=100)
    reasoning_summary: str
    explanation: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    recommendation: str
    flags: SignalFlags
    risk_indicators: list[str]
    intent_analysis: list[str]
    manipulation_cues: list[str]
    contradiction_flags: list[str]
    pattern_matches: list[PatternMatch]
    deep_check_available: bool
    input_received: dict


class ClusterInfo(BaseModel):
    id: str
    similarity: float = Field(ge=0.0, le=1.0)
    reason: str
    snippet: str | None = None


class DeepCheckResponse(TrustSignalResponse):
    neighbors: list[ClusterInfo] = Field(default_factory=list)
    cluster_summary: dict = Field(default_factory=dict)
    step_by_step_analysis: list[str] = Field(default_factory=list)
    verdict: str | None = None


def build_sphinx_trust_signal(payload: AnalyzePayload, mode: str = "trust_signal") -> TrustSignalResponse | DeepCheckResponse:
    """
    Call Sphinx API via HTTP/REST to generate trust signal or deep check analysis.
    Falls back to placeholder if Sphinx unavailable.
    """
    match_type: Literal["image", "video", "profile", "text", "cluster"] = "text"
    if payload.video_url or payload.video_urls:
        match_type = "video"
    elif payload.image_url or payload.image_urls:
        match_type = "image"
    elif payload.profile_username or payload.profile_display_name or payload.profile_bio:
        match_type = "profile"

    # Build raw text for Sphinx from available content
    raw_text = ""
    if payload.post_text:
        raw_text += f"Post: {payload.post_text}\n"
    if payload.dm_text:
        raw_text += f"DM: {payload.dm_text}\n"
    if payload.profile_text:
        raw_text += f"Profile: {payload.profile_text}\n"
    if payload.profile_bio:
        raw_text += f"Bio: {payload.profile_bio}\n"

    if not raw_text.strip():
        raw_text = "(no text content)"

    # Prepare Sphinx input payload (matching your spec)
    sphinx_input = {
        "raw_text": raw_text,
        "image_tags": [],
        "actian_neighbors": [],
        "scores": {
            "similarity": 0.5,
            "novelty": 0.5,
            "toxicity": 0.0,
        },
        "metadata": {
            "url": str(payload.image_url or payload.video_url or ""),
            "content_type": payload.content_type or "unknown",
        },
    }

    # Try Sphinx reasoning via HTTP
    if sphinx_enabled:
        try:
            logger.info(f"Calling Sphinx API for {mode}...")
            # Sphinx API endpoint (adjust URL if needed)
            sphinx_url = "https://api.sphinx.ai/v1/reason"
            
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    sphinx_url,
                    json={
                        "api_key": sphinx_api_key,
                        "task": mode,
                        "inputs": sphinx_input,
                    }
                )
                response.raise_for_status()
                sphinx_response = response.json()
            
            logger.debug(f"Sphinx response: {sphinx_response}")

            # Parse Sphinx response
            risk_level = sphinx_response.get("risk_level", "medium")
            trust_score = {"low": 80, "medium": 50, "high": 20}.get(risk_level, 50)
            confidence = sphinx_response.get("confidence", 0.85)
            explanation = sphinx_response.get("explanation", "")
            recommendation = sphinx_response.get("recommendation", "Review content carefully")
            signals = sphinx_response.get("signals", {})

            base_response = TrustSignalResponse(
                risk_level=risk_level,
                trust_score=trust_score,
                reasoning_summary=explanation,
                explanation=explanation,
                confidence=confidence,
                recommendation=recommendation,
                flags=SignalFlags(
                    similarity=signals.get("similarity_flags", []),
                    linguistic=signals.get("linguistic_flags", []),
                    visual=signals.get("visual_flags", []),
                    metadata=signals.get("metadata_flags", []),
                ),
                risk_indicators=signals.get("linguistic_flags", []),
                intent_analysis=signals.get("intent_flags", []),
                manipulation_cues=signals.get("manipulation_flags", []),
                contradiction_flags=signals.get("contradiction_flags", []),
                pattern_matches=[
                    PatternMatch(match_type=match_type, similarity=0.75, source="sphinx_analysis"),
                ],
                deep_check_available=True,
                input_received=payload.model_dump(mode="json"),
            )

            # If deep check, add cluster analysis
            if mode == "deep_check":
                neighbors = sphinx_response.get("neighbors", [])
                cluster_info = [
                    ClusterInfo(
                        id=n.get("id", f"cluster_{i}"),
                        similarity=float(n.get("similarity", 0.0)),
                        reason=n.get("reason", ""),
                        snippet=n.get("snippet"),
                    )
                    for i, n in enumerate(neighbors[:5])
                ]
                step_by_step = sphinx_response.get("step_by_step", [])
                verdict = sphinx_response.get("verdict", "Review required")

                return DeepCheckResponse(
                    **base_response.model_dump(),
                    neighbors=cluster_info,
                    step_by_step_analysis=step_by_step,
                    verdict=verdict,
                )
            return base_response

        except Exception as e:
            logger.error(f"Sphinx API error: {e}")
            # Fall through to placeholder

    # Placeholder response if Sphinx unavailable
    logger.warning("Sphinx unavailable, returning placeholder response")
    placeholder_response = TrustSignalResponse(
        risk_level="medium",
        trust_score=50,
        reasoning_summary="Sphinx not configured. Replace with real analysis.",
        explanation="Backend running but Sphinx analysis not available.",
        confidence=0.0,
        recommendation="Configure Sphinx API key to enable analysis",
        flags=SignalFlags(),
        risk_indicators=[],
        intent_analysis=[],
        manipulation_cues=[],
        contradiction_flags=[],
        pattern_matches=[
            PatternMatch(match_type=match_type, similarity=0.0, source="placeholder"),
        ],
        deep_check_available=False,
        input_received=payload.model_dump(mode="json"),
    )

    if mode == "deep_check":
        return DeepCheckResponse(**placeholder_response.model_dump())
    return placeholder_response


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
def analyze(payload: AnalyzePayload) -> TrustSignalResponse:
    logger.debug(f"Analyze request received: content_id={payload.content_id}")
    return build_sphinx_trust_signal(payload, mode="trust_signal")


@app.post("/trust-signal")
def trust_signal(payload: AnalyzePayload) -> TrustSignalResponse:
    logger.debug(f"Trust signal request: content_id={payload.content_id}")
    return build_sphinx_trust_signal(payload, mode="trust_signal")


@app.post("/deep-check")
def deep_check(payload: AnalyzePayload) -> DeepCheckResponse:
    logger.debug(f"Deep check request: content_id={payload.content_id}")
    response = build_sphinx_trust_signal(payload, mode="deep_check")
    if isinstance(response, DeepCheckResponse):
        return response
    # Fallback: convert to DeepCheckResponse if not already
    return DeepCheckResponse(**response.model_dump())
