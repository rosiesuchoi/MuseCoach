// Compares the JS plan math (docs edition) against Python app/goals.py on many profiles.
// Run: node tools/parity_check.mjs   (uses .venv\Scripts\python)
import { createRequire } from "node:module";
import { execFileSync } from "node:child_process";
const { buildPlan } = createRequire(import.meta.url)("./pages/local-backend.js");

const cases = [];
for (const age of [16, 25, 40, 70])
  for (const sex of ["female", "male"])
    for (const [h, w] of [[150, 48], [165, 60], [165, 50.5], [180, 95]])
      for (const goal of ["lose", "maintain", "build"])
        for (const activity of ["low", "high"])
          for (const gw of [null, 45, 70])
            cases.push({ age, sex, height_cm: h, weight_kg: w, goal, activity, goal_weight_kg: gw });

const py = `
import json, sys
from app.goals import Profile, build_plan
out = []
for c in json.load(sys.stdin):
    out.append(build_plan(Profile(**c), "lean_dancer"))
print(json.dumps(out))`;
const expected = JSON.parse(execFileSync(".venv/Scripts/python.exe", ["-c", py], { input: JSON.stringify(cases) }).toString());

let bad = 0;
cases.forEach((c, i) => {
  const got = buildPlan(c, "lean_dancer"), want = expected[i];
  for (const k of Object.keys(want)) {
    const same = JSON.stringify(got[k]) === JSON.stringify(want[k]);
    // Python rounds .5 to even, JS rounds up: allow a 1-unit gap on whole-number fields.
    const close = typeof want[k] === "number" && Math.abs(got[k] - want[k]) <= 1;
    if (!same && !close) { bad++; console.log("MISMATCH", JSON.stringify(c), k, "js:", got[k], "py:", want[k]); }
  }
});
console.log(`${cases.length} profiles compared, ${bad} mismatches`);
process.exit(bad ? 1 : 0);
