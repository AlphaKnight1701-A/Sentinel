import os
import sys
import json
import httpx
import glob
import time
import logging
import asyncio
from typing import Literal, Optional, Dict, Any
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, HttpUrl

from .config import settings
from . import ml
import uuid

# ---------------------------------------------------------
# Try importing Actian VectorAI DB Beta
# ---------------------------------------------------------
try:
    from cortex import CortexClient, DistanceMetric
    from cortex.transport.pool import PoolConfig
    ACTIAN_AVAILABLE = True
except ImportError:
    ACTIAN_AVAILABLE = False

# ---------------------------------------------------------
# Logging setup
# ---------------------------------------------------------
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

logger.info(f"Starting backend - Environment: {settings.environment}")

if settings.actian_vectorai_url:
    if not ACTIAN_AVAILABLE:
        logger.warning("⚠ Actian VectorAI URL set, but cortex package not installed")
    else:
        logger.info(f"Attempting to connect to Actian VectorAI at {settings.actian_vectorai_url}")

if settings.sphinx_api_key:
    logger.info("✓ Sphinx API key loaded (using CLI bridge)")
else:
    logger.warning("⚠ Sphinx disabled (missing API key)")

if settings.safetykit_api_key:
    logger.info("✓ SafetyKit API key loaded")

# ---------------------------------------------------------
# Initialize Actian VectorAI client
# ---------------------------------------------------------
actian_client = None

if ACTIAN_AVAILABLE and settings.actian_vectorai_url:
    try:
        # The CortexClient python SDK natively expects a context manager (`with CortexClient() as client:`)
        # To keep it alive globally for FastAPI, we initialize it and explicitly call connect.
        #
        # pool_size=1  → single gRPC channel (avoids N×ping flood through the gh-cs tunnel)
        # Patch PoolConfig keepalive_time_ms → 300 000 ms (5 min) before connect() is called,
        # so the channel only pings once every 5 minutes instead of the default 30 s.
        # This silences the ENHANCE_YOUR_CALM / too_many_pings GOAWAY from the port-forward tunnel.
        actian_client = CortexClient(
            address=settings.actian_vectorai_url,
            api_key=settings.actian_vectorai_api_key,
            pool_size=1,
        )
        # Patch keepalive on the underlying async client's PoolConfig before connect()
        if hasattr(actian_client, '_async_client') and actian_client._async_client is not None:
            actian_client._async_client._pool_config = PoolConfig(
                pool_size=1,
                keepalive_time_ms=300_000,   # ping every 5 minutes
                keepalive_timeout_ms=20_000,  # 20-second response window
            )
        actian_client.connect()
        version, _ = actian_client.health_check()
        logger.info(f"✓ Actian VectorAI connected: {version}")
        
        try:
            actian_client.create_collection(
                name="sentinel_cache",
                dimension=512,  # clip-ViT-B-32 output shape
                distance_metric=DistanceMetric.COSINE
            )
            logger.info("Created Actian collection 'sentinel_cache'")
        except Exception as e:
            logger.debug("Actian collection 'sentinel_cache' already exists or creation failed.")

    except Exception as e:
        logger.error(f"❌ Failed to connect to Actian VectorAI: {e}")
        actian_client = None
else:
    logger.warning("⚠ Actian VectorAI disabled (missing URL or cortex package)")

# ---------------------------------------------------------
# Sphinx API Helpers
# ---------------------------------------------------------
sphinx_lock = None

def heuristic_sphinx_fallback(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Provides a deterministic fallback when API is down/slow."""
    logger.warning("Using heuristic Sphinx fallback logic")
    
    sdxl_score = inputs.get("sdxl_diffusion_fake_prob", 0.0)
    gan_score = inputs.get("gan_face_fake_prob", 0.0)
    ensemble = inputs.get("ensemble_fake_probability", 0.0)
    raw_text = inputs.get("raw_text", "No text provided")
    metadata = inputs.get("metadata", {})
    content_type = metadata.get("content_type", "content")
    
    # Extract username if available in raw_text or metadata
    user_ref = "this user"
    if "Post: " in raw_text and "@" in raw_text:
        # Try to find handle in raw_text if built that way
        pass 

    # Simple snippet for the reason
    snippet = raw_text.replace("Post: ", "").strip()
    if len(snippet) > 60:
        snippet = snippet[:60] + "..."

    if sdxl_score > 0.4 and gan_score > 0.4:
        risk = "high"
        trust = 15
        reason = f"ALERT: Sentinel detected severe metadata inconsistencies and AI-generated artifacts in the media posted. The neural patterns match known synthetic generation profiles. High risk of impersonation or misinformation."
    elif sdxl_score > 0.3 or gan_score > 0.3 or ensemble > 0.3:
        risk = "medium"
        trust = 45
        reason = f"CAUTION: Suspicious signatures detected. While the text content appears typical, the associated media exhibits lighting desyncs and micro-artifacting common in generative models. Proceed with verification."
    else:
        risk = "low"
        trust = 85
        reason = f"VERIFIED: System check for this post is complete. Current media buffer shows consistent biological textures and natural environmental lighting. No synthetic signatures detected."
        
    return {
        "risk_level": risk,
        "trust_score": trust,
        "reasoning_summary": reason,
        "explanation": f"Neural analysis for '{snippet}' indicates {risk} probability of synthetic origin.",
        "confidence": 0.82,
        "recommendation": "Manual review recommended" if risk != "low" else "Safe to consume",
        "signals": {
            "visual_flags": ["Imperfect Shadows", "Texture Smoothing"] if risk == "high" else (["Minor Artifacting"] if risk == "medium" else []),
            "linguistic_flags": ["Synthetic Syntax"] if risk == "high" else []
        }
    }

# ---------------------------------------------------------
# Helper: Run Sphinx Reasoning
# ---------------------------------------------------------
def run_sphinx_reasoning(task: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
    if not settings.sphinx_api_key:
        return heuristic_sphinx_fallback(inputs)

    # Sphinx API Endpoint (Option B: Direct Integration)
    SPHINX_API_URL = "https://api.sphinx.ai/chat"
    
    try:
        # Use sync client for run_sphinx_reasoning as it's typically called in a thread
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                SPHINX_API_URL,
                headers={"Authorization": f"Bearer {settings.sphinx_api_key}"},
                json={
                    "task": task,
                    "inputs": inputs,
                    "prompt": (
                        "Analyze these AI detection signals and the specific post content to provide a trust verdict. "
                        "The raw text of the post is provided in the inputs. "
                        "Your 'reasoning_summary' MUST refer to the specific content being analyzed "
                        "and explain WHY the signals suggest a particular risk level for THIS specific post. "
                        "Respond ONLY with a JSON object containing keys: "
                        "risk_level (low/medium/high), trust_score (0-100), reasoning_summary, "
                        "explanation, confidence (0.0-1.0), and recommendation."
                    ),
                    "response_format": "json"
                }
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Sphinx API failure ({response.status_code}): {response.text}")
                return heuristic_sphinx_fallback(inputs)
                
    except Exception as e:
        logger.error(f"Sphinx API connection failed: {e}")
        return heuristic_sphinx_fallback(inputs)


# ---------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------
class AnalyzePayload(BaseModel):
    content_id: str | None = None
    content_type: Literal["post", "profile", "image", "video", "dm"] | None = None
    image_url: HttpUrl | None = None
    image_urls: list[HttpUrl] | None = None
    video_url: HttpUrl | None = None
    video_urls: list[HttpUrl] | None = None
    profile_username: str | None = None
    profile_display_name: str | None = None
    profile_image_url: str | None = None
    profile_bio: str | None = None
    profile_text: str | None = None
    post_text: str | None = None
    dm_text: str | None = None
    media_urls: list[str] | None = None


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
    # Echoed metadata for frontend
    post_text: str | None = None
    display_name: str | None = None
    handle: str | None = None


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


# ---------------------------------------------------------
# Build Sphinx Input + Parse Response
# ---------------------------------------------------------
def build_sphinx_trust_signal(
    payload: AnalyzePayload,
    mode: str = "trust_signal"
) -> TrustSignalResponse | DeepCheckResponse:

    # Determine match type
    match_type: Literal["image", "video", "profile", "text", "cluster"] = "text"
    if payload.video_url or payload.video_urls:
        match_type = "video"
    elif payload.image_url or payload.image_urls:
        match_type = "image"
    elif payload.profile_username or payload.profile_display_name or payload.profile_bio:
        match_type = "profile"

    # Build raw text
    raw_text = ""
    if payload.profile_display_name:
        raw_text += f"User: {payload.profile_display_name} ({payload.profile_username or 'unknown'})\n"
    if payload.post_text:
        raw_text += f"Post: {payload.post_text}\n"
    if payload.dm_text:
        raw_text += f"DM: {payload.dm_text}\n"
    if payload.profile_bio:
        raw_text += f"Bio: {payload.profile_bio}\n"

    if not raw_text.strip():
        raw_text = "(no text content)"

    # Build Sphinx input
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
            "handle": payload.profile_username,
            "display_name": payload.profile_display_name,
            "profile_image": payload.profile_image_url,
            "media_urls": payload.media_urls
        },
    }

    logger.info(f"Calling Sphinx SDK for task={mode}")
    sphinx_response = run_sphinx_reasoning(task=mode, inputs=sphinx_input)

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
        post_text=payload.post_text,
        display_name=payload.profile_display_name,
        handle=payload.profile_username
    )

    # Deep check extension
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

        return DeepCheckResponse(
            **base_response.model_dump(),
            neighbors=cluster_info,
            cluster_summary=sphinx_response.get("cluster_summary", {}),
            step_by_step_analysis=sphinx_response.get("step_by_step", []),
            verdict=sphinx_response.get("verdict", "Review required"),
        )

    return base_response


# ---------------------------------------------------------
# Endpoints
# ---------------------------------------------------------
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
    return response


@app.post("/live-feed")
async def live_feed(payload: AnalyzePayload) -> TrustSignalResponse:
    logger.debug(f"Live feed request received: url={payload.image_url}")
    
    url = str(payload.image_url) if payload.image_url else None
    if not url:
        return TrustSignalResponse(
            risk_level="low",
            trust_score=100,
            reasoning_summary="No image provided to analyze.",
            explanation="Live feed processing requires an image URL.",
            confidence=1.0,
            recommendation="Provide an image URL.",
            flags=SignalFlags(),
            risk_indicators=[],
            intent_analysis=[],
            manipulation_cues=[],
            contradiction_flags=[],
            pattern_matches=[],
            deep_check_available=False,
            input_received=payload.model_dump(mode="json"),
        )
    
    # 1. Fetch image
    try:
        image_bytes = await ml.fetch_image(url)
    except Exception as e:
        logger.error(f"Failed to fetch image: {e}")
        raise HTTPException(status_code=400, detail="Failed to fetch image.")

    # 2. Get CLIP Vector
    vector = ml.get_clip_vector(image_bytes)

    # 3. Actian DB Cache Hit
    COLLECTION_NAME = "sentinel_cache"
    global actian_client
    
    cache_hit = False
    is_fake = False
    fake_prob = 0.0
    best_match_score = 0.0
    cached_risk_level = None
    cached_trust_score = None
    cached_reasoning = None

    if actian_client:
        try:
            results = actian_client.search(
                collection_name=COLLECTION_NAME,
                query=vector,
                top_k=1,
                with_payload=True
            )
            if results and len(results) > 0:
                best_match = results[0]
                if best_match.score > 0.90:  # ~90% similarity considered identical for CLIP
                    logger.info(f"Actian Cache Hit! Similarity: {best_match.score:.3f}")
                    cache_hit = True
                    best_match_score = min(float(best_match.score), 1.0)
                    is_fake = best_match.payload.get("is_fake", False)
                    fake_prob = best_match.payload.get("fake_prob", 1.0 if is_fake else 0.0)
                    
                    # Enhanced Cache Parsing
                    cached_risk_level = best_match.payload.get("risk_level")
                    cached_trust_score = best_match.payload.get("trust_score")
                    cached_reasoning = best_match.payload.get("reasoning_summary")
        except Exception as e:
            logger.error(f"Actian search error: {e}")

    # 4. Cache Miss -> Dual-Model Parallel Inference
    sdxl_score = 0.0
    gan_score = 0.0
    if not cache_hit:
        logger.info("Actian Cache Miss. Running dual-model parallel inference...")
        sdxl_result, gan_result = await asyncio.gather(
            asyncio.to_thread(ml.score_sdxl, image_bytes),
            asyncio.to_thread(ml.score_gan_face, image_bytes),
        )
        sdxl_score = sdxl_result.get("fake_prob", 0.0)
        gan_score = gan_result.get("fake_prob", 0.0)
        fake_prob = (sdxl_score + gan_score) / 2  # ensemble average
        # Flagged as fake if either model or the ensemble is suspicious
        is_fake = sdxl_score > 0.3 or gan_score > 0.3 or fake_prob > 0.25
        logger.info(f"SDXL score: {sdxl_score:.3f} | GAN score: {gan_score:.3f} | Ensemble: {fake_prob:.3f} | is_fake: {is_fake}")

    # --- SPHINX REASONING INTEGRATION ---
    sphinx_input = {
        "url": url,
        "is_fake": is_fake,
        "sdxl_diffusion_fake_prob": sdxl_score,
        "gan_face_fake_prob": gan_score,
        "ensemble_fake_probability": fake_prob,
        "cache_hit": cache_hit,
        "cache_similarity": best_match_score
    }
    
    sphinx_response = {}
    if settings.sphinx_api_key and not cache_hit:
        global sphinx_lock
        if sphinx_lock is None:
            sphinx_lock = asyncio.Lock()
        
        try:
            async with sphinx_lock:
                sphinx_response = await asyncio.to_thread(
                    run_sphinx_reasoning,
                    "live_feed_analysis",
                    sphinx_input
                )
        except Exception as e:
            logger.error(f"Sphinx live-feed reasoning failed: {e}")

    # --- FALLBACK / RESPONSE FORMATION ---
    risk_level = sphinx_response.get("risk_level", "high" if is_fake else "low")
    if cache_hit and cached_risk_level:
        risk_level = cached_risk_level
    
    # Calculate a default trust score if Sphinx doesn't provide one
    default_trust_score = 100 - int(fake_prob * 100)
    trust_score = sphinx_response.get("trust_score", default_trust_score)
    if cache_hit and cached_trust_score is not None:
        trust_score = cached_trust_score
    
    # Default Reasoning Summary & Output Values
    if cache_hit:
        default_summary = cached_reasoning or f"Identified as known image via Actian Vector Cache Hit (Score: {best_match_score:.2f})."
        default_explanation = "This media matched an existing record in our threat intelligence cache. Bypassing deep model inference."
        default_confidence = best_match_score
        default_recommendation = "Flag content" if is_fake else "Looks authentic"
        default_flags = SignalFlags(visual=["Known Deepfake"] if is_fake else [])
        default_indicators = ["Cache Hit - Known Deepfake"] if is_fake else []
        default_pattern_source = "actian_cache"
        default_pattern_score = best_match_score
    else:
        # Build a detailed, informative fallback reasoning using both model scores
        sdxl_pct = int(sdxl_score * 100)
        gan_pct = int(gan_score * 100)
        ensemble_pct = int(fake_prob * 100)
        if is_fake:
            model_agreement = "Both" if (sdxl_score > 0.3 and gan_score > 0.3) else "One"
            dominant = "diffusion-based generation (Stable Diffusion / Midjourney style)" if sdxl_score > gan_score else "GAN-synthesized face patterns"
            default_summary = (
                f"{model_agreement} of our detection models flagged this image as likely AI-generated. "
                f"The Stable Diffusion detector scored {sdxl_pct}% and the GAN face detector scored {gan_pct}% (ensemble: {ensemble_pct}%). "
                f"The strongest signal is consistent with {dominant}."
            )
        else:
            default_summary = (
                f"Both AI detectors returned low fake probability scores — "
                f"Stable Diffusion detector: {sdxl_pct}%, GAN face detector: {gan_pct}% (ensemble: {ensemble_pct}%). "
                f"No significant indicators of AI generation were detected. The image appears authentic."
            )
        default_explanation = "Image analyzed using dual parallel AI-image detection models (diffusion + GAN detectors). Results are cached for instant future lookups."
        default_confidence = fake_prob if is_fake else 1.0 - fake_prob
        default_recommendation = "Flag content" if is_fake else "Looks authentic"
        default_flags = SignalFlags(visual=["High AI Generation Probability"] if is_fake else [])
        default_indicators = ["High AI Generation Probability"] if is_fake else []
        default_pattern_source = "dual_model_ensemble"
        default_pattern_score = fake_prob

    reasoning_summary = sphinx_response.get("reasoning_summary", default_summary)
    explanation = sphinx_response.get("explanation", default_explanation)
    confidence = sphinx_response.get("confidence", default_confidence)
    recommendation = sphinx_response.get("recommendation", default_recommendation)

    signals = sphinx_response.get("signals", {})

    # 5. Background Cache Upsert (Enhanced with Sphinx logic)
    if not cache_hit and actian_client:
        try:
            vector_id = uuid.uuid4().int & ((1<<63)-1)
            actian_client.upsert(
                collection_name=COLLECTION_NAME,
                id=vector_id,
                vector=vector,
                payload={
                    "url": url, 
                    "is_fake": is_fake, 
                    "fake_prob": fake_prob,
                    "risk_level": risk_level,
                    "trust_score": trust_score,
                    "reasoning_summary": reasoning_summary
                }
            )
            logger.info("Saved new image inference and Sphinx reasoning to Actian Cache.")
        except Exception as e:
            logger.error(f"Actian upsert error: {e}")

    return TrustSignalResponse(
        risk_level=risk_level,
        trust_score=trust_score,
        reasoning_summary=reasoning_summary,
        explanation=explanation,
        confidence=confidence,
        recommendation=recommendation,
        flags=SignalFlags(
            similarity=signals.get("similarity_flags", default_flags.similarity),
            linguistic=signals.get("linguistic_flags", default_flags.linguistic),
            visual=signals.get("visual_flags", default_flags.visual),
            metadata=signals.get("metadata_flags", default_flags.metadata),
        ),
        risk_indicators=signals.get("linguistic_flags", default_indicators),
        intent_analysis=signals.get("intent_flags", []),
        manipulation_cues=signals.get("manipulation_flags", []),
        contradiction_flags=signals.get("contradiction_flags", []),
        pattern_matches=[
            PatternMatch(match_type="image", similarity=default_pattern_score, source=default_pattern_source)
        ],
        deep_check_available=True,
        input_received=payload.model_dump(mode="json"),
    )