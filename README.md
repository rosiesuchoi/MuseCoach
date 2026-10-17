# Muse Coach

Log meals with a photo, get calorie and macro targets from your own stats, and train with a coach persona
that matches the celebrity style you admire. Includes a 7-day meal plan linked to real recipes.

Runs as a Python (FastAPI) server with a phone-sized web app. On iPhone: open it in Safari → Share →
Add to Home Screen.

## Setup

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
set ANTHROPIC_API_KEY=your-key      # optional; without it photos give a demo estimate
.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`, or `http://<your PC's IP>:8000` from a phone on the same Wi-Fi.

Tests: `.venv\Scripts\python -m pytest`

## Web edition (GitHub Pages)

Live: https://rosiesuchoi.github.io/MuseCoach/ (open in Safari → Share → Add to Home Screen).

Pages can't run Python, so `docs/` is a static build where the same UI runs on a JavaScript copy of the
back end. Your profile and meals stay in your browser's storage. For real photo estimates, paste your own
Anthropic API key on the Me tab; it is stored only in your browser and sent only to api.anthropic.com.
Without a key, photos give a demo estimate. Rebuild with `.venv\Scripts\python tools/build_pages.py`.

## About the celebrities and coaches

Picking a celebrity only chooses a coach style. The app does not claim anything about a real person's
body, diet or training. Targets come from your own height, weight, age and goal, and are kept within
healthy limits (see `app/goals.py`). This is not medical advice.
