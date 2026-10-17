# CLAUDE.md — Muse Coach

Read this first in every session. Artifact 2 for TCSS 490 (due Sun Oct 18, 2026, 11:59 PM).

## What this is

A calorie tracker and fitness coach that runs as an iPhone-friendly web app (Safari → Add to
Home Screen). Python (FastAPI) back end, one static HTML page for the UI.

- Log meals by **photo** (Claude identifies the food, the app looks up USDA nutrition, Claude explains it) or by hand.
- Enter age / sex / height / weight / goal. The app computes calorie and macro targets.
- Pick a **celebrity as a style inspiration**. That selects a **fictional coach persona**
  (Coach Rhea, Dax, Juno, Bram) with its own voice and tips.
- The **Coach tab** gives a 7-day training week built from a **training style the user chooses** (6 styles in `app/data/workouts.json`: cardio intervals,
  bodyweight, boxing, push/pull/legs, athletic circuits, strength first). Activity level sets 3, 4 or 5 workout days; other days get a specific recovery routine.
  Every exercise is measurable (sets × reps, seconds or rounds), and each day has a check-off saved per calendar week.
- A 7-day meal plan of **Wikibooks recipes shown inside the app** (ingredients + cooking steps modal), portions scaled to the calorie target.

## Hard rules

1. **Celebrity = label only.** Never attribute weights, measurements, diets, workouts or quotes to a
   real person. The celebrity only picks an archetype in `app/data/celebrities.json`.
2. **Safety clamps live in `app/goals.py` and are tested.** Goal weight never below BMI 18.5, calorie
   floor (1200 F / 1500 M), max deficit 25% of maintenance, no deficit under 18. Never loosen these.
3. **Server authority.** The browser sends intents (profile, photo, meal). The server computes every number.
   The one exception is the GitHub Pages edition (no server exists there); its JS port must match
   `goals.py`, checked by `node tools/parity_check.mjs`.
4. **Workouts stay specific and measurable.** Every exercise needs a number (sets × reps, seconds, rounds) plus rest and a cue. No filler like "long walk" or
   "dance class" (a test enforces it). Keep the safety text and warm-ups; never prescribe training through pain or promise body changes.
5. **Recipes: only openly licensed text.** `app/data/recipes.json` comes from Wikibooks Cookbook (CC BY-SA 4.0) via `tools/build_recipes.py`.
   Never paste in text scraped from commercial recipe sites. Keep each recipe's source, history link and license visible in the app.
   Nutrition is computed from USDA data, never scraped.
6. **No secrets in git, in chat, or in the public site.** The server edition reads `ANTHROPIC_API_KEY` from the gitignored `.env`
   file (or the environment) via `app/config.py`, and only ever sends it to api.anthropic.com. Never print, log, store or echo it, never
   put it in `docs/` or client code, and never ask the user to paste it into chat (if they do, tell them to revoke it). Without a key,
   photo estimates return a labelled demo value so the app still runs. The Pages edition has each visitor paste their own key in their browser.
   Tests must never read the real `.env` or call the real API (`tests/conftest.py` enforces this).
7. **The model never supplies the numbers.** In `shared/pipeline.mjs` calories and nutrients are computed in code from retrieved USDA
   rows; a database id the model returns must be one that was actually retrieved, and model-supplied estimates are only accepted if they
   agree with their own macros and are labelled "AI estimate". Health text must follow from the numbers, make no medical claims, and
   never encourage skipping meals or restriction (nothing about dieting for under-18s).

## Layout

| Path | Holds |
| --- | --- |
| `app/main.py` | FastAPI routes |
| `app/goals.py` | BMR/TDEE/targets + safety clamps (pure functions) |
| `app/vision.py` | photo → calories via Claude |
| `app/coach.py`, `app/mealplan.py` | personas, check-in text, weekly plan |
| `app/db.py` | SQLite (profile + meals), file `app/data/muse.db` (gitignored) |
| `app/data/*.json` | celebrities, coach personas, recipes, food data (see below) |
| `app/static/` | the iPhone web UI (`index.html`, manifest, icon) |
| `tests/` | pytest: goal math, API, AI pipeline, training |
| `app/data/workouts.json` | training styles, day layouts by activity level, recovery routines, safety text. A test fails if any exercise has no number |
| `app/training.py` | builds the training week (Python); the browser edition has the same logic in `local-backend.js`, checked by `node tools/training_parity.mjs` |
| `tools/pages/local-backend.js` | in-browser copy of the API for GitHub Pages (localStorage, direct Claude call with the user's own key) |
| `tools/build_pages.py` | builds `docs/` (generated: never edit by hand) |
| `tools/parity_check.mjs` | compares the JS plan math with `goals.py` |
| `docs/` | the GitHub Pages site, served from `main` / `/docs` |
| `shared/pipeline.mjs`, `app/rag.py` | the identify → retrieve → explain → compute pipeline: JavaScript for the browser edition, a Python port for the server. Must stay in step: `node tools/pipeline_parity.mjs` |
| `shared/prompts.json` | the two model prompts, one source for both languages (`tools/sync_prompts.py` regenerates `prompts.mjs`) |
| `app/config.py`, `.env.example` | `.env` loading and the key placeholder |
| `tools/check_key.py` | self-test the user runs to confirm their key and image analysis work |
| `app/data/nutrition.json` | USDA SR Legacy knowledge base (built by `tools/build_nutrition_kb.py`; public domain) |
| `app/data/recipes.json` | scraped recipes + computed nutrition (built by `tools/build_recipes.py` from `tools/recipes_src.json`) |
| `app/data/food_calories.json` | typical-serving calories for the 101 classes the on-device model knows (approximate; keys must match the model's labels, checked by `node tools/ondevice_check.mjs --live`) |

After changing `app/static/`, `app/data/` or `local-backend.js`, run `tools/build_pages.py` and commit `docs/`.

## Run

```
.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
.venv\Scripts\python -m pytest
```

On the phone (same Wi-Fi) open `http://<PC IP>:8000`. Set `ANTHROPIC_API_KEY` first for real photo estimates.

## Session ritual

1. Start: read `PLAN.md` and the top entry of `LOG.md`.
2. Work on the next unchecked task.
3. End: tick tasks in `PLAN.md`, add a `LOG.md` entry (newest first), suggest a commit message.
4. Run the tests before committing. Ask before pushing.

## Style

Small functions, early returns, comments for *why*. Log lines prefixed like `[vision] ...`.
