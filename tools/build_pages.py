"""Builds the static GitHub Pages edition into docs/.

Run:  .venv\\Scripts\\python tools/build_pages.py
Pages then serves docs/ (repo Settings -> Pages -> Deploy from branch -> main -> /docs).
The UI file is shared with the server edition; the build only fixes paths and adds local-backend.js.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"


def main() -> None:
    if DOCS.exists():
        shutil.rmtree(DOCS)
    (DOCS / "data").mkdir(parents=True)

    # Absolute paths break under https://user.github.io/MuseCoach/, so make them relative.
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    html = html.replace('href="/', 'href="')
    html = html.replace("<title>", '<script src="local-backend.js"></script>\n<title>', 1)
    (DOCS / "index.html").write_text(html, encoding="utf-8")

    manifest = (ROOT / "app/static/manifest.webmanifest").read_text(encoding="utf-8")
    manifest = manifest.replace('"start_url": "/"', '"start_url": "./"').replace('"src": "/icon.svg"', '"src": "icon.svg"')
    (DOCS / "manifest.webmanifest").write_text(manifest, encoding="utf-8")

    # proxy_url: where the key-holding Worker lives (see worker/README.md). Empty = users paste their own key.
    config = json.loads((ROOT / "tools/pages/config.json").read_text(encoding="utf-8"))
    config["proxy_url"] = os.environ.get("MUSE_PROXY_URL", config["proxy_url"])
    (DOCS / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    shutil.copy(ROOT / "app/static/icon.svg", DOCS / "icon.svg")
    shutil.copy(ROOT / "tools/pages/local-backend.js", DOCS / "local-backend.js")
    for name in ("celebrities", "coaches", "meals"):
        shutil.copy(ROOT / f"app/data/{name}.json", DOCS / "data" / f"{name}.json")
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")
    print(f"[build_pages] wrote {sum(1 for _ in DOCS.rglob('*') if _.is_file())} files to {DOCS}")


if __name__ == "__main__":
    main()
