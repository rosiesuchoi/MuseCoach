"""Meal-analysis pipeline for the server edition: photo -> identify (Claude vision) -> retrieve (USDA knowledge base)
-> explain (Claude, grounded in the retrieved numbers) -> compute (code).

This is a Python port of shared/pipeline.mjs (which the Pages edition runs in the browser). The prompts come from
shared/prompts.json so both send identical instructions, and tools/pipeline_parity.mjs checks that retrieval returns
the same foods in both languages. If you change the logic here, change it there too.

The model never supplies the numbers: totals are grams x USDA nutrients-per-100g computed in code, a database id the
model returns must be one we actually retrieved, and model estimates are only accepted if they agree with their own macros.
"""

from __future__ import annotations

import json
import math
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL = "claude-sonnet-5-5"
# Generous on purpose: the model may spend part of the budget on a "thinking" block before the JSON answer.
MAX_TOKENS_IDENTIFY = 2500
MAX_TOKENS_EXPLAIN = 4000
NUTRIENTS = ["kcal", "protein", "fat", "satfat", "carb", "fiber", "sugar", "sodium", "chol", "potassium", "calcium", "iron", "vitc", "caffeine", "alcohol"]
CONF_RANK = {"low": 0, "medium": 1, "high": 2}
SOURCES = "USDA FoodData Central, SR Legacy (public domain)"


class PipelineError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def js_round(x: float) -> int:
    """JavaScript's Math.round (halves round up), so results match the browser edition exactly."""
    return math.floor(x + 0.5)


def clip(s, n: int) -> str:
    return re.sub(r"[\x00-\x1f]", " ", "" if s is None else str(s))[:n]


@lru_cache(maxsize=1)
def prompts() -> dict:
    return json.loads((ROOT / "shared" / "prompts.json").read_text(encoding="utf-8"))


# ---------- requests to the model ----------

def _js_numbers(obj):
    """Whole-number floats print as 120 (not 120.0), exactly as JSON.stringify would, so the model sees the same text from both editions."""
    if isinstance(obj, float) and obj.is_integer():
        return int(obj)
    if isinstance(obj, dict):
        return {k: _js_numbers(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_js_numbers(v) for v in obj]
    return obj


def identify_request(image_b64: str) -> dict:
    return {
        "model": MODEL, "max_tokens": MAX_TOKENS_IDENTIFY,
        "messages": [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}},
            {"type": "text", "text": prompts()["identify"]}]}],
    }


def explain_request(payload: dict) -> dict:
    items = []
    for i, it in enumerate((payload.get("items") or [])[:8]):
        cands = [{"fdc_id": int(c.get("id") or 0), "description": clip(c.get("d"), 120), "per_100g": c.get("per100g"),
                  "example_portions": (c.get("portions") or [])[:2], "at_estimated_grams": c.get("at_grams")}
                 for c in (it.get("candidates") or [])[:8]]
        items.append({"item": i, "name": clip(it.get("name"), 80), "grams": js_round(float(it.get("grams") or 0)), "candidates": cands})
    c = payload.get("context") or {}
    context = {
        "goal": c.get("goal") if c.get("goal") in ("lose", "maintain", "build") else "maintain",
        "remaining_calories_today": js_round(c["remaining_kcal"]) if isinstance(c.get("remaining_kcal"), (int, float)) else None,
        "daily_target_calories": js_round(c["target_kcal"]) if isinstance(c.get("target_kcal"), (int, float)) else None,
        "minor": c.get("minor") is True,
    }
    data = json.dumps(_js_numbers({"items": items, "user_context": context}), separators=(",", ":"), ensure_ascii=False)
    return {"model": MODEL, "max_tokens": MAX_TOKENS_EXPLAIN,
            "messages": [{"role": "user", "content": f"{prompts()['explain']}\n\nDATA:\n{data}"}]}


# ---------- retrieval over the USDA index ----------

STOP = {"and", "with", "the", "of", "in", "a", "an", "or", "for", "style", "type"}


def _stem(w: str) -> str:
    return w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w


def tokenize(s: str) -> list[str]:
    return [_stem(w) for w in re.sub(r"[^a-z0-9]+", " ", str(s).lower()).split(" ") if w and w not in STOP]


class Index:
    def __init__(self, kb: dict):
        self.kb = kb
        self.df: dict[str, int] = {}
        self.docs = []
        for f in kb["foods"]:
            tokens = set(tokenize(f[1]))
            for t in tokens:
                self.df[t] = self.df.get(t, 0) + 1
            self.docs.append((tokens, set(tokenize(f[1].split(",")[0])), len(tokens)))
        self.n = len(self.docs)

    def search(self, phrases: list[str], k: int = 8) -> list[list]:
        best: dict[int, float] = {}
        for phrase in phrases:
            q = list(dict.fromkeys(tokenize(phrase)))
            if not q:
                continue
            idf = {t: math.log(1 + self.n / (1 + self.df.get(t, 0))) for t in q}
            total = sum(idf.values())
            for i, (tokens, first, length) in enumerate(self.docs):
                hit = first_hit = 0.0
                for t in q:
                    if t in tokens:
                        hit += idf[t]
                        if t in first:
                            first_hit += 1
                coverage = hit / total
                if coverage < 0.5:  # too weak a match to show to the model
                    continue
                score = coverage + 0.3 * (first_hit / len(q)) - 0.002 * length
                if score > best.get(i, -1):
                    best[i] = score
        top = sorted(best.items(), key=lambda kv: kv[1], reverse=True)[:k]  # stable, like JS
        return [self.kb["foods"][i] for i, _ in top]


@lru_cache(maxsize=1)
def default_index() -> Index:
    return Index(json.loads((ROOT / "app" / "data" / "nutrition.json").read_text(encoding="utf-8")))


def per100(food: list, kb: dict) -> dict:
    return dict(zip(kb["nutrients"], food[3]))


def scale(p100: dict, grams: float) -> dict:
    return {k: (None if v is None else js_round(v * grams) / 100) for k, v in p100.items()}


# ---------- deterministic flags (label-style thresholds, per meal) ----------

def flags_for(t: dict) -> list[dict]:
    flags = []

    def add(key, label, level, detail):
        flags.append({"key": key, "label": label, "level": level, "detail": detail})

    g = lambda k: t.get(k) or 0  # noqa: E731
    if g("sodium") >= 460:
        add("sodium", "High sodium", "watch", f"{js_round(t['sodium'])} mg is over 20% of the 2,300 mg daily limit")
    if g("satfat") >= 4:
        add("satfat", "High saturated fat", "watch", f"{t['satfat']:.1f} g is over 20% of the 20 g daily reference")
    if g("sugar") >= 15:
        add("sugar", "Lots of sugar", "watch", f"{js_round(t['sugar'])} g of sugars (natural and added)")
    if g("caffeine") >= 100:
        add("caffeine", "Caffeine", "info", f"about {js_round(t['caffeine'])} mg")
    if g("alcohol") >= 1:
        add("alcohol", "Contains alcohol", "info", f"about {t['alcohol']:.0f} g of alcohol")
    if g("fiber") >= 5.5:
        add("fiber", "High fiber", "good", f"{t['fiber']:.1f} g is over 20% of the daily value")
    if g("protein") >= 20:
        add("protein", "Good protein", "good", f"{js_round(t['protein'])} g")
    return flags


# ---------- helpers ----------

def parse_json(text) -> dict:
    m = re.search(r"\{.*\}", str(text or ""), re.S)
    if not m:
        raise PipelineError(502, "The AI's answer came back in an unexpected format. Try again.")
    try:
        return json.loads(m.group(0))
    except ValueError:
        raise PipelineError(502, "The AI's answer came back in an unexpected format. Try again.") from None


def _num(v, lo, hi, fallback=None):
    try:
        n = float(v)
    except (TypeError, ValueError):
        return fallback
    return n if math.isfinite(n) and lo <= n <= hi else fallback


def _str_list(v, mx, length=220):
    return [s for s in (clip(x, length) for x in (v if isinstance(v, list) else [])) if s][:mx]


def _plausible_estimate(e):
    """A model-supplied estimate is only accepted when its calories agree with its own macros (4/4/9 rule, +-40%)."""
    if not isinstance(e, dict):
        return None
    kcal, p, f, c = (_num(e.get(k), 0, hi) for k, hi in (("kcal", 900), ("protein", 100), ("fat", 100), ("carb", 100)))
    if None in (kcal, p, f, c):
        return None
    from_macros = 4 * p + 4 * c + 9 * f
    if kcal > 20 and (from_macros < 0.6 * kcal or from_macros > 1.4 * kcal):
        return None
    return {"kcal": kcal, "protein": p, "fat": f, "carb": c}


# ---------- the pipeline ----------

def analyze_meal(image: str, context: dict, identify, explain, index: Index | None = None) -> dict:
    """identify(image_b64) -> text and explain(payload) -> text are supplied by the caller (see anthropic_functions)."""
    index = index or default_index()
    kb = index.kb

    # 1. IDENTIFY
    seen = parse_json(identify(image))
    raw_items = seen.get("items") if isinstance(seen.get("items"), list) else []
    raw_items = raw_items[:8]
    if seen.get("is_food") is False or not raw_items:
        reason = f" ({clip(seen.get('reason'), 120)})" if seen.get("reason") else ""
        raise PipelineError(422, f"I can't see food or a drink in that photo{reason}. Try a closer shot, or enter it by hand.")
    items = []
    for it in raw_items:
        it = it if isinstance(it, dict) else {}
        terms = it.get("search_terms") if isinstance(it.get("search_terms"), list) and it.get("search_terms") else [it.get("name")]
        items.append({
            "name": clip(it.get("name"), 80) or "Food item",
            "grams": _num(it.get("grams"), 1, 2000, 100),
            "terms": [clip(t, 60) for t in terms][:3],
            "confidence": it.get("confidence") if it.get("confidence") in CONF_RANK else "low",
        })

    # 2. RETRIEVE
    retrieved = [index.search([*it["terms"], it["name"]]) for it in items]
    payload = {"context": context, "items": []}
    for it, foods in zip(items, retrieved):
        cands = []
        for f in foods:
            p = per100(f, kb)
            slim = {k: p[k] for k in ("kcal", "protein", "fat", "satfat", "carb", "fiber", "sugar", "sodium")}
            cands.append({"id": f[0], "d": f[1], "per100g": slim, "portions": f[4], "at_grams": {"kcal": js_round(p["kcal"] * it["grams"]) / 100}})
        payload["items"].append({"name": it["name"], "grams": it["grams"], "candidates": cands})

    # 3. EXPLAIN (grounded in the retrieved candidates)
    out = parse_json(explain(payload))

    # 4. COMPUTE: totals come from database numbers, never from the model's prose
    picks = out.get("selections") if isinstance(out.get("selections"), list) else []
    lines = []
    for i, it in enumerate(items):
        sel = next((s for s in picks if isinstance(s, dict) and _num(s.get("item"), -1e9, 1e9) == i), {})
        grams = _num(sel.get("grams"), 1, 2000, it["grams"])
        wanted = _num(sel.get("fdc_id"), -1e12, 1e12)
        food = next((f for f in retrieved[i] if wanted is not None and f[0] == wanted), None)  # must be one we retrieved
        if food:
            n = scale(per100(food, kb), grams)
            lines.append({"name": it["name"], "grams": grams, "kcal": js_round(n["kcal"]), "nutrients": n,
                          "source": {"type": "usda", "fdc_id": food[0], "description": food[1]}, "confidence": it["confidence"], "reason": clip(sel.get("reason"), 160)})
            continue
        est = _plausible_estimate(sel.get("fallback_per_100g"))
        if est:
            n = scale({**dict.fromkeys(NUTRIENTS), **est}, grams)
            lines.append({"name": it["name"], "grams": grams, "kcal": js_round(n["kcal"]), "nutrients": n,
                          "source": {"type": "estimate"}, "confidence": "low", "reason": clip(sel.get("reason"), 160)})
            continue
        lines.append({"name": it["name"], "grams": grams, "kcal": None, "nutrients": None, "source": {"type": "none"}, "confidence": "low",
                      "reason": "No reliable nutrition data found for this item."})

    priced = [ln for ln in lines if ln["kcal"] is not None]
    if not priced:
        raise PipelineError(422, "I couldn't work out calories for that. Try another photo, or enter it by hand.")
    totals = {}
    for k in NUTRIENTS:
        vals = [ln["nutrients"][k] for ln in priced if ln["nutrients"][k] is not None]
        totals[k] = js_round(sum(vals) * 100) / 100 if vals else None
    total_kcal = js_round(totals["kcal"])
    if total_kcal > 5000:
        raise PipelineError(422, "That estimate looked too large to be right. Try another photo, or enter it by hand.")

    grounded = sum(ln["kcal"] for ln in priced if ln["source"]["type"] == "usda")
    share = grounded / total_kcal if total_kcal > 0 else 1
    weakest = min(CONF_RANK[ln["confidence"]] for ln in lines)
    verdict = out.get("verdict") if isinstance(out.get("verdict"), dict) else {}
    return {
        "meal_name": clip(out.get("title"), 80) or ", ".join(i["name"] for i in items)[:80],
        "items": lines, "total_kcal": total_kcal, "totals": totals,
        # The model can see what the food is, but amounts are always an estimate, so this is never "high".
        "confidence": "low" if weakest == 0 or share < 0.7 or any(ln["kcal"] is None for ln in lines) else "medium",
        "kcal_range": [js_round(total_kcal * 0.75), js_round(total_kcal * 1.25)],
        "grounded_share": js_round(share * 100) / 100,
        "flags": flags_for(totals),
        "insight": {
            "contents": _str_list(out.get("contents"), 8), "benefits": _str_list(out.get("benefits"), 4),
            "concerns": _str_list(out.get("concerns"), 4), "tips": _str_list(out.get("tips"), 3),
            "verdict": {
                "rating": verdict.get("rating") if verdict.get("rating") in ("good", "okay", "limit") else "okay",
                "headline": clip(verdict.get("headline"), 160), "why": clip(verdict.get("why"), 300), "fits_goal": clip(verdict.get("fits_goal"), 220),
            },
        },
        "method": "ai-rag", "demo": False, "sources": SOURCES,
    }


# ---------- talking to Anthropic with the key from the environment ----------

def reply_text(msg) -> str:
    """The answer text. Replies can begin with a "thinking" block, so join the text blocks instead of taking block 0."""
    if getattr(msg, "stop_reason", None) == "max_tokens":
        raise PipelineError(502, "The AI's answer was cut off. Try again.")
    return "".join(b.text for b in (msg.content or []) if getattr(b, "type", None) == "text")


def anthropic_functions(api_key: str):
    """Returns (identify, explain) callables that call Claude with this key. Errors are translated to
    PipelineError with fixed messages, so no request details (and never the key) can leak into a response."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key, max_retries=1, timeout=60)

    def call(body: dict) -> str:
        try:
            msg = client.messages.create(**body)
        except anthropic.AuthenticationError:
            raise PipelineError(502, "The Anthropic API key was rejected. Check the key in your .env file.") from None
        except anthropic.PermissionDeniedError:
            raise PipelineError(502, "That Anthropic key isn't allowed to use this model or feature.") from None
        except anthropic.RateLimitError:
            raise PipelineError(429, "The AI service is rate-limiting this key. Wait a minute and try again.") from None
        except anthropic.APIConnectionError:
            raise PipelineError(502, "Couldn't reach the AI service. Check your internet connection.") from None
        except anthropic.APIError:
            raise PipelineError(502, "Couldn't analyze that photo right now. Enter calories by hand.") from None
        return reply_text(msg)

    return (lambda image: call(identify_request(image)), lambda payload: call(explain_request(payload)))
