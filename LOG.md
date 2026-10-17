# LOG — Muse Coach

Newest entry on top.

## 2026-10-16: In-app recipes and AI photo analysis (RAG)

**Asked for:** (1) stop sending users to external recipe pages that ask them to subscribe; scrape the recipe and show it inside
the app, ingredients first and cooking steps in a separate modal. (2) Make photo analysis accurate with a smart AI agent, as a RAG app:
photo in, then retrieve calories, contents, benefits/harms and whether it's a good idea to eat or drink.

**Recipes.** I did not scrape the blog sites we linked before: republishing their writing in a public app and repo is copying
their copyrighted text. Chosen with Rosie: scrape Wikibooks Cookbook (CC BY-SA 4.0). `tools/build_recipes.py` fetches each page's wikitext
(revision id recorded), cleans it, and writes `app/data/recipes.json` with source page, authors link and license, all shown in the app.
Nutrition is NOT scraped: I curated ingredient weights and servings in `tools/recipes_src.json` (stating assumptions where a page is vague)
and compute per-serving nutrition from USDA data. Check: Black Bean Soup computed 387 cal/serving vs 390 printed on its own page.
The 9 recipes replaced the 9 external links; `GET /api/recipes/{id}` exists in both back ends. Because the recipe data is CC BY-SA,
that file is too.

**Knowledge base.** Downloaded USDA FoodData Central SR Legacy (public domain, 6.07 MB zip) into a scratch folder, extracted it safely, and
`tools/build_nutrition_kb.py` builds a compact `app/data/nutrition.json` (7,283 foods, 1.37 MB, ~350 KB gzipped): per-100 g nutrients plus
household portions. Only that file is committed.

**Pipeline** (`shared/pipeline.mjs`, used by the browser and the Worker): identify (Claude vision) → retrieve (lexical search over the USDA
index, 8 candidates per item) → explain (Claude chooses among only the retrieved candidates and writes contents, benefits, concerns, a verdict
and goal fit) → compute (code multiplies grams × per-100 g and sums; flags use label-style thresholds). Guards: a database id the model returns
must be one we retrieved; fallback estimates must agree with their own macros; absurd totals refused; items are labelled USDA or "AI estimate";
confidence never "high"; totals shown as a likely range; prompts forbid medical claims and restriction advice and drop diet talk for minors; text in
the photo is treated as data.

**Where it runs.** The Worker only makes the two model calls (`/identify`, `/explain`), so it stays small enough for Cloudflare's free CPU limit;
retrieval and math run in the browser. With a pasted key the browser makes the same two calls itself. With neither, the on-device model is the fallback
and shows calories only. The Python server edition is unchanged (no AI analysis there).

**Honest limits.** I cannot be the app's runtime: the AI step needs an Anthropic key via the Worker or a pasted key, so Rosie still has to do that
setup. I have **not** run it against the real model (no key): the pipeline was tested with a mocked model against the real USDA data, and in the browser
through a fake proxy. Retrieval is lexical, so unusual dish names may miss (those become "AI estimate"). Amounts from a photo are estimates.
SR Legacy is a 2018 snapshot and is light on newer products and some prepared foods (for example, no sushi roll entry).

**Verified:** 20 pytest tests; 12 pipeline tests (real index, mocked model); 15 Worker tests; on-device and parity checks; in a phone-sized browser:
the analysis modal rendered (verdict, totals with range, flags, items with USDA tags, contents, benefits, concerns, tips), all 9 recipes open with
ingredients, the steps modal stacks on top, and Close/Esc work.

**Next:** Rosie creates an Anthropic key with a spend limit and deploys the Worker (`worker/README.md`), then tries real meal photos and reports what it gets wrong.

## 2026-10-16: On-device photo estimates (no API key)

**Why:** Rosie wanted photo logging that works without an API key.

**What:** the web edition now runs `onnx-community/swin-finetuned-food101-ONNX` (Apache-2.0, `q4` build, ~60 MB)
in the browser through transformers.js. Library version (3.8.1) and model revision are pinned. The top
prediction maps to a typical-serving calorie figure in `app/data/food_calories.json` (101 classes, rounded
ballpark numbers). Order of use: proxy → pasted Claude key → on-device. First use shows a download
progress label; later uses read the browser cache. Meals can now be edited (✎ on the Today tab; new `PATCH /api/meals/{id}`
in both back ends) because the estimate is approximate.

**Honest limits:** it only knows 101 dishes, can't see portion size, and is weaker on mixed plates. It never reports
"high" confidence, and below a 0.20 score it refuses and asks for manual entry. Food-101 models are overconfident on
non-food in general, but a cat and a mountain photo were both refused in testing.

**Verified:** real model download in the browser; Wikipedia photos of pizza, ramen, sushi, hamburger, Caesar salad
and pancakes were all named correctly; cat and Mount Everest were refused; cache confirmed (reload ran in ~4 s); edit and
validation work; table matches the model's 101 labels (`node tools/ondevice_check.mjs --live`); 20 pytest tests, 6+1 on-device
checks, 576-profile parity check all pass. Layout fixed so the ✎ ✕ buttons stay on one line on a phone.
**Not verified:** accuracy on real phone photos of home-cooked or mixed meals (the test photos were clean Wikipedia
images), and speed/memory on an actual iPhone (the ~60 MB model plus wasm is the main risk on older phones).

**Next:** Rosie tests a few of her own meal photos on her iPhone and tells me which dishes it gets wrong.

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
