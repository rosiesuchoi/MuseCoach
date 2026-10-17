"""Coach persona lookup and the daily check-in message, written in each persona's voice."""

from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).parent / "data"


def _load(name: str) -> dict:
    with open(DATA / name, encoding="utf-8") as f:
        return json.load(f)


def celebrity_options() -> list[dict]:
    return [{"name": c["name"], "wiki": c["wiki"]} for c in _load("celebrities.json")["celebrities"]]


def style_options() -> list[dict]:
    return [{"key": k, "coach": v["coach"], "tagline": v["tagline"]} for k, v in _load("coaches.json").items()]


def archetype_for(celebrity: str, style: str = "") -> str:
    """Listed celebrities have a fixed archetype. For anyone else (typed in and found on Wikipedia)
    the user picks a coach style; with no pick they get the all-round coach."""
    cfg = _load("celebrities.json")
    wanted = celebrity.strip().lower()
    for c in cfg["celebrities"]:
        if c["name"].lower() == wanted:
            return c["archetype"]
    return style if style in _load("coaches.json") else cfg["default_archetype"]


def coach_for(archetype: str) -> dict:
    return _load("coaches.json")[archetype]


OPENERS = {
    "lean_dancer": "Okay, from the top!",
    "sculpted": "Here's today's read.",
    "athletic": "Team check-in!",
    "strong": "Listen up.",
}


def checkin(archetype: str, goal: str, eaten: int, target: int) -> str:
    coach = coach_for(archetype)["coach"]
    opener = OPENERS.get(archetype, "Check-in!")
    remaining = target - eaten
    if eaten == 0:
        body = f"Nothing logged yet. Snap a photo of your first meal and I'll do the math. Today's target: {target} calories."
    elif remaining > target * 0.15:
        body = f"{eaten} calories in, {remaining} to go. You're on pace. Keep protein in every meal."
    elif remaining >= -target * 0.05:
        body = f"{eaten} calories in, right on target. That's exactly the plan."
    else:
        body = f"{eaten} calories in, about {-remaining} over. No stress: one day doesn't undo a week. Tomorrow we reset."
    return f"{coach}: {opener} {body}"
