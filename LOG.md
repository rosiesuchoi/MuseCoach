# LOG — Muse Coach

Newest entry on top.

## 2026-10-16: Celebrity photo carousel + key safety

**Style inspiration:** now a swipeable row of portraits with names. Portraits are fetched live from
Wikipedia/Wikimedia Commons by page title (nothing stored in the repo, only `https://upload|thumb.wikimedia.org`
URLs are accepted). If a celebrity isn't listed, the user types a name, Wikipedia search shows matches
with photos, and they tap the right one. Names that aren't in the built-in list then get a coach-style
picker (stored as `style` on the profile). Two earlier list entries had to change: Karina's Wikipedia title
is a disambiguation page (dropped), and Lisa's page thumbnail is a signature image (replaced by Rosé).
All 13 listed names were checked to return real portraits.

**API key:** "bypass the key" isn't possible (any hosted vision model needs one), and no key can be
supplied for the user. Instead: a saved key is never written back into the page (only its last 4 characters,
plus Remove), and for the public site there is a Cloudflare Worker proxy in `worker/` that holds the key as
a secret. The Worker fixes the model, prompt and token limit, restricts origins, caps requests per day
globally and per IP, fails closed without its KV store, and never forwards upstream errors. 11 Worker tests
pass with mocked network. Note: localStorage is shared by every page on `rosiesuchoi.github.io`, so a pasted
key is readable by any script on the user's other Pages sites. That is why the proxy is the recommended path.

**Verified:** 19 pytest tests, 576-profile parity check (0 mismatches), 11 Worker tests; in the browser the
carousel loaded 13 real portraits, search found Gong Yoo, the style picker worked and was restored on reload,
a bad key was rejected, a saved key was masked and absent from the page HTML, and a photo went through a fake
local proxy end to end (no key field shown, meal logged).

**Not verified:** a real Claude photo estimate (no key available to me), and the deployed Worker.
**Next:** Rosie creates a key with a spend limit and deploys the Worker (`worker/README.md`).

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
