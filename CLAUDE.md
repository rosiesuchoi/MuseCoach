# CLAUDE.md — Muse Coach

Read this first in every session. Artifact 2 for TCSS 490 (due Sun Oct 18, 2026, 11:59 PM).

## What this is

A calorie tracker and fitness coach that runs as an iPhone-friendly web app (Safari → Add to
Home Screen). Python (FastAPI) back end, one static HTML page for the UI.

- Log meals by **photo** (Claude vision estimates calories) or by hand.
- Enter age / sex / height / weight / goal. The app computes calorie and macro targets.
- Pick a **celebrity as a style inspiration**. That selects a **fictional coach persona**
  (Coach Rhea, Dax, Juno, Bram) with its own training week, tips and voice.
- A 7-day meal plan links to **real recipes**, with portions scaled to the user's calorie target.

## Hard rules

1. **Celebrity = label only.** Never attribute weights, measurements, diets, workouts or quotes to a
   real person. The celebrity only picks an archetype in `app/data/celebrities.json`.
2. **Safety clamps live in `app/goals.py` and are tested.** Goal weight never below BMI 18.5, calorie
   floor (1200 F / 1500 M), max deficit 25% of maintenance, no deficit under 18. Never loosen these.
3. **Server authority.** The browser sends intents (profile, photo, meal). The server computes every number.
   The one exception is the GitHub Pages edition (no server exists there); its JS port must match
   `goals.py`, checked by `node tools/parity_check.mjs`.
4. **Real links only.** Every URL in `app/data/meals.json` must be opened and checked before it is added.
5. **No secrets in git.** `ANTHROPIC_API_KEY` comes from the environment. Without it, photo estimates
   return a labelled demo value so the app still runs.

## Layout

| Path | Holds |
| --- | --- |
| `app/main.py` | FastAPI routes |
| `app/goals.py` | BMR/TDEE/targets + safety clamps (pure functions) |
| `app/vision.py` | photo → calories via Claude |
| `app/coach.py`, `app/mealplan.py` | personas, check-in text, weekly plan |
| `app/db.py` | SQLite (profile + meals), file `app/data/muse.db` (gitignored) |
| `app/data/*.json` | celebrities, coach personas, verified recipes |
| `app/static/` | the iPhone web UI (`index.html`, manifest, icon) |
| `tests/` | pytest: goal math and API |
| `tools/pages/local-backend.js` | in-browser copy of the API for GitHub Pages (localStorage, direct Claude call with the user's own key) |
| `tools/build_pages.py` | builds `docs/` (generated: never edit by hand) |
| `tools/parity_check.mjs` | compares the JS plan math with `goals.py` |
| `docs/` | the GitHub Pages site, served from `main` / `/docs` |

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
