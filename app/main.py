"""Muse Coach API. The server computes every number; the phone only sends intents
(profile answers, a photo, a manual entry)."""

from __future__ import annotations

import base64
from datetime import date
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from . import coach, config, db, goals, mealplan, rag, training, vision

config.load_env()  # reads ANTHROPIC_API_KEY from the gitignored .env file, if there is one
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
    training: str | None = Field(default=None, max_length=30)  # None = keep what's saved


class TrainingIn(BaseModel):
    style: str = Field(max_length=30)  # "" = the coach's default


class CheckIn(BaseModel):
    day: str
    done: bool


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
    today = date.today()
    style = profile.training if training.is_style(profile.training) else coach.coach_for(archetype)["default_training"]
    week = training.build_week(style, profile.activity, db.get_checks(training.week_start(today).isoformat()), today)
    return {
        "profile": stored,
        "archetype": archetype,
        "coach": coach.coach_for(archetype),
        "plan": plan,
        "meals": meals,
        "eaten_kcal": eaten,
        "remaining_kcal": plan["target_kcal"] - eaten,
        "message": coach.checkin(archetype, plan["goal"], eaten, plan["target_kcal"]),
        "training": week,
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
    if data["training"] is None:  # the profile form doesn't send it: keep the user's chosen training style
        data["training"] = (db.load_profile() or {}).get("training", "")
    try:
        goals.build_plan(goals.Profile(**data), coach.archetype_for(body.celebrity, body.style))  # validate first
    except goals.ProfileError as e:
        raise HTTPException(422, str(e))
    db.save_profile(data)
    return _state()


@app.put("/api/training")
def put_training(body: TrainingIn):
    stored = db.load_profile()
    if stored is None:
        raise HTTPException(400, "Set up your profile first.")
    if body.style and not training.is_style(body.style):
        raise HTTPException(422, "Unknown training style.")
    db.save_profile({**stored, "training": body.style})
    return _state()


@app.post("/api/workouts/check")
def workout_check(body: CheckIn):
    if db.load_profile() is None:
        raise HTTPException(400, "Set up your profile first.")
    if body.day not in training.DAYS:
        raise HTTPException(422, "Unknown day.")
    db.set_check(training.week_start(date.today()).isoformat(), body.day, body.done)
    return _state()


@app.post("/api/meals/photo")
async def meal_photo(photo: UploadFile = File(...)):
    if db.load_profile() is None:
        raise HTTPException(400, "Set up your profile first.")
    data = await photo.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "Photo is too large (max 10 MB).")
    try:
        jpeg = vision.prepare_image(data)
    except vision.PhotoError as e:
        raise HTTPException(422, str(e))

    key = config.anthropic_key()  # read per request; never logged, stored or sent anywhere but api.anthropic.com
    if not key:
        result, analysis = vision.demo_estimate(), None  # no key configured: clearly-labelled demo value
    else:
        st = _state()
        context = {"goal": st["plan"]["goal"], "remaining_kcal": st["remaining_kcal"], "target_kcal": st["plan"]["target_kcal"],
                   "minor": st["profile"]["age"] < 18}
        identify, explain = rag.anthropic_functions(key)
        try:  # the model calls are blocking, so keep them off the event loop
            result = await run_in_threadpool(rag.analyze_meal, base64.b64encode(jpeg).decode(), context, identify, explain)
        except rag.PipelineError as e:
            raise HTTPException(e.status, e.message)
        except Exception as e:  # anything unexpected: log only the type, never the details
            print(f"[rag] analysis failed: {type(e).__name__}")
            raise HTTPException(502, "Couldn't analyze that photo right now. Enter calories by hand.")
        analysis = result
    if result["total_kcal"] > 0:
        items = [{"name": i["name"], "kcal": i["kcal"]} for i in result["items"]]
        db.add_meal(result["meal_name"], result["total_kcal"], items, "photo", analysis)
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


@app.get("/api/recipes/{recipe_id}")
def recipe(recipe_id: str):
    r = mealplan.get_recipe(recipe_id)
    if r is None:
        raise HTTPException(404, "Recipe not found.")
    return r


app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")
