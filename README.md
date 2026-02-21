## Sentinel

🛡️ Sentinel (or Sherlock?): AI Content & Fake Account Detection Extension
Hacklytics 2026 Project

A real‑time trust & safety layer for the modern web.

## 📌 Overview

Sentinel (codename: Sherlock) is a Chrome browser extension that helps users identify AI‑generated images, fake accounts, and bot‑driven scams across social platforms like Twitter/X, Instagram Web, Facebook, TikTok Web, and Snapchat Web.

As users scroll, Sentinel automatically:

- Extracts images, profile pictures, bios, and post text from the DOM
- Analyzes them through a multi‑tier AI pipeline
- Detects AI‑generated content, impersonation attempts, and bot‑like behavior
- Injects a clear, human‑readable Trust Signal directly into the feed

This project addresses a real and growing problem:Most people — especially older users — can no longer tell what’s real online.

Sentinel restores clarity by “fighting AI with AI.”

## 🎯 Hackathon Challenge Alignment

# 🧥 Best AI for Human Safety (SafetyKit)

Sentinel directly targets:

- Impersonation
- Deception
- Scams
- Coercion
- Unsafe DMs
- Bot accounts
- AI‑generated misinformation

Perfect alignment with SafetyKit’s mission.

# 🧠 Most Unique Application of Sphinx

Sphinx acts as a Trust & Safety Reasoning Agent, transforming raw signals into:

- Risk scores
- Explanations
- Safety warnings
- Bot‑likelihood assessments

This is a non‑chat, high‑impact use of Sphinx.

# 🧬 Best Use of Actian VectorAI DB

Actian stores embeddings of:

- Known AI‑generated images
- Known bot profile pictures
- Known scam patterns

Sentinel uses Actian for:

- KNN similarity search
- Instant threat detection (<100ms)
- Caching
- Clustering bot profiles

# 🎨 Figma Make Challenge

All UI components — Trust Signals, skeleton loaders, popup dashboard — are prototyped in Figma.

## 🧩 Features

# ✔ Passive “Live Feed” Detection

Runs automatically as the user scrolls:

- Detects new posts via MutationObserver
- Extracts images + profile metadata
- Shows “Analyzing…” skeleton loader
- Performs CLIP embedding + Actian similarity search

injects Trust Signal under the post

# ✔ Manual “Deep Check”

Triggered via:

- Right‑click → “Analyze with Sentinel”
- Clicking a small “Deep Check” button

Provides:

- Detailed Sphinx reasoning
- Bot‑likelihood analysis
- Similarity matches
- Recommended safety actions

# ✔ Fake Account Detection

Analyzes:

- Follower/following ratios
- Username patterns
- Posting frequency
- Profile picture embeddings
- Bio language patterns

# ✔ Scam & Manipulation Detection

For pasted DMs or posts:

- Coercion patterns
- Emotional manipulation
- Impersonation cues
- Unsafe escalation

## 🛠️ Tech Stack

# Frontend (Browser Extension)

- React.js
- Vite
- Tailwind CSS
- Manifest V3
- Content Scripts\
- MutationObserver
- DOM Injection
- Extension Popup (React UI)

# Backend

- Python
- FastAPI
- CLIP (HuggingFace)
- Actian VectorAI DB
- Sphinx Python SDK
- SafetyKit API (optional)
- Hive Moderation API (optional fallback)

# Why this stack works

- No Instagram/Facebook APIs needed
- No screen‑level CV needed
- All heavy AI runs server‑side
- Extension stays lightweight and fast

## 🏗️ System Architecture

# Passive Live Feed Layer (Automatic)

- Content script detects new posts
- Extracts image URLs, profile metadata, text
- Sends to backend

Backend:

- CLIP embedding
- Actian similarity search
- Sphinx reasoning
- Frontend injects Trust Signal

# Manual Deep Check Layer (User‑Triggered)

- User right‑clicks → “Analyze with Sentinel”
- Backend performs deeper reasoning
- Returns detailed breakdown

Modal UI displays:

 - Risk Score
 - Explanation
 - Bot likelihood
 - Similarity Hits

## 🐳 Docker Setup (Local Dev)

This repository now includes a Dockerized backend so you can run the API layer immediately.

### 1) Start services

From the project root:

```bash
docker compose up --build
```

Backend API will be available at:

- `http://localhost:8000`
- `http://localhost:8000/health`
- `http://localhost:8000/docs`

### 2) Stop services

```bash
docker compose down
```

### 3) Environment variables

Backend environment values live in `backend/.env`.

Use these placeholders to wire in real integrations as they are implemented:

- `ACTIAN_VECTORAI_URL`
- `ACTIAN_VECTORAI_API_KEY`
- `SPHINX_API_KEY`
- `SAFETYKIT_API_KEY`
- `HIVE_API_KEY`

### Notes

- The current `/analyze` route is a scaffold response so Docker startup works immediately.
- Replace it with your full CLIP + Actian + Sphinx analysis pipeline in `backend/app/main.py`.