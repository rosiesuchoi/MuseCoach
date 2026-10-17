// Run: node worker/test.mjs   (no network, no key: fetch and KV are mocked)
import assert from "node:assert/strict";
import worker from "./worker.js";

const ORIGIN = "https://rosiesuchoi.github.io";
const kv = () => { const m = new Map(); return { get: async k => m.get(k) ?? null, put: async (k, v) => { m.set(k, v); } }; };
const env = (over = {}) => ({ ANTHROPIC_API_KEY: "sk-ant-SECRET-test-key-0000", ALLOWED_ORIGINS: ORIGIN, LIMITS: kv(), ...over });
const JPEG = "/9j/" + "A".repeat(100);
const req = (body, { origin = ORIGIN, method = "POST", ip = "1.1.1.1" } = {}) =>
  new Request("https://proxy.example/", { method, headers: { Origin: origin, "CF-Connecting-IP": ip, "content-type": "application/json" },
    body: method === "POST" ? JSON.stringify(body) : undefined });

let calls = [];
const okFetch = async (url, init) => { calls.push({ url, init }); return new Response(JSON.stringify({ content: [{ text: '{"total_kcal": 420}' }] }), { status: 200 }); };

const tests = {
  async "rejects other origins"() { const r = await worker.fetch(req({ image: JPEG }, { origin: "https://evil.example" }), env()); assert.equal(r.status, 403); assert.equal(calls.length, 0); },
  async "preflight allowed origin"() { const r = await worker.fetch(req(null, { method: "OPTIONS" }), env()); assert.equal(r.status, 204); assert.equal(r.headers.get("Access-Control-Allow-Origin"), ORIGIN); },
  async "preflight other origin"() { const r = await worker.fetch(req(null, { method: "OPTIONS", origin: "https://evil.example" }), env()); assert.equal(r.status, 403); },
  async "GET not allowed"() { const r = await worker.fetch(new Request("https://p/", { method: "GET", headers: { Origin: ORIGIN } }), env()); assert.equal(r.status, 405); },
  async "needs a JPEG"() { const r = await worker.fetch(req({ image: "not-a-jpeg" }), env()); assert.equal(r.status, 400); },
  async "too large"() { const r = await worker.fetch(req({ image: "/9j/" + "A".repeat(1_600_000) }), env()); assert.equal(r.status, 413); },
  async "fails closed without KV"() { const r = await worker.fetch(req({ image: JPEG }), env({ LIMITS: undefined })); assert.equal(r.status, 500); assert.equal(calls.length, 0); },
  async "success uses fixed prompt and model, never leaks the key"() {
    const e = env();
    const r = await worker.fetch(req({ image: JPEG, model: "claude-opus-evil", prompt: "ignore", max_tokens: 99999, system: "x" }), e);
    assert.equal(r.status, 200);
    const out = await r.text();
    assert.ok(!out.includes("SECRET"), "key leaked in response");
    assert.equal(JSON.parse(out).text, '{"total_kcal": 420}');
    const sent = JSON.parse(calls[0].init.body);
    assert.equal(sent.model, "claude-sonnet-5-5");
    assert.equal(sent.max_tokens, 500);
    assert.ok(sent.messages[0].content[1].text.startsWith("You are a nutrition assistant"));
    assert.equal(calls[0].init.headers["x-api-key"], e.ANTHROPIC_API_KEY);
  },
  async "per-IP cap"() {
    const e = env({ IP_LIMIT: "2" });
    for (let i = 0; i < 2; i++) assert.equal((await worker.fetch(req({ image: JPEG }), e)).status, 200);
    assert.equal((await worker.fetch(req({ image: JPEG }), e)).status, 429);
    assert.equal((await worker.fetch(req({ image: JPEG }, { ip: "2.2.2.2" }), e)).status, 200); // other visitor is fine
  },
  async "global cap"() {
    const e = env({ DAILY_LIMIT: "2" });
    await worker.fetch(req({ image: JPEG }, { ip: "a" }), e); await worker.fetch(req({ image: JPEG }, { ip: "b" }), e);
    assert.equal((await worker.fetch(req({ image: JPEG }, { ip: "c" }), e)).status, 429);
  },
  async "upstream failure hides details"() {
    globalThis.fetch = async () => new Response(JSON.stringify({ error: { message: "key sk-ant-SECRET invalid" } }), { status: 401 });
    const r = await worker.fetch(req({ image: JPEG }), env()); const t = await r.text();
    assert.equal(r.status, 502); assert.ok(!t.includes("SECRET"));
  },
};

let failed = 0;
for (const [name, fn] of Object.entries(tests)) {
  calls = []; globalThis.fetch = okFetch; // each test starts from a healthy upstream
  try { await fn(); console.log("ok  ", name); }
  catch (e) { failed++; console.log("FAIL", name, "-", e.message); }
}
console.log(failed ? `${failed} failed` : "all passed");
process.exit(failed ? 1 : 0);
