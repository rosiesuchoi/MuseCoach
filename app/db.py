"""Tiny SQLite store. One user, one profile row, a table of logged meals."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path

DEFAULT_PATH = Path(__file__).parent / "data" / "muse.db"


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
            CREATE TABLE IF NOT EXISTS meals (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              day TEXT NOT NULL,
              name TEXT NOT NULL,
              kcal INTEGER NOT NULL,
              items TEXT NOT NULL DEFAULT '[]',
              source TEXT NOT NULL DEFAULT 'manual'
            );
            """
        )
        # Older databases predate the AI analysis column: add it in place so existing meals are kept.
        if "analysis" not in {r["name"] for r in c.execute("PRAGMA table_info(meals)")}:
            c.execute("ALTER TABLE meals ADD COLUMN analysis TEXT")
        yield c
        c.commit()
    finally:
        c.close()


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


def delete_meal(meal_id: int) -> None:
    with conn() as c:
        c.execute("DELETE FROM meals WHERE id = ?", (meal_id,))
