/* In-browser version of the Muse Coach API, for the GitHub Pages edition.
 *
 * GitHub Pages can't run Python, so this file re-implements app/*.py in JavaScript and
 * intercepts the UI's fetch("/api/...") calls. The UI file is shared with the server edition.
 * Keep the math in sync with app/goals.py (tools/parity_check.mjs compares them).
 * Data lives in localStorage on the user's own device; the API key never leaves the browser
 * except in calls to api.anthropic.com.
 */
(function (root) {
  // ---------- goals (mirrors app/goals.py) ----------
  const ACTIVITY = { low: 1.375, medium: 1.55, high: 1.725 };
  const LB_PER_KG = 2.2046226; // API and storage are metric; messages shown to users are in lb
  const MIN_BMI = 18.5, MAX_DEFICIT_FRACTION = 0.25, KCAL_PER_KG = 7700, SURPLUS = 250;
  const FLOOR = { female: 1200, male: 1500 };
  const MACROS = { lean_dancer: [0.28, 0.45, 0.27], sculpted: [0.32, 0.40, 0.28], athletic: [0.28, 0.45, 0.27], strong: [0.30, 0.40, 0.30] };

  class HttpError extends Error { constructor(status, detail) { super(detail); this.status = status; } }
  const r2 = x => Math.round(x * 100) / 100;
  const r1 = x => Math.round(x * 10) / 10;
  const bmi = (w, h) => w / ((h / 100) ** 2);

  function validate(p) {
    if (!(p.age >= 13 && p.age <= 100)) throw new HttpError(422, "Age must be between 13 and 100.");
    if (!(p.sex in FLOOR)) throw new HttpError(422, "Sex must be 'female' or 'male' (used only for the calorie formula).");
    if (!(p.height_cm >= 120 && p.height_cm <= 230)) throw new HttpError(422, "Height must be between 3 ft 11 in and 7 ft 7 in.");
    if (!(p.weight_kg >= 30 && p.weight_kg <= 300)) throw new HttpError(422, "Weight must be between 66 and 661 lb.");
    if (!["lose", "maintain", "build"].includes(p.goal)) throw new HttpError(422, "Goal must be lose, maintain or build.");
    if (!(p.activity in ACTIVITY)) throw new HttpError(422, "Activity must be low, medium or high.");
  }

  function buildPlan(p, archetype) {
    validate(p);
    const notes = [];
    const bmr = 10 * p.weight_kg + 6.25 * p.height_cm - 5 * p.age + (p.sex === "male" ? 5 : -161);
    const maintenance = bmr * ACTIVITY[p.activity];
    let goal = p.goal;
    if (p.age < 18 && goal === "lose") {
      goal = "maintain";
      notes.push("Under 18, so this plan keeps you at maintenance. Talk to a doctor before dieting.");
    }
    const floorWeight = MIN_BMI * (p.height_cm / 100) ** 2;
    let goalWeight = p.goal_weight_kg ?? null;
    if (goal === "lose") {
      if (bmi(p.weight_kg, p.height_cm) <= MIN_BMI + 0.3) {
        goal = "maintain";
        notes.push("You're already at the low end of a healthy weight, so we're maintaining.");
      } else if (goalWeight !== null && goalWeight < floorWeight) {
        goalWeight = r1(floorWeight);
        notes.push(`Goal weight raised to ${Math.round(goalWeight * LB_PER_KG)} lb: the lowest healthy weight for your height.`);
      }
    }
    let target, weekly;
    if (goal === "lose") {
      let deficit = Math.min(500, maintenance * MAX_DEFICIT_FRACTION);
      target = maintenance - deficit;
      const floor = FLOOR[p.sex];
      if (target < floor) {
        target = floor;
        deficit = Math.max(maintenance - floor, 0);
        notes.push(`Calories held at ${floor}, the minimum this app will ever recommend.`);
      }
      weekly = -deficit * 7 / KCAL_PER_KG;
    } else if (goal === "build") {
      target = maintenance + SURPLUS;
      weekly = SURPLUS * 7 / KCAL_PER_KG;
    } else { target = maintenance; weekly = 0; }

    const [ps, cs, fs] = MACROS[archetype] || MACROS.athletic;
    let weeks = null;
    if (goalWeight !== null && weekly) {
      const remaining = goalWeight - p.weight_kg;
      if (remaining * weekly > 0) weeks = Math.round(Math.abs(remaining / weekly));
    }
    return {
      goal, maintenance_kcal: Math.round(maintenance), target_kcal: Math.round(target),
      protein_g: Math.round(target * ps / 4), carbs_g: Math.round(target * cs / 4), fat_g: Math.round(target * fs / 9),
      weekly_change_kg: r2(weekly), goal_weight_kg: goalWeight, weeks_to_goal: weeks,
      bmi: r1(bmi(p.weight_kg, p.height_cm)), notes,
    };
  }

  // ---------- coach + meal plan (mirror app/coach.py, app/mealplan.py) ----------
  const OPENERS = { lean_dancer: "Okay, from the top!", sculpted: "Here's today's read.", athletic: "Team check-in!", strong: "Listen up." };

  function makeCore(data) {
    // Listed celebrities have a fixed archetype; anyone else gets the style the user picked (or the default).
    const archetypeFor = (name, style) => {
      const w = (name || "").trim().toLowerCase();
      const hit = data.celebrities.celebrities.find(c => c.name.toLowerCase() === w);
      if (hit) return hit.archetype;
      return style && style in data.coaches ? style : data.celebrities.default_archetype;
    };
    const checkin = (archetype, eaten, target) => {
      const coach = data.coaches[archetype].coach, remaining = target - eaten;
      let body;
      if (eaten === 0) body = `Nothing logged yet. Snap a photo of your first meal and I'll do the math. Today's target: ${target} calories.`;
      else if (remaining > target * 0.15) body = `${eaten} calories in, ${remaining} to go. You're on pace. Keep protein in every meal.`;
      else if (remaining >= -target * 0.05) body = `${eaten} calories in, right on target. That's exactly the plan.`;
      else body = `${eaten} calories in, about ${-remaining} over. No stress: one day doesn't undo a week. Tomorrow we reset.`;
      return `${coach}: ${OPENERS[archetype] || "Check-in!"} ${body}`;
    };
    const portion = (budget, kcal) => Math.min(2, Math.max(0.5, Math.round(budget / kcal * 4) / 4));
    const SHARES = [["breakfast", 0.25], ["lunch", 0.35], ["dinner", 0.30]];
    const buildWeek = target => ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((day, i) => ({
      day,
      meals: SHARES.map(([slot, share]) => {
        const opts = data.meals[slot], r = opts[(i + slot.length) % opts.length], serv = portion(target * share, r.kcal);
        return { slot, name: r.name, source: r.source, url: r.url, servings: serv, kcal: Math.round(r.kcal * serv) };
      }),
      snack_budget: Math.round(target * 0.10),
    }));
    return { archetypeFor, checkin, buildWeek, buildPlan };
  }

  // ---------- vision (mirrors app/vision.py) ----------
  const PROMPT = "You are a nutrition assistant. Look at this meal photo and estimate calories. Reply with ONLY JSON: " +
    '{"meal_name": str, "items": [{"name": str, "kcal": int}], "total_kcal": int, "confidence": "low"|"medium"|"high"}. ' +
    "If the photo does not show food, return total_kcal 0 and meal_name 'No food found'.";
  const MODEL = "claude-sonnet-5-5";

  function parseReply(text) {
    const m = text.match(/\{[\s\S]*\}/);
    if (!m) throw new HttpError(422, "The estimate came back in an unexpected format.");
    const d = JSON.parse(m[0]), total = parseInt(d.total_kcal, 10) || 0;
    if (total < 0 || total > 5000) throw new HttpError(422, "The estimate looked wrong. Try another photo or enter calories by hand.");
    return {
      meal_name: String(d.meal_name || "Meal").slice(0, 80),
      items: (d.items || []).map(i => ({ name: String(i.name || "?"), kcal: parseInt(i.kcal, 10) || 0 })),
      total_kcal: total, confidence: d.confidence || "low", demo: false,
    };
  }

  async function toJpegBase64(file) {
    let bmp;
    try { bmp = await createImageBitmap(file); } catch { throw new HttpError(422, "Couldn't read that image. Try a JPEG or PNG."); }
    const scale = Math.min(1, 1024 / Math.max(bmp.width, bmp.height));
    const c = document.createElement("canvas");
    c.width = Math.round(bmp.width * scale); c.height = Math.round(bmp.height * scale);
    c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
    return c.toDataURL("image/jpeg", 0.85).split(",")[1];
  }

  // Preferred path: a small proxy (see worker/) holds the real key, so no key is ever in the browser.
  async function estimateViaProxy(url, b64) {
    let res;
    try {
      res = await fetch(url, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ image: b64 }) });
    } catch { throw new HttpError(502, "Couldn't reach the estimate service. Check your connection or enter calories by hand."); }
    if (res.status === 429) throw new HttpError(429, "Today's free photo estimates are used up. Try again tomorrow or enter calories by hand.");
    if (!res.ok) throw new HttpError(502, "Couldn't estimate that photo right now. Enter calories by hand.");
    return parseReply((await res.json()).text);
  }

  async function estimateMeal(file, apiKey) {
    const b64 = await toJpegBase64(file);
    if (config.proxy_url) return estimateViaProxy(config.proxy_url, b64);
    if (!apiKey) {
      return { meal_name: "Demo meal (no API key set)", items: [{ name: "Estimated plate", kcal: 500 }], total_kcal: 500, confidence: "low", demo: true };
    }
    let res;
    try {
      res = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: {
          "content-type": "application/json", "x-api-key": apiKey, "anthropic-version": "2023-06-01",
          "anthropic-dangerous-direct-browser-access": "true", // required for browser calls; the key is the user's own
        },
        body: JSON.stringify({
          model: MODEL, max_tokens: 500,
          messages: [{ role: "user", content: [
            { type: "image", source: { type: "base64", media_type: "image/jpeg", data: b64 } },
            { type: "text", text: PROMPT }] }],
        }),
      });
    } catch { throw new HttpError(502, "Couldn't reach the estimate service. Check your connection or enter calories by hand."); }
    if (res.status === 401) throw new HttpError(502, "Your API key was rejected. Check it on the Me tab.");
    if (!res.ok) throw new HttpError(502, "Couldn't estimate that photo right now. Enter calories by hand.");
    const body = await res.json();
    return parseReply(body.content[0].text);
  }

  // ---------- storage ----------
  const KEY = "muse.v1", API_KEY = "muse.apikey";
  const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
  const load = () => { try { return JSON.parse(localStorage.getItem(KEY)) || { profile: null, meals: [], nextId: 1 }; } catch { return { profile: null, meals: [], nextId: 1 }; } };
  const save = s => localStorage.setItem(KEY, JSON.stringify(s));

  const exported = { makeCore, parseReply, HttpError, buildPlan };
  if (typeof module !== "undefined" && module.exports) { module.exports = exported; return; }

  // ---------- browser wiring ----------
  root.MUSE_STATIC = true;
  let core = null, config = { proxy_url: "" };
  const getJson = path => fetch(path).then(r => r.json());
  const dataReady = Promise.all([getJson("data/celebrities.json"), getJson("data/coaches.json"), getJson("data/meals.json"), getJson("config.json")])
    .then(([celebrities, coaches, meals, cfg]) => {
      config = { proxy_url: "", ...cfg };
      const m = Object.fromEntries(Object.entries(meals).filter(([k]) => !k.startsWith("_")));
      core = makeCore({ celebrities, coaches, meals: m });
      core.data = { celebrities, coaches };
    });

  function stateOf(s) {
    if (!s.profile) return { profile: null };
    const archetype = core.archetypeFor(s.profile.celebrity, s.profile.style), plan = buildPlan(s.profile, archetype);
    const meals = s.meals.filter(m => m.day === today());
    const eaten = meals.reduce((a, m) => a + m.kcal, 0);
    return { profile: s.profile, archetype, coach: core.data.coaches[archetype], plan, meals, eaten_kcal: eaten,
      remaining_kcal: plan.target_kcal - eaten, message: core.checkin(archetype, eaten, plan.target_kcal) };
  }
  const needProfile = s => { if (!s.profile) throw new HttpError(400, "Set up your profile first."); };

  async function route(method, path, init) {
    await dataReady;
    const s = load();
    if (method === "GET" && path === "/api/options") {
      return {
        celebrities: core.data.celebrities.celebrities.map(c => ({ name: c.name, wiki: c.wiki })),
        styles: Object.entries(core.data.coaches).map(([key, v]) => ({ key, coach: v.coach, tagline: v.tagline })),
      };
    }
    if (method === "GET" && path === "/api/state") return stateOf(s);
    if (method === "PUT" && path === "/api/profile") {
      const b = JSON.parse(init.body);
      buildPlan(b, core.archetypeFor(b.celebrity, b.style)); // validate before saving
      s.profile = b; save(s); return stateOf(s);
    }
    if (method === "GET" && path === "/api/mealplan") {
      needProfile(s);
      const t = stateOf(s).plan.target_kcal;
      return { target_kcal: t, week: core.buildWeek(t) };
    }
    if (method === "POST" && path === "/api/meals/photo") {
      needProfile(s);
      const file = init.body.get("photo");
      if (file.size > 10 * 1024 * 1024) throw new HttpError(413, "Photo is too large (max 10 MB).");
      const est = await estimateMeal(file, localStorage.getItem(API_KEY) || "");
      if (est.total_kcal > 0) { s.meals.push({ id: s.nextId++, day: today(), name: est.meal_name, kcal: est.total_kcal, items: est.items, source: "photo" }); save(s); }
      return { estimate: est, ...stateOf(s) };
    }
    if (method === "POST" && path === "/api/meals") {
      needProfile(s);
      const b = JSON.parse(init.body);
      if (!b.name || b.name.length > 80 || !(b.kcal >= 0 && b.kcal <= 5000)) throw new HttpError(422, "Enter a meal name and calories (0-5000).");
      s.meals.push({ id: s.nextId++, day: today(), name: b.name, kcal: b.kcal, items: [], source: "manual" }); save(s); return stateOf(s);
    }
    const del = path.match(/^\/api\/meals\/(\d+)$/);
    if (method === "DELETE" && del) { s.meals = s.meals.filter(m => m.id !== +del[1]); save(s); return stateOf(s); }
    throw new HttpError(404, "Not found.");
  }

  const realFetch = root.fetch.bind(root);
  root.fetch = async (input, init = {}) => {
    const url = new URL(typeof input === "string" ? input : input.url, location.href);
    const i = url.pathname.indexOf("/api/");
    if (i < 0) return realFetch(input, init);
    const reply = (status, body) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
    try { return reply(200, await route((init.method || "GET").toUpperCase(), url.pathname.slice(i), init)); }
    catch (e) { return e instanceof HttpError ? reply(e.status, { detail: e.message }) : (console.error(e), reply(500, { detail: "Something went wrong." })); }
  };

  // Hooks the shared UI calls on the profile/setup screen.
  // A saved key is never written back into the page: once saved, only the last 4 characters are shown.
  const keyBoxHtml = () => {
    const saved = localStorage.getItem(API_KEY);
    if (saved) {
      return `<div class="note">✓ API key saved on this device (ends in ${saved.slice(-4).replace(/[^\w-]/g, "")}).
        <button class="small ghost" id="keyrm" type="button" style="margin-top:8px">Remove key</button></div>`;
    }
    return `<input id="apikey" type="password" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="sk-ant-...">
      <button class="small" id="keysave" type="button" style="margin-top:8px">Save key</button><div id="keyerr"></div>`;
  };
  const wireKeyBox = () => {
    const box = document.getElementById("keybox"); if (!box) return;
    const redraw = () => { box.innerHTML = keyBoxHtml(); wireKeyBox(); };
    const save = document.getElementById("keysave"), rm = document.getElementById("keyrm");
    if (save) save.onclick = () => {
      const el = document.getElementById("apikey"), v = el.value.trim();
      if (!/^sk-ant-[\w-]{20,}$/.test(v)) { document.getElementById("keyerr").innerHTML = '<div class="err">That doesn\'t look like an Anthropic key (it starts with sk-ant-).</div>'; return; }
      localStorage.setItem(API_KEY, v); el.value = ""; redraw();
    };
    if (rm) rm.onclick = () => { localStorage.removeItem(API_KEY); redraw(); };
  };
  root.museExtraHtml = () => config.proxy_url
    ? `<h2>Photo estimates</h2><p class="mute">Photo estimates are built in. There's nothing to set up.</p>`
    : `<h2>Photo estimates</h2>
       <p class="mute">This web edition keeps everything on your device. For real photo estimates, paste your own Anthropic API key.
       It stays in this browser and is only sent to api.anthropic.com. Use a key with a low spend limit.</p>
       <div id="keybox">${keyBoxHtml()}</div>`;
  root.museWireExtra = wireKeyBox;
})(typeof window !== "undefined" ? window : globalThis);
