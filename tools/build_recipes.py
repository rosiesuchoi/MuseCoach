"""Builds app/data/recipes.json.

Scrapes ingredients and instructions from Wikibooks Cookbook (text licensed CC BY-SA 4.0, so every recipe
keeps its source page, revision and license), and COMPUTES nutrition from the USDA knowledge base using the
curated weights in tools/recipes_src.json. Nothing nutritional is scraped.

Run:  .venv\\Scripts\\python tools/build_recipes.py     (needs internet; run build_nutrition_kb.py first)
"""

from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://en.wikibooks.org/w/api.php"
UA = "MuseCoachBuild/1.0 (TCSS490 student project; https://github.com/rosiesuchoi/MuseCoach)"  # Wikimedia asks for an identifying UA
LICENSE = "CC BY-SA 4.0"


def fetch_page(title: str) -> tuple[str, int]:
    q = urllib.parse.urlencode({"action": "query", "titles": title, "prop": "revisions", "rvprop": "content|ids",
                                "rvslots": "main", "format": "json", "formatversion": "2"})
    req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        page = json.load(r)["query"]["pages"][0]
    if page.get("missing"):
        raise SystemExit(f"page missing: {title}")
    rev = page["revisions"][0]
    return rev["slots"]["main"]["content"], rev["revid"]


def strip_files(text: str) -> str:
    """Remove [[File:...]] / [[Image:...]] including captions that contain nested [[links]]."""
    out, i = [], 0
    while i < len(text):
        m = re.match(r"\[\[(?:File|Image):", text[i:], re.I)
        if not m:
            out.append(text[i])
            i += 1
            continue
        depth, j = 0, i
        while j < len(text):
            if text.startswith("[[", j):
                depth += 1
                j += 2
            elif text.startswith("]]", j):
                depth -= 1
                j += 2
                if depth == 0:
                    break
            else:
                j += 1
        i = j
    return "".join(out)


def clean(text: str) -> str:
    text = strip_files(text)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>", "", text, flags=re.S)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    text = re.sub(r"\[\[([^\]|]*)\|([^\]]*)\]\]", r"\2", text)  # [[target|label]] -> label
    text = re.sub(r"\[\[([^\]]*)\]\]", lambda m: m.group(1).split(":")[-1], text)  # [[Cookbook:Egg]] -> Egg
    text = re.sub(r"\[https?://\S+ ([^\]]+)\]", r"\1", text)
    text = re.sub(r"'{2,}", "", text)
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip(" *#")


def sections(wikitext: str) -> dict[str, str]:
    parts = re.split(r"^==\s*([^=\n][^=\n]*?)\s*==\s*$", wikitext, flags=re.M)
    return {parts[i].strip().lower(): parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def parse_ingredients(block: str, keep_groups: list[str] | None):
    groups, current = [], {"heading": "", "items": []}
    for line in block.splitlines():
        h = re.match(r"^===\s*(.*?)\s*===\s*$", line)
        if h:
            if current["items"]:
                groups.append(current)
            current = {"heading": clean(h.group(1)), "items": []}
        elif line.lstrip().startswith("*"):
            text = clean(line)
            if text:
                current["items"].append(text)
    if current["items"]:
        groups.append(current)
    if keep_groups:
        groups = [g for g in groups if g["heading"] in keep_groups]
    return groups


def parse_steps(block: str) -> list[str]:
    return [t for t in (clean(l) for l in block.splitlines() if l.lstrip().startswith("#")) if t]


def parse_notes(block: str) -> list[str]:
    return [t for t in (clean(l) for l in block.splitlines() if l.lstrip().startswith("*")) if t][:6]


def nutrition_per_serving(kb, lines, servings):
    names = kb["nutrients"]
    index = {f[0]: f for f in kb["foods"]}
    totals = dict.fromkeys(names, 0.0)
    for ln in lines:
        food = index.get(ln["fdc"])
        if food is None:
            raise SystemExit(f"unknown FDC id {ln['fdc']} ({ln['what']})")
        for key, val in zip(names, food[3]):
            if val is not None:
                totals[key] += val * ln["g"] / 100
    out = {k: round(v / servings, 1) for k, v in totals.items() if k not in ("caffeine", "alcohol")}
    out["kcal"] = round(out["kcal"])
    out["sodium"] = round(out["sodium"])
    return out


def main() -> None:
    kb = json.loads((ROOT / "app/data/nutrition.json").read_text(encoding="utf-8"))
    src = json.loads((ROOT / "tools/recipes_src.json").read_text(encoding="utf-8"))["recipes"]
    recipes = []
    for r in src:
        wikitext, revid = fetch_page(r["page"])
        sec = sections(wikitext)
        groups = parse_ingredients(sec.get("ingredients", ""), r.get("keep_groups"))
        steps = parse_steps(sec.get("procedure", ""))
        if not groups or not steps:
            raise SystemExit(f"could not parse {r['page']}: ingredients={bool(groups)} steps={bool(steps)}")
        nutr = nutrition_per_serving(kb, r["nutrition"], r["servings"])
        assert 50 <= nutr["kcal"] <= 1200, f"{r['id']} has implausible calories: {nutr['kcal']}"
        title = r["page"].split(":", 1)[1]
        recipes.append({
            "id": r["id"], "slot": r["slot"], "name": title,
            "servings": r["servings"], "servings_note": r["servings_note"],
            "ingredients": groups, "steps": steps, "notes": parse_notes(sec.get("notes, tips, and variations", "")),
            "nutrition": nutr, "assumptions": r["assumptions"],
            "source": {
                "title": f"{title} (Wikibooks Cookbook)",
                "url": "https://en.wikibooks.org/wiki/" + urllib.parse.quote(r["page"].replace(" ", "_")),
                "history": f"https://en.wikibooks.org/w/index.php?title={urllib.parse.quote(r['page'].replace(' ', '_'))}&action=history",
                "revision": revid, "license": LICENSE,
                "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
            },
        })
        print(f"{r['id']:24} {nutr['kcal']:4} kcal/serving  P{nutr['protein']:5.1f} F{nutr['fat']:5.1f} C{nutr['carb']:5.1f} Na{nutr['sodium']:5}  rev {revid}")
    out = {
        "_license": ("Ingredient lists and instructions are from Wikibooks Cookbook contributors, licensed CC BY-SA 4.0 "
                     "(https://creativecommons.org/licenses/by-sa/4.0/), reformatted for this app. Each recipe links its page and edit "
                     "history for attribution. Nutrition is computed by this project from USDA FoodData Central (public domain). "
                     "This file is therefore also available under CC BY-SA 4.0."),
        "recipes": recipes,
    }
    (ROOT / "app/data/recipes.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(recipes)} recipes")


if __name__ == "__main__":
    main()
