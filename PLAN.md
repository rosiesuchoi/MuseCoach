# PLAN — Muse Coach (Artifact 2)

Due Sun Oct 18, 2026, 11:59 PM. Scope: one week, small, runs, and Rosie will keep using it.

## Scope decisions

- **iPhone web app, not native Swift.** Xcode needs a Mac. A Safari web app added to the home
  screen gives camera upload and an app-like feel, in Python.
- **Celebrity picks a fictional coach.** No real trainer names, no invented celebrity diets.
- **Safety first.** Goals are derived from the user's own body and clamped to healthy limits.

## Tasks

### v1 (this week)
- [x] New repo, venv, dependencies, CLAUDE.md
- [x] Goal math + safety clamps + tests (`goals.py`)
- [x] Coach personas and celebrity → archetype map
- [x] Photo → calorie estimate with Claude vision, demo fallback with no key
- [x] FastAPI routes: profile, state, photo, manual meal, delete, meal plan
- [x] Mobile web UI: Today / Coach / Meal plan / Me
- [x] 7-day meal plan (now 9 Wikibooks recipes shown in-app instead of external links)
- [x] API tests (16 passing)
- [x] GitHub Pages edition: static build in `docs/` with an in-browser backend
- [ ] Rosie: enable Pages (Settings → Pages → main → /docs) and open the live link
- [x] Celebrity photo carousel (Wikipedia), name search, coach-style picker for unlisted names
- [x] Key hidden after saving in the web edition (a Cloudflare proxy was built, then removed: Rosie chose not to use Cloudflare)
- [x] AI photo analysis (identify → USDA retrieval → explain), recipes shown in-app from Wikibooks (CC BY-SA)
- [x] On-device photo estimates (no key): food model in the browser + calorie table + meal editing
- [x] Server edition runs the full AI pipeline with the key from a gitignored `.env` (`app/rag.py`, `tools/check_key.py`)
- [ ] Rosie: create `.env` with her key, run `tools/check_key.py`, then try real meal photos
- [ ] Rosie: test a real photo on her iPhone
- [ ] Rosie: add to Home Screen, use it for a few days
- [ ] Portfolio card: title, repo link, short reflection

### Later (Week 5+)
- [ ] More recipes (snacks, vegetarian) from Wikibooks via `tools/recipes_src.json`
- [ ] Weight check-ins and a weekly chart
- [ ] Editing a photo estimate (rename / change kcal)
- [ ] HEIC upload support, HTTPS for off-network use
