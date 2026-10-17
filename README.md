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
back end. Your profile and meals stay in your browser's storage. Rebuild with
`.venv\Scripts\python tools/build_pages.py`.

**Photo estimates and the API key.** There are three ways to run them, safest first:
1. **Proxy (best for the public site):** deploy the small Cloudflare Worker in `worker/` (see its README).
   The key lives only as a Worker secret, so no browser or repo ever has it. Daily caps limit cost.
   Then build with `MUSE_PROXY_URL` set and the key box disappears from the app.
2. **Local server:** run the FastAPI server at home with `ANTHROPIC_API_KEY` in its environment.
   The key never leaves your PC.
3. **Paste your own key** on the Me tab of the web edition. It is stored only in that browser, never
   shown again (only its last 4 characters), and sent only to api.anthropic.com. Use a key with a low spend limit.

Without any of these, photos give a clearly-labelled demo estimate.

**Celebrity photos** are fetched live from Wikipedia/Wikimedia Commons, so no images live in this repo.

## About the celebrities and coaches

Picking a celebrity only chooses a coach style. The app does not claim anything about a real person's
body, diet or training. Targets come from your own height, weight, age and goal, and are kept within
healthy limits (see `app/goals.py`). This is not medical advice.
