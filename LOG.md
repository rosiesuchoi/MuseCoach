# LOG — Muse Coach

Newest entry on top.

## 2026-10-16: US units

**Changed:** the screen now uses feet/inches, pounds and "calories" instead of cm, kg and kcal.
Height is entered as ft + in, weight and goal weight in lb, and the plan shows lb/week.

**How:** the API and stored data stay metric, so the math, tests and the JS/Python parity check are
unchanged. Conversion happens only at the edges: the form and display in `app/static/index.html`, and the
user-facing messages in `goals.py`, `coach.py` and `local-backend.js`. Stored values use 2 decimals so a
weight like 132 lb survives repeated saves without drifting (an earlier version drifted to 132.1).

**Verified:** 16 pytest tests pass, 576-profile parity check has 0 mismatches, and in the browser the
form, plan screen, prefill after save, and out-of-range height message all show US units.

**Still open:** Pages isn't serving the site yet (see the previous status); recipe pages still show
their own calorie figures as printed.

## 2026-10-16: GitHub Pages edition

**Why:** Rosie wanted it hosted on GitHub Pages. Pages only serves static files, so the Python server
can't run there.

**Decision:** keep the FastAPI app, and add a static build. `tools/pages/local-backend.js` re-implements
the API in JavaScript and intercepts the UI's `fetch("/api/...")` calls, so the UI file is shared.
Data is in localStorage. Photo estimates call Claude directly from the browser with the user's own API
key (pasted on the Me tab, kept only in that browser). No key is ever committed.

**Trade-offs:** the math exists twice (Python and JS). `tools/parity_check.mjs` compares 576 profiles
and found 0 mismatches. This also breaks the "server authority" rule for this edition only, since
there is no server. Anyone using the live site has to supply their own key for real estimates.

**Verified:** served `docs/` under a `/MuseCoach/` subpath and ran setup, safety clamp, manual meal,
demo photo, and meal plan in the browser. Not verified: a real Claude photo call from the browser,
and the live Pages URL (Pages must be enabled in repo settings first).

**Next:** enable Pages, open the live link on the iPhone, try a real photo with a key.

## 2026-10-16: First build

**Planned:** a small, usable calorie tracker with photo logging, a celebrity-style coach and a
recipe meal plan, in Python.

**Decisions made with Claude Code**
- The idea was an iOS app. Native iOS needs Xcode on a Mac, so it became a FastAPI back end with
  a phone-sized web app (Add to Home Screen).
- Celebrities became a *style label*. Choosing one assigns a fictional coach persona. The app never
  states a real person's weight, diet or workouts. Any celebrity name can be typed in; unknown
  names get the all-round coach.
- Added safety limits (BMI 18.5 floor, calorie floors, capped deficit, no dieting under 18),
  because the target body comes from the user's input and shouldn't be able to produce an unsafe plan.

**Built**
- `goals.py` (math + clamps), `coach.py`, `mealplan.py`, `vision.py`, `db.py`, `main.py`, `static/index.html`.
- Recipes: searched for candidates, then opened every link with curl and checked the page loaded
  and showed the calories. Dropped links that were bot-blocked or had moved (Orlando Health,
  Allina, cancer.org, HEB, Mama Maggie's). Kept 9.
- 16 pytest tests pass. Ran the server and clicked through setup, Today, Coach and Meal plan at
  iPhone size. Entering a 45 kg goal at 165 cm was raised to 50.4 kg as intended.

**Not verified yet:** a real photo estimate (no `ANTHROPIC_API_KEY` was set, so it returned the
demo value) and use on an actual iPhone.

**Next:** set the API key, try real meal photos, add to Home Screen, fill in the portfolio card.

**Blockers:** none.
