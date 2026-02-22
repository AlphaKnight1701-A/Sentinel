"""
Sentinel endpoint test script.
Run from backend directory:  venv\Scripts\python test_endpoints.py
"""
import sys
import os
import json
import time
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

BASE = "http://localhost:8000"
HEADERS = {"Content-Type": "application/json"}

# ──────────────────────────────────────────────────────
# 1. Quick sphinx-cli smoke test (before hitting the API)
# ──────────────────────────────────────────────────────
def test_sphinx_cli():
    scripts = Path(sys.executable).parent
    cli = scripts / ("sphinx-cli.exe" if sys.platform == "win32" else "sphinx-cli")
    print(f"sphinx-cli path: {cli}")
    print(f"exists: {cli.exists()}")

    if not cli.exists():
        print("❌  sphinx-cli not found in venv — skipping CLI smoke test")
        return

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    r = subprocess.run(
        [str(cli), "chat", "--prompt",
         'Reply ONLY with valid JSON: {"risk_level":"low","trust_score":90,"reasoning_summary":"test"}'],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        env=env,
    )
    print(f"returncode: {r.returncode}")
    print(f"stdout: {r.stdout[:400]!r}")
    print(f"stderr: {r.stderr[:200]!r}")
    print()


# ──────────────────────────────────────────────────────
# 2. HTTP helpers
# ──────────────────────────────────────────────────────
def http_get(path, timeout=10):
    try:
        with urllib.request.urlopen(f"{BASE}{path}", timeout=timeout) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except:
            return e.code, {"detail": raw}


def http_post(path, data, timeout=120):
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{BASE}{path}", data=body, headers=HEADERS, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except:
            return e.code, {"detail": raw}


def show(label, status, resp):
    ok = "✅" if status == 200 else "❌"
    print(f"{ok}  [{status}]  {label}")
    if status == 200:
        for k in ["risk_level", "trust_score", "reasoning_summary", "verdict", "recommendation"]:
            if k in resp:
                val = resp[k]
                if isinstance(val, str):
                    val = val[:120]
                print(f"     {k}: {val}")
    else:
        detail = resp.get("detail", resp)
        if isinstance(detail, str) and len(detail) > 200:
            detail = detail[:200] + "..."
        print(f"     detail: {detail}")
    print()


# ──────────────────────────────────────────────────────
# 3. Run tests
# ──────────────────────────────────────────────────────
print("=" * 60)
print("  API endpoint tests")
print("=" * 60)

# /health
s, r = http_get("/health")
show("/health (GET)", s, r)

# /analyze
t = time.time()
s, r = http_post("/analyze", {"post_text": "Win a free iPhone! Click now to claim your prize!", "content_type": "post"})
show(f"/analyze ({time.time()-t:.1f}s)", s, r)

# /trust-signal
t = time.time()
s, r = http_post("/trust-signal", {"dm_text": "Send me your bank details, I have a deal for you", "content_type": "dm"})
show(f"/trust-signal ({time.time()-t:.1f}s)", s, r)

# /deep-check
t = time.time()
s, r = http_post("/deep-check", {"profile_username": "crypto_guru99", "profile_bio": "100x gains guaranteed. DM for tips.", "content_type": "profile"})
show(f"/deep-check ({time.time()-t:.1f}s)", s, r)

# /live-feed
t = time.time()
s, r = http_post("/live-feed", {
    "image_url": "https://picsum.photos/200/300",
    "content_type": "image"
}, timeout=120)
show(f"/live-feed ({time.time()-t:.1f}s)", s, r)

print("Done.")
