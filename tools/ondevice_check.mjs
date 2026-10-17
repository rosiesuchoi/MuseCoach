// Checks the on-device estimate logic and the calorie table (offline, no model download).
// Run: node tools/ondevice_check.mjs
// Add --live to also confirm the table covers exactly the model's labels (needs internet).
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
const { fromPredictions } = createRequire(import.meta.url)("./pages/local-backend.js");

const raw = JSON.parse(readFileSync(new URL("../app/data/food_calories.json", import.meta.url), "utf8"));
const table = Object.fromEntries(Object.entries(raw).filter(([k]) => !k.startsWith("_")));

const tests = {
  "table has 101 sane entries"() {
    assert.equal(Object.keys(table).length, 101);
    for (const [k, v] of Object.entries(table)) {
      assert.ok(v.name && v.serving, `${k} needs name and serving`);
      assert.ok(Number.isInteger(v.kcal) && v.kcal >= 30 && v.kcal <= 1000, `${k} kcal out of range: ${v.kcal}`);
    }
  },
  "confident prediction -> medium confidence, table calories"() {
    const r = fromPredictions([{ label: "pizza", score: 0.9 }, { label: "lasagna", score: 0.05 }], table);
    assert.equal(r.meal_name, "Pizza"); assert.equal(r.total_kcal, 570); assert.equal(r.confidence, "medium");
    assert.equal(r.method, "on-device"); assert.equal(r.demo, false);
  },
  "middling score -> low confidence"() { assert.equal(fromPredictions([{ label: "sushi", score: 0.4 }], table).confidence, "low"); },
  "never claims high confidence"() { assert.notEqual(fromPredictions([{ label: "ramen", score: 0.999 }], table).confidence, "high"); },
  "guessing (score < 0.20) is refused"() { assert.throws(() => fromPredictions([{ label: "pizza", score: 0.15 }], table), /recognize/); },
  "empty or unknown label is refused"() {
    assert.throws(() => fromPredictions([], table), /recognize/);
    assert.throws(() => fromPredictions([{ label: "not_a_dish", score: 0.9 }], table), /recognize/);
  },
};

let failed = 0;
for (const [name, fn] of Object.entries(tests)) { try { fn(); console.log("ok  ", name); } catch (e) { failed++; console.log("FAIL", name, "-", e.message); } }

if (process.argv.includes("--live")) {
  const cfg = await (await fetch("https://huggingface.co/onnx-community/swin-finetuned-food101-ONNX/resolve/e5e50bfc6425aa546f3b4421ca8bd79d0dd610b8/config.json")).json();
  const labels = new Set(Object.values(cfg.id2label));
  const mine = new Set(Object.keys(table));
  const missing = [...labels].filter(l => !mine.has(l)), extra = [...mine].filter(l => !labels.has(l));
  if (missing.length || extra.length) { failed++; console.log("FAIL labels differ. missing:", missing, "extra:", extra); } else console.log("ok   table matches the model's 101 labels");
}
console.log(failed ? `${failed} failed` : "all passed");
process.exit(failed ? 1 : 0);
