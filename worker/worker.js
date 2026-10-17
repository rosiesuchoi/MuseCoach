// Muse Coach photo proxy (Cloudflare Worker).
//
// Why it exists: the GitHub Pages site is public, so a key placed in its code would be public.
// This Worker holds the Anthropic key as a secret, so it never reaches any browser.
//
// What keeps it from being abused (a public endpoint that spends your money):
//  - The prompt, model and max_tokens are fixed HERE. Callers only send a JPEG, so it can't be used
//    as a free general-purpose Claude relay.
//  - Only the listed origins get CORS access (stops other websites using it from a browser).
//  - Per-IP and global daily caps, kept in KV. If KV isn't configured it refuses to run (fails closed).
//  - Small JPEG-only uploads. Upstream errors are never forwarded to the caller.
// Also set a monthly spend limit on the key in the Anthropic console: that is the hard backstop.

const MODEL = "claude-sonnet-5-5";
const MAX_B64_CHARS = 1_500_000; // the app sends a ~1024px JPEG, which is far smaller than this
const PROMPT =
  "You are a nutrition assistant. Look at this meal photo and estimate calories. Reply with ONLY JSON: " +
  '{"meal_name": str, "items": [{"name": str, "kcal": int}], "total_kcal": int, "confidence": "low"|"medium"|"high"}. ' +
  "If the photo does not show food, return total_kcal 0 and meal_name 'No food found'.";

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";
    const allowed = (env.ALLOWED_ORIGINS || "").split(",").map(s => s.trim()).filter(Boolean);
    const originOk = allowed.includes(origin);
    const cors = originOk
      ? { "Access-Control-Allow-Origin": origin, "Access-Control-Allow-Methods": "POST, OPTIONS",
          "Access-Control-Allow-Headers": "content-type", "Access-Control-Max-Age": "86400", Vary: "Origin" }
      : {};
    const reply = (status, body) =>
      new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", ...cors } });

    if (request.method === "OPTIONS") return new Response(null, { status: originOk ? 204 : 403, headers: cors });
    if (request.method !== "POST") return reply(405, { error: "POST only" });
    if (!originOk) return reply(403, { error: "origin not allowed" });
    if (!env.ANTHROPIC_API_KEY || !env.LIMITS) return reply(500, { error: "server not configured" });

    let image;
    try { ({ image } = await request.json()); } catch { return reply(400, { error: "bad json" }); }
    if (typeof image !== "string" || !image.startsWith("/9j/")) return reply(400, { error: "send a base64 JPEG" });
    if (image.length > MAX_B64_CHARS) return reply(413, { error: "image too large" });

    // Count before calling the model so parallel requests can't slip past the cap.
    // KV is not atomic, so these caps are approximate. That is fine for a cost guard.
    const day = new Date().toISOString().slice(0, 10);
    const ip = request.headers.get("CF-Connecting-IP") || "unknown";
    const globalLimit = Number(env.DAILY_LIMIT || 150), ipLimit = Number(env.IP_LIMIT || 15);
    for (const [key, limit] of [[`g:${day}`, globalLimit], [`ip:${day}:${ip}`, ipLimit]]) {
      const used = Number(await env.LIMITS.get(key)) || 0;
      if (used >= limit) return reply(429, { error: "daily limit reached" });
      await env.LIMITS.put(key, String(used + 1), { expirationTtl: 172800 });
    }

    let upstream;
    try {
      upstream = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: { "content-type": "application/json", "x-api-key": env.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01" },
        body: JSON.stringify({
          model: MODEL, max_tokens: 500,
          messages: [{ role: "user", content: [
            { type: "image", source: { type: "base64", media_type: "image/jpeg", data: image } },
            { type: "text", text: PROMPT }] }],
        }),
      });
    } catch { return reply(502, { error: "upstream unreachable" }); }
    if (!upstream.ok) return reply(502, { error: "upstream error" });
    const data = await upstream.json();
    return reply(200, { text: data.content?.[0]?.text ?? "" });
  },
};
