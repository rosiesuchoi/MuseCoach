"""Checks that your Anthropic key works and that the AI can really see an image, end to end.

Run it yourself (the key stays in your .env file; this script never prints it):
    .venv\\Scripts\\python tools/check_key.py                  # uses a picture of an apple that the script draws
    .venv\\Scripts\\python tools/check_key.py path\\to\\meal.jpg   # or use one of your own photos

It runs the same pipeline as the app: identify (Claude vision) -> look up USDA nutrition -> explain.
Cost: about one to two cents per run.
"""

from __future__ import annotations

import base64
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw  # noqa: E402

from app import config, rag, vision  # noqa: E402


def draw_apple() -> bytes:
    img = Image.new("RGB", (512, 512), "white")
    d = ImageDraw.Draw(img)
    d.ellipse((96, 120, 416, 440), fill=(200, 30, 40))          # red apple body
    d.ellipse((130, 150, 230, 250), fill=(225, 80, 85))         # highlight
    d.rectangle((248, 70, 264, 140), fill=(110, 70, 30))        # stem
    d.ellipse((264, 60, 350, 110), fill=(60, 150, 60))          # leaf
    out = io.BytesIO()
    img.save(out, "JPEG", quality=90)
    return out.getvalue()


def main() -> int:
    config.load_env()
    key = config.anthropic_key()
    if not key:
        print("No API key found.\n  1. Copy .env.example to .env\n  2. Put your key after ANTHROPIC_API_KEY=\n  3. Run this again.")
        return 1
    print(f"Found a key in your environment ({len(key)} characters). It will only be sent to api.anthropic.com.")

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        path = Path(args[0])
        if not path.is_file():
            print(f"Can't find the photo: {path}")
            return 1
        raw, label = path.read_bytes(), f"your photo {path.name}"
    else:
        raw, label = draw_apple(), "a drawn picture of a red apple"
    jpeg = vision.prepare_image(raw)
    print(f"Sending {label} ({len(jpeg) // 1024} KB)...")

    identify, explain = rag.anthropic_functions(key)
    context = {"goal": "maintain", "remaining_kcal": 1200, "target_kcal": 2000, "minor": False}
    try:
        r = rag.analyze_meal(base64.b64encode(jpeg).decode(), context, identify, explain)
    except rag.PipelineError as e:
        if e.status == 422 and not args:  # the AI read the drawing but, reasonably, doesn't call a cartoon real food
            print(f"\nThe key works and the AI can see images: it looked at the drawing and answered:\n  {e.message}\n"
                  "A cartoon isn't a good test meal. Try a real photo:\n  .venv\\Scripts\\python tools/check_key.py path\\to\\meal.jpg")
            return 0
        print(f"\nThe pipeline stopped: {e.message}")
        return 2
    except Exception as e:  # by default show only the type: never details that could contain request data
        print(f"\nUnexpected failure ({type(e).__name__}).")
        if "--debug" in sys.argv:  # opt-in: the traceback, with the key blanked out
            import traceback

            print(traceback.format_exc().replace(key, "<KEY>"))
        return 3

    print(f"\nThe AI saw: {r['meal_name']}")
    for i in r["items"]:
        src = {"usda": "USDA", "estimate": "AI estimate", "none": "no data"}[i["source"]["type"]]
        cal = "?" if i["kcal"] is None else i["kcal"]
        print(f"  - {i['name']}: about {i['grams']:g} g, {cal} cal  [{src}]")
    print(f"Total: {r['total_kcal']} calories (likely {r['kcal_range'][0]}-{r['kcal_range'][1]}), confidence {r['confidence']}")
    v = r["insight"]["verdict"]
    print(f"Verdict: {v['rating']} - {v['headline']}")
    if r["flags"]:
        print("Flags: " + ", ".join(f["label"] for f in r["flags"]))
    print("\nIt works: the key is valid, the AI can see images, and the USDA lookup ran.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
