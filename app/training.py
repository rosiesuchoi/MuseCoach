"""Builds the 7-day training week from data/workouts.json.

The user picks a training style; their activity level decides how many days are workouts (3, 4 or 5), and the other days get a
specific recovery routine. Check-offs are per calendar week (Monday start), so they reset every week.

The browser edition has the same logic in tools/pages/local-backend.js; tools/training_parity.mjs checks they match.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).parent / "data"
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


@lru_cache(maxsize=1)
def load() -> dict:
    return json.loads((DATA / "workouts.json").read_text(encoding="utf-8"))


def style_options() -> list[dict]:
    return [{"key": k, "name": s["name"], "tagline": s["tagline"], "equipment": s["equipment"]} for k, s in load()["styles"].items()]


def is_style(key: str) -> bool:
    return key in load()["styles"]


def week_start(today: date) -> date:
    return today - timedelta(days=today.weekday())  # Monday


def build_week(style_key: str, activity: str, done: set[str], today: date) -> dict:
    data = load()
    style = data["styles"][style_key]
    layout = data["layouts"].get(activity, data["layouts"]["medium"])
    start = week_start(today)
    days, recovery_i = [], 0
    for i, name in enumerate(DAYS):
        code = layout.get(name)
        if code:
            kind, body = "workout", style["days"][code]
        else:
            kind, code = "recovery", f"R{recovery_i % 2 + 1}"
            body, recovery_i = data["recovery"][code], recovery_i + 1
        days.append({
            "day": name, "date": (start + timedelta(days=i)).isoformat(), "kind": kind, "code": code,
            "title": body["title"], "focus": body["focus"], "minutes": body["minutes"], "warmup": body["warmup"],
            "exercises": body["exercises"], "cooldown": body["cooldown"], "metric": body["metric"], "done": name in done,
        })
    workouts = [d for d in days if d["kind"] == "workout"]
    done_workouts = sum(1 for d in workouts if d["done"])
    return {
        "style": style_key, "style_name": style["name"], "tagline": style["tagline"], "equipment": style["equipment"],
        "equipment_note": style["equipment_note"], "progression": style["progression"], "safety": data["safety"],
        "styles": style_options(), "week_start": start.isoformat(), "today": DAYS[today.weekday()], "days": days,
        "planned": len(workouts), "done_workouts": done_workouts, "all_done": done_workouts == len(workouts),
    }
