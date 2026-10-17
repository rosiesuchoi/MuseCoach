"""Photo -> calorie estimate using Claude's vision. Falls back to a clearly-labelled demo
estimate when there is no API key, so the app still runs end to end offline."""

from __future__ import annotations

import base64
import io
import json
import os
import re

from PIL import Image, ImageOps

MODEL = os.environ.get("MUSE_VISION_MODEL", "claude-sonnet-5-5")

PROMPT = (
    "You are a nutrition assistant. Look at this meal photo and estimate calories. "
    "Reply with ONLY JSON: "
    '{"meal_name": str, "items": [{"name": str, "kcal": int}], "total_kcal": int, '
    '"confidence": "low"|"medium"|"high"}. '
    "If the photo does not show food, return total_kcal 0 and meal_name 'No food found'."
)


class PhotoError(ValueError):
    pass


def prepare_image(data: bytes) -> bytes:
    """Fix phone rotation, shrink (cheaper + faster), and re-encode as JPEG."""
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img).convert("RGB")
    except Exception as e:  # PIL raises many types for bad files
        raise PhotoError("Couldn't read that image. Try a JPEG or PNG.") from e
    img.thumbnail((1024, 1024))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=85)
    return out.getvalue()


def _demo() -> dict:
    return {
        "meal_name": "Demo meal (no API key set)",
        "items": [{"name": "Estimated plate", "kcal": 500}],
        "total_kcal": 500,
        "confidence": "low",
        "demo": True,
    }


def parse_reply(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise PhotoError("The estimate came back in an unexpected format.")
    data = json.loads(match.group(0))
    total = int(data.get("total_kcal", 0))
    if not 0 <= total <= 5000:  # sanity cap: no single plate is 5000+ kcal
        raise PhotoError("The estimate looked wrong. Try another photo or enter calories by hand.")
    items = [{"name": str(i.get("name", "?")), "kcal": int(i.get("kcal", 0))} for i in data.get("items", [])]
    return {
        "meal_name": str(data.get("meal_name", "Meal"))[:80],
        "items": items,
        "total_kcal": total,
        "confidence": data.get("confidence", "low"),
        "demo": False,
    }


def estimate_meal(image_bytes: bytes) -> dict:
    jpeg = prepare_image(image_bytes)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return _demo()
    import anthropic

    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=MODEL,
        max_tokens=500,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": base64.b64encode(jpeg).decode(),
                        },
                    },
                    {"type": "text", "text": PROMPT},
                ],
            }
        ],
    )
    return parse_reply(msg.content[0].text)
