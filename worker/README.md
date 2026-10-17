# Photo proxy (Cloudflare Worker)

Keeps the Anthropic API key **secret** so the public GitHub Pages site can do photo estimates without any
key in the browser or the repo. Free Cloudflare plan is enough.

## One-time setup (about 10 minutes)

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

On the live site the key box on the Me tab disappears, since photo estimates are built in.

## What protects it

- The model, prompt and token limit are fixed in `worker.js`; callers can only send a JPEG.
- Only origins in `ALLOWED_ORIGINS` get CORS access. A script outside a browser can fake an origin, so the
  caps below matter more than this.
- Daily caps: `DAILY_LIMIT` for everyone and `IP_LIMIT` per visitor. If the KV namespace is missing the Worker refuses to run.
- The spend limit from step 1.

If you ever suspect a leak, delete the key in the Anthropic console and run `npx wrangler secret put ANTHROPIC_API_KEY` with a new one.

## Test

`node test.mjs` runs 11 checks with mocked network. No key needed.
