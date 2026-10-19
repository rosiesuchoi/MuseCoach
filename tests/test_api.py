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
               goal_weight_kg=55, celebrity="Jennie (BLACKPINK)")


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
    ids = {m["recipe_id"] for d in plan["week"] for m in d["meals"]}
    assert len(ids) >= 6
    for rid in ids:  # every planned meal opens a full in-app recipe, no external link needed
        r = client.get(f"/api/recipes/{rid}").json()
        assert r["ingredients"] and r["steps"] and r["nutrition"]["kcal"] > 0
        if r["source"]["license"] == "CC BY-SA 4.0":  # Wikibooks recipes keep their attribution; the rest are original to this app
            assert r["source"]["url"].startswith("https://en.wikibooks.org/")
        else:
            assert r["source"]["license"] == "original"
    assert client.get("/api/recipes/nope").status_code == 404


def test_style_picked_for_unlisted_celebrity(client):
    r = client.put("/api/profile", json={**PROFILE, "celebrity": "Gong Yoo", "style": "strong"}).json()
    assert r["archetype"] == "strong"
    assert r["coach"]["coach"] == "Coach Bram"


def test_listed_celebrity_ignores_style(client):
    r = client.put("/api/profile", json={**PROFILE, "style": "strong"}).json()
    assert r["archetype"] == "lean_dancer"


def test_options_have_wiki_titles_and_styles(client):
    o = client.get("/api/options").json()
    assert all(c["wiki"] for c in o["celebrities"])
    assert {s["key"] for s in o["styles"]} == {"lean_dancer", "sculpted", "athletic", "strong"}


def test_edit_meal(client):
    client.put("/api/profile", json=PROFILE)
    s = client.post("/api/meals", json={"name": "Pizza", "kcal": 570}).json()
    mid = s["meals"][0]["id"]
    s = client.patch(f"/api/meals/{mid}", json={"name": "1 slice of pizza", "kcal": 285}).json()
    assert s["eaten_kcal"] == 285 and s["meals"][0]["name"] == "1 slice of pizza"
    assert client.patch("/api/meals/9999", json={"name": "x", "kcal": 1}).status_code == 404
    assert client.patch(f"/api/meals/{mid}", json={"name": "x", "kcal": 99999}).status_code == 422
