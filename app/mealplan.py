"""The weekly meal plan service: builds a varied plan that respects the user's diet and allergies, saves it in the database, and prices it.

A plan is saved per calendar week, so it doesn't change every time the app is opened. It is rebuilt when the diet or calorie target changes,
and the user can ask for a different one ("shuffle"). Older weeks stay in the database as history.
"""

from __future__ import annotations

from datetime import date

from . import db, diet, training


def _slot_counts(recipes: list[dict], diet_profile: dict) -> dict:
    return {slot: sum(1 for r in recipes if r["slot"] == slot and diet.eligible(r, diet_profile)) for slot, _ in diet.SLOTS}


def get_plan(target_kcal: int, diet_profile: dict, today: date, reshuffle: bool = False) -> dict:
    week = training.week_start(today).isoformat()
    sig = f"{diet.signature(diet_profile)}|{target_kcal}"
    recipes = db.get_recipes()
    saved = db.get_plan(week)
    shuffle = (saved["shuffle"] if saved else 0) + (1 if reshuffle else 0)
    if saved is None or saved["sig"] != sig or reshuffle:
        built = diet.build_week(recipes, target_kcal, diet.seed_for(week, shuffle), diet_profile)
        db.save_plan(week, shuffle, sig, target_kcal, built)
        saved = db.get_plan(week)
    catalog, overrides = db.get_catalog(), db.get_overrides()
    by_id = {r["id"]: r for r in recipes}
    for d in saved["days"]:
        for m in d["meals"]:
            m["cost_cents"] = diet.js_round(diet.recipe_cost_cents(by_id[m["recipe_id"]], catalog, overrides) * m["servings"])
    return {
        "week_start": week, "shuffle": saved["shuffle"], "target_kcal": target_kcal, "notes": saved["notes"], "week": saved["days"],
        "eligible": _slot_counts(recipes, diet_profile), "diet": {"profile": diet.normalize(diet_profile), "summary": diet.summary(diet_profile)},
    }


def grocery_for(plan: dict) -> dict:
    recipes = {r["id"]: r for r in db.get_recipes()}
    meals = [{"recipe_id": m["recipe_id"], "servings": m["servings"]} for d in plan["week"] for m in d["meals"]]
    result = diet.grocery(meals, recipes, db.get_catalog(), db.get_overrides())
    result["week_start"] = plan["week_start"]
    result["meals"] = len(meals)
    result["prices"] = {"as_of": "2026-09", "source": "US Bureau of Labor Statistics average retail prices (Sep 2026) where marked; other prices are typical-store estimates. Edit any price to match your store."}
    return result


def recipe_with_cost(recipe_id: str) -> dict | None:
    r = db.get_recipe(recipe_id)
    if r is None:
        return None
    r["cost_cents_per_serving"] = diet.js_round(diet.recipe_cost_cents(r, db.get_catalog(), db.get_overrides()))
    return r
