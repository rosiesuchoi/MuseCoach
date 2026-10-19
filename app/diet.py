"""Diet profile, recipe filtering, the varied weekly meal plan, recipe costs and the grocery list.

Pure functions (no database, no I/O) so they are easy to test. The browser edition has the same logic in
tools/pages/local-backend.js; tools/diet_parity.mjs checks both give identical results.

Safety note: allergen tags come from the ingredient catalog (app/data/ingredients.json). They describe what the recipe's listed
ingredients typically contain. They do not know about brands, "may contain" warnings or cross-contact, so the app always tells people to read labels.
"""

from __future__ import annotations

import json
import math

ALLERGENS = ["milk", "egg", "peanut", "tree_nut", "wheat", "soy", "fish", "shellfish", "sesame"]
PATTERNS = ["none", "pescatarian", "vegetarian", "vegan"]
PATTERN_EXCLUDES = {
    "none": set(),
    "pescatarian": {"meat", "poultry"},
    "vegetarian": {"meat", "poultry", "fish", "shellfish"},
    "vegan": {"meat", "poultry", "fish", "shellfish", "milk", "egg", "honey"},
}
SLOTS = [("breakfast", 0.25), ("lunch", 0.35), ("dinner", 0.30)]  # the last 10% is for snacks
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
AISLES = ["Produce", "Meat & seafood", "Dairy & eggs", "Grains & bakery", "Canned & dry goods", "Frozen", "Pantry staples", "Spices"]
LB_G = 453.6


def js_round(x: float) -> int:
    """JavaScript's Math.round (halves round up), so results match the browser edition exactly."""
    return math.floor(x + 0.5)


# ---------- the diet profile ----------

def normalize(raw: dict | None) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    allergens = [a for a in ALLERGENS if a in (raw.get("allergens") or [])]
    pattern = raw.get("pattern") if raw.get("pattern") in PATTERNS else "none"
    avoid, seen = [], set()
    for w in raw.get("avoid") or []:
        w = " ".join(str(w).lower().split())[:40]
        if w and w not in seen:
            seen.add(w)
            avoid.append(w)
    return {"allergens": allergens, "pattern": pattern, "gluten_free": raw.get("gluten_free") is True, "avoid": avoid[:20]}


def signature(diet: dict) -> str:
    d = normalize(diet)
    return json.dumps(d, sort_keys=True, separators=(",", ":"))


def excluded_tags(diet: dict) -> set[str]:
    d = normalize(diet)
    return set(d["allergens"]) | PATTERN_EXCLUDES[d["pattern"]] | ({"gluten"} if d["gluten_free"] else set())


def recipe_text(recipe: dict) -> str:
    parts = [recipe["name"]] + [t for g in recipe["ingredients"] for t in g["items"]]
    return " ".join(parts).lower()


def eligible(recipe: dict, diet: dict) -> bool:
    if (set(recipe["allergens"]) | set(recipe["contains"])) & excluded_tags(diet):
        return False
    text = recipe_text(recipe)
    return not any(w in text for w in normalize(diet)["avoid"])


def summary(diet: dict) -> list[str]:
    d = normalize(diet)
    out = []
    if d["pattern"] != "none":
        out.append(d["pattern"].capitalize())
    if d["gluten_free"]:
        out.append("Gluten-free")
    out += [f"No {a.replace('_', ' ')}" for a in d["allergens"]]
    out += [f"No {w}" for w in d["avoid"]]
    return out


# ---------- seeded shuffling (the same numbers in Python and JavaScript) ----------

def mulberry32(seed: int):
    state = seed & 0xFFFFFFFF

    def nxt() -> float:
        nonlocal state
        state = (state + 0x6D2B79F5) & 0xFFFFFFFF
        t = state
        t = ((t ^ (t >> 15)) * (t | 1)) & 0xFFFFFFFF
        t = (t ^ ((t + (((t ^ (t >> 7)) * (t | 61)) & 0xFFFFFFFF)) & 0xFFFFFFFF)) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296

    return nxt


def shuffled(items: list, rng) -> list:
    out = list(items)
    for i in range(len(out) - 1, 0, -1):
        j = math.floor(rng() * (i + 1))
        out[i], out[j] = out[j], out[i]
    return out


def seed_for(week_start: str, shuffle: int) -> int:
    return (int(week_start.replace("-", "")) * 31 + shuffle) & 0xFFFFFFFF


def portion(budget: float, kcal: int) -> float:
    return min(2.0, max(0.5, js_round(budget / kcal * 4) / 4))


# ---------- the weekly plan ----------

def build_week(recipes: list[dict], target_kcal: int, seed: int, diet: dict) -> dict:
    """Pick 7 days x 3 meals. With a flexible diet every meal in the week is different; a strict diet that leaves fewer than 7
    options for a slot repeats them as far apart as possible, and says so."""
    notes, counts = [], {}
    picks: dict[str, list[dict | None]] = {}
    for si, (slot, share) in enumerate(SLOTS):
        pool = sorted([r for r in recipes if r["slot"] == slot and eligible(r, diet)], key=lambda r: r["id"])
        counts[slot] = len(pool)
        if not pool:
            picks[slot] = [None] * 7
            notes.append(f"No {slot} recipes fit your diet and allergies, so {slot} is left out. Loosen a restriction to see options.")
            continue
        budget = target_kcal * share
        feasible = [r for r in pool if 0.5 <= budget / r["nutrition"]["kcal"] <= 2.0]  # a portion of 0.5x-2x can reach the target
        need = min(len(pool), 7)
        if len(feasible) >= need:
            chosen = feasible
        else:
            rest = sorted((r for r in pool if r not in feasible), key=lambda r: (abs(math.log(budget / r["nutrition"]["kcal"])), r["id"]))
            chosen = feasible + rest[: need - len(feasible)]
        order = shuffled(chosen, mulberry32(seed + si * 7919))
        picks[slot] = [order[i % len(order)] for i in range(7)]
        if len(pool) < 7:
            notes.append(f"Only {len(pool)} {slot} recipe{'s' if len(pool) != 1 else ''} fit your diet and allergies, so some repeat during the week.")
    days = []
    for i, day in enumerate(DAYS):
        meals = []
        for slot, share in SLOTS:
            r = picks[slot][i]
            if r is None:
                continue
            serv = portion(target_kcal * share, r["nutrition"]["kcal"])
            meals.append({"slot": slot, "recipe_id": r["id"], "name": r["name"], "servings": serv, "kcal": js_round(r["nutrition"]["kcal"] * serv)})
        days.append({"day": day, "meals": meals, "snack_budget": js_round(target_kcal * 0.10)})
    return {"days": days, "notes": notes, "counts": counts}


# ---------- prices ----------

def pack_cents(item_id: str, item: dict, overrides: dict) -> int:
    return js_round(overrides.get(item_id, item["pack"]["price"]) * 100)


def price_src(item_id: str, item: dict, overrides: dict) -> str:
    return "you" if item_id in overrides else item["pack"]["src"]


def recipe_cost_cents(recipe: dict, catalog: dict, overrides: dict) -> float:
    """What the food in ONE serving costs (pro-rated from pack prices; you can't buy a pinch of paprika, but this is the value of what you eat)."""
    total = 0
    for ln in recipe["lines"]:
        it = catalog[ln["item"]]
        total += js_round(pack_cents(ln["item"], it, overrides) * ln["g"] / it["pack"]["g"])
    return total / recipe["servings"]


def amount_text(g: float, each: dict | None) -> str:
    if each:
        n = js_round(g / each["g"] * 2) / 2
        if n >= 1:
            name = each["name"] if n == 1 else each.get("plural", each["name"] + "s")
            return f"{n:g} {name}"
    if g >= 227:
        return f"{js_round(g / LB_G * 10) / 10:.1f} lb"
    if g >= 28.35:
        return f"{js_round(g / 28.35)} oz"
    return f"{js_round(g)} g"


def grocery(meals: list[dict], recipes_by_id: dict, catalog: dict, overrides: dict) -> dict:
    """meals: [{recipe_id, servings}] for the week. Returns shopping lines (what to buy) and totals, all in integer cents."""
    need: dict[str, float] = {}
    uses: dict[str, set] = {}
    for m in meals:
        r = recipes_by_id[m["recipe_id"]]
        for ln in r["lines"]:
            need[ln["item"]] = need.get(ln["item"], 0) + ln["g"] / r["servings"] * m["servings"]
            uses.setdefault(ln["item"], set()).add(r["name"])
    lines = []
    for item_id, g in need.items():
        it = catalog[item_id]
        pc = pack_cents(item_id, it, overrides)
        packs = max(1, math.ceil(g / it["pack"]["g"] - 1e-9))
        src = price_src(item_id, it, overrides)
        lines.append({
            "item": item_id, "name": it["name"], "aisle": it["aisle"], "need_g": js_round(g * 10) / 10,
            "need_text": amount_text(g, it.get("each")), "packs": packs, "pack_label": it["pack"]["label"],
            "pack_cents": pc, "line_cents": pc * packs, "used_cents": js_round(pc * g / it["pack"]["g"]),
            "src": src, "official": src in ("bls", "bls-derived"), "staple": bool(it.get("staple")),
            "uses": sorted(uses[item_id])[:4],
        })
    lines.sort(key=lambda ln: (AISLES.index(ln["aisle"]) if ln["aisle"] in AISLES else len(AISLES), ln["name"]))
    to_buy = sum(ln["line_cents"] for ln in lines)
    staples = sum(ln["line_cents"] for ln in lines if ln["staple"])
    return {
        "lines": lines,
        "totals": {
            "to_buy_cents": to_buy, "used_cents": sum(ln["used_cents"] for ln in lines), "staples_cents": staples, "without_staples_cents": to_buy - staples,
            "items": len(lines), "official_items": sum(1 for ln in lines if ln["official"]), "estimated_items": sum(1 for ln in lines if ln["src"] == "estimate"),
            "your_items": sum(1 for ln in lines if ln["src"] == "you"),
        },
    }
