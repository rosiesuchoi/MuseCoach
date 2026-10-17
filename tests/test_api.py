import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import vision


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MUSE_DB", str(tmp_path / "t.db"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from app.main import app

    return TestClient(app)


PROFILE = dict(age=25, sex="female", height_cm=165, weight_kg=60, goal="lose", activity="medium",
               goal_weight_kg=55, celebrity="Lisa (BLACKPINK)")


def jpeg_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), "red").save(buf, "JPEG")
    return buf.getvalue()


def test_no_profile_state_is_empty(client):
    assert client.get("/api/state").json() == {"profile": None}


def test_profile_picks_persona_and_plan(client):
    r = client.put("/api/profile", json=PROFILE).json()
    assert r["coach"]["coach"] == "Coach Rhea"
    assert r["plan"]["target_kcal"] >= 1200


def test_unknown_celebrity_gets_default_coach(client):
    r = client.put("/api/profile", json={**PROFILE, "celebrity": "Somebody New"}).json()
    assert r["archetype"] == "athletic"


def test_bad_profile_rejected(client):
    assert client.put("/api/profile", json={**PROFILE, "age": 5}).status_code == 422


def test_photo_demo_logs_meal(client):
    client.put("/api/profile", json=PROFILE)
    r = client.post("/api/meals/photo", files={"photo": ("a.jpg", jpeg_bytes(), "image/jpeg")}).json()
    assert r["estimate"]["demo"] is True
    assert r["eaten_kcal"] == 500


def test_bad_photo_is_422(client):
    client.put("/api/profile", json=PROFILE)
    r = client.post("/api/meals/photo", files={"photo": ("a.jpg", b"not an image", "image/jpeg")})
    assert r.status_code == 422


def test_manual_meal_and_delete(client):
    client.put("/api/profile", json=PROFILE)
    s = client.post("/api/meals", json={"name": "Toast", "kcal": 200}).json()
    assert s["eaten_kcal"] == 200
    s = client.delete(f"/api/meals/{s['meals'][0]['id']}").json()
    assert s["eaten_kcal"] == 0


def test_mealplan_has_seven_days_with_links(client):
    client.put("/api/profile", json=PROFILE)
    plan = client.get("/api/mealplan").json()
    assert len(plan["week"]) == 7
    assert all(m["url"].startswith("https://") for d in plan["week"] for m in d["meals"])


def test_vision_rejects_absurd_estimate():
    with pytest.raises(vision.PhotoError):
        vision.parse_reply(json.dumps({"meal_name": "x", "items": [], "total_kcal": 99999}))
