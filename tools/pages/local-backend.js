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
    const bySlot = slot => data.recipes.filter(r => r.slot === slot);
    const getRecipe = id => data.recipes.find(r => r.id === id) || null;
    const buildWeek = target => ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((day, i) => ({
      day,
      meals: SHARES.map(([slot, share]) => {
        const opts = bySlot(slot), r = opts[(i + slot.length) % opts.length], serv = portion(target * share, r.nutrition.kcal);
        return { slot, recipe_id: r.id, name: r.name, servings: serv, kcal: Math.round(r.nutrition.kcal * serv) };
      }),
      snack_budget: Math.round(target * 0.10),
    }));
    return { archetypeFor, checkin, buildWeek, buildPlan, getRecipe };
  }

  // ---------- on-device estimate (no key, no upload) ----------
  // A small open food classifier runs in the browser; calories come from a typical-serving table.
  // Pinned library and model revision so a remote change can't alter behaviour under users.
  const ONDEVICE = {
    lib: "https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.8.1",
    model: "onnx-community/swin-finetuned-food101-ONNX",
    revision: "e5e50bfc6425aa546f3b4421ca8bd79d0dd610b8",
    dtype: "q4", // ~60 MB, the smallest variant that kept accuracy in testing
  };
  const MIN_SCORE = 0.20; // below this the model is basically guessing: ask for manual entry instead

  // preds: [{label, score}] sorted best first. Returns the same shape as the AI analysis (minus the insight).
  function fromPredictions(preds, table) {
    const best = preds && preds[0];
    if (!best || best.score < MIN_SCORE || !table[best.label]) {
      throw new HttpError(422, "Couldn't recognize that dish. Try a closer photo, or enter it by hand.");
    }
    const f = table[best.label];
    return {
      meal_name: f.name,
      items: [{ name: `${f.name} (${f.serving})`, kcal: f.kcal }],
      total_kcal: f.kcal,
      // Never "high": the model can name the dish but cannot see how big the portion is.
      confidence: best.score >= 0.6 ? "medium" : "low",
      demo: false, method: "on-device", serving: f.serving, score: best.score,
    };
  }

  let classifierPromise = null;
  const say = text => { if (typeof root.dispatchEvent === "function") root.dispatchEvent(new CustomEvent("muse-status", { detail: text })); };

  function loadClassifier() {
    if (!classifierPromise) {
      classifierPromise = (async () => {
        const { pipeline, env } = await import(ONDEVICE.lib);
        env.allowLocalModels = false;
        const files = {};
        // Only the very first run downloads (~60 MB); later runs read the browser's cache, so word it accordingly.
        let firstTime = true;
        try { firstTime = !(await caches.keys()).includes("transformers-cache"); } catch { /* no Cache API: assume first time */ }
        const verb = firstTime ? "Downloading food model (first time only)" : "Loading food model";
        say(`${verb}…`);
        return pipeline("image-classification", ONDEVICE.model, {
          dtype: ONDEVICE.dtype, revision: ONDEVICE.revision,
          progress_callback: p => {
            if (p.status !== "progress" || !p.total) return;
            files[p.file] = { loaded: p.loaded, total: p.total };
            const all = Object.values(files), got = all.reduce((a, x) => a + x.loaded, 0), tot = all.reduce((a, x) => a + x.total, 0);
            say(`${verb}: ${Math.round(got / tot * 100)}%`);
          },
        });
      })().catch(e => { classifierPromise = null; throw e; }); // allow a retry after a network failure
    }
    return classifierPromise;
  }

  async function estimateOnDevice(b64) {
    let classify;
    try { classify = await loadClassifier(); }
    catch (e) {
      console.error("on-device model failed to load", e);
      throw new HttpError(502, "Couldn't load the on-device food model (it needs a connection the first time). Enter calories by hand.");
    }
    say("Looking at your meal…");
    const out = await classify(`data:image/jpeg;base64,${b64}`, { top_k: 3 });
    return fromPredictions(out, foodTable);
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

  // ---------- AI analysis: identify -> retrieve (USDA) -> explain, see shared/pipeline.mjs ----------
  // The two model calls go either through the Worker proxy (key stays secret there) or straight to Anthropic
  // with the user's own pasted key. Retrieval and all the calorie math always run here in the browser.
  const NETWORK_MSG = "Couldn't reach the AI service. Check your connection or enter calories by hand.";
  const failure = (res, who) => {
    if (res.status === 429) return new HttpError(429, "Today's AI photo analyses are used up. Try again tomorrow, or enter calories by hand.");
    if (res.status === 401 && who === "key") return new HttpError(502, "Your API key was rejected. Check it on the Me tab.");
    return new HttpError(502, "Couldn't analyze that photo right now. Enter calories by hand.");
  };
  const textOf = async (res, who, field) => { if (!res.ok) throw failure(res, who); const b = await res.json(); return field(b); };

  function proxyClient(base) {
    const post = async (route, body) => {
      let res;
      try { res = await fetch(base.replace(/\/+$/, "") + route, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) }); }
      catch { throw new HttpError(502, NETWORK_MSG); }
      return textOf(res, "proxy", b => b.text);
    };
    return { identify: image => post("/identify", { image }), explain: payload => post("/explain", payload) };
  }

  function directClient(apiKey, pipeline) {
    const call = async body => {
      let res;
      try {
        res = await fetch("https://api.anthropic.com/v1/messages", { method: "POST", body: JSON.stringify(body), headers: {
          "content-type": "application/json", "x-api-key": apiKey, "anthropic-version": "2023-06-01",
          "anthropic-dangerous-direct-browser-access": "true", // required for browser calls; the key is the user's own
        } });
      } catch { throw new HttpError(502, NETWORK_MSG); }
      return textOf(res, "key", b => b.content?.[0]?.text ?? "");
    };
    return { identify: image => call(pipeline.identifyRequest(image)), explain: payload => call(pipeline.explainRequest(payload)) };
  }

  let aiLoad = null; // pipeline module + USDA index, loaded once on first use
  function loadAi() {
    if (!aiLoad) {
      aiLoad = (async () => {
        const [pipeline, kb] = await Promise.all([import("./pipeline.mjs"), getJson("data/nutrition.json")]);
        return { pipeline, index: pipeline.buildIndex(kb) };
      })().catch(e => { aiLoad = null; throw e; });
    }
    return aiLoad;
  }

  async function analyzeWithAI(b64, context, apiKey) {
    let ai;
    try { say("Loading the nutrition database…"); ai = await loadAi(); }
    catch (e) { console.error("pipeline failed to load", e); throw new HttpError(502, "Couldn't load the nutrition database. Check your connection."); }
    const { pipeline, index } = ai;
    const client = config.proxy_url ? proxyClient(config.proxy_url) : directClient(apiKey, pipeline);
    try {
      return await pipeline.analyzeMeal({
        image: b64, context, index,
        identify: async img => { say("Looking at your photo…"); return client.identify(img); },
        explain: async payload => { say("Checking the USDA nutrition facts…"); const t = await client.explain(payload); say("Writing your food notes…"); return t; },
      });
    } catch (e) {
      if (e instanceof pipeline.PipelineError) throw new HttpError(e.status, e.message);
      throw e;
    }
  }

  async function estimateMeal(file, apiKey, context) {
    const b64 = await toJpegBase64(file);
    if (config.proxy_url || apiKey) return analyzeWithAI(b64, context, apiKey);
    return estimateOnDevice(b64); // no proxy and no key: the smaller on-device model, calories only
  }

  // ---------- storage ----------
  const KEY = "muse.v1", API_KEY = "muse.apikey";
  const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
  const load = () => { try { return JSON.parse(localStorage.getItem(KEY)) || { profile: null, meals: [], nextId: 1 }; } catch { return { profile: null, meals: [], nextId: 1 }; } };
  const save = s => localStorage.setItem(KEY, JSON.stringify(s));

  const exported = { makeCore, HttpError, buildPlan, fromPredictions };
  if (typeof module !== "undefined" && module.exports) { module.exports = exported; return; }

  // ---------- browser wiring ----------
  root.MUSE_STATIC = true;
  let core = null, config = { proxy_url: "" }, foodTable = {};
  const getJson = path => fetch(path).then(r => r.json());
  const dataReady = Promise.all([getJson("data/celebrities.json"), getJson("data/coaches.json"), getJson("data/recipes.json"), getJson("config.json"), getJson("data/food_calories.json")])
    .then(([celebrities, coaches, recipes, cfg, food]) => {
      config = { proxy_url: "", ...cfg };
      foodTable = Object.fromEntries(Object.entries(food).filter(([k]) => !k.startsWith("_")));
      core = makeCore({ celebrities, coaches, recipes: recipes.recipes });
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
    const rec = path.match(/^\/api\/recipes\/([\w-]+)$/);
    if (method === "GET" && rec) {
      const r = core.getRecipe(rec[1]);
      if (!r) throw new HttpError(404, "Recipe not found.");
      return r;
    }
    if (method === "POST" && path === "/api/meals/photo") {
      needProfile(s);
      const file = init.body.get("photo");
      if (file.size > 10 * 1024 * 1024) throw new HttpError(413, "Photo is too large (max 10 MB).");
      const before = stateOf(s);
      const context = { goal: before.plan.goal, remaining_kcal: before.remaining_kcal, target_kcal: before.plan.target_kcal, minor: s.profile.age < 18 };
      const est = await estimateMeal(file, localStorage.getItem(API_KEY) || "", context);
      if (est.total_kcal > 0) {
        // `analysis` keeps the full AI breakdown (items, nutrients, insight) so the meal's details can be reopened later.
        s.meals.push({ id: s.nextId++, day: today(), name: est.meal_name, kcal: est.total_kcal, items: est.items.map(i => ({ name: i.name, kcal: i.kcal })),
          source: "photo", analysis: est.method === "ai-rag" ? est : null });
        save(s);
      }
      return { estimate: est, ...stateOf(s) };
    }
    if (method === "POST" && path === "/api/meals") {
      needProfile(s);
      const b = JSON.parse(init.body);
      if (!b.name || b.name.length > 80 || !(b.kcal >= 0 && b.kcal <= 5000)) throw new HttpError(422, "Enter a meal name and calories (0-5000).");
      s.meals.push({ id: s.nextId++, day: today(), name: b.name, kcal: b.kcal, items: [], source: "manual" }); save(s); return stateOf(s);
    }
    const del = path.match(/^\/api\/meals\/(\d+)$/);
    if (method === "PATCH" && del) { // edit a logged meal (estimates are approximate, so people fix them)
      const b = JSON.parse(init.body), m = s.meals.find(x => x.id === +del[1]);
      if (!m) throw new HttpError(404, "Meal not found.");
      if (!b.name || b.name.length > 80 || !(b.kcal >= 0 && b.kcal <= 5000)) throw new HttpError(422, "Enter a meal name and calories (0-5000).");
      m.name = b.name; m.kcal = b.kcal; save(s); return stateOf(s);
    }
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
    ? `<h2>Photo analysis</h2><p class="mute">AI photo analysis is built in. There's nothing to set up.</p>`
    : `<h2>Photo estimates</h2>
       <p class="mute"><b>With an Anthropic API key</b>, photos get a full AI analysis: every food and drink identified, calories and
       nutrients looked up in the USDA database, what's in it, benefits, things to watch, and whether it fits your goal.
       The key stays in this browser and is only sent to api.anthropic.com. Use one with a low spend limit.</p>
       <p class="mute"><b>Without a key</b>, a small food-recognition model runs on your device (about 60 MB the first time; photos never
       leave it). It only names the dish and assumes one typical serving, so edit the calories if your portion differs.</p>
       <div id="keybox">${keyBoxHtml()}</div>`;
  root.museWireExtra = wireKeyBox;
})(typeof window !== "undefined" ? window : globalThis);
