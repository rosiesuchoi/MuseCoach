import json
import re
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import training

DATA = Path(__file__).resolve().parent.parent / "app" / "data"
SAT = date(2026, 10, 17)  # a Saturday; its week starts Monday 2026-10-12


# ---------- the workout data itself ----------

def all_days(data):
    for key, style in data["styles"].items():
        for code, day in style["days"].items():
            yield f"{key}/{code}", day
    for code, day in data["recovery"].items():
        yield code, day


def test_every_exercise_has_a_measurable_prescription():
    data = training.load()
    exercises = 0
    for where, day in all_days(data):
        assert day["warmup"] and day["cooldown"] and day["metric"] and day["minutes"] > 0, where
        for e in day["exercises"]:
            exercises += 1
            assert re.search(r"\d", e["do"]), f"{where}: '{e['n']}' has no number in '{e['do']}'"
            assert e["rest"] and e["cue"] and e["n"], f"{where}: {e}"
    assert exercises > 100


def test_each_style_has_five_workouts_and_layouts_point_at_real_days():
    data = training.load()
    for key, style in data["styles"].items():
        assert set(style["days"]) == {"A", "B", "C", "D", "E"}, key
        assert style["name"] and style["progression"] and style["equipment_note"], key
    for activity, layout in data["layouts"].items():
        assert set(layout.values()) <= {"A", "B", "C", "D", "E"} and set(layout) <= set(training.DAYS)
    assert [len(data["layouts"][a]) for a in ("low", "medium", "high")] == [3, 4, 5]


def test_no_vague_filler_in_the_week():
    banned = re.compile(r"\b(dance class|long walk|anything fun)\b", re.I)
    for where, day in all_days(training.load()):
        text = json.dumps(day)
        assert not banned.search(text), where


def test_every_coach_default_is_a_real_style():
    coaches = json.loads((DATA / "coaches.json").read_text(encoding="utf-8"))
    for k, c in coaches.items():
        assert training.is_style(c["default_training"]), k
        assert "week" not in c, "the old vague weekly text should be gone"


# ---------- the weekly plan ----------

@pytest.mark.parametrize("activity,expected", [("low", 3), ("medium", 4), ("high", 5)])
def test_activity_level_sets_the_number_of_workout_days(activity, expected):
    for style in training.load()["styles"]:
        w = training.build_week(style, activity, set(), SAT)
        assert w["planned"] == expected and len(w["days"]) == 7
        assert [d["day"] for d in w["days"]] == training.DAYS


def test_week_dates_today_and_recovery_days():
    w = training.build_week("bodyweight", "medium", set(), SAT)
    assert w["week_start"] == "2026-10-12" and w["today"] == "Sat"
    assert [d["date"] for d in w["days"]][0] == "2026-10-12" and w["days"][6]["date"] == "2026-10-18"
    kinds = {d["day"]: d["kind"] for d in w["days"]}
    assert kinds == {"Mon": "workout", "Tue": "workout", "Wed": "recovery", "Thu": "workout", "Fri": "recovery", "Sat": "workout", "Sun": "recovery"}
    assert [d["code"] for d in w["days"] if d["kind"] == "recovery"] == ["R1", "R2", "R1"]


def test_done_flags_and_progress_count_only_workouts():
    w = training.build_week("boxing", "medium", {"Mon", "Wed", "Tue"}, SAT)  # Wed is a recovery day
    assert w["done_workouts"] == 2 and not w["all_done"]
    w = training.build_week("boxing", "medium", {"Mon", "Tue", "Thu", "Sat"}, SAT)
    assert w["all_done"] and w["done_workouts"] == 4


def test_week_starts_on_monday_even_on_a_sunday():
    assert training.week_start(date(2026, 10, 18)) == date(2026, 10, 12)
    assert training.week_start(date(2026, 10, 12)) == date(2026, 10, 12)


# ---------- the API ----------

PROFILE = dict(age=25, sex="female", height_cm=165, weight_kg=60, goal="maintain", activity="medium", celebrity="Jennie (BLACKPINK)")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MUSE_DB", str(tmp_path / "t.db"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from app import main

    class FakeDate(date):
        @classmethod
        def today(cls):
            return SAT

    monkeypatch.setattr(main, "date", FakeDate)
    return TestClient(main.app)


def test_default_style_follows_the_coach_and_can_be_changed(client):
    s = client.put("/api/profile", json=PROFILE).json()
    assert s["training"]["style"] == "cardio_core"  # Coach Rhea's default (no dancing)
    s = client.put("/api/training", json={"style": "boxing"}).json()
    assert s["training"]["style"] == "boxing" and s["profile"]["training"] == "boxing"
    s = client.put("/api/training", json={"style": ""}).json()  # back to the coach's default
    assert s["training"]["style"] == "cardio_core"
    assert client.put("/api/training", json={"style": "dance_party"}).status_code == 422


def test_saving_the_profile_form_keeps_the_chosen_training_style(client):
    client.put("/api/profile", json=PROFILE)
    client.put("/api/training", json={"style": "bodyweight"})
    s = client.put("/api/profile", json={**PROFILE, "weight_kg": 58}).json()  # the form doesn't send `training`
    assert s["training"]["style"] == "bodyweight"


def test_checking_off_days_is_saved_and_can_be_undone(client):
    client.put("/api/profile", json=PROFILE)
    s = client.post("/api/workouts/check", json={"day": "Mon", "done": True}).json()
    assert [d["done"] for d in s["training"]["days"]][:2] == [True, False] and s["training"]["done_workouts"] == 1
    s = client.post("/api/workouts/check", json={"day": "Mon", "done": True}).json()  # idempotent
    assert s["training"]["done_workouts"] == 1
    assert client.get("/api/state").json()["training"]["days"][0]["done"] is True  # persisted
    s = client.post("/api/workouts/check", json={"day": "Mon", "done": False}).json()
    assert s["training"]["done_workouts"] == 0
    assert client.post("/api/workouts/check", json={"day": "Funday", "done": True}).status_code == 422


def test_checks_reset_each_week(client, monkeypatch):
    from app import main

    client.put("/api/profile", json=PROFILE)
    client.post("/api/workouts/check", json={"day": "Mon", "done": True})

    class NextWeek(date):
        @classmethod
        def today(cls):
            return date(2026, 10, 20)  # the following Tuesday

    monkeypatch.setattr(main, "date", NextWeek)
    assert client.get("/api/state").json()["training"]["done_workouts"] == 0


def test_training_endpoints_need_a_profile(client):
    assert client.put("/api/training", json={"style": "boxing"}).status_code == 400
    assert client.post("/api/workouts/check", json={"day": "Mon", "done": True}).status_code == 400
