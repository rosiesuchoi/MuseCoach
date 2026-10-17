# Muse Coach

Log meals with a photo, get calorie and macro targets from your own stats, and train with a coach persona
that matches the celebrity style you admire. Includes a 7-day meal plan whose recipes (ingredients and
cooking steps) open inside the app.

Runs as a Python (FastAPI) server with a phone-sized web app. On iPhone: open it in Safari → Share →
Add to Home Screen.

## What's in the app

- **Today:** calorie ring, photo logging with AI analysis, manual entries, and today's workout.
- **Coach:** pick a training style (cardio intervals, bodyweight, boxing, push/pull/legs, athletic circuits or strength first) and get a 7-day week
  with the exact exercises, sets × reps, rest times and a number to track. Your activity level sets 3, 4 or 5 workout days; the other days are
  guided recovery. Tick each day when you finish; ticks are saved for the week and reset on Monday.
- **Meals:** a 7-day plan with full recipes (ingredients, cooking steps) inside the app.
- **Me:** your numbers, celebrity style inspiration, and your key settings.

**Works on any screen.** On a phone it is a single column with a bottom tab bar. On a tablet the content flows into two columns. On a desktop
browser (about 960 px and wider) it becomes a full layout: a navigation sidebar on the left, the training styles and week laid out in a grid, the celebrity
gallery and your numbers side by side, and recipes and analyses opening as centered dialogs. It has hover effects, a "Skip to content" link for keyboard
users, and all controls are real buttons and labelled fields.

The first time you open the app in a visit it plays a short entrance animation (skipped if your device asks for reduced motion). It follows your
light or dark setting.

## Setup

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`, or `http://<your PC's IP>:8000` from a phone on the same Wi-Fi.

Tests: `.venv\Scripts\python -m pytest`

## Turning on the AI photo analysis (your Anthropic key)

The AI step needs an Anthropic API key (https://console.anthropic.com/settings/keys; set a monthly spend limit on it first).
**The key lives only in a file called `.env` on your PC.** That file is gitignored, so it can never be committed.

1. Copy `.env.example` to `.env` (same folder).
2. Open `.env` in a text editor and put the key after `ANTHROPIC_API_KEY=`. Save it. Don't paste the key into chat, code or screenshots.
3. Check it works (the script never prints the key and costs about a cent or two):

   ```
   .venv\Scripts\python tools/check_key.py                  # tries a picture of an apple the script draws
   .venv\Scripts\python tools/check_key.py path\to\meal.jpg   # or one of your own photos
   ```
4. Start the server (above). Photos you log now get the full analysis. Restart the server after changing `.env`.

Without a key the server returns a clearly-labelled demo estimate (500 calories).

### How the analysis works (RAG)

A photo goes through a pipeline (`app/rag.py`; the same logic runs in the browser edition as `shared/pipeline.mjs`):
1. **Identify**: Claude looks at the photo and lists each food and drink with an estimated amount.
2. **Retrieve**: the app searches a bundled USDA FoodData Central index (about 7,300 foods, public domain, built by
   `tools/build_nutrition_kb.py`) for each item.
3. **Explain**: Claude picks the best match per item from only those retrieved candidates and writes what's in it, benefits, things
   to watch and whether it fits your goal and remaining calories.
4. **Compute**: code, not the model, multiplies grams by the database nutrients and adds up totals and flags (high sodium, saturated
   fat, sugar, and so on). Anything the database couldn't match is labelled "AI estimate", and amounts are always approximate (shown as a range).

The two prompts live in `shared/prompts.json` (one source for both languages; run `tools/sync_prompts.py` after editing).
`node tools/pipeline_parity.mjs` checks the Python and JavaScript versions give identical results.

### Where the key is used

Only the server reads it, and only to call api.anthropic.com. It is never sent to the phone, never logged, never stored in the database, and
error messages from the AI service are replaced with fixed text so nothing from a request can leak. Tests run with a fake key and a mocked model.

## Web edition (GitHub Pages)

Live: https://rosiesuchoi.github.io/MuseCoach/ (open in Safari → Share → Add to Home Screen).

Pages can't run Python, so `docs/` is a static build where the same UI runs on a JavaScript copy of the back end. Your profile and meals
stay in your browser's storage. Rebuild with `.venv\Scripts\python tools/build_pages.py`.

For the AI analysis here, each person pastes their **own** Anthropic key on the Me tab. It stays in that browser (never shown again, only its
last 4 characters), is sent only to api.anthropic.com, and your key is never in this repo or on any server of ours. Browser storage is shared by
every page on the same github.io address, so use a key with a low spend limit, and remove it when you're done.

Without a key the web edition still works: a small open food-recognition model (Swin Transformer fine-tuned on Food-101, Apache-2.0,
about 60 MB, downloaded once and cached) runs inside the browser and photos never leave the device. It names the dish (101 common dishes) and
assumes one typical serving from `app/data/food_calories.json`, so it is approximate; every logged meal can be edited with ✎. It refuses to
guess when it isn't sure, is weaker on mixed plates, and can't see portion size.

**Recipes** are scraped from Wikibooks Cookbook (`tools/build_recipes.py`), shown fully in the app (ingredients, then cooking steps in a
second modal), with each recipe's source page, authors link and CC BY-SA 4.0 license. Nutrition is calculated from the USDA data with weights I
curated in `tools/recipes_src.json`; where a page was vague the app shows my assumption.

**Celebrity photos** are fetched live from Wikipedia/Wikimedia Commons, so no images live in this repo.

## About the celebrities and coaches

Picking a celebrity only chooses a coach style. The app does not claim anything about a real person's
body, diet or training. Targets come from your own height, weight, age and goal, and are kept within
healthy limits (see `app/goals.py`). This is not medical advice.
