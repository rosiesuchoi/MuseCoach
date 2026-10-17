"""Calorie and goal math. Pure functions, no I/O, so the safety rules are easy to test.

Why this file matters: the app lets people pick a celebrity as a "style target". The celebrity
only picks a coach persona and training style. The numbers come from the user's own body and
are clamped to healthy limits here, so no goal can ask for an unsafe target.
"""

from __future__ import annotations

from dataclasses import dataclass

ACTIVITY_FACTORS = {
    "low": 1.375,  # desk job, light workouts 1-3x/week
    "medium": 1.55,  # workouts 3-5x/week
    "high": 1.725,  # hard training 6-7x/week
}

MIN_BMI = 18.5  # goal weight is never allowed below this
MAX_DEFICIT_FRACTION = 0.25  # never cut more than 25% of maintenance
KCAL_PER_KG = 7700
LB_PER_KG = 2.2046226  # the API and storage are metric; messages shown to users are in lb
FLOOR_KCAL = {"female": 1200, "male": 1500}
SURPLUS_KCAL = 250  # gentle surplus for "build"

# archetype -> (protein, carb, fat) share of calories
MACROS = {
    "lean_dancer": (0.28, 0.45, 0.27),
    "sculpted": (0.32, 0.40, 0.28),
    "athletic": (0.28, 0.45, 0.27),
    "strong": (0.30, 0.40, 0.30),
}


@dataclass
class Profile:
    age: int
    sex: str  # "female" | "male"
    height_cm: float
    weight_kg: float
    goal: str  # "lose" | "maintain" | "build"
    activity: str  # "low" | "medium" | "high"
    goal_weight_kg: float | None = None
    celebrity: str = ""


class ProfileError(ValueError):
    pass


def validate(p: Profile) -> None:
    if not 13 <= p.age <= 100:
        raise ProfileError("Age must be between 13 and 100.")
    if p.sex not in FLOOR_KCAL:
        raise ProfileError("Sex must be 'female' or 'male' (used only for the calorie formula).")
    if not 120 <= p.height_cm <= 230:
        raise ProfileError("Height must be between 3 ft 11 in and 7 ft 7 in.")
    if not 30 <= p.weight_kg <= 300:
        raise ProfileError("Weight must be between 66 and 661 lb.")
    if p.goal not in ("lose", "maintain", "build"):
        raise ProfileError("Goal must be lose, maintain or build.")
    if p.activity not in ACTIVITY_FACTORS:
        raise ProfileError("Activity must be low, medium or high.")


def bmi(weight_kg: float, height_cm: float) -> float:
    m = height_cm / 100
    return weight_kg / (m * m)


def bmr(p: Profile) -> float:
    """Mifflin-St Jeor."""
    base = 10 * p.weight_kg + 6.25 * p.height_cm - 5 * p.age
    return base + (5 if p.sex == "male" else -161)


def min_goal_weight(height_cm: float) -> float:
    m = height_cm / 100
    return MIN_BMI * m * m


def build_plan(p: Profile, archetype: str) -> dict:
    """Return targets plus plain-language notes about any safety clamps that were applied."""
    validate(p)
    notes: list[str] = []
    maintenance = bmr(p) * ACTIVITY_FACTORS[p.activity]
    goal = p.goal

    # Under 18: no dieting, just fuel growth. Easy to remove from the app, hard to talk it out.
    if p.age < 18 and goal == "lose":
        goal = "maintain"
        notes.append("Under 18, so this plan keeps you at maintenance. Talk to a doctor before dieting.")

    floor_weight = min_goal_weight(p.height_cm)
    goal_weight = p.goal_weight_kg
    if goal == "lose":
        if bmi(p.weight_kg, p.height_cm) <= MIN_BMI + 0.3:
            goal = "maintain"
            notes.append("You're already at the low end of a healthy weight, so we're maintaining.")
        elif goal_weight is not None and goal_weight < floor_weight:
            goal_weight = round(floor_weight, 1)
            notes.append(
                f"Goal weight raised to {round(goal_weight * LB_PER_KG)} lb: the lowest healthy weight for your height."
            )

    if goal == "lose":
        deficit = min(500, maintenance * MAX_DEFICIT_FRACTION)
        target = maintenance - deficit
        floor = FLOOR_KCAL[p.sex]
        if target < floor:
            target = floor
            deficit = max(maintenance - floor, 0)
            notes.append(f"Calories held at {floor}, the minimum this app will ever recommend.")
        weekly_change = -deficit * 7 / KCAL_PER_KG
    elif goal == "build":
        target = maintenance + SURPLUS_KCAL
        weekly_change = SURPLUS_KCAL * 7 / KCAL_PER_KG
    else:
        target = maintenance
        weekly_change = 0.0

    protein_share, carb_share, fat_share = MACROS.get(archetype, MACROS["athletic"])
    weeks = None
    if goal_weight is not None and weekly_change:
        remaining = goal_weight - p.weight_kg
        if remaining * weekly_change > 0:
            weeks = round(abs(remaining / weekly_change))

    return {
        "goal": goal,
        "maintenance_kcal": round(maintenance),
        "target_kcal": round(target),
        "protein_g": round(target * protein_share / 4),
        "carbs_g": round(target * carb_share / 4),
        "fat_g": round(target * fat_share / 9),
        "weekly_change_kg": round(weekly_change, 2),
        "goal_weight_kg": goal_weight,
        "weeks_to_goal": weeks,
        "bmi": round(bmi(p.weight_kg, p.height_cm), 1),
        "notes": notes,
    }
