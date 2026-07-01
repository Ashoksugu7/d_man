"""Storage abstraction for garment images (Phase B).

Local-disk implementation writing under assets/garments/ (served by the /assets
static mount). Swap for S3/GCS in Phase E behind the same functions.
"""
from __future__ import annotations

import io
import os
from pathlib import Path

from PIL import Image

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BASE_DIR.parent
ASSETS_DIR = Path(os.getenv("ASSETS_DIR", REPO_DIR / "assets"))
GARMENTS_DIR = ASSETS_DIR / "garments"
THUMBS_DIR = GARMENTS_DIR / "thumbs"
GARMENTS_DIR.mkdir(parents=True, exist_ok=True)
THUMBS_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXT = {"png", "webp", "jpg", "jpeg"}


def save_image(garment_id: str, role: str | None, ext: str, data: bytes) -> str:
    """Write image bytes; return the catalog-relative path (garments/<name>.<ext>)."""
    ext = ext.lower().lstrip(".")
    if ext not in ALLOWED_EXT:
        raise ValueError(f"Unsupported image type: {ext}")
    stem = garment_id if not role else f"{garment_id}_{role}"
    rel = f"garments/{stem}.{ext}"
    (ASSETS_DIR / rel).write_bytes(data)
    return rel


def save_keypoints_json(garment_id: str, role: str | None, payload: dict) -> str:
    import json
    stem = garment_id if not role else f"{garment_id}_{role}"
    rel = f"garments/{stem}.json"
    (ASSETS_DIR / rel).write_text(json.dumps(payload, indent=2))
    return rel


def make_thumbnail(garment_id: str, image_rel: str, size: int = 256) -> str | None:
    """Generate a square-ish thumbnail; return its catalog-relative path."""
    try:
        src = ASSETS_DIR / image_rel
        im = Image.open(src).convert("RGBA")
        im.thumbnail((size, size))
        rel = f"garments/thumbs/{garment_id}.webp"
        # composite over white so thumbnails aren't transparent-on-dark
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        Image.alpha_composite(bg, im).convert("RGB").save(ASSETS_DIR / rel, "WEBP", quality=80)
        return rel
    except Exception:
        return None


def delete_rel(rel_path: str | None) -> None:
    if not rel_path:
        return
    try:
        (ASSETS_DIR / rel_path).unlink()
    except OSError:
        pass


def read_image_meta(data: bytes) -> tuple[int, int, bool]:
    """Return (width, height, has_alpha) — used for validation."""
    im = Image.open(io.BytesIO(data))
    has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
    return im.width, im.height, has_alpha


def remove_background(data: bytes, tol: int = 38) -> bytes:
    """Cut out a near-uniform background → transparent PNG.

    Flood-fills from the four corners (fixed range vs the corner colour) so a
    plain studio/white background becomes alpha=0 while the garment stays opaque.
    Good enough for typical product shots; for hard cases use a pre-made cutout.
    Returns PNG bytes (RGBA).
    """
    import numpy as np
    import cv2
    rgb = np.array(Image.open(io.BytesIO(data)).convert("RGB"))
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    h, w = bgr.shape[:2]
    mask = np.zeros((h + 2, w + 2), np.uint8)
    flags = cv2.FLOODFILL_MASK_ONLY | cv2.FLOODFILL_FIXED_RANGE | (255 << 8) | 4
    for seed in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, 0), (w // 2, h - 1)]:
        cv2.floodFill(bgr.copy(), mask, seed, 0, (tol, tol, tol), (tol, tol, tol), flags)
    bg = mask[1:-1, 1:-1]
    alpha = np.where(bg > 0, 0, 255).astype(np.uint8)
    k = max(3, (min(h, w) // 200) | 1)
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
    alpha = cv2.medianBlur(alpha, 5)
    out = np.dstack([rgb, alpha])
    buf = io.BytesIO()
    Image.fromarray(out, "RGBA").save(buf, "PNG")
    return buf.getvalue()
