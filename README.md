# Muse Coach

Log meals with a photo, get calorie and macro targets from your own stats, and train with a coach persona
that matches the celebrity style you admire. Includes a 7-day meal plan whose recipes (ingredients and
cooking steps) open inside the app.

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

**Photo analysis (AI + USDA retrieval).** With Claude access, a photo goes through a small RAG pipeline (`shared/pipeline.mjs`):
1. **Identify**: Claude looks at the photo and lists each food and drink with an estimated amount.
2. **Retrieve**: the app searches a bundled USDA FoodData Central index (about 7,300 foods, public domain, built by
   `tools/build_nutrition_kb.py`) for each item.
3. **Explain**: Claude picks the best match per item from only those retrieved candidates and writes what's in it, benefits, things
   to watch and whether it fits your goal and remaining calories.
4. **Compute**: code, not the model, multiplies grams by the database nutrients and adds up totals and flags (high sodium, saturated
   fat, sugar, and so on). Anything the database couldn't match is labelled "AI estimate", and amounts are always approximate (shown as a range).

**Recipes** are scraped from Wikibooks Cookbook (`tools/build_recipes.py`), shown fully in the app (ingredients, then cooking steps in a
second modal), with each recipe's source page, authors link and CC BY-SA 4.0 license. Nutrition is calculated from the USDA data with weights I
curated in `tools/recipes_src.json`; where a page was vague the app shows my assumption.

**Without Claude access** the web edition still works with **no key at all**: a small open food-recognition model
(Swin Transformer fine-tuned on Food-101, Apache-2.0, about 60 MB, downloaded once and cached) runs
inside the browser. Photos never leave the device. It names the dish (101 common dishes) and assumes one typical
serving from `app/data/food_calories.json`, so it is approximate; every logged meal can be edited with ✎. It
refuses to guess when it isn't sure (for example a photo that isn't food). It is weaker on mixed plates and can't see portion size.
For the full AI analysis there are three routes, safest first:
1. **Proxy (best for the public site):** deploy the small Cloudflare Worker in `worker/` (see its README).
   The key lives only as a Worker secret, so no browser or repo ever has it. Daily caps limit cost.
   Then build with `MUSE_PROXY_URL` set and the key box disappears from the app.
2. **Local server:** run the FastAPI server at home with `ANTHROPIC_API_KEY` in its environment.
   The key never leaves your PC.
3. **Paste your own key** on the Me tab of the web edition. It is stored only in that browser, never
   shown again (only its last 4 characters), and sent only to api.anthropic.com. Use a key with a low spend limit.

The Python server edition without a key still returns a clearly-labelled demo estimate (the on-device model is a web-edition feature).

**Celebrity photos** are fetched live from Wikipedia/Wikimedia Commons, so no images live in this repo.

## About the celebrities and coaches

Picking a celebrity only chooses a coach style. The app does not claim anything about a real person's
body, diet or training. Targets come from your own height, weight, age and goal, and are kept within
healthy limits (see `app/goals.py`). This is not medical advice.
