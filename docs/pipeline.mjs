// Muse Coach meal-analysis pipeline: photo -> identify (Claude vision) -> retrieve (USDA knowledge base)
// -> explain (Claude, grounded in the retrieved numbers).
//
// This is a RAG design: the model never recalls nutrition from memory for the numbers.
//  1. IDENTIFY  Claude looks at the photo and lists each food/drink with an estimated amount and search phrases.
//  2. RETRIEVE  Code searches the bundled USDA FoodData Central index (public domain) for each item.
//  3. EXPLAIN   Claude picks the best match per item from the retrieved candidates and writes the explanation.
//  4. COMPUTE   Code (not the model) multiplies grams x nutrients-per-100g and adds up totals and flags.
//
// Used by the browser (the Pages edition). The Python server edition has the same pipeline in app/rag.py; the
// prompts live in prompts.json so both send identical instructions, and tools/pipeline_parity.mjs checks that
// retrieval agrees. Keep this file free of DOM / Node APIs.

import PROMPTS from "./prompts.mjs";

export const MODEL = "claude-sonnet-5-5";
// Generous on purpose: the model may spend part of the budget on a "thinking" block before the JSON answer.
export const MAX_TOKENS_IDENTIFY = 2500;
export const MAX_TOKENS_EXPLAIN = 4000;

// The answer text of a Messages API reply. Replies can begin with a "thinking" block, so join the text blocks instead of taking block 0.
export function replyText(body) {
  if (body && body.stop_reason === "max_tokens") throw new PipelineError(502, "The AI's answer was cut off. Try again.");
  return ((body && body.content) || []).filter(b => b.type === "text").map(b => b.text).join("");
}
export const NUTRIENTS = ["kcal", "protein", "fat", "satfat", "carb", "fiber", "sugar", "sodium", "chol", "potassium", "calcium", "iron", "vitc", "caffeine", "alcohol"];

export class PipelineError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

const clip = (s, n) => String(s ?? "").replace(/[\u0000-\u001f]/g, " ").slice(0, n);

export function identifyRequest(imageB64) {
  return {
    model: MODEL, max_tokens: MAX_TOKENS_IDENTIFY,
    messages: [{ role: "user", content: [
      { type: "image", source: { type: "base64", media_type: "image/jpeg", data: imageB64 } },
      { type: "text", text: PROMPTS.identify }] }],
  };
}

// payload: { items:[{name, grams, candidates:[{id, d, per100g:{...}, portions:[[label,g]], at_grams:{...}}]}], context:{goal, remaining_kcal, target_kcal, minor} }
export function explainRequest(payload) {
  const items = (payload.items || []).slice(0, 8).map((it, i) => ({
    item: i, name: clip(it.name, 80), grams: Math.round(Number(it.grams) || 0),
    candidates: (it.candidates || []).slice(0, 8).map(c => ({
      fdc_id: Number(c.id) || 0, description: clip(c.d, 120), per_100g: c.per100g, example_portions: (c.portions || []).slice(0, 2),
      at_estimated_grams: c.at_grams,
    })),
  }));
  const c = payload.context || {};
  const context = {
    goal: ["lose", "maintain", "build"].includes(c.goal) ? c.goal : "maintain",
    remaining_calories_today: Number.isFinite(c.remaining_kcal) ? Math.round(c.remaining_kcal) : null,
    daily_target_calories: Number.isFinite(c.target_kcal) ? Math.round(c.target_kcal) : null,
    minor: c.minor === true,
  };
  return {
    model: MODEL, max_tokens: MAX_TOKENS_EXPLAIN,
    messages: [{ role: "user", content: `${PROMPTS.explain}\n\nDATA:\n${JSON.stringify({ items, user_context: context })}` }],
  };
}

// ---------- retrieval over the USDA index ----------

const STOP = new Set(["and", "with", "the", "of", "in", "a", "an", "or", "for", "style", "type"]);
const stem = w => (w.length > 3 && w.endsWith("s") && !w.endsWith("ss") ? w.slice(0, -1) : w);
export const tokenize = s => String(s).toLowerCase().replace(/[^a-z0-9]+/g, " ").split(" ").filter(w => w && !STOP.has(w)).map(stem);

export function buildIndex(kb) {
  const df = new Map(), docs = kb.foods.map((f, i) => {
    const tokens = new Set(tokenize(f[1]));
    for (const t of tokens) df.set(t, (df.get(t) || 0) + 1);
    return { i, tokens, first: new Set(tokenize(f[1].split(",")[0])), len: tokens.size };
  });
  return { kb, docs, df, n: docs.length };
}

// Returns up to k foods for the given search phrases, best first.
export function search(index, phrases, k = 8) {
  const best = new Map();
  for (const phrase of phrases) {
    const q = [...new Set(tokenize(phrase))];
    if (!q.length) continue;
    const idf = t => Math.log(1 + index.n / (1 + (index.df.get(t) || 0)));
    const total = q.reduce((a, t) => a + idf(t), 0);
    for (const d of index.docs) {
      let hit = 0, firstHit = 0;
      for (const t of q) if (d.tokens.has(t)) { hit += idf(t); if (d.first.has(t)) firstHit += 1; }
      const coverage = hit / total;
      if (coverage < 0.5) continue; // too weak a match to show to the model
      // coverage dominates; a hit in the name's first segment ("Pizza, ...") and a shorter, less qualified entry win ties
      const score = coverage + 0.3 * (firstHit / q.length) - 0.002 * d.len;
      if (score > (best.get(d.i) ?? -1)) best.set(d.i, score);
    }
  }
  return [...best.entries()].sort((a, b) => b[1] - a[1]).slice(0, k).map(([i]) => index.kb.foods[i]);
}

export const per100 = (food, kb) => Object.fromEntries(kb.nutrients.map((n, j) => [n, food[3][j]]));
export const scale = (p100, grams) => Object.fromEntries(Object.entries(p100).map(([k, v]) => [k, v == null ? null : Math.round(v * grams) / 100]));

// ---------- deterministic flags (FDA "high = 20% of Daily Value" style thresholds, per meal) ----------

export function flagsFor(t) {
  const flags = [];
  const add = (key, label, level, detail) => flags.push({ key, label, level, detail });
  if ((t.sodium ?? 0) >= 460) add("sodium", "High sodium", "watch", `${Math.round(t.sodium)} mg is over 20% of the 2,300 mg daily limit`);
  if ((t.satfat ?? 0) >= 4) add("satfat", "High saturated fat", "watch", `${t.satfat.toFixed(1)} g is over 20% of the 20 g daily reference`);
  if ((t.sugar ?? 0) >= 15) add("sugar", "Lots of sugar", "watch", `${Math.round(t.sugar)} g of sugars (natural and added)`);
  if ((t.caffeine ?? 0) >= 100) add("caffeine", "Caffeine", "info", `about ${Math.round(t.caffeine)} mg`);
  if ((t.alcohol ?? 0) >= 1) add("alcohol", "Contains alcohol", "info", `about ${t.alcohol.toFixed(0)} g of alcohol`);
  if ((t.fiber ?? 0) >= 5.5) add("fiber", "High fiber", "good", `${t.fiber.toFixed(1)} g is over 20% of the daily value`);
  if ((t.protein ?? 0) >= 20) add("protein", "Good protein", "good", `${Math.round(t.protein)} g`);
  return flags;
}

// ---------- helpers ----------

export function parseJson(text) {
  const m = String(text ?? "").match(/\{[\s\S]*\}/);
  if (!m) throw new PipelineError(502, "The AI's answer came back in an unexpected format. Try again.");
  try { return JSON.parse(m[0]); } catch { throw new PipelineError(502, "The AI's answer came back in an unexpected format. Try again."); }
}

const num = (v, lo, hi, fallback = null) => { const n = Number(v); return Number.isFinite(n) && n >= lo && n <= hi ? n : fallback; };
const strList = (v, max, len = 220) => (Array.isArray(v) ? v : []).map(s => clip(s, len)).filter(Boolean).slice(0, max);

// A model-supplied estimate is only accepted when its calories agree with its own macros (4/4/9 rule, +-40%).
function plausibleEstimate(e) {
  if (!e) return null;
  const kcal = num(e.kcal, 0, 900), p = num(e.protein, 0, 100), f = num(e.fat, 0, 100), c = num(e.carb, 0, 100);
  if ([kcal, p, f, c].some(v => v === null)) return null;
  const fromMacros = 4 * p + 4 * c + 9 * f;
  if (kcal > 20 && (fromMacros < 0.6 * kcal || fromMacros > 1.4 * kcal)) return null;
  return { kcal, protein: p, fat: f, carb: c };
}

const CONF_RANK = { low: 0, medium: 1, high: 2 };

// ---------- the pipeline ----------

// identify(imageB64) -> text, explain(payload) -> text : supplied by the caller (a direct call to Anthropic with the user's own key).
export async function analyzeMeal({ image, context = {}, identify, explain, index }) {
  const kb = index.kb;

  // 1. IDENTIFY
  const seen = parseJson(await identify(image));
  const rawItems = Array.isArray(seen.items) ? seen.items.slice(0, 8) : [];
  if (seen.is_food === false || !rawItems.length) {
    throw new PipelineError(422, `I can't see food or a drink in that photo${seen.reason ? ` (${clip(seen.reason, 120)})` : ""}. Try a closer shot, or enter it by hand.`);
  }
  const items = rawItems.map(it => ({
    name: clip(it.name, 80) || "Food item",
    grams: num(it.grams, 1, 2000, 100),
    terms: (Array.isArray(it.search_terms) && it.search_terms.length ? it.search_terms : [it.name]).map(t => clip(t, 60)).slice(0, 3),
    confidence: it.confidence in CONF_RANK ? it.confidence : "low",
  }));

  // 2. RETRIEVE
  const retrieved = items.map(it => search(index, [...it.terms, it.name]));
  const payload = {
    context,
    items: items.map((it, i) => ({
      name: it.name, grams: it.grams,
      candidates: retrieved[i].map(f => {
        const p = per100(f, kb);
        const slim = { kcal: p.kcal, protein: p.protein, fat: p.fat, satfat: p.satfat, carb: p.carb, fiber: p.fiber, sugar: p.sugar, sodium: p.sodium };
        return { id: f[0], d: f[1], per100g: slim, portions: f[4], at_grams: { kcal: Math.round(p.kcal * it.grams) / 100 } };
      }),
    })),
  };

  // 3. EXPLAIN (grounded in the retrieved candidates)
  const out = parseJson(await explain(payload));

  // 4. COMPUTE: totals come from database numbers, never from the model's prose
  const picks = Array.isArray(out.selections) ? out.selections : [];
  const lines = items.map((it, i) => {
    const sel = picks.find(s => Number(s.item) === i) || {};
    const grams = num(sel.grams, 1, 2000, it.grams);
    const food = retrieved[i].find(f => f[0] === Number(sel.fdc_id)); // must be one we actually retrieved
    if (food) {
      const n = scale(per100(food, kb), grams);
      return { name: it.name, grams, kcal: Math.round(n.kcal), nutrients: n, source: { type: "usda", fdc_id: food[0], description: food[1] }, confidence: it.confidence, reason: clip(sel.reason, 160) };
    }
    const est = plausibleEstimate(sel.fallback_per_100g);
    if (est) {
      const n = scale({ ...Object.fromEntries(NUTRIENTS.map(k => [k, null])), ...est }, grams);
      return { name: it.name, grams, kcal: Math.round(n.kcal), nutrients: n, source: { type: "estimate" }, confidence: "low", reason: clip(sel.reason, 160) };
    }
    return { name: it.name, grams, kcal: null, nutrients: null, source: { type: "none" }, confidence: "low", reason: "No reliable nutrition data found for this item." };
  });

  const priced = lines.filter(l => l.kcal !== null);
  if (!priced.length) throw new PipelineError(422, "I couldn't work out calories for that. Try another photo, or enter it by hand.");
  const totals = {};
  for (const k of NUTRIENTS) {
    const vals = priced.map(l => l.nutrients[k]).filter(v => v != null);
    totals[k] = vals.length ? Math.round(vals.reduce((a, b) => a + b, 0) * 100) / 100 : null;
  }
  const total_kcal = Math.round(totals.kcal);
  if (total_kcal > 5000) throw new PipelineError(422, "That estimate looked too large to be right. Try another photo, or enter it by hand.");

  const groundedKcal = priced.filter(l => l.source.type === "usda").reduce((a, l) => a + l.kcal, 0);
  const groundedShare = total_kcal > 0 ? groundedKcal / total_kcal : 1;
  const weakest = Math.min(...lines.map(l => CONF_RANK[l.confidence]));
  const verdict = out.verdict || {};
  return {
    meal_name: clip(out.title, 80) || items.map(i => i.name).join(", ").slice(0, 80),
    items: lines, total_kcal, totals,
    // The model can see what the food is, but amounts are always an estimate, so this is never "high".
    confidence: weakest === 0 || groundedShare < 0.7 || lines.some(l => l.kcal === null) ? "low" : "medium",
    kcal_range: [Math.round(total_kcal * 0.75), Math.round(total_kcal * 1.25)],
    grounded_share: Math.round(groundedShare * 100) / 100,
    flags: flagsFor(totals),
    insight: {
      contents: strList(out.contents, 8), benefits: strList(out.benefits, 4), concerns: strList(out.concerns, 4), tips: strList(out.tips, 3),
      verdict: {
        rating: ["good", "okay", "limit"].includes(verdict.rating) ? verdict.rating : "okay",
        headline: clip(verdict.headline, 160), why: clip(verdict.why, 300), fits_goal: clip(verdict.fits_goal, 220),
      },
    },
    method: "ai-rag", demo: false,
    sources: "USDA FoodData Central, SR Legacy (public domain)",
  };
}
