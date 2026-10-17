"""Photo helpers for the server edition: normalize an upload to a small JPEG, and the labelled demo answer used when
no API key is configured. The real analysis (Claude vision + USDA retrieval) lives in app/rag.py."""

from __future__ import annotations

import io

from PIL import Image, ImageOps


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


def demo_estimate() -> dict:
    return {
        "meal_name": "Demo meal (no API key set)",
        "items": [{"name": "Estimated plate", "kcal": 500}],
        "total_kcal": 500,
        "confidence": "low",
        "demo": True,
    }
