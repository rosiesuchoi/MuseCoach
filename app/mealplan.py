"""Builds a 7-day meal plan from the recipes in data/recipes.json.

Recipes have fixed calories per serving, so instead of inventing numbers we scale the portion
(0.5x-2x) to hit each meal's share of the daily target.
"""

from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).parent / "data"
SHARES = {"breakfast": 0.25, "lunch": 0.35, "dinner": 0.30}  # the last 10% is for snacks
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def load_all() -> list[dict]:
    with open(DATA / "recipes.json", encoding="utf-8") as f:
        return json.load(f)["recipes"]


def get_recipe(recipe_id: str) -> dict | None:
    return next((r for r in load_all() if r["id"] == recipe_id), None)


def portion(budget_kcal: float, recipe_kcal: int) -> float:
    scaled = round(budget_kcal / recipe_kcal * 4) / 4  # nearest quarter serving
    return min(2.0, max(0.5, scaled))


def build_week(target_kcal: int) -> list[dict]:
    by_slot: dict[str, list[dict]] = {s: [] for s in SHARES}
    for r in load_all():
        by_slot[r["slot"]].append(r)
    week = []
    for i, day in enumerate(DAYS):
        meals = []
        for slot, share in SHARES.items():
            options = by_slot[slot]
            r = options[(i + len(slot)) % len(options)]  # rotate so days differ
            serv = portion(target_kcal * share, r["nutrition"]["kcal"])
            meals.append(
                {
                    "slot": slot,
                    "recipe_id": r["id"],
                    "name": r["name"],
                    "servings": serv,
                    "kcal": round(r["nutrition"]["kcal"] * serv),
                }
            )
        week.append({"day": day, "meals": meals, "snack_budget": round(target_kcal * 0.10)})
    return week
