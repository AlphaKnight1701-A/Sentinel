### 🛡️ Sentinel: The Trust Layer for the Internet

A browser extension that gives you a sixth sense for trust.

### ⭐ Overview

Sentinel is a Chrome extension that helps users instantly understand the trustworthiness of anything they see online — posts, profiles, images, comments, and DMs.

Instead of simply detecting “AI-generated content,” Sentinel interprets patterns across the web using:

 - Actian Vector Database → memory, similarity search, pattern clustering
 - Sphinx Reasoning Engine → human-readable explanations, intent detection, risk interpretation
 - Sentinel doesn’t tell you what’s true.It tells you what’s trustworthy — and why.

### ⭐ Why Sentinel Exists

The modern internet is full of:

 - Fake accounts
 - Recycled misinformation
 - Emotionally manipulative posts
 - AI-generated images
 - Scam DMs
 - Coordinated bot networks
 - Most people can’t tell what’s real anymore.
 - Sentinel solves the real problem:
 - “I don’t know what I can trust.”
 - It gives users a new sense — a trust intuition powered by AI.

### ⭐ Core Features

🔹 1. Passive Trust Signals (Automatic)

    As you scroll, Sentinel automatically analyzes each post and injects a small Trust Signal beneath it.

    Each Trust Signal includes:

     - Trust Score
     - Pattern Matches (via Actian)
     - Risk Indicators (manipulation, impersonation, bot-like behavior)
     - Sphinx Reasoning Summary (“why this matters”)

    This happens in real time with zero user effort.

🔹 2. Deep Check (Manual X‑Ray Mode)

    Right‑click any image, profile, or text → Deep Check with Sentinel

    Deep Check reveals:

     - Similarity to known patterns
     - Cluster membership (bot networks, repeated images)
     - Emotional manipulation cues
     - Contradiction detection
     - Intent analysis
     - Safety risks

    This is your X‑ray vision for the internet.

🔹 3. Pattern Memory (Actian Vector DB)

    Sentinel stores embeddings of:

     - Suspicious images
     - Bot-like profiles
     - Repeated claims
     - Scam patterns
     - Manipulative language

    This enables:

     - “You’ve seen this pattern before” alerts
     - Detection of recycled scams
     - Cluster detection
     - Contradiction detection
     - Long-term trust intelligence

🔹 4. Sphinx Reasoning Engine

    Sphinx turns raw signals into clear, human-readable explanations, such as:

     - “This account resembles a bot cluster you encountered earlier.”
     - “This image is 92% similar to a known AI-generated pattern.”
     - “This DM contains coercive language patterns.”
     - “This claim contradicts a post you saw yesterday.”

    This is what makes Sentinel feel like a new sense, not a tool.

### ⭐ Tech Stack

    Frontend

     - React + Vite
     - Tailwind CSS
     - Chrome Extension (Manifest V3)
     - Content Scripts + DOM Injection
     - MutationObserver for passive scanning

    Backend

     - FastAPI
     - Actian VectorAI DB
     - Sphinx Reasoning SDK
     - CLIP Embeddings (HuggingFace)

### ⭐ Sentinel Pipeline Flow

    This is the full end‑to‑end flow that powers Sentinel’s trust intelligence.

    1. DOM Watcher (Frontend)

    Sentinel monitors the page as you scroll.

    Detect new posts/images/profiles

    Extract:

     - Image URLs
     - Profile picture
     - Username
     - Bio
     - Post text
     - Send payload to backend
     - Show “Analyzing…” skeleton loader

    2. Embedding Engine (Backend)

    FastAPI generates a CLIP embedding for the content.

    3. Actian Vector Search (Backend)

    Actian retrieves:

     - Similar images
     - Similar profiles
     - Similar claims
     - Cluster membership
     - Past encounters

    4. Sphinx Reasoning (Backend)

    Sphinx interprets the signals and produces:

     - Trust score
     - Reasoning summary
     - Risk indicators
     - Intent analysis
     - Contradiction detection
     - Manipulation cues

    5. Trust Signal Injection (Frontend)

    Sentinel injects a small UI card under the content:

     - Trust Score
     - “Why this matters” explanation
     - Similarity matches
     - Risk indicators
     - Deep Check button

    6. Deep Check (Optional)

    User triggers Deep Check via right‑click or button.

    Backend performs:

     - Deeper similarity search
     - Cluster analysis
     - Manipulation detection
     - Contradiction detection
     - Intent reasoning
     - Frontend displays a detailed breakdown.

    7. Pattern Memory Update (Backend)

     - Actian stores new embeddings and updates clusters.
     - Sentinel gets smarter with every page you browse.

### ⭐ Demo Flow (For Judges)

     - Scroll Twitter/Instagram → Trust Signals appear automatically
     - Right‑click → Deep Check → X‑ray analysis
     - “You’ve seen this pattern before” → Actian cluster reveal
     - Toggle Trust Mode → page overlays highlight risks

### ⭐ Installation

(fill this in once packaged.)

### ⭐ Team

    Team Names