// Checks that diet filtering, the seeded weekly planner, recipe costs and the grocery list give IDENTICAL results in the browser edition
// (tools/pages/local-backend.js) and the Python server (app/diet.py). Run from the repo root: node tools/diet_parity.mjs
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

const { makeCore } = createRequire(import.meta.url)("./pages/local-backend.js");
const read = p => JSON.parse(readFileSync(new URL(p, import.meta.url), "utf8"));
const recipes = read("../app/data/recipes.json").recipes, catalog = read("../app/data/ingredients.json").items, workouts = read("../app/data/workouts.json");
const core = makeCore({ celebrities: { celebrities: [], default_archetype: "athletic" }, coaches: {}, recipes, workouts, catalog });
const D = core.diet;

const DIETS = {
  none: {}, vegetarian: { pattern: "vegetarian" }, vegan: { pattern: "vegan" }, pescatarian: { pattern: "pescatarian" }, gluten_free: { gluten_free: true },
  dairy_free: { allergens: ["milk"] }, nuts: { allergens: ["peanut", "tree_nut"] }, soy_wheat: { allergens: ["soy", "wheat"] }, vegan_gf: { pattern: "vegan", gluten_free: true },
  strict: { pattern: "vegan", allergens: ["soy"], gluten_free: true }, avoid: { avoid: ["mushroom", "bell pepper"] }, impossible: { pattern: "vegan", allergens: ["soy", "tree_nut", "peanut", "wheat", "milk", "egg"], avoid: ["bean", "chickpea", "lentil"] },
  messy: { allergens: ["milk", "bogus", "milk"], pattern: "carnivore", gluten_free: "yes", avoid: ["  Mushrooms ", "mushrooms", "", "BELL   pepper"] },
};
const targets = [1300, 2000, 3000], seeds = [D.seedFor("2026-10-12", 0), D.seedFor("2026-10-12", 3), D.seedFor("2027-01-04", 1)];
const overrideSets = [{}, { egg: 5.0, chicken_breast: 3.5, olive_oil: 12.34 }];
const amountCases = [[150, "egg"], [50, "egg"], [300, "tomato"], [20, "garlic"], [600, null], [100, null], [9, null], [227, null], [2000, "potato"], [260, "sweet_potato"]];

const input = { diets: DIETS, targets, seeds, overrideSets, amountCases };
const py = `
import json, sys
from app import diet
d = json.load(sys.stdin)
recipes = json.load(open("app/data/recipes.json", encoding="utf-8"))["recipes"]
catalog = json.load(open("app/data/ingredients.json", encoding="utf-8"))["items"]
by_id = {r["id"]: r for r in recipes}
out = {"normalize": {k: diet.normalize(v) for k, v in d["diets"].items()}, "summary": {k: diet.summary(v) for k, v in d["diets"].items()},
       "eligible": {k: [r["id"] for r in recipes if diet.eligible(r, v)] for k, v in d["diets"].items()},
       "rng": [(lambda r: [r() for _ in range(6)])(diet.mulberry32(s)) for s in d["seeds"]],
       "shuffle": [diet.shuffled(list(range(12)), diet.mulberry32(s)) for s in d["seeds"]],
       "plans": {}, "grocery": {}, "costs": {}, "amounts": []}
for name, v in d["diets"].items():
    for t in d["targets"]:
        for i, s in enumerate(d["seeds"]):
            out["plans"][f"{name}|{t}|{i}"] = diet.build_week(recipes, t, s, v)
plan = diet.build_week(recipes, 2000, d["seeds"][0], {})
meals = [{"recipe_id": m["recipe_id"], "servings": m["servings"]} for day in plan["days"] for m in day["meals"]]
for i, ov in enumerate(d["overrideSets"]):
    out["grocery"][str(i)] = diet.grocery(meals, by_id, catalog, ov)
    out["costs"][str(i)] = {r["id"]: diet.recipe_cost_cents(r, catalog, ov) for r in recipes}
out["amounts"] = [diet.amount_text(g, (catalog[k]["each"] if k else None)) for g, k in d["amountCases"]]
print(json.dumps(out))`;
const pyOut = JSON.parse(execFileSync(".venv/Scripts/python.exe", ["-c", py], { input: JSON.stringify(input), maxBuffer: 200e6, env: { ...process.env, PYTHONIOENCODING: "utf-8" } }).toString());

const clone = x => JSON.parse(JSON.stringify(x));
const near = (a, b) => Math.abs(a - b) < 1e-9;
const tests = {
  "diet normalization and summaries match"() {
    for (const [k, v] of Object.entries(DIETS)) { assert.deepEqual(D.normalizeDiet(v), pyOut.normalize[k], k); assert.deepEqual(D.summary(v), pyOut.summary[k], k); }
  },
  "the same recipes are eligible for every diet"() {
    for (const [k, v] of Object.entries(DIETS)) assert.deepEqual(recipes.filter(r => D.eligible(r, v)).map(r => r.id), pyOut.eligible[k], k);
  },
  "seeded random numbers and shuffles are identical"() {
    seeds.forEach((s, i) => {
      const r = D.mulberry32(s); assert.deepEqual(Array.from({ length: 6 }, () => r()), pyOut.rng[i], `rng seed ${s}`);
      assert.deepEqual(D.shuffled([...Array(12).keys()], D.mulberry32(s)), pyOut.shuffle[i], `shuffle seed ${s}`);
    });
  },
  "weekly plans are identical for every diet, calorie target and seed"() {
    let n = 0;
    for (const [name, v] of Object.entries(DIETS)) for (const t of targets) seeds.forEach((s, i) => {
      assert.deepEqual(clone(core.buildWeekDiet(recipes, t, s, v)), pyOut.plans[`${name}|${t}|${i}`], `${name} @ ${t} kcal, seed #${i}`); n++;
    });
    assert.equal(n, Object.keys(DIETS).length * targets.length * seeds.length);
  },
  "grocery lists (items, packs, cents, totals) are identical, with and without price edits"() {
    const plan = core.buildWeekDiet(recipes, 2000, seeds[0], {});
    const meals = plan.days.flatMap(d => d.meals.map(m => ({ recipe_id: m.recipe_id, servings: m.servings })));
    overrideSets.forEach((ov, i) => assert.deepEqual(clone(D.grocery(meals, ov)), pyOut.grocery[String(i)], `overrides #${i}`));
  },
  "recipe costs per serving are identical"() {
    overrideSets.forEach((ov, i) => { for (const r of recipes) assert.ok(near(D.recipeCostCents(r, ov), pyOut.costs[String(i)][r.id]), `${r.id} #${i}`); });
  },
  "amount wording is identical"() {
    assert.deepEqual(amountCases.map(([g, k]) => D.amountText(g, k ? catalog[k].each : null)), pyOut.amounts);
  },
};
let failed = 0;
for (const [name, fn] of Object.entries(tests)) { try { fn(); console.log("ok  ", name); } catch (e) { failed++; console.log("FAIL", name, "-", String(e.message).slice(0, 700)); } }
console.log(failed ? `${failed} failed` : "all passed");
process.exit(failed ? 1 : 0);
