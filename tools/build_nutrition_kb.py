"""Builds app/data/nutrition.json, the app's nutrition knowledge base, from USDA FoodData Central
"SR Legacy" (public domain, CC0): https://fdc.nal.usda.gov/download-datasets

Run (the data folder is untrusted input, so use isolated mode and keep it outside the repo):
    python -I tools/build_nutrition_kb.py <folder containing sr_legacy_food.csv, food_nutrient.csv, ...>

Output is compact on purpose (the browser downloads it): per-100 g nutrients plus a few household portions.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

# (key, [FDC nutrient ids in order of preference])
NUTRIENTS = [
    ("kcal", [1008, 2047, 2048]),
    ("protein", [1003]),
    ("fat", [1004]),
    ("satfat", [1258]),
    ("carb", [1005]),
    ("fiber", [1079]),
    ("sugar", [2000, 1063]),
    ("sodium", [1093]),
    ("chol", [1253]),
    ("potassium", [1092]),
    ("calcium", [1087]),
    ("iron", [1089]),
    ("vitc", [1162]),
    ("caffeine", [1057]),
    ("alcohol", [1018]),
]
DROP_CATEGORIES = {"Baby Foods", "American Indian/Alaska Native Foods"}  # rarely what a photo shows
OUT = Path(__file__).resolve().parent.parent / "app" / "data" / "nutrition.json"


def rows(path: Path):
    with open(path, encoding="utf-8", newline="") as f:
        yield from csv.DictReader(f)


def main(src: Path) -> None:
    cats = {r["id"]: r["description"] for r in rows(src / "food_category.csv")}
    units = {r["id"]: r["name"] for r in rows(src / "measure_unit.csv")}
    wanted = {i for _, ids in NUTRIENTS for i in ids}

    foods = {}
    for r in rows(src / "food.csv"):
        cat = cats.get(r["food_category_id"], "")
        if cat in DROP_CATEGORIES:
            continue
        foods[r["fdc_id"]] = {"id": int(r["fdc_id"]), "d": r["description"], "c": cat, "n": {}, "p": []}

    for r in rows(src / "food_nutrient.csv"):
        nid = int(r["nutrient_id"])
        if nid in wanted and r["fdc_id"] in foods and r["amount"] != "":
            foods[r["fdc_id"]]["n"][nid] = float(r["amount"])

    for r in sorted(rows(src / "food_portion.csv"), key=lambda r: int(r["seq_num"] or 0)):
        f = foods.get(r["fdc_id"])
        if not f or len(f["p"]) >= 4 or not r["gram_weight"]:
            continue
        unit = units.get(r["measure_unit_id"], "")
        unit = "" if unit == "undetermined" else unit
        label = " ".join(x for x in (f"{float(r['amount']):g}", unit, r["portion_description"], r["modifier"]) if x).strip()
        f["p"].append([label, round(float(r["gram_weight"]), 1)])

    cat_list = sorted({f["c"] for f in foods.values()})
    out_foods = []
    for f in foods.values():
        vals = []
        for _, ids in NUTRIENTS:
            v = next((f["n"][i] for i in ids if i in f["n"]), None)
            vals.append(None if v is None else round(v, 2))
        if vals[0] is None:  # no calories on record: useless for this app
            continue
        out_foods.append([f["id"], f["d"], cat_list.index(f["c"]), vals, f["p"]])

    data = {
        "v": 1,
        "source": "USDA FoodData Central, SR Legacy (April 2018 release). Public domain (CC0).",
        "per": "100 g",
        "nutrients": [k for k, _ in NUTRIENTS],
        "units": {"kcal": "kcal", "sodium": "mg", "chol": "mg", "potassium": "mg", "calcium": "mg", "iron": "mg", "vitc": "mg", "caffeine": "mg"},
        "cats": cat_list,
        "foods": out_foods,
    }
    OUT.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    print(f"[build_nutrition_kb] {len(out_foods)} foods -> {OUT} ({OUT.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(Path(sys.argv[1]))
