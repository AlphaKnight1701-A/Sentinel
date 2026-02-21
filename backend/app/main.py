from fastapi import FastAPI
from pydantic import BaseModel, HttpUrl


app = FastAPI(title="Sentinel Backend", version="0.1.0")


class AnalyzePayload(BaseModel):
    image_url: HttpUrl | None = None
    profile_text: str | None = None
    post_text: str | None = None


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "sentinel-backend"}


@app.post("/analyze")
def analyze(payload: AnalyzePayload) -> dict:
    return {
        "risk_score": 0,
        "trust_signal": "analysis_not_implemented",
        "summary": "Dockerized backend is running. Replace this with CLIP/Actian/Sphinx pipeline.",
        "input_received": payload.model_dump(mode="json"),
    }
