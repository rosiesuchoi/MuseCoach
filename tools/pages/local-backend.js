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
    // ---- diet, varied weekly plan, prices and grocery list (mirrors app/diet.py; tools/diet_parity.mjs checks both agree) ----
    const jsRound = x => Math.floor(x + 0.5);
    const ALLERGENS = ["milk", "egg", "peanut", "tree_nut", "wheat", "soy", "fish", "shellfish", "sesame"];
    const PATTERNS = ["none", "pescatarian", "vegetarian", "vegan"];
    const PATTERN_EXCLUDES = { none: [], pescatarian: ["meat", "poultry"], vegetarian: ["meat", "poultry", "fish", "shellfish"], vegan: ["meat", "poultry", "fish", "shellfish", "milk", "egg", "honey"] };
    const SLOTS = [["breakfast", 0.25], ["lunch", 0.35], ["dinner", 0.30]]; // the last 10% is for snacks
    const AISLES = ["Produce", "Meat & seafood", "Dairy & eggs", "Grains & bakery", "Canned & dry goods", "Frozen", "Pantry staples", "Spices"];
    const LB_G = 453.6, catalog = data.catalog || {};
    const getRecipe = id => data.recipes.find(r => r.id === id) || null;

    const normalizeDiet = raw => {
      raw = raw && typeof raw === "object" ? raw : {};
      const allergens = ALLERGENS.filter(x => (raw.allergens || []).includes(x));
      const pattern = PATTERNS.includes(raw.pattern) ? raw.pattern : "none";
      const avoid = [], seen = new Set();
      for (let w of raw.avoid || []) {
        w = String(w).toLowerCase().split(/\s+/).filter(Boolean).join(" ").slice(0, 40);
        if (w && !seen.has(w)) { seen.add(w); avoid.push(w); }
      }
      return { allergens, pattern, gluten_free: raw.gluten_free === true, avoid: avoid.slice(0, 20) };
    };
    const signature = d => { const n = normalizeDiet(d); return JSON.stringify({ allergens: n.allergens, avoid: n.avoid, gluten_free: n.gluten_free, pattern: n.pattern }); };
    const excludedTags = d => { const n = normalizeDiet(d); return new Set([...n.allergens, ...PATTERN_EXCLUDES[n.pattern], ...(n.gluten_free ? ["gluten"] : [])]); };
    const recipeText = r => [r.name, ...r.ingredients.flatMap(g => g.items)].join(" ").toLowerCase();
    const eligible = (r, d) => {
      const ex = excludedTags(d);
      if ([...r.allergens, ...r.contains].some(t => ex.has(t))) return false;
      const text = recipeText(r);
      return !normalizeDiet(d).avoid.some(w => text.includes(w));
    };
    const summary = d => {
      const n = normalizeDiet(d), out = [];
      if (n.pattern !== "none") out.push(n.pattern[0].toUpperCase() + n.pattern.slice(1));
      if (n.gluten_free) out.push("Gluten-free");
      return [...out, ...n.allergens.map(x => "No " + x.replace("_", " ")), ...n.avoid.map(w => "No " + w)];
    };

    const mulberry32 = seed => {
      let a = seed >>> 0;
      return () => {
        a = (a + 0x6D2B79F5) | 0;
        let t = Math.imul(a ^ (a >>> 15), 1 | a);
        t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
      };
    };
    const shuffled = (items, rng) => {
      const out = [...items];
      for (let i = out.length - 1; i > 0; i--) { const j = Math.floor(rng() * (i + 1)); [out[i], out[j]] = [out[j], out[i]]; }
      return out;
    };
    const seedFor = (week, shuffle) => (Number(week.replace(/-/g, "")) * 31 + shuffle) >>> 0;
    const portion = (budget, kcal) => Math.min(2, Math.max(0.5, jsRound(budget / kcal * 4) / 4));
    const byId = (x, y) => (x.id < y.id ? -1 : x.id > y.id ? 1 : 0);

    // 7 days x 3 meals. A flexible diet gets different meals all week; a strict diet that leaves fewer than 7 options for a meal repeats them as far apart as possible, and says so.
    const buildWeekDiet = (recipes, target, seed, dietProfile) => {
      const notes = [], counts = {}, picks = {};
      SLOTS.forEach(([slot, share], si) => {
        const pool = recipes.filter(r => r.slot === slot && eligible(r, dietProfile)).sort(byId);
        counts[slot] = pool.length;
        if (!pool.length) {
          picks[slot] = Array(7).fill(null);
          notes.push(`No ${slot} recipes fit your diet and allergies, so ${slot} is left out. Loosen a restriction to see options.`);
          return;
        }
        const budget = target * share;
        const feasible = pool.filter(r => { const x = budget / r.nutrition.kcal; return x >= 0.5 && x <= 2.0; });
        const need = Math.min(pool.length, 7), inFeasible = new Set(feasible);
        let chosen = feasible;
        if (feasible.length < need) {
          const rest = pool.filter(r => !inFeasible.has(r)).sort((x, y) => (Math.abs(Math.log(budget / x.nutrition.kcal)) - Math.abs(Math.log(budget / y.nutrition.kcal))) || byId(x, y));
          chosen = feasible.concat(rest.slice(0, need - feasible.length));
        }
        const order = shuffled(chosen, mulberry32(seed + si * 7919));
        picks[slot] = Array.from({ length: 7 }, (_, i) => order[i % order.length]);
        if (pool.length < 7) notes.push(`Only ${pool.length} ${slot} recipe${pool.length !== 1 ? "s" : ""} fit your diet and allergies, so some repeat during the week.`);
      });
      const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((day, i) => ({
        day,
        meals: SLOTS.flatMap(([slot, share]) => {
          const r = picks[slot][i];
          if (!r) return [];
          const serv = portion(target * share, r.nutrition.kcal);
          return [{ slot, recipe_id: r.id, name: r.name, servings: serv, kcal: jsRound(r.nutrition.kcal * serv) }];
        }),
        snack_budget: jsRound(target * 0.10),
      }));
      return { days, notes, counts };
    };

    const packCents = (id, it, overrides) => jsRound((id in overrides ? overrides[id] : it.pack.price) * 100);
    const priceSrc = (id, it, overrides) => (id in overrides ? "you" : it.pack.src);
    const recipeCostCents = (r, overrides) => r.lines.reduce((t, ln) => { const it = catalog[ln.item]; return t + jsRound(packCents(ln.item, it, overrides) * ln.g / it.pack.g); }, 0) / r.servings;
    const amountText = (g, each) => {
      if (each) {
        const n = jsRound(g / each.g * 2) / 2;
        if (n >= 1) return `${n} ${n === 1 ? each.name : (each.plural || each.name + "s")}`;
      }
      if (g >= 227) return `${(jsRound(g / LB_G * 10) / 10).toFixed(1)} lb`;
      if (g >= 28.35) return `${jsRound(g / 28.35)} oz`;
      return `${jsRound(g)} g`;
    };
    const grocery = (meals, overrides) => {
      const need = {}, uses = {};
      for (const m of meals) {
        const r = getRecipe(m.recipe_id);
        for (const ln of r.lines) { need[ln.item] = (need[ln.item] || 0) + ln.g / r.servings * m.servings; (uses[ln.item] = uses[ln.item] || new Set()).add(r.name); }
      }
      const lines = Object.entries(need).map(([id, g]) => {
        const it = catalog[id], pc = packCents(id, it, overrides), packs = Math.max(1, Math.ceil(g / it.pack.g - 1e-9)), src = priceSrc(id, it, overrides);
        return { item: id, name: it.name, aisle: it.aisle, need_g: jsRound(g * 10) / 10, need_text: amountText(g, it.each), packs, pack_label: it.pack.label, pack_cents: pc,
          line_cents: pc * packs, used_cents: jsRound(pc * g / it.pack.g), src, official: src === "bls" || src === "bls-derived", staple: !!it.staple, uses: [...uses[id]].sort().slice(0, 4) };
      });
      const rank = a => (AISLES.includes(a) ? AISLES.indexOf(a) : AISLES.length);
      lines.sort((x, y) => (rank(x.aisle) - rank(y.aisle)) || (x.name < y.name ? -1 : x.name > y.name ? 1 : 0));
      const sum = (arr, k) => arr.reduce((t, l) => t + l[k], 0), toBuy = sum(lines, "line_cents"), staples = sum(lines.filter(l => l.staple), "line_cents");
      return { lines, totals: { to_buy_cents: toBuy, used_cents: sum(lines, "used_cents"), staples_cents: staples, without_staples_cents: toBuy - staples, items: lines.length,
        official_items: lines.filter(l => l.official).length, estimated_items: lines.filter(l => l.src === "estimate").length, your_items: lines.filter(l => l.src === "you").length } };
    };

    // ---- training week (mirrors app/training.py) ----
    const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    const pad = n => String(n).padStart(2, "0");
    const iso = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    const addDays = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
    const weekStart = today => addDays(today, -((today.getDay() + 6) % 7)); // Monday
    const isStyle = key => !!(data.workouts.styles[key]);
    const styleOptions = () => Object.entries(data.workouts.styles).map(([k, st]) => ({ key: k, name: st.name, tagline: st.tagline, equipment: st.equipment }));
    const buildTraining = (styleKey, activity, done, today) => {
      const w = data.workouts, style = w.styles[styleKey], layout = w.layouts[activity] || w.layouts.medium, start = weekStart(today);
      let recovery = 0;
      const days = DAYS.map((name, i) => {
        let code = layout[name], kind = "workout", body;
        if (code) body = style.days[code];
        else { kind = "recovery"; code = `R${recovery % 2 + 1}`; body = w.recovery[code]; recovery++; }
        return { day: name, date: iso(addDays(start, i)), kind, code, title: body.title, focus: body.focus, minutes: body.minutes, warmup: body.warmup,
          exercises: body.exercises, cooldown: body.cooldown, metric: body.metric, done: done.has(name) };
      });
      const workouts = days.filter(d => d.kind === "workout"), doneWorkouts = workouts.filter(d => d.done).length;
      return { style: styleKey, style_name: style.name, tagline: style.tagline, equipment: style.equipment, equipment_note: style.equipment_note,
        progression: style.progression, safety: w.safety, styles: styleOptions(), week_start: iso(start), today: DAYS[(today.getDay() + 6) % 7], days,
        planned: workouts.length, done_workouts: doneWorkouts, all_done: doneWorkouts === workouts.length };
    };
    return { archetypeFor, checkin, buildWeekDiet, buildPlan, getRecipe, buildTraining, isStyle, weekStart, iso, DAYS,
      diet: { normalizeDiet, signature, eligible, summary, mulberry32, shuffled, seedFor, recipeCostCents, amountText, grocery, jsRound, SLOTS, catalog } };
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
  // The two model calls go straight to Anthropic with the user's own pasted key (it never touches a server of ours).
  // Retrieval and all the calorie math run here in the browser.
  const NETWORK_MSG = "Couldn't reach the AI service. Check your connection or enter calories by hand.";
  const failure = res => {
    if (res.status === 401) return new HttpError(502, "Your API key was rejected. Check it on the Me tab.");
    if (res.status === 429) return new HttpError(429, "The AI service is rate-limiting this key. Wait a minute and try again, or enter calories by hand.");
    return new HttpError(502, "Couldn't analyze that photo right now. Enter calories by hand.");
  };
  const textOf = async (res, field) => { if (!res.ok) throw failure(res); const b = await res.json(); return field(b); };

  function directClient(apiKey, pipeline) {
    const call = async body => {
      let res;
      try {
        res = await fetch("https://api.anthropic.com/v1/messages", { method: "POST", body: JSON.stringify(body), headers: {
          "content-type": "application/json", "x-api-key": apiKey, "anthropic-version": "2023-06-01",
          "anthropic-dangerous-direct-browser-access": "true", // required for browser calls; the key is the user's own
        } });
      } catch { throw new HttpError(502, NETWORK_MSG); }
      return textOf(res, b => pipeline.replyText(b));
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
    const client = directClient(apiKey, pipeline);
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
    if (apiKey) return analyzeWithAI(b64, context, apiKey);
    return estimateOnDevice(b64); // no key: the smaller on-device model, calories only
  }

  // ---------- storage ----------
  const KEY = "muse.v1", API_KEY = "muse.apikey";
  const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
  const fresh = () => ({ profile: null, meals: [], nextId: 1, checks: {}, diet: null, prices: {}, plans: {} });
  const load = () => { try { return { ...fresh(), ...(JSON.parse(localStorage.getItem(KEY)) || {}) }; } catch { return fresh(); } };
  const save = s => localStorage.setItem(KEY, JSON.stringify(s));

  const exported = { makeCore, HttpError, buildPlan, fromPredictions };
  if (typeof module !== "undefined" && module.exports) { module.exports = exported; return; }

  // ---------- browser wiring ----------
  root.MUSE_STATIC = true;
  let core = null, foodTable = {};
  const getJson = path => fetch(path).then(r => r.json());
  const dataReady = Promise.all([getJson("data/celebrities.json"), getJson("data/coaches.json"), getJson("data/recipes.json"), getJson("data/food_calories.json"), getJson("data/workouts.json"), getJson("data/ingredients.json")])
    .then(([celebrities, coaches, recipes, food, workouts, ingredients]) => {
      foodTable = Object.fromEntries(Object.entries(food).filter(([k]) => !k.startsWith("_")));
      core = makeCore({ celebrities, coaches, recipes: recipes.recipes, workouts, catalog: ingredients.items });
      core.data = { celebrities, coaches };
      core.recipes = recipes.recipes;
    });

  function stateOf(s) {
    if (!s.profile) return { profile: null };
    const archetype = core.archetypeFor(s.profile.celebrity, s.profile.style), plan = buildPlan(s.profile, archetype);
    const meals = s.meals.filter(m => m.day === today());
    const eaten = meals.reduce((a, m) => a + m.kcal, 0);
    const now = new Date(), done = new Set(s.checks[core.iso(core.weekStart(now))] || []);
    const style = core.isStyle(s.profile.training) ? s.profile.training : core.data.coaches[archetype].default_training;
    return { profile: s.profile, archetype, coach: core.data.coaches[archetype], plan, meals, eaten_kcal: eaten,
      remaining_kcal: plan.target_kcal - eaten, message: core.checkin(archetype, eaten, plan.target_kcal),
      training: core.buildTraining(style, s.profile.activity, done, now),
      diet: { profile: core.diet.normalizeDiet(s.diet), summary: core.diet.summary(s.diet || {}) } };
  }
  // The plan is saved for the calendar week (so it doesn't change between visits), rebuilt when the diet or calorie target changes, and re-rolled by "shuffle".
  function planFor(s, reshuffle) {
    needProfile(s);
    const target = stateOf(s).plan.target_kcal, week = core.iso(core.weekStart(new Date())), dietProfile = s.diet || {};
    const sig = core.diet.signature(dietProfile) + "|" + target, saved = s.plans[week];
    const shuffle = (saved ? saved.shuffle : 0) + (reshuffle ? 1 : 0);
    let plan = saved;
    if (!saved || saved.sig !== sig || reshuffle) {
      const built = core.buildWeekDiet(core.recipes, target, core.diet.seedFor(week, shuffle), dietProfile);
      plan = s.plans[week] = { shuffle, sig, target, notes: built.notes, days: built.days, created: new Date().toISOString().slice(0, 19) };
      save(s);
    }
    const overrides = s.prices || {}, days = JSON.parse(JSON.stringify(plan.days));
    for (const d of days) for (const m of d.meals) m.cost_cents = core.diet.jsRound(core.diet.recipeCostCents(core.getRecipe(m.recipe_id), overrides) * m.servings);
    const eligible = Object.fromEntries(core.diet.SLOTS.map(([slot]) => [slot, core.recipes.filter(r => r.slot === slot && core.diet.eligible(r, dietProfile)).length]));
    return { week_start: week, shuffle: plan.shuffle, target_kcal: target, notes: plan.notes, week: days, eligible, diet: { profile: core.diet.normalizeDiet(dietProfile), summary: core.diet.summary(dietProfile) } };
  }
  function groceryFor(s, plan) {
    const meals = plan.week.flatMap(d => d.meals.map(m => ({ recipe_id: m.recipe_id, servings: m.servings })));
    return { ...core.diet.grocery(meals, s.prices || {}), week_start: plan.week_start, meals: meals.length,
      prices: { as_of: "2026-09", source: "US Bureau of Labor Statistics average retail prices (Sep 2026) where marked; other prices are typical-store estimates. Edit any price to match your store." } };
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
      if (b.training === undefined || b.training === null) b.training = (s.profile && s.profile.training) || ""; // the form doesn't send it
      s.profile = b; save(s); return stateOf(s);
    }
    if (method === "PUT" && path === "/api/training") {
      needProfile(s);
      const b = JSON.parse(init.body);
      if (typeof b.style !== "string" || (b.style && !core.isStyle(b.style))) throw new HttpError(422, "Unknown training style.");
      s.profile.training = b.style; save(s); return stateOf(s);
    }
    if (method === "POST" && path === "/api/workouts/check") {
      needProfile(s);
      const b = JSON.parse(init.body);
      if (!core.DAYS.includes(b.day)) throw new HttpError(422, "Unknown day.");
      const wk = core.iso(core.weekStart(new Date())), set = new Set(s.checks[wk] || []);
      b.done ? set.add(b.day) : set.delete(b.day);
      s.checks[wk] = [...set]; save(s); return stateOf(s);
    }
    if (method === "PUT" && path === "/api/diet") {
      needProfile(s);
      s.diet = core.diet.normalizeDiet(JSON.parse(init.body)); save(s); return stateOf(s);
    }
    if (method === "GET" && path === "/api/mealplan") return planFor(s, false);
    if (method === "POST" && path === "/api/mealplan/shuffle") return planFor(s, true);
    if (method === "GET" && path === "/api/plans") {
      return { plans: Object.entries(s.plans).sort((x, y) => (x[0] < y[0] ? 1 : -1)).slice(0, 12).map(([week, p]) => ({ week, shuffle: p.shuffle, created: p.created, target: p.target, meals: p.days.reduce((n, d) => n + d.meals.length, 0) })) };
    }
    if (method === "GET" && path === "/api/grocery") return groceryFor(s, planFor(s, false));
    if (method === "PUT" && path === "/api/prices") {
      const b = JSON.parse(init.body);
      if (!(b.item in core.diet.catalog)) throw new HttpError(404, "Unknown grocery item.");
      if (b.price === null || b.price === undefined) delete s.prices[b.item];
      else if (typeof b.price === "number" && b.price > 0 && b.price <= 500) s.prices[b.item] = b.price;
      else throw new HttpError(422, "Enter a price between $0.01 and $500.");
      save(s); return groceryFor(s, planFor(s, false));
    }
    const rec = path.match(/^\/api\/recipes\/([\w-]+)$/);
    if (method === "GET" && rec) {
      const r = core.getRecipe(rec[1]);
      if (!r) throw new HttpError(404, "Recipe not found.");
      return { ...r, cost_cents_per_serving: core.diet.jsRound(core.diet.recipeCostCents(r, s.prices || {})) };
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
  root.museExtraHtml = () => `<h2>Photo estimates</h2>
       <p class="mute"><b>With an Anthropic API key</b>, photos get a full AI analysis: every food and drink identified, calories and
       nutrients looked up in the USDA database, what's in it, benefits, things to watch, and whether it fits your goal.
       The key stays in this browser and is only sent to api.anthropic.com. Use one with a low spend limit.</p>
       <p class="mute"><b>Without a key</b>, a small food-recognition model runs on your device (about 60 MB the first time; photos never
       leave it). It only names the dish and assumes one typical serving, so edit the calories if your portion differs.</p>
       <div id="keybox">${keyBoxHtml()}</div>`;
  root.museWireExtra = wireKeyBox;
})(typeof window !== "undefined" ? window : globalThis);
