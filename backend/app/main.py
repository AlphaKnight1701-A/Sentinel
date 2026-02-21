import os
import json
import subprocess
import glob
import time
import logging
from typing import Literal, Optional, Dict, Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, HttpUrl

from .config import settings

# ---------------------------------------------------------
# Try importing Actian VectorAI DB Beta
# ---------------------------------------------------------
try:
    from cortex import CortexClient
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
        actian_client = CortexClient(
            address=settings.actian_vectorai_url,
            api_key=settings.actian_vectorai_api_key
        )
        version, _ = actian_client.health_check()
        logger.info(f"✓ Actian VectorAI connected: {version}")
    except Exception as e:
        logger.error(f"❌ Failed to connect to Actian VectorAI: {e}")
        actian_client = None
else:
    logger.warning("⚠ Actian VectorAI disabled (missing URL or cortex package)")

# ---------------------------------------------------------
# Sphinx CLI Helpers
# ---------------------------------------------------------
def cleanup_notebooks(directory="."):
    """Deletes all auto-generated Sphinx notebooks in the directory to keep it clean."""
    notebooks = glob.glob(os.path.join(directory, "*.ipynb"))
    for notebook in notebooks:
        try:
            os.remove(notebook)
        except OSError:
            pass

def parse_notebook_output(notebook_path):
    try:
        with open(notebook_path, 'r', encoding='utf-8') as f:
            notebook = json.load(f)
        cells = notebook.get('cells', [])
        if not cells: return {"error": "No cells found"}
        outputs = cells[0].get('outputs', [])
        if not outputs: return {"error": "No outputs found"}
        for output in outputs:
            if output.get('name') == 'stdout':
                text_data = output.get('text', '')
                if isinstance(text_data, list): text_data = "".join(text_data)
                try:
                    return json.loads(text_data)
                except json.JSONDecodeError:
                    return {"error": "Failed to parse JSON", "raw_text": text_data}
        return {"error": "No stdout found"}
    except Exception as e:
        return {"error": f"Error parsing notebook: {e}"}

# ---------------------------------------------------------
# Helper: Run Sphinx Reasoning
# ---------------------------------------------------------
def run_sphinx_reasoning(task: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
    if not settings.sphinx_api_key:
        raise HTTPException(
            status_code=500,
            detail="Sphinx is not enabled. Set SPHINX_API_KEY."
        )

    cleanup_notebooks()
    
    # Construct a prompt that forces JSON output matching the expected format
    prompt_text = f"Task: {task}. Inputs: {json.dumps(inputs)}. Output a JSON object. Do not include any other markdown formatting outside of the JSON block. If the task requires it, include risk_level (low, medium, high), trust_score (0-100), and reasoning_summary."
    
    try:
        result = subprocess.run(
            ["sphinx-cli", "chat", "--prompt", prompt_text],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            logger.error(f"Sphinx CLI failed: {result.stderr}")
            raise HTTPException(status_code=500, detail="Sphinx CLI error")
            
        time.sleep(1) # wait for file sync
        notebooks = glob.glob("*.ipynb")
        if not notebooks:
            raise HTTPException(status_code=500, detail="Sphinx notebook not generated")
            
        target = notebooks[0]
        parsed = parse_notebook_output(target)
        cleanup_notebooks()
        
        if "error" in parsed:
            raise HTTPException(status_code=500, detail=parsed["error"])
            
        return parsed
    except Exception as e:
        logger.error(f"Sphinx reasoning failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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