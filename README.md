# Vision Assistant

Multimodal video understanding and query demo for uploaded indoor CCTV-style footage.

## What it does

- Upload MP4 video.
- Process frames incrementally so the UI feels live.
- Detect objects and create structured events.
- Query past events with text or voice.
- Speak answers aloud in the browser.
- Create alert rules and see alert hits in-app.

## Repo Layout

- `backend/` FastAPI + SQLite + processing pipeline.
- `frontend/` React + Vite UI.
- `IMPLEMENTATION_PLAN.md` build plan and design notes.

## Quick Start

1. Copy `backend/.env.example` to `backend/.env` and adjust model URLs if needed.
2. Run the backend from `backend/`:

```bash
cd backend
uv run uvicorn app.main:app --reload
```

3. Run the frontend from `frontend/`:

```bash
cd frontend
npm install
npm run dev
```

4. Open the frontend, upload a video, or click `Load demo memory`.

## Demo Guide (Hackathon Ready)

This app is optimized for live demos even without a GPU.

### 1. Zero-Setup "Mock Mode"
By default, `VISION_MOCK_MODE=true` is enabled in `.env`. This simulates a realistic "lost bag" scenario:
- **0-5s**: Empty room.
- **5-15s**: Person enters.
- **15-25s**: Person places a bag.
- **25-40s**: Person leaves; bag remains (triggering "item left behind" logic).
- **40s+**: Someone returns for the bag.

### 2. Natural Language Alerts
1. Open the UI.
2. Type or **speak** (click "Speak rule"): *"Notify me when a bag is detected"*
3. Click "Create alert".
4. Upload any MP4 video (or use the "Load demo memory" button).
5. Watch the "Alert Hits" section populate as the mock processor reaches the 15-second mark.

### 3. Voice Querying
1. Once events are in the timeline, click "Speak query".
2. Say: *"Where was my bag last seen?"*
3. The system will retrieve the latest event with a bag and **speak the answer aloud** using browser text-to-speech.

## Tech Stack
- **Frontend**: React + Vite, TypeScript, Vanilla CSS (with smooth auto-scroll & animations).
- **Backend**: FastAPI, SQLite, OpenCV for frame processing.
- **AI/ML**: YOLOv8 (Detector), Qwen-VL (VLM), GPT-4o-mini (LLM) - all with robust local fallbacks.
- **Voice**: Web Speech API (Input) + Speech Synthesis (Output).
