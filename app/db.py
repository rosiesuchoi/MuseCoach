"""SQLite store for the server edition.

Reference data (the grocery catalog and every recipe) is loaded from app/data/*.json into tables, and the tables are what the API reads, so
recipes can be queried, saved plans can point at them, and the app keeps working from one file. User data lives alongside it: profile, logged meals,
workout check-offs, the diet profile (allergies and preferences), saved weekly meal plans, and any grocery prices the user has edited.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DEFAULT_PATH = DATA_DIR / "muse.db"
_seeded: dict[str, str] = {}  # database path -> hash of the reference data already loaded into it
_hash_cache: list[str] = []


def _path() -> str:
    return os.environ.get("MUSE_DB", str(DEFAULT_PATH))


@contextmanager
def conn():
    c = sqlite3.connect(_path())
    c.row_factory = sqlite3.Row
    try:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS profile (id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS checks (week TEXT NOT NULL, day TEXT NOT NULL, PRIMARY KEY (week, day));
            CREATE TABLE IF NOT EXISTS meals (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              day TEXT NOT NULL,
              name TEXT NOT NULL,
              kcal INTEGER NOT NULL,
              items TEXT NOT NULL DEFAULT '[]',
              source TEXT NOT NULL DEFAULT 'manual'
            );
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS ingredients (
              id TEXT PRIMARY KEY, name TEXT NOT NULL, fdc INTEGER NOT NULL, aisle TEXT NOT NULL, allergens TEXT NOT NULL, contains_flags TEXT NOT NULL,
              pack_label TEXT NOT NULL, pack_g REAL NOT NULL, pack_price REAL NOT NULL, price_src TEXT NOT NULL, staple INTEGER NOT NULL,
              each_name TEXT, each_g REAL, each_plural TEXT
            );
            CREATE TABLE IF NOT EXISTS recipes (
              id TEXT PRIMARY KEY, slot TEXT NOT NULL, name TEXT NOT NULL, cuisine TEXT, minutes INTEGER, servings INTEGER NOT NULL, kcal INTEGER NOT NULL,
              allergens TEXT NOT NULL, contains_flags TEXT NOT NULL, data TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS recipe_lines (
              recipe_id TEXT NOT NULL REFERENCES recipes(id), item TEXT NOT NULL REFERENCES ingredients(id), grams REAL NOT NULL, PRIMARY KEY (recipe_id, item)
            );
            CREATE TABLE IF NOT EXISTS diet (id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS price_overrides (item TEXT PRIMARY KEY, price REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS plans (
              id INTEGER PRIMARY KEY AUTOINCREMENT, week TEXT NOT NULL, shuffle INTEGER NOT NULL DEFAULT 0, sig TEXT NOT NULL, target INTEGER NOT NULL,
              created TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '[]'
            );
            CREATE TABLE IF NOT EXISTS plan_meals (
              plan_id INTEGER NOT NULL REFERENCES plans(id), day TEXT NOT NULL, slot TEXT NOT NULL, recipe_id TEXT NOT NULL, servings REAL NOT NULL, kcal INTEGER NOT NULL,
              PRIMARY KEY (plan_id, day, slot)
            );
            CREATE INDEX IF NOT EXISTS plans_week ON plans(week);
            """
        )
        _seed(c)
        # Older databases predate the AI analysis column: add it in place so existing meals are kept.
        if "analysis" not in {r["name"] for r in c.execute("PRAGMA table_info(meals)")}:
            c.execute("ALTER TABLE meals ADD COLUMN analysis TEXT")
        yield c
        c.commit()
    finally:
        c.close()


def _data_hash() -> str:
    if not _hash_cache:
        h = hashlib.sha1()
        for name in ("ingredients.json", "recipes.json"):
            h.update((DATA_DIR / name).read_bytes())
        _hash_cache.append(h.hexdigest())
    return _hash_cache[0]


def _seed(c: sqlite3.Connection) -> None:
    """Load the catalog and recipes into their tables, once per process and database, and again whenever the data files change."""
    digest, path = _data_hash(), _path()
    if _seeded.get(path) == digest:
        return
    row = c.execute("SELECT value FROM meta WHERE key = 'data_hash'").fetchone()
    if row and row["value"] == digest:
        _seeded[path] = digest
        return
    catalog = json.loads((DATA_DIR / "ingredients.json").read_text(encoding="utf-8"))["items"]
    recipes = json.loads((DATA_DIR / "recipes.json").read_text(encoding="utf-8"))["recipes"]
    for table in ("recipe_lines", "recipes", "ingredients"):
        c.execute(f"DELETE FROM {table}")
    for item_id, it in catalog.items():
        each = it.get("each") or {}
        c.execute(
            "INSERT INTO ingredients VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (item_id, it["name"], it["fdc"], it["aisle"], json.dumps(it["allergens"]), json.dumps(it["contains"]), it["pack"]["label"], it["pack"]["g"],
             it["pack"]["price"], it["pack"]["src"], 1 if it.get("staple") else 0, each.get("name"), each.get("g"), each.get("plural")),
        )
    for r in recipes:
        c.execute(
            "INSERT INTO recipes VALUES (?,?,?,?,?,?,?,?,?,?)",
            (r["id"], r["slot"], r["name"], r.get("cuisine"), r.get("minutes"), r["servings"], r["nutrition"]["kcal"], json.dumps(r["allergens"]),
             json.dumps(r["contains"]), json.dumps(r)),
        )
        for ln in r["lines"]:
            c.execute("INSERT INTO recipe_lines VALUES (?,?,?)", (r["id"], ln["item"], ln["g"]))
    c.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('data_hash', ?)", (digest,))
    _seeded[path] = digest


# ---------- reference data ----------

def get_catalog() -> dict:
    with conn() as c:
        rows = c.execute("SELECT * FROM ingredients").fetchall()
    out = {}
    for r in rows:
        it = {"name": r["name"], "fdc": r["fdc"], "allergens": json.loads(r["allergens"]), "contains": json.loads(r["contains_flags"]), "aisle": r["aisle"],
              "pack": {"label": r["pack_label"], "g": r["pack_g"], "price": r["pack_price"], "src": r["price_src"]}}
        if r["staple"]:
            it["staple"] = True
        if r["each_name"]:
            it["each"] = {"name": r["each_name"], "g": r["each_g"], **({"plural": r["each_plural"]} if r["each_plural"] else {})}
        out[r["id"]] = it
    return out


def get_recipes() -> list[dict]:
    with conn() as c:
        rows = c.execute("SELECT data FROM recipes ORDER BY rowid").fetchall()
    return [json.loads(r["data"]) for r in rows]


def get_recipe(recipe_id: str) -> dict | None:
    with conn() as c:
        row = c.execute("SELECT data FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    return json.loads(row["data"]) if row else None


# ---------- the user's diet, price edits and saved plans ----------

def get_diet() -> dict | None:
    with conn() as c:
        row = c.execute("SELECT data FROM diet WHERE id = 1").fetchone()
    return json.loads(row["data"]) if row else None


def set_diet(data: dict) -> None:
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO diet (id, data) VALUES (1, ?)", (json.dumps(data),))


def get_overrides() -> dict:
    with conn() as c:
        return {r["item"]: r["price"] for r in c.execute("SELECT item, price FROM price_overrides")}


def set_override(item: str, price: float | None) -> None:
    with conn() as c:
        if price is None:
            c.execute("DELETE FROM price_overrides WHERE item = ?", (item,))
        else:
            c.execute("INSERT OR REPLACE INTO price_overrides (item, price) VALUES (?, ?)", (item, price))


def get_plan(week: str) -> dict | None:
    """The saved plan for a week (days, meals, notes), or None. A plan whose recipes no longer exist is ignored."""
    with conn() as c:
        p = c.execute("SELECT * FROM plans WHERE week = ? ORDER BY id DESC LIMIT 1", (week,)).fetchone()
        if p is None:
            return None
        rows = c.execute(
            "SELECT m.day, m.slot, m.recipe_id, m.servings, m.kcal, r.name FROM plan_meals m LEFT JOIN recipes r ON r.id = m.recipe_id WHERE m.plan_id = ?", (p["id"],)
        ).fetchall()
    if any(r["name"] is None for r in rows):
        return None
    days = []
    for day in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"):
        meals = [{"slot": slot, "recipe_id": r["recipe_id"], "name": r["name"], "servings": r["servings"], "kcal": r["kcal"]}
                 for slot in ("breakfast", "lunch", "dinner") for r in rows if r["day"] == day and r["slot"] == slot]
        days.append({"day": day, "meals": meals, "snack_budget": int(p["target"] * 0.10 + 0.5)})
    return {"id": p["id"], "week": p["week"], "shuffle": p["shuffle"], "sig": p["sig"], "target": p["target"], "notes": json.loads(p["notes"]), "days": days}


def save_plan(week: str, shuffle: int, sig: str, target: int, plan: dict) -> None:
    """Replace the saved plan for this week (older weeks stay as history)."""
    from datetime import datetime

    with conn() as c:
        for pid in [r["id"] for r in c.execute("SELECT id FROM plans WHERE week = ?", (week,))]:
            c.execute("DELETE FROM plan_meals WHERE plan_id = ?", (pid,))
            c.execute("DELETE FROM plans WHERE id = ?", (pid,))
        cur = c.execute("INSERT INTO plans (week, shuffle, sig, target, created, notes) VALUES (?,?,?,?,?,?)",
                        (week, shuffle, sig, target, datetime.now().isoformat(timespec="seconds"), json.dumps(plan["notes"])))
        for d in plan["days"]:
            for m in d["meals"]:
                c.execute("INSERT INTO plan_meals VALUES (?,?,?,?,?,?)", (cur.lastrowid, d["day"], m["slot"], m["recipe_id"], m["servings"], m["kcal"]))


def list_plans(limit: int = 12) -> list[dict]:
    with conn() as c:
        rows = c.execute(
            "SELECT p.week, p.shuffle, p.created, p.target, COUNT(m.recipe_id) AS meals FROM plans p LEFT JOIN plan_meals m ON m.plan_id = p.id GROUP BY p.id ORDER BY p.week DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def save_profile(data: dict) -> None:
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO profile (id, data) VALUES (1, ?)", (json.dumps(data),))


def load_profile() -> dict | None:
    with conn() as c:
        row = c.execute("SELECT data FROM profile WHERE id = 1").fetchone()
    return json.loads(row["data"]) if row else None


def add_meal(name: str, kcal: int, items: list, source: str, analysis: dict | None = None) -> int:
    with conn() as c:
        cur = c.execute(
            "INSERT INTO meals (day, name, kcal, items, source, analysis) VALUES (?, ?, ?, ?, ?, ?)",
            (date.today().isoformat(), name, kcal, json.dumps(items), source, json.dumps(analysis) if analysis else None),
        )
        return cur.lastrowid


def todays_meals() -> list[dict]:
    with conn() as c:
        rows = c.execute(
            "SELECT id, name, kcal, items, source, analysis FROM meals WHERE day = ? ORDER BY id",
            (date.today().isoformat(),),
        ).fetchall()
    return [{**dict(r), "items": json.loads(r["items"]), "analysis": json.loads(r["analysis"]) if r["analysis"] else None} for r in rows]


def update_meal(meal_id: int, name: str, kcal: int) -> bool:
    with conn() as c:
        cur = c.execute("UPDATE meals SET name = ?, kcal = ? WHERE id = ?", (name, kcal, meal_id))
        return cur.rowcount > 0


def get_checks(week: str) -> set[str]:
    with conn() as c:
        return {r["day"] for r in c.execute("SELECT day FROM checks WHERE week = ?", (week,))}


def set_check(week: str, day: str, done: bool) -> None:
    with conn() as c:
        if done:
            c.execute("INSERT OR IGNORE INTO checks (week, day) VALUES (?, ?)", (week, day))
        else:
            c.execute("DELETE FROM checks WHERE week = ? AND day = ?", (week, day))


def delete_meal(meal_id: int) -> None:
    with conn() as c:
        c.execute("DELETE FROM meals WHERE id = ?", (meal_id,))
