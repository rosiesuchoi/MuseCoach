"""Builds a 7-day meal plan from the verified recipes in data/meals.json.

Recipes have fixed calories, so instead of inventing numbers we scale the portion
(0.5x-2x) to hit each meal's share of the daily target.
"""

from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).parent / "data"
SHARES = {"breakfast": 0.25, "lunch": 0.35, "dinner": 0.30}  # the last 10% is for snacks
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def load_recipes() -> dict:
    with open(DATA / "meals.json", encoding="utf-8") as f:
        raw = json.load(f)
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def portion(budget_kcal: float, recipe_kcal: int) -> float:
    scaled = round(budget_kcal / recipe_kcal * 4) / 4  # nearest quarter serving
    return min(2.0, max(0.5, scaled))


def build_week(target_kcal: int) -> list[dict]:
    recipes = load_recipes()
    week = []
    for i, day in enumerate(DAYS):
        meals = []
        for slot, share in SHARES.items():
            options = recipes[slot]
            r = options[(i + len(slot)) % len(options)]  # rotate so days differ
            serv = portion(target_kcal * share, r["kcal"])
            meals.append(
                {
                    "slot": slot,
                    "name": r["name"],
                    "source": r["source"],
                    "url": r["url"],
                    "servings": serv,
                    "kcal": round(r["kcal"] * serv),
                }
            )
        week.append({"day": day, "meals": meals, "snack_budget": round(target_kcal * 0.10)})
    return week
