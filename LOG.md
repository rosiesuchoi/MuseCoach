# LOG — Muse Coach

Newest entry on top.

## 2026-10-18: Diet and allergies, a database, varied recipes, priced grocery list

**Asked for:** a backend database for the recipes and foods; the user's dietary needs and allergies; less boring and repetitive food (when the diet isn't
too strict); a grocery list for the recipes with itemized, accurate pricing.

**Built.**
- *Data:* `app/data/ingredients.json` (100 grocery items: USDA id, allergens, meat/poultry/honey flags, aisle, pack size and price). Recipes grew from 9 to 62 (9 Wikibooks +
  53 original in `tools/recipes_original.json`, including enough vegetarian, vegan and gluten-free ones that strict diets still get choices). Each recipe now lists grams per
  ingredient; allergens, nutrition and cost are computed from that, not typed by hand.
- *Database (`app/db.py`):* tables for ingredients, recipes, recipe lines, the user's diet, price edits, and saved weekly plans with their meals. The plan is saved per
  Monday-start week so it stays put, is rebuilt when the diet or calorie target changes, and "Shuffle my week" makes a new one. Old weeks stay as history.
- *Variety (`app/diet.py`):* a seeded planner picks 7 different recipes per meal slot when the diet allows 7 or more, and otherwise repeats them as far apart as possible and
  shows a note. If nothing fits a slot the slot is left out with a note. Portions are chosen so a serving of 0.5x to 2x can reach the calorie target.
- *Grocery list:* amounts summed across the week, converted to household units, rounded up to whole packs, grouped by aisle, integer-cent totals, a "without pantry staples" figure,
  and per-item prices the user can edit (`PUT /api/prices`).
- *UI:* diet and allergies form (Meals and Me tabs), diet chips, shuffle, cost per meal and per serving, allergen "Contains" line, grocery modal with copy and share.
- *Both editions:* the server uses SQLite; the GitHub Pages edition has the same logic in `local-backend.js` using browser storage.

**Honest limits.**
- Only **17 of 100 prices are official** (BLS average retail prices, US city average, Sep 2026; BLS's data files returned 403 so I read its published HTML table). The other **83 are my
  estimates**, tagged "est." in the app. Totals are good guides, not store quotes. They run high for one person (about $130 to $240 a week) because 21 different recipes mean many whole packs; the
  "you'll actually eat" figure shows the value of the food used.
- Allergen tags come from listed ingredients. They do not know brands, "may contain" labels or cross-contact. The app says to read labels and that this is not medical advice.
- The database only exists in the server edition; Pages keeps data in the browser.
- Coverage is thinner for stacked restrictions (e.g. vegan + gluten-free + no soy has about 4 to 6 options per slot, so recipes repeat; the app says so).

**Checks.** 84 pytest tests (data lint, allergen-word lint, diet patterns, variety, determinism, calorie sizing, packs and price overrides, DB persistence, API); `node tools/diet_parity.mjs` confirms JS and Python
give identical plans for 13 diets x 3 calorie targets x 3 seeds, identical grocery lists and costs; the older parity and pipeline checks still pass. In a browser at 1440 and 375 px: Meals, grocery list, price edit
(total changed by the expected amount), and a vegan + gluten-free + no-soy plan with notes all worked with no console errors and no horizontal overflow. **Not verified:** a real phone, a screen reader, the Python server in a
browser (covered by API tests instead).

**Next:** Rosie to check the estimated prices; push when ready.

## 2026-10-17: Desktop layout (the app was a phone column stretched on desktop)

**Problem:** on a desktop browser the app was a 560px column in the middle of a wide empty page with a phone-style bottom bar.

**Fix (CSS and light markup only; no logic changed):** the page is now wrapped in a layout shell with three modes.
Phone (default): unchanged. Tablet (700px+): wider content and two-column grids for Coach days, Meals and the Today panels, centered dialogs instead of bottom sheets.
Desktop (960px+): a sticky left sidebar replaces the bottom bar, a 1160px-wide layout, Today as ring + message then "log a meal" beside "logged today",
Coach with hero beside weekly progress, all six training styles in a 3 x 2 grid and days in two columns, Meals in two columns, Me with the celebrity
picker as a wrapping gallery beside the form, hover states (only on devices that hover), and wider dialogs.
Accessibility: a "Skip to content" link, `<main>` landmark (focus moves into it when you change tabs), nav and field labels checked, real buttons everywhere.

**Verified in a browser at 1440, 820 and 375 px:** no horizontal overflow on any of the four tabs at any width; the expected column counts and nav mode at each width; the
recipe dialog centers on desktop; skip link moves focus to the main content. **Not verified:** real devices beyond the emulated widths, and a screen reader.
(An unrelated, uncommitted change to the intro animation was discarded at Rosie's request.)

## 2026-10-17: Coach tab rebuilt, workout check-offs, visual refresh, entrance animation

**Asked for:** no dancing; other equal-effort workouts that are specific and measurable (exact exercises, reps); the user can choose the training style;
a checkmark per day; a visual upgrade and an entrance animation.

**Workouts.** New `app/data/workouts.json`: 6 training styles (Cardio Intervals + Core, Bodyweight Strength, Boxing Conditioning, Push/Pull/Legs Lifting,
Athletic Circuits, Strength First), each with 5 workout days and a progression rule, plus 2 shared recovery routines (mobility flow; stretch + easy walk with RPE and
timings) and safety text. 123 exercises, every one with a number, rest and a coaching cue. Dance is replaced by timed cardio intervals (RPE-based, with a jump rope, run,
bike or high-knees option) and Pilates-style core work; the old vague weekly text ("long walk", "dance class") is gone, and a test blocks it coming back.
The coach persona (set by the celebrity) now only supplies voice, tips and a default style; the user can switch styles on the Coach tab at any time.
Activity level sets 3, 4 or 5 workout days (Mon/Wed/Fri, Mon/Tue/Thu/Sat, Mon/Tue/Thu/Fri/Sat); other days get a specific recovery routine.

**Check-offs.** Per calendar week (Monday start), saved server-side in SQLite (`checks` table) or in the browser's storage on the Pages edition. Progress counts workout days
only; recovery days are optional. Finishing every workout triggers a small confetti burst. Saving the profile form no longer wipes the chosen training style.

**API:** `state.training`, `PUT /api/training`, `POST /api/workouts/check` (same in both editions; `app/training.py` and `local-backend.js`).

**UI.** Rewrote the stylesheet and Coach tab: design tokens, light and dark themes, glass bottom nav with icons, an animated calorie ring on Today, rounded cards, a
Today's-workout shortcut, expandable day cards (warm-up, exercises with big sets × reps, rest, cues, cool-down, what to track). Entrance animation: a splash with a
popping heart and "Train. Eat. Glow." that fades into staggered card entrances; it plays once per visit, can be tapped away, and is skipped for `prefers-reduced-motion`.

**Verified:** 57 pytest tests (data lint, plan logic per activity, API, persistence, weekly reset); `node tools/training_parity.mjs` (216 weeks, 0 mismatches vs Python);
in a phone-sized browser: splash and cascade, Coach tab, check-off with progress and persistence, style switch rebuilding the week, confetti on the final workout, dark mode,
and the same flows against the Python server (state persisted in its database across a reload).
**Not verified:** on a real iPhone (safe-area padding, the translucent nav blur and touch feel), and I have not had a trainer review the programs: they are standard,
conservative templates, not individualized or medical advice.

## 2026-10-17: First real run with Rosie's key, and the bug it found

Rosie put her key in `.env` (I only checked its shape: present, 106 characters, starts with `sk-ant-`; I never printed it). `tools/check_key.py` then
failed with `AttributeError`. Cause: the model sometimes starts its reply with a **thinking block** that has no `.text`, and both the Python and
browser code read `content[0].text`. Mocked tests could never have caught it. Fix (both editions): join only the `text` blocks (`rag.reply_text`,
`replyText` in pipeline.mjs), treat `stop_reason: max_tokens` as a clear "answer was cut off" error, and raise `max_tokens` (identify 700 → 2500,
explain 1400 → 4000) because thinking shares that budget. Regression tests for thinking-first replies in Python and JS; test guard moved to patch
`anthropic.Anthropic` itself so no test can ever build a real client.

Also: the drawn-apple default in `check_key.py` was sometimes judged "not real food" (it is a cartoon), so the script now reports that case as
"key works, AI can see images" and suggests a real photo; `--debug` prints a key-redacted traceback.

**Verified with the real API:** a Wikimedia pizza photo and a ramen photo both ran identify → USDA retrieval → explain.
Ramen: shoyu ramen with chashu, 6 items, 457 cal (likely 343-571), 5 items matched to USDA and 1 labelled "AI estimate", verdict "okay", flags high
sodium + good protein. Pizza: 8 items, 2,486 cal (whole pizza ~800 g plus a lager and the raw vegetables arranged around it), confidence low.
**Honest notes on quality:** amounts come from the AI's eye, so a whole-pizza photo reads as a very large meal; props in the shot (raw
vegetables) get counted as food; the "low" confidence label and the likely-range are there for exactly this. The live server UI with a real key
has not been clicked through yet (only the script and the mocked endpoint tests), and the Pages edition's direct-key path has not run against the real API.

**Next:** Rosie runs the server and logs a few of her own meals; tell me which ones it gets wrong.

## 2026-10-17: Dropped Cloudflare; the server runs the AI pipeline with a key from `.env`

**Decision (Rosie):** no Cloudflare, and no key shared with the assistant: she will use her own Anthropic key. (An attempt to deploy the Worker
had hit a Cloudflare "Authentication error 10000" while creating the KV store; moot now. Rosie can revoke wrangler's access with `npx wrangler logout`.)
Earlier entries below mention the Worker; it no longer exists (`worker/`, `deploy.ps1` and the proxy code in the browser edition are deleted, still in git history).

**Built**
- `app/rag.py`: Python port of the identify → retrieve → explain → compute pipeline, same logic and same prompts. Prompts moved to
  `shared/prompts.json` (one source; `tools/sync_prompts.py` generates `prompts.mjs` for the browser; a test checks they're in sync).
- `app/config.py` + `.env.example`: the key comes from the gitignored `.env` (or the environment), read per request. `tools/check_key.py` lets
  Rosie confirm her key and the image analysis work, without printing the key.
- `POST /api/meals/photo` now runs the pipeline when a key is set (off the event loop), saves the full analysis with the meal (new `analysis` column,
  old databases upgraded in place), and falls back to the labelled demo value with no key. Same UI as the web edition: verdict, totals, flags, ⓘ details.
- Error handling: Anthropic errors become fixed messages (key rejected, rate limit, offline); unexpected errors log only the exception type.

**Safety checks:** key never in any response, log, DB row or test output; tests use a fake key and a mocked model, and `tests/conftest.py` blocks real
API calls and the real `.env`; `.env` is verified gitignored by a test.

**Verified:** 38 pytest tests; `node tools/pipeline_parity.mjs` (identical retrieval order for 19 queries, byte-identical model requests, identical full
analysis for the same mocked model); with a deliberately fake key the running server called the real Anthropic API, got a 401, and returned the
clean "key was rejected" message with the key nowhere in the response or the server log.
**Not verified:** a successful call with a real key (I never had one): that is what `tools/check_key.py` is for.

**Next:** Rosie creates `.env`, runs `tools/check_key.py`, then logs real meal photos and reports what it gets wrong.

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
