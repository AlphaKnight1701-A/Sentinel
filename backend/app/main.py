import os
import sys
import json
import httpx
import subprocess
import glob
import time
import logging
import asyncio
from typing import Literal, Optional, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, HttpUrl

from .config import settings
from . import ml
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from .jupyter_manager import JupyterManager

jupyter_manager = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global jupyter_manager
    # Root dir should be the backend folder
    root_dir = str(Path(__file__).parent.parent.resolve())
    jupyter_manager = JupyterManager(root_dir=root_dir)
    await jupyter_manager.start()
    yield
    # Shutdown
    if jupyter_manager:
        jupyter_manager.stop()

app = FastAPI(
    title="Sentinel Backend",
    version="0.1.0",
    description="AI Content & Fake Account Detection Backend",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://twitter.com",
        "https://x.com",
        "https://pro.twitter.com",
        "https://tweetdeck.twitter.com",
        "http://localhost:3000",
        "http://127.0.0.1:3000"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
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

# Suppress the benign grpcio + uvloop BlockingIOError noise.
# grpcio's PollerCompletionQueue registers cleanup callbacks on uvloop which emit
# EAGAIN (errno 35) when the underlying gRPC FD is torn down after each `with CortexClient`
# block. Operations succeed regardless — this is a known grpcio/uvloop incompatibility.
class _GrpcUvloopFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        return not (
            record.name == "asyncio"
            and record.levelno == logging.ERROR
            and "PollerCompletionQueue" in record.getMessage()
        )

logging.getLogger("asyncio").addFilter(_GrpcUvloopFilter())

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
            # Create collection if it doesn't exist
            actian_client.create_collection(
                name="sentinel_cache_v10",
                dimension=512,  # clip-ViT-B-32 output shape
                distance_metric=DistanceMetric.COSINE
            )
            logger.info("Created Actian collection 'sentinel_cache_v10'")
        except Exception as e:
            logger.debug(f"Actian collection 'sentinel_cache_v10' already exists or creation failed: {e}")

    except Exception as e:
        logger.error(f"❌ Failed to connect to Actian VectorAI: {e}")
        actian_client = None
else:
    logger.warning("⚠ Actian VectorAI disabled (missing URL or cortex package)")

# ---------------------------------------------------------
# Sphinx API Helpers
# ---------------------------------------------------------
sphinx_lock = None

# ---------------------------------------------------------
# Helper: Build a professional fallback summary from scores
# (used when Sphinx times out so the endpoint never hangs)
# ---------------------------------------------------------
def build_fallback_summary(scores: Dict[str, Any]) -> Dict[str, Any]:
    diff = scores.get("diffusion_score", 0.0)
    gan = scores.get("gan_score", 0.0)
    exif = scores.get("exif_data", {})
    has_exif = bool(exif and "error" not in exif)
    dominant = max(diff, gan)

    if dominant >= 0.7:
        risk_level = "high"
        trust_score = max(0, int((1.0 - dominant) * 20))
        summary = (
            f"Forensic detectors flagged this image with very high AI-generation probability "
            f"(diffusion: {diff:.0%}{'  GAN: ' + f'{gan:.0%}' if gan > 0 else ''}). "
            f"{'No EXIF metadata was found.' if not has_exif else 'EXIF present but detector scores overwhelm.'} "
            "This content is highly likely to be artificially generated."
        )
    elif dominant >= 0.35:
        risk_level = "medium"
        trust_score = max(20, int((1.0 - dominant) * 60))
        summary = (
            f"AI-generation detectors returned moderate scores (diffusion: {diff:.0%}). "
            f"{'No authenticating EXIF metadata was found.' if not has_exif else 'EXIF metadata was present.'} "
            "Treat with caution — manual review is recommended."
        )
    else:
        risk_level = "low"
        trust_score = min(100, int(90 + (1.0 - dominant) * 10))
        summary = (
            f"Both AI-detection models returned low scores (diffusion: {diff:.0%}{'  GAN: ' + f'{gan:.0%}' if gan > 0 else ''}). "
            f"{'No EXIF was found, but detector signals strongly suggest authenticity.' if not has_exif else 'EXIF metadata supports authenticity.'} "
            "This image is highly likely to be real."
        )
    return {"risk_level": risk_level, "trust_score": trust_score, "reasoning_summary": summary}


# ---------------------------------------------------------
# Helper: Run Sphinx Reasoning (synthesis-only)
# Accepts pre-computed scores so Sphinx only writes the summary
# ---------------------------------------------------------
def run_sphinx_reasoning(scores: Dict[str, Any], context_text: str = "") -> Dict[str, Any]:
    """Calls Sphinx CLI to synthesise a reasoning summary from pre-computed forensic scores.
    
    Sphinx no longer downloads the image or runs models — all inference has already
    been done natively by FastAPI. This cuts the Sphinx call from ~40s to ~5-8s.
    """
    if not settings.sphinx_api_key:
        raise HTTPException(
            status_code=500,
            detail="Sphinx is not enabled. Set SPHINX_API_KEY."
        )
    
    global jupyter_manager
    if not jupyter_manager or not jupyter_manager.url:
        logger.error("Jupyter manager is not running.")
        raise HTTPException(status_code=500, detail="Sphinx Jupyter Server offline.")

    temp_notebook = f"/tmp/sphinx_synthesis_{uuid.uuid4().hex[:8]}.ipynb"
    
    diff = scores.get("diffusion_score", 0.0)
    gan = scores.get("gan_score", 0.0)
    num_faces = scores.get("num_faces", 0)
    exif_data = scores.get("exif_data", {})
    has_exif = bool(exif_data and "error" not in exif_data)
    
    # Concise prompt — Sphinx just synthesises text, no tool calls needed
    prompt_text = (
        f"You are Sentinel, an elite AI Trust & Safety analyst. "
        f"Forensic analysis of a Twitter post and its image is complete.\n"
        f"{'Context from the post: ' + context_text + chr(10) if context_text else ''}"
        f"Here are the pre-computed findings for the media attached to this post:\n"
        f"Diffusion model AI-generation probability: {diff:.1%}. "
        f"GAN deepfake probability: {gan:.1%} ({'faces detected' if num_faces > 0 else 'no faces detected'}). "
        f"EXIF metadata: {'present' if has_exif else 'absent (suspicious)'}. "
        f"Interpretation guide: >0.7 = very high risk, 0.35-0.7 = medium risk, <0.35 = likely real. "
        f"Based ONLY on these scores and the context provided, output exactly this JSON schema — no code execution needed: "
        f"1. 'risk_level': one of 'low', 'medium', or 'high'. "
        f"2. 'trust_score': integer 0-100 (100=definitely real, 0=definitely AI). "
        f"3. 'reasoning_summary': 1-3 professional sentences summarising the findings for an end user, incorporating the post text if relevant. Do not mention Python or variable names."
    )
    
    schema_definition = json.dumps({
        "risk_level": "string",
        "trust_score": "integer",
        "reasoning_summary": "string"
    })

    try:
        result = subprocess.run(
            [
                "sphinx-cli", "chat",
                "--prompt", prompt_text,
                "--output-schema", schema_definition,
                "--notebook-filepath", temp_notebook,
                "--jupyter-server-url", jupyter_manager.url,
                "--jupyter-server-token", jupyter_manager.token
            ],
            capture_output=True, text=True,
            timeout=25  # Hard cap: fall back to programmatic summary if Sphinx stalls
        )
        
        try:
            if os.path.exists(temp_notebook):
                os.remove(temp_notebook)
        except Exception:
            pass

        if result.returncode != 0:
            logger.error(f"Sphinx CLI failed: {result.stderr}")
            raise ValueError("Sphinx CLI non-zero exit")
            
        parsed = json.loads(result.stdout)
        if "_meta" in parsed:
            del parsed["_meta"]
        return parsed

    except subprocess.TimeoutExpired:
        logger.warning("Sphinx timed out — using programmatic fallback summary")
        return build_fallback_summary(scores)
    except Exception as e:
        logger.error(f"Sphinx reasoning failed: {e}")
        return build_fallback_summary(scores)


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
    # Raw ML inference scores
    diffusion_score: float | None = None
    gan_score: float | None = None
    faces_detected: int | None = None


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
    # Update to match the new signature of run_sphinx_reasoning
    sphinx_response = run_sphinx_reasoning(task=mode, url=str(payload.image_url or payload.video_url or ""))

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
    url = str(payload.image_url) if payload.image_url else None
    if not url and payload.media_urls and len(payload.media_urls) > 0:
        url = payload.media_urls[0]

    logger.debug(f"Live feed request received: url={url}")
    
    context_text = ""
    if payload.profile_display_name or payload.profile_username:
        context_text += f"User: {payload.profile_display_name or ''} ({payload.profile_username or ''})\n"
    if payload.post_text:
        context_text += f"Post Text: {payload.post_text}\n"

    if not url:
        return TrustSignalResponse(
            risk_level="low",
            trust_score=100,
            reasoning_summary="No media provided to analyze in this post.",
            explanation="Live feed processing requires media URLs.",
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
            post_text=payload.post_text,
            display_name=payload.profile_display_name,
            handle=payload.profile_username
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
    COLLECTION_NAME = "sentinel_cache_v10"
    global actian_client
    
    cache_hit = False
    is_fake = False
    fake_prob = 0.0
    best_match_score = 0.0
    cached_risk_level = None
    cached_trust_score = None
    cached_reasoning = None
    cached_confidence = None

    if actian_client:
        try:
            # Use asyncio.to_thread to prevent gRPC from clashing with FastAPI's uvloop
            def _do_search():
                return actian_client.search(
                    collection_name=COLLECTION_NAME,
                    query=vector,
                    top_k=1,
                    with_payload=True
                )
            
            results = await asyncio.to_thread(_do_search)
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
                        cached_confidence = best_match.payload.get("confidence")
        except Exception as e:
            logger.error(f"Actian search error: {e}")

    if not cache_hit:
        logger.info("Actian Cache Miss. Running parallel ML inference...")
    
    # --- PARALLEL ML INFERENCE (only on cache miss) ---
    # Runs EXIF + diffusion + face/GAN detection concurrently in FastAPI's thread pool.
    # This is significantly faster than doing it inside a Sphinx Jupyter kernel.
    scores = {}
    sphinx_response = {}
    
    if not cache_hit:
        from app import sentinel_tools
        try:
            scores = await sentinel_tools.analyze_image_parallel(image_bytes)
            logger.info(f"Parallel inference complete: diffusion={scores.get('diffusion_score'):.3f} gan={scores.get('gan_score'):.3f} faces={scores.get('num_faces')}")
        except Exception as e:
            logger.error(f"Parallel inference failed: {e}")
            scores = {"diffusion_score": 0.5, "gan_score": 0.0, "num_faces": 0, "exif_data": {}}

        # Pass pre-computed scores to Sphinx — it only synthesises the text summary now
        if settings.sphinx_api_key:
            global sphinx_lock
            if sphinx_lock is None:
                sphinx_lock = asyncio.Lock()
            
            try:
                async with sphinx_lock:
                    sphinx_response = await asyncio.to_thread(
                        run_sphinx_reasoning,
                        scores,
                        context_text
                    )
            except Exception as e:
                logger.error(f"Sphinx synthesis failed: {e}")
                sphinx_response = build_fallback_summary(scores)
        else:
            sphinx_response = build_fallback_summary(scores)

    # --- FALLBACK / RESPONSE FORMATION ---
    is_fake = sphinx_response.get("risk_level", "low") == "high"
    fake_prob = 1.0 - (sphinx_response.get("trust_score", 50) / 100.0)
    
    risk_level = sphinx_response.get("risk_level", "high" if is_fake else "low")
    if cache_hit and cached_risk_level:
        risk_level = cached_risk_level
    
    trust_score = sphinx_response.get("trust_score", 50)
    if cache_hit and cached_trust_score is not None:
        trust_score = cached_trust_score
    
    # Default Reasoning Summary & Output Values
    if cache_hit:
        default_summary = cached_reasoning or f"Identified as known image via Actian Vector Cache Hit (Score: {best_match_score:.2f})."
        default_explanation = "This media matched an existing record in our threat intelligence cache. Bypassing deep model inference."
        default_confidence = cached_confidence if cached_confidence is not None else best_match_score
        default_recommendation = "Flag content" if is_fake else "Looks authentic"
        default_flags = SignalFlags(visual=["Known Deepfake"] if is_fake else [])
        default_indicators = ["Cache Hit - Known Deepfake"] if is_fake else []
        default_pattern_source = "actian_cache"
        default_pattern_score = best_match_score
    else:
        default_summary = sphinx_response.get("reasoning_summary", "Agentic orchestration analysis completed.")
        default_explanation = "Image analyzed dynamically orchestrated by Sphinx running dual parallel AI-image detection models and EXIF metadata extraction."
        default_confidence = fake_prob if is_fake else 1.0 - fake_prob
        default_recommendation = "Flag content" if is_fake else "Looks authentic"
        default_flags = SignalFlags(visual=["High AI Generation Probability"] if is_fake else [])
        default_indicators = ["High AI Generation Probability"] if is_fake else []
        default_pattern_source = "sphinx_agentic_orchestration"
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
            def _do_upsert():
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
                        "reasoning_summary": reasoning_summary,
                        "confidence": confidence
                    }
                )
            
            await asyncio.to_thread(_do_upsert)
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
        post_text=payload.post_text,
        display_name=payload.profile_display_name,
        handle=payload.profile_username,
        diffusion_score=scores.get("diffusion_score") if scores else None,
        gan_score=scores.get("gan_score") if scores else None,
        faces_detected=scores.get("num_faces") if scores else None,
    )