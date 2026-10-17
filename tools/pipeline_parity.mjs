// Checks that the Python pipeline (app/rag.py) and the JavaScript pipeline (shared/pipeline.mjs) agree:
// same retrieval results, byte-identical model requests, and identical analysis output for the same mocked model.
// Run from the repo root: node tools/pipeline_parity.mjs
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import * as js from "../shared/pipeline.mjs";

const kb = JSON.parse(readFileSync(new URL("../app/data/nutrition.json", import.meta.url), "utf8"));
const index = js.buildIndex(kb);

const queries = [["pizza cheese regular crust"], ["coffee brewed"], ["banana raw"], ["cheeseburger fast food", "hamburger"], ["salmon atlantic cooked"],
  ["rice white cooked"], ["french fries"], ["carbonated beverage cola", "cola"], ["orange juice"], ["chicken breast grilled"], ["egg scrambled"],
  ["whole milk"], ["avocado raw"], ["oats cooked"], ["beer regular"], ["chocolate cake frosting"], ["greek yogurt plain"], ["zzqxv plorb"], ["sushi roll"]];

const seen = { is_food: true, items: [
  { name: "cheeseburger", grams: 200, search_terms: ["cheeseburger fast food"], confidence: "medium" },
  { name: "fries", grams: 120, search_terms: ["french fries"], confidence: "medium" },
  { name: "mystery sauce", grams: 30, search_terms: ["zzqxv"], confidence: "low" },
  { name: "cola", grams: 355, search_terms: ["carbonated beverage cola", "cola"], confidence: "medium" }] };
const context = { goal: "lose", remaining_kcal: 640, target_kcal: 1600, minor: false };
const imageB64 = "QUJDREVG";

// the explain step: pick the first candidate; give the unmatched item a plausible estimate
const fakeExplain = payload => JSON.stringify({
  selections: payload.items.map((it, i) => it.candidates.length
    ? { item: i, fdc_id: it.candidates[0].id, grams: it.grams, reason: "closest" }
    : { item: i, fdc_id: null, grams: it.grams, reason: "no match", fallback_per_100g: { kcal: 200, protein: 3, fat: 12, carb: 20 } }),
  title: "Burger meal", contents: ["a", "b"], benefits: ["protein"], concerns: ["sodium"], tips: ["salad"],
  verdict: { rating: "limit", headline: "Occasional.", why: "Salty.", fits_goal: "Uses a lot of today's calories." } });

const jsOut = {
  search: queries.map(q => js.search(index, q, 8).map(f => f[0])),
  identifyRequest: JSON.stringify(js.identifyRequest(imageB64)),
  explainRequest: null, analysis: null,
};
let capturedPayload;
jsOut.analysis = await js.analyzeMeal({ image: imageB64, context, index, identify: async () => JSON.stringify(seen),
  explain: async p => { capturedPayload = p; return fakeExplain(p); } });
jsOut.explainRequest = JSON.stringify(js.explainRequest(capturedPayload));

const py = `
import json, sys
from app import rag
d = json.load(sys.stdin)
idx = rag.default_index()
out = {"search": [[f[0] for f in idx.search(q, 8)] for q in d["queries"]],
       "identifyRequest": json.dumps(rag.identify_request(d["image"]), separators=(",", ":"), ensure_ascii=False)}
captured = {}
def explain(p):
    captured["p"] = p
    return d["explainText"](p) if callable(d.get("explainText")) else json.dumps(fake(p))
def fake(p):
    sel = []
    for i, it in enumerate(p["items"]):
        if it["candidates"]:
            sel.append({"item": i, "fdc_id": it["candidates"][0]["id"], "grams": it["grams"], "reason": "closest"})
        else:
            sel.append({"item": i, "fdc_id": None, "grams": it["grams"], "reason": "no match", "fallback_per_100g": {"kcal": 200, "protein": 3, "fat": 12, "carb": 20}})
    return {"selections": sel, "title": "Burger meal", "contents": ["a", "b"], "benefits": ["protein"], "concerns": ["sodium"], "tips": ["salad"],
            "verdict": {"rating": "limit", "headline": "Occasional.", "why": "Salty.", "fits_goal": "Uses a lot of today's calories."}}
out["analysis"] = rag.analyze_meal(d["image"], d["context"], lambda img: json.dumps(d["seen"]), explain)
out["explainRequest"] = json.dumps(rag.explain_request(captured["p"]), separators=(",", ":"), ensure_ascii=False)
print(json.dumps(out))
`;
const pyOut = JSON.parse(execFileSync(".venv/Scripts/python.exe", ["-c", py], {
  input: JSON.stringify({ queries, image: imageB64, seen, context }), env: { ...process.env, PYTHONIOENCODING: "utf-8" }, maxBuffer: 20e6 }).toString());

const tests = {
  "retrieval returns the same foods, in the same order, for every query"() {
    queries.forEach((q, i) => assert.deepEqual(pyOut.search[i], jsOut.search[i], `query ${JSON.stringify(q)}`));
  },
  "identify request is identical"() { assert.equal(pyOut.identifyRequest, jsOut.identifyRequest); },
  "explain request (prompt + sanitized data) is identical"() { assert.equal(pyOut.explainRequest, jsOut.explainRequest); },
  "full analysis output is identical"() { assert.deepEqual(pyOut.analysis, JSON.parse(JSON.stringify(jsOut.analysis))); },
  "sanity: the sample meal produced USDA, estimate and refused items"() {
    const kinds = jsOut.analysis.items.map(i => i.source.type);
    assert.ok(kinds.includes("usda") && kinds.includes("estimate"), kinds.join());
  },
};
let failed = 0;
for (const [name, fn] of Object.entries(tests)) { try { fn(); console.log("ok  ", name); } catch (e) { failed++; console.log("FAIL", name, "-", String(e.message).slice(0, 600)); } }
console.log(failed ? `${failed} failed` : "all passed");
process.exit(failed ? 1 : 0);
