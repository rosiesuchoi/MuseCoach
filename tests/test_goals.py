import pytest

from app.goals import Profile, ProfileError, build_plan, min_goal_weight


def make(**kw):
    base = dict(age=25, sex="female", height_cm=165, weight_kg=60, goal="lose", activity="medium")
    base.update(kw)
    return Profile(**base)


def test_lose_creates_deficit_and_respects_floor():
    plan = build_plan(make(), "lean_dancer")
    assert plan["target_kcal"] < plan["maintenance_kcal"]
    assert plan["target_kcal"] >= 1200
    assert plan["weekly_change_kg"] < 0


def test_goal_weight_clamped_to_healthy_bmi():
    p = make(goal_weight_kg=40)
    plan = build_plan(p, "lean_dancer")
    assert plan["goal_weight_kg"] == round(min_goal_weight(165), 1)
    assert any("lowest healthy weight" in n for n in plan["notes"])


def test_already_lean_switches_to_maintain():
    plan = build_plan(make(weight_kg=50.5), "lean_dancer")  # BMI ~18.5
    assert plan["goal"] == "maintain"
    assert plan["weekly_change_kg"] == 0


def test_minor_never_gets_a_deficit():
    plan = build_plan(make(age=16), "lean_dancer")
    assert plan["goal"] == "maintain"
    assert plan["target_kcal"] == plan["maintenance_kcal"]


def test_calorie_floor_for_small_sedentary_user():
    plan = build_plan(make(age=70, height_cm=150, weight_kg=48, activity="low", goal_weight_kg=45), "athletic")
    assert plan["target_kcal"] >= 1200


def test_build_adds_surplus():
    plan = build_plan(make(goal="build"), "sculpted")
    assert plan["target_kcal"] > plan["maintenance_kcal"]


def test_validation_rejects_bad_input():
    with pytest.raises(ProfileError):
        build_plan(make(age=9), "athletic")
    with pytest.raises(ProfileError):
        build_plan(make(sex="x"), "athletic")
