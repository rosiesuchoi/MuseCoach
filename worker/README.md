# Photo proxy (Cloudflare Worker)

Keeps the Anthropic API key **secret** so the public GitHub Pages site can do the AI photo analysis without any
key in the browser or the repo. Free Cloudflare plan is enough.

It only makes the two model calls of the meal pipeline (`POST /identify` with a JPEG, `POST /explain` with the retrieved USDA
candidates). Retrieval from the USDA database and all calorie math run in the browser, which keeps this Worker tiny. One meal analysis = 2 calls.

## Easiest: run the setup script

From the repo root in PowerShell (you still sign in to Cloudflare and paste your key yourself; the script never reads it):

```bash
powershell -ExecutionPolicy Bypass -File workerdeploy.ps1
```

It logs you in, creates the usage-cap store, stores the key as a secret, deploys, checks the Worker answers, rebuilds the site and asks
before pushing. The manual steps below do the same thing.

## One-time setup by hand (about 10 minutes)

1. Make an Anthropic API key at https://console.anthropic.com → API keys. Then, in Settings → Limits, set a
   **monthly spend limit** (for example $5). This is the hard backstop if anything goes wrong.
   The API is billed separately from a Claude subscription and needs a few dollars of credit.
2. Make a free Cloudflare account at https://dash.cloudflare.com/sign-up.
3. In this folder:

```bash
cd worker
npx wrangler login
npx wrangler kv namespace create LIMITS
```

4. Paste the `id` it prints into `wrangler.toml` (replace `PASTE_KV_NAMESPACE_ID_HERE`).
5. Store the key as a secret. Wrangler asks you to paste it, and it is never written to a file or to git:

```bash
npx wrangler secret put ANTHROPIC_API_KEY
npx wrangler deploy
```

6. Deploy prints a URL like `https://muse-coach-proxy.<you>.workers.dev`. Rebuild the site with it:

```bash
cd ..
set MUSE_PROXY_URL=https://muse-coach-proxy.<you>.workers.dev
.venv\Scripts\python tools/build_pages.py
git add -A && git commit -m "Use photo proxy" && git push
```

On the live site the key box on the Me tab disappears, since the AI analysis is built in.

## What protects it

- The model, prompts and token limits are built in the Worker (from `shared/pipeline.mjs`). Callers send only a JPEG or a size-limited,
  sanitized data payload, so it can't be used as a free general-purpose chatbot. (A determined caller could still stuff short text into the
  payload, which is why the caps below exist.)
- Only origins in `ALLOWED_ORIGINS` get CORS access. A script outside a browser can fake an origin, so the
  caps below matter more than this.
- Daily caps on model calls: `DAILY_LIMIT` for everyone (default 300) and `IP_LIMIT` per visitor (default 30). If the KV namespace is missing the Worker refuses to run.
- The spend limit from step 1.

If you ever suspect a leak, delete the key in the Anthropic console and run `npx wrangler secret put ANTHROPIC_API_KEY` with a new one.

## Test

`node test.mjs` runs 15 checks with mocked network. No key needed.
