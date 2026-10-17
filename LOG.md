# LOG — Muse Coach

Newest entry on top.

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
