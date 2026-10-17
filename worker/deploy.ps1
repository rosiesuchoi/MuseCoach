# One-command setup for the Muse Coach AI proxy. Run from the repo root in PowerShell:
#     powershell -ExecutionPolicy Bypass -File worker\deploy.ps1
#
# What it does (you stay in control of the secret parts):
#   1. Logs you in to Cloudflare (a browser window opens: you sign in, I never see your password)
#   2. Creates the KV store that holds the daily usage caps and writes its id into wrangler.toml
#   3. Asks wrangler to store your Anthropic key as a Worker secret. YOU paste it at wrangler's own prompt;
#      this script never reads, prints or saves it.
#   4. Deploys the Worker and checks it answers
#   5. Rebuilds the site pointing at the Worker, then asks before committing and pushing
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root "worker")

function Step($n, $text) { Write-Host "`n[$n/5] $text" -ForegroundColor Cyan }
function Run($cmd) { Write-Host "> $cmd" -ForegroundColor DarkGray; Invoke-Expression $cmd; if ($LASTEXITCODE -ne 0) { throw "Command failed: $cmd" } }

Step 1 "Cloudflare login"
$who = (& npx --yes wrangler whoami 2>&1 | Out-String)
if ($who -match "not authenticated|You are not") { Run "npx --yes wrangler login" } else { Write-Host "Already logged in." }

Step 2 "Usage-cap store (KV)"
$toml = Get-Content wrangler.toml -Raw
if ($toml -match 'PASTE_KV_NAMESPACE_ID_HERE') {
    $out = (& npx --yes wrangler kv namespace create LIMITS 2>&1 | Out-String)
    Write-Host $out
    if ($out -match '"?id"?\s*[:=]\s*"([0-9a-f]{32})"') { $kvId = $Matches[1] }
    else { $kvId = Read-Host "Couldn't read the id automatically. Paste the 32-character id printed above" }
    if ($kvId -notmatch '^[0-9a-f]{32}$') { throw "That doesn't look like a KV namespace id." }
    $toml = $toml -replace 'PASTE_KV_NAMESPACE_ID_HERE', $kvId
    Set-Content wrangler.toml $toml -NoNewline
    Write-Host "Saved the KV id to wrangler.toml."
} else { Write-Host "wrangler.toml already has a KV id." }

Step 3 "Store your Anthropic key as a secret (paste it when wrangler asks; it is hidden and never saved to a file)"
Run "npx --yes wrangler secret put ANTHROPIC_API_KEY"

Step 4 "Deploy"
$deploy = (& npx --yes wrangler deploy 2>&1 | Out-String)
Write-Host $deploy
if ($LASTEXITCODE -ne 0) { throw "Deploy failed." }
if ($deploy -match '(https://[\w.-]+\.workers\.dev)') { $url = $Matches[1] } else { $url = Read-Host "Paste the workers.dev URL printed above" }
$origin = "https://rosiesuchoi.github.io"
$code = (curl.exe -s -o NUL -w "%{http_code}" -X OPTIONS -H "Origin: $origin" -H "Access-Control-Request-Method: POST" "$url/identify")
if ($code -eq "204") { Write-Host "Worker is up and allows $origin." -ForegroundColor Green } else { throw "Worker answered $code to a preflight check, expected 204. Check ALLOWED_ORIGINS in wrangler.toml." }

Step 5 "Point the site at the Worker"
Set-Location $root
$env:MUSE_PROXY_URL = $url
& "$root\.venv\Scripts\python.exe" tools\build_pages.py
if ($LASTEXITCODE -ne 0) { throw "Site build failed." }
git status --short
$go = Read-Host "`nCommit and push these changes so the live site uses the AI analysis? (y/n)"
if ($go -eq "y") {
    git add docs worker/wrangler.toml
    git commit -m "Use the AI proxy Worker"
    git push
    Write-Host "Pushed. The live site updates in about a minute: $origin/MuseCoach/" -ForegroundColor Green
} else { Write-Host "Not pushed. Run 'git add docs worker/wrangler.toml; git commit; git push' when ready." }
