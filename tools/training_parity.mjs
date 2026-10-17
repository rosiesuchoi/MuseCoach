// Checks that the training week built in the browser (tools/pages/local-backend.js) matches the Python one (app/training.py)
// for every style x activity level x a spread of dates (including month and year boundaries and every weekday).
// Run from the repo root: node tools/training_parity.mjs
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

const { makeCore } = createRequire(import.meta.url)("./pages/local-backend.js");
const workouts = JSON.parse(readFileSync(new URL("../app/data/workouts.json", import.meta.url), "utf8"));
const core = makeCore({ celebrities: { celebrities: [], default_archetype: "athletic" }, coaches: {}, recipes: [], workouts });

const dates = ["2026-10-12", "2026-10-14", "2026-10-17", "2026-10-18", "2026-11-01", "2026-12-31", "2027-01-01", "2028-02-29", "2026-03-29"];
const doneSets = [[], ["Mon"], ["Mon", "Wed", "Fri", "Sat"], ["Mon", "Tue", "Thu", "Fri", "Sat"]];
const cases = [];
for (const style of Object.keys(workouts.styles)) for (const activity of ["low", "medium", "high", "weird"])
  dates.forEach((d, i) => cases.push({ style, activity, date: d, done: doneSets[i % doneSets.length] }));

const py = `
import json, sys
from datetime import date
from app import training
out = [training.build_week(c["style"], c["activity"], set(c["done"]), date.fromisoformat(c["date"])) for c in json.load(sys.stdin)]
print(json.dumps(out))`;
const pyOut = JSON.parse(execFileSync(".venv/Scripts/python.exe", ["-c", py], { input: JSON.stringify(cases), maxBuffer: 80e6, env: { ...process.env, PYTHONIOENCODING: "utf-8" } }).toString());

let failed = 0;
const jsOut = cases.map(c => {
  const [y, m, d] = c.date.split("-").map(Number);
  return JSON.parse(JSON.stringify(core.buildTraining(c.style, c.activity, new Set(c.done), new Date(y, m - 1, d))));
});
cases.forEach((c, i) => {
  try { assert.deepEqual(jsOut[i], pyOut[i]); }
  catch (e) { failed++; if (failed < 4) console.log("MISMATCH", JSON.stringify(c), "\n", String(e.message).slice(0, 500)); }
});
console.log(`${cases.length} weeks compared (${Object.keys(workouts.styles).length} styles x 4 activity values x ${dates.length} dates), ${failed} mismatches`);
process.exit(failed ? 1 : 0);
