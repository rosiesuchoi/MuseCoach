"""Diet filtering, the varied meal plan, saved plans in the database, the grocery list and its prices."""

import json
import re
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import db, diet

DATA = Path(__file__).resolve().parent.parent / "app" / "data"
RECIPES = json.loads((DATA / "recipes.json").read_text(encoding="utf-8"))["recipes"]
CATALOG = json.loads((DATA / "ingredients.json").read_text(encoding="utf-8"))["items"]
KB_IDS = {f[0] for f in json.loads((DATA / "nutrition.json").read_text(encoding="utf-8"))["foods"]}
BY_ID = {r["id"]: r for r in RECIPES}
SAT = date(2026, 10, 17)

DIETS = {
    "none": {}, "vegetarian": {"pattern": "vegetarian"}, "vegan": {"pattern": "vegan"}, "pescatarian": {"pattern": "pescatarian"},
    "gluten_free": {"gluten_free": True}, "dairy_free": {"allergens": ["milk"]}, "peanut_free": {"allergens": ["peanut"]},
    "tree_nut_free": {"allergens": ["tree_nut"]}, "soy_free": {"allergens": ["soy"]}, "no_fish": {"allergens": ["fish", "shellfish"]},
    "vegan_gf": {"pattern": "vegan", "gluten_free": True}, "avoid_mushroom": {"avoid": ["mushroom"]},
}


# ---------- the data itself ----------

def test_catalog_and_recipes_are_consistent():
    assert len(CATALOG) >= 90 and len(RECIPES) >= 60
    for k, it in CATALOG.items():
        assert it["fdc"] in KB_IDS, f"{k}: USDA id {it['fdc']} not in the nutrition data"
        assert it["pack"]["g"] > 0 and it["pack"]["price"] > 0 and it["pack"]["src"] in ("bls", "bls-derived", "estimate"), k
        assert set(it["allergens"]) <= set(diet.ALLERGENS) | {"gluten"} and set(it["contains"]) <= {"meat", "poultry", "honey"}, k
    ids = [r["id"] for r in RECIPES]
    assert len(ids) == len(set(ids))
    for r in RECIPES:
        assert r["slot"] in ("breakfast", "lunch", "dinner") and len(r["steps"]) >= 2 and r["nutrition"]["kcal"] >= 50, r["id"]
        items = [ln["item"] for ln in r["lines"]]
        assert len(items) == len(set(items)) and all(i in CATALOG for i in items), r["id"]
        assert r["servings"] >= 1 and r["minutes"] > 0 and r["cuisine"], r["id"]


def test_each_meal_has_real_variety():
    counts = {s: sum(1 for r in RECIPES if r["slot"] == s) for s in ("breakfast", "lunch", "dinner")}
    assert all(c >= 15 for c in counts.values()), counts
    assert len({r["cuisine"] for r in RECIPES}) >= 8


def test_catalog_tags_match_what_the_food_is():
    expect = {"egg": {"egg"}, "soy_sauce": {"soy", "wheat", "gluten"}, "peanut_butter": {"peanut"}, "hummus": {"sesame"}, "shrimp": {"shellfish"}, "salmon_fillet": {"fish"},
              "butter": {"milk"}, "almonds": {"tree_nut"}, "tofu_firm": {"soy"}, "pasta_spaghetti": {"wheat", "gluten"}, "oats_rolled": {"gluten"}, "mayonnaise": {"egg"}}
    for item, allergens in expect.items():
        assert allergens <= set(CATALOG[item]["allergens"]), item
    assert CATALOG["honey"]["contains"] == ["honey"] and "poultry" in CATALOG["chicken_breast"]["contains"] and "meat" in CATALOG["ground_beef"]["contains"]


def test_allergen_tags_cover_every_allergen_word_in_the_ingredient_text():
    """Safety lint: if the ingredient text names an allergen food, the recipe must carry that allergen tag."""
    words = {"milk": r"(milk|cheese|yogurt|butter|cream|parmesan|mozzarella|feta|cheddar)", "egg": r"egg", "peanut": r"peanut", "tree_nut": r"(almond|walnut)",
             "soy": r"(tofu|soy)", "fish": r"(salmon|tuna|cod)", "shellfish": r"shrimp", "wheat": r"(flour|bread|spaghetti|pasta|noodles|wheat)", "sesame": r"hummus|sesame"}
    for r in RECIPES:
        text = " ".join(t for g in r["ingredients"] for t in g["items"]).lower()
        text = text.replace("almond milk", "").replace("peanut butter", "peanut")  # plant 'milk' and nut 'butter' are not dairy
        for allergen, pattern in words.items():
            if re.search(pattern, text):
                assert allergen in r["allergens"], f"{r['id']}: text mentions {allergen} but tags are {r['allergens']}"


# ---------- the diet profile and filtering ----------

def test_normalize_cleans_up_input():
    d = diet.normalize({"allergens": ["milk", "bogus", "milk", "peanut"], "pattern": "carnivore", "gluten_free": "yes", "avoid": ["  Mushrooms ", "mushrooms", "", "BELL   pepper"]})
    assert d == {"allergens": ["milk", "peanut"], "pattern": "none", "gluten_free": False, "avoid": ["mushrooms", "bell pepper"]}
    assert diet.normalize(None) == {"allergens": [], "pattern": "none", "gluten_free": False, "avoid": []}


def test_diet_patterns_exclude_the_right_foods():
    def ok(recipe_id, d):
        return diet.eligible(BY_ID[recipe_id], d)

    assert ok("sheet-pan-salmon", {"pattern": "pescatarian"}) and not ok("sheet-pan-salmon", {"pattern": "vegetarian"})
    assert not ok("turkey-chili", {"pattern": "pescatarian"}) and not ok("pork-chops-sweet-potato", {"pattern": "pescatarian"})
    assert ok("tofu-scramble", {"pattern": "vegan"}) and not ok("veggie-egg-muffins", {"pattern": "vegan"}) and ok("veggie-egg-muffins", {"pattern": "vegetarian"})
    assert not ok("granola", {"pattern": "vegan"})  # honey
    assert not ok("berry-walnut-oatmeal", {"gluten_free": True})  # oats can carry gluten
    assert ok("quinoa-black-bean-bowl", {"gluten_free": True}) and not ok("minestrone-soup", {"allergens": ["wheat"]})
    assert not ok("quinoa-black-bean-bowl", {"avoid": ["avocado"]})


def test_every_diet_plan_only_contains_eligible_recipes():
    for name, d in DIETS.items():
        plan = diet.build_week(RECIPES, 1800, 12345, d)
        for day in plan["days"]:
            for m in day["meals"]:
                assert diet.eligible(BY_ID[m["recipe_id"]], d), f"{name}: {m['recipe_id']} breaks the diet"


# ---------- the varied weekly plan ----------

def test_a_flexible_diet_gets_no_repeats_all_week():
    for name in ("none", "vegetarian", "vegan", "gluten_free", "dairy_free", "peanut_free", "soy_free"):
        plan = diet.build_week(RECIPES, 2000, 777, DIETS[name])
        for slot, _ in diet.SLOTS:
            ids = [m["recipe_id"] for d in plan["days"] for m in d["meals"] if m["slot"] == slot]
            assert len(ids) == 7 and len(set(ids)) == 7, f"{name}/{slot} repeats: {ids}"
        assert plan["notes"] == [], name


def test_a_strict_diet_repeats_and_says_so():
    d = DIETS["vegan_gf"]
    plan = diet.build_week(RECIPES, 2000, 5, d)
    assert any("Only 4 dinner recipes" in n and "repeat" in n for n in plan["notes"])
    dinners = [m["recipe_id"] for day in plan["days"] for m in day["meals"] if m["slot"] == "dinner"]
    assert len(dinners) == 7 and len(set(dinners)) == 4
    # repeats are spread out, never the same dinner two days in a row
    assert all(a != b for a, b in zip(dinners, dinners[1:]))


def test_an_impossible_diet_leaves_that_meal_out_with_a_note():
    d = {"pattern": "vegan", "allergens": ["soy", "tree_nut", "peanut"], "avoid": ["bean", "chickpea", "lentil", "quinoa", "oat", "banana", "pasta", "spaghetti"]}
    plan = diet.build_week(RECIPES, 2000, 1, d)
    assert plan["counts"]["breakfast"] == 0 or any("left out" in n for n in plan["notes"]) or all(plan["counts"].values())
    empty = [s for s, c in plan["counts"].items() if c == 0]
    for s in empty:
        assert any(f"No {s} recipes" in n for n in plan["notes"])
        assert not any(m["slot"] == s for day in plan["days"] for m in day["meals"])


def test_same_seed_same_plan_and_a_new_seed_changes_it():
    a = diet.build_week(RECIPES, 1800, diet.seed_for("2026-10-12", 0), {})
    b = diet.build_week(RECIPES, 1800, diet.seed_for("2026-10-12", 0), {})
    c = diet.build_week(RECIPES, 1800, diet.seed_for("2026-10-12", 1), {})
    ids = lambda p: [m["recipe_id"] for d in p["days"] for m in d["meals"]]  # noqa: E731
    assert ids(a) == ids(b) and ids(a) != ids(c)
    assert diet.seed_for("2026-10-12", 0) != diet.seed_for("2026-10-19", 0)


def test_meals_are_sized_to_hit_the_calorie_target():
    for target in (1300, 1800, 2400, 3000):
        plan = diet.build_week(RECIPES, target, 99, {})
        for day in plan["days"]:
            assert all(0.5 <= m["servings"] <= 2.0 for m in day["meals"])
        avg = sum(sum(m["kcal"] for m in d["meals"]) for d in plan["days"]) / 7
        assert 0.75 * 0.9 * target <= avg <= 1.2 * 0.9 * target, (target, avg)  # 90% of the day is meals, 10% is left for snacks


def test_seeded_random_numbers_are_stable():
    r = diet.mulberry32(1)
    first = [r() for _ in range(3)]
    assert first == [diet.mulberry32(1)() for _ in range(1)] + first[1:]
    assert all(0 <= x < 1 for x in first) and len(set(first)) == 3
    assert diet.shuffled(list(range(8)), diet.mulberry32(42)) == diet.shuffled(list(range(8)), diet.mulberry32(42))
    assert sorted(diet.shuffled(list(range(8)), diet.mulberry32(7))) == list(range(8))


# ---------- prices and the grocery list ----------

def test_amount_text_reads_naturally():
    egg, tomato = CATALOG["egg"]["each"], CATALOG["tomato"]["each"]
    assert diet.amount_text(150, egg) == "3 egg" + "s" and diet.amount_text(50, egg) == "1 egg"
    assert diet.amount_text(300, tomato) == "2 tomatoes"
    assert diet.amount_text(600, None) == "1.3 lb" and diet.amount_text(100, None) == "4 oz" and diet.amount_text(9, None) == "9 g"


def test_grocery_rounds_up_to_packs_and_prices_in_cents():
    meals = [{"recipe_id": "scrambled-eggs", "servings": 1}, {"recipe_id": "veggie-egg-muffins", "servings": 2}]
    g = diet.grocery(meals, BY_ID, CATALOG, {})
    eggs = next(ln for ln in g["lines"] if ln["item"] == "egg")
    need = 150 / 1 * 1 + 400 / 4 * 2  # grams: 3 eggs + 4 eggs' worth
    assert eggs["need_g"] == need and eggs["packs"] == 1 and eggs["pack_label"] == "1 dozen" and eggs["line_cents"] == 227 and eggs["official"] is True
    assert eggs["used_cents"] == round(227 * need / 600)
    assert g["totals"]["to_buy_cents"] == sum(ln["line_cents"] for ln in g["lines"]) and g["totals"]["items"] == len(g["lines"])
    assert g["totals"]["official_items"] + g["totals"]["estimated_items"] + g["totals"]["your_items"] == g["totals"]["items"]
    assert g["totals"]["without_staples_cents"] == g["totals"]["to_buy_cents"] - g["totals"]["staples_cents"]


def test_buying_more_means_more_packs():
    one = diet.grocery([{"recipe_id": "egg-fried-rice", "servings": 1}], BY_ID, CATALOG, {})
    many = diet.grocery([{"recipe_id": "egg-fried-rice", "servings": 2}] * 12, BY_ID, CATALOG, {})  # 12 x 2 servings = 1200 g of rice, more than one 2 lb bag
    rice1 = next(ln for ln in one["lines"] if ln["item"] == "rice_white")
    rice6 = next(ln for ln in many["lines"] if ln["item"] == "rice_white")
    assert rice1["packs"] == 1 and rice6["packs"] > 1 and rice6["line_cents"] == rice6["packs"] * rice6["pack_cents"]


def test_a_user_price_overrides_the_default_everywhere():
    meals = [{"recipe_id": "scrambled-eggs", "servings": 1}]
    base = diet.grocery(meals, BY_ID, CATALOG, {})
    custom = diet.grocery(meals, BY_ID, CATALOG, {"egg": 5.00})
    e = next(ln for ln in custom["lines"] if ln["item"] == "egg")
    assert e["pack_cents"] == 500 and e["src"] == "you" and e["official"] is False and custom["totals"]["your_items"] == 1
    assert custom["totals"]["to_buy_cents"] == base["totals"]["to_buy_cents"] - 227 + 500
    assert diet.recipe_cost_cents(BY_ID["scrambled-eggs"], CATALOG, {"egg": 5.0}) > diet.recipe_cost_cents(BY_ID["scrambled-eggs"], CATALOG, {})


def test_a_full_week_grocery_total_is_plausible_for_one_person():
    plan = diet.build_week(RECIPES, 2000, 3, {})
    meals = [{"recipe_id": m["recipe_id"], "servings": m["servings"]} for d in plan["days"] for m in d["meals"]]
    t = diet.grocery(meals, BY_ID, CATALOG, {})["totals"]
    assert 4000 <= t["to_buy_cents"] <= 40000  # $40-$400 including pantry staples; a sanity band, not a promise
    assert t["used_cents"] < t["to_buy_cents"]  # you buy whole packs but eat part of them


# ---------- the database and API ----------

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


PROFILE = dict(age=25, sex="female", height_cm=165, weight_kg=60, goal="maintain", activity="medium", celebrity="Jennie (BLACKPINK)")


def meal_ids(plan):
    return [m["recipe_id"] for d in plan["week"] for m in d["meals"]]


def test_reference_data_is_loaded_into_the_database(client):
    client.put("/api/profile", json=PROFILE)
    assert len(db.get_recipes()) == len(RECIPES) and len(db.get_catalog()) == len(CATALOG)
    assert db.get_recipe("turkey-chili")["name"] == BY_ID["turkey-chili"]["name"] and db.get_catalog()["egg"]["each"]["g"] == 50


def test_diet_is_saved_and_shapes_the_plan(client):
    client.put("/api/profile", json=PROFILE)
    s = client.put("/api/diet", json={"allergens": ["peanut", "bogus"], "pattern": "vegetarian", "gluten_free": True, "avoid": ["mushroom"]}).json()
    assert s["diet"]["profile"] == {"allergens": ["peanut"], "pattern": "vegetarian", "gluten_free": True, "avoid": ["mushroom"]}
    assert s["diet"]["summary"] == ["Vegetarian", "Gluten-free", "No peanut", "No mushroom"]
    plan = client.get("/api/mealplan").json()
    for rid in meal_ids(plan):
        assert diet.eligible(BY_ID[rid], s["diet"]["profile"])
    assert plan["diet"]["summary"] == s["diet"]["summary"]
    assert plan["eligible"] == {slot: sum(1 for r in RECIPES if r["slot"] == slot and diet.eligible(r, s["diet"]["profile"])) for slot in ("breakfast", "lunch", "dinner")}


def test_the_plan_is_saved_for_the_week_and_rebuilt_when_the_diet_changes(client):
    client.put("/api/profile", json=PROFILE)
    first = client.get("/api/mealplan").json()
    assert first["week_start"] == "2026-10-12" and meal_ids(client.get("/api/mealplan").json()) == meal_ids(first)  # stable between visits
    assert len(db.list_plans()) == 1
    client.put("/api/diet", json={"pattern": "vegan"})
    vegan = client.get("/api/mealplan").json()
    assert meal_ids(vegan) != meal_ids(first) and len(db.list_plans()) == 1  # replaced, not piled up
    assert all("meat" not in BY_ID[r]["contains"] and "poultry" not in BY_ID[r]["contains"] for r in meal_ids(vegan))
    assert vegan["shuffle"] == first["shuffle"] == 0


def test_shuffle_gives_a_different_week_with_the_same_diet(client):
    client.put("/api/profile", json=PROFILE)
    a = client.get("/api/mealplan").json()
    b = client.post("/api/mealplan/shuffle").json()
    assert b["shuffle"] == 1 and meal_ids(a) != meal_ids(b)
    assert meal_ids(client.get("/api/mealplan").json()) == meal_ids(b)  # the new week sticks


def test_plan_history_keeps_old_weeks(client, monkeypatch):
    from app import main

    client.put("/api/profile", json=PROFILE)
    client.get("/api/mealplan")

    class NextWeek(date):
        @classmethod
        def today(cls):
            return date(2026, 10, 20)

    monkeypatch.setattr(main, "date", NextWeek)
    client.get("/api/mealplan")
    weeks = [p["week"] for p in client.get("/api/plans").json()["plans"]]
    assert weeks == ["2026-10-19", "2026-10-12"]


def test_plan_with_a_vanished_recipe_is_rebuilt(client):
    client.put("/api/profile", json=PROFILE)
    plan = client.get("/api/mealplan").json()
    with db.conn() as c:
        c.execute("UPDATE plan_meals SET recipe_id = 'does-not-exist' WHERE rowid = (SELECT MIN(rowid) FROM plan_meals)")
    assert db.get_plan(plan["week_start"]) is None
    assert meal_ids(client.get("/api/mealplan").json()) == meal_ids(plan)  # rebuilt identically from the same seed


def test_grocery_endpoint_and_price_editing(client):
    client.put("/api/profile", json=PROFILE)
    g = client.get("/api/grocery").json()
    assert g["totals"]["items"] == len(g["lines"]) > 10 and g["meals"] == 21 and "Bureau of Labor Statistics" in g["prices"]["source"]
    aisles = [ln["aisle"] for ln in g["lines"]]
    assert aisles == sorted(aisles, key=lambda a: diet.AISLES.index(a))  # grouped in shopping order
    item = next(ln for ln in g["lines"] if not ln["staple"])
    g2 = client.put("/api/prices", json={"item": item["item"], "price": 9.99}).json()
    edited = next(ln for ln in g2["lines"] if ln["item"] == item["item"])
    assert edited["pack_cents"] == 999 and edited["src"] == "you" and g2["totals"]["your_items"] == 1
    g3 = client.put("/api/prices", json={"item": item["item"], "price": None}).json()  # back to the default
    assert next(ln for ln in g3["lines"] if ln["item"] == item["item"])["src"] == item["src"]
    assert client.put("/api/prices", json={"item": "unicorn_meat", "price": 1}).status_code == 404
    assert client.put("/api/prices", json={"item": item["item"], "price": -5}).status_code == 422


def test_recipe_endpoint_reports_cost_allergens_and_flags(client):
    r = client.get("/api/recipes/turkey-chili").json()
    assert r["cost_cents_per_serving"] > 0 and "poultry" in r["contains"] and r["lines"] and r["cuisine"]
    assert client.get("/api/recipes/nope").status_code == 404


def test_diet_and_grocery_need_a_profile(client):
    assert client.put("/api/diet", json={"pattern": "vegan"}).status_code == 400
    assert client.get("/api/mealplan").status_code == 400 and client.get("/api/grocery").status_code == 400
