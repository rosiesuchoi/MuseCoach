"""Muse Coach API. The server computes every number; the phone only sends intents
(profile answers, a photo, a manual entry)."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import coach, db, goals, mealplan, vision

app = FastAPI(title="Muse Coach")
MAX_UPLOAD = 10 * 1024 * 1024  # 10 MB


class ProfileIn(BaseModel):
    age: int
    sex: str
    height_cm: float
    weight_kg: float
    goal: str
    activity: str
    goal_weight_kg: float | None = None
    celebrity: str = Field(default="", max_length=80)
    style: str = Field(default="", max_length=20)


class MealIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kcal: int = Field(ge=0, le=5000)


def _state() -> dict:
    stored = db.load_profile()
    if stored is None:
        return {"profile": None}
    profile = goals.Profile(**stored)
    archetype = coach.archetype_for(profile.celebrity, profile.style)
    plan = goals.build_plan(profile, archetype)
    meals = db.todays_meals()
    eaten = sum(m["kcal"] for m in meals)
    return {
        "profile": stored,
        "archetype": archetype,
        "coach": coach.coach_for(archetype),
        "plan": plan,
        "meals": meals,
        "eaten_kcal": eaten,
        "remaining_kcal": plan["target_kcal"] - eaten,
        "message": coach.checkin(archetype, plan["goal"], eaten, plan["target_kcal"]),
    }


@app.get("/api/options")
def options():
    return {"celebrities": coach.celebrity_options(), "styles": coach.style_options()}


@app.get("/api/state")
def state():
    return _state()


@app.put("/api/profile")
def put_profile(body: ProfileIn):
    data = body.model_dump()
    try:
        goals.build_plan(goals.Profile(**data), coach.archetype_for(body.celebrity, body.style))  # validate first
    except goals.ProfileError as e:
        raise HTTPException(422, str(e))
    db.save_profile(data)
    return _state()


@app.post("/api/meals/photo")
async def meal_photo(photo: UploadFile = File(...)):
    if db.load_profile() is None:
        raise HTTPException(400, "Set up your profile first.")
    data = await photo.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "Photo is too large (max 10 MB).")
    try:
        result = vision.estimate_meal(data)
    except vision.PhotoError as e:
        raise HTTPException(422, str(e))
    except Exception as e:  # API outage, bad key, etc. Don't crash the phone UI.
        print(f"[vision] estimate failed: {e}")
        raise HTTPException(502, "Couldn't estimate that photo right now. Enter calories by hand.")
    if result["total_kcal"] > 0:
        db.add_meal(result["meal_name"], result["total_kcal"], result["items"], "photo")
    return {"estimate": result, **_state()}


@app.post("/api/meals")
def meal_manual(body: MealIn):
    if db.load_profile() is None:
        raise HTTPException(400, "Set up your profile first.")
    db.add_meal(body.name, body.kcal, [], "manual")
    return _state()


@app.patch("/api/meals/{meal_id}")
def meal_edit(meal_id: int, body: MealIn):
    if not db.update_meal(meal_id, body.name, body.kcal):
        raise HTTPException(404, "Meal not found.")
    return _state()


@app.delete("/api/meals/{meal_id}")
def meal_delete(meal_id: int):
    db.delete_meal(meal_id)
    return _state()


@app.get("/api/mealplan")
def meal_plan():
    s = _state()
    if s["profile"] is None:
        raise HTTPException(400, "Set up your profile first.")
    return {"target_kcal": s["plan"]["target_kcal"], "week": mealplan.build_week(s["plan"]["target_kcal"])}


app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")
