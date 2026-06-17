"""FastAPI backend for Virtual Try-On (Sprint 1, static image mode)."""
from __future__ import annotations

import io
import json
import os
import uuid
from pathlib import Path
from typing import Dict, Tuple

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

from .pose import estimate_body_keypoints, mediapipe_available
from .warp import warp_and_composite, draw_debug

# ---------------------------------------------------------------------------
# Paths & config
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent          # backend/
REPO_DIR = BASE_DIR.parent                                  # repo root
ASSETS_DIR = Path(os.getenv("ASSETS_DIR", REPO_DIR / "assets"))
RESULTS_DIR = Path(os.getenv("RESULTS_DIR", BASE_DIR / "storage" / "results"))
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Virtual Try-On API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten for production
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve garment images and generated results statically.
app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")
app.mount("/results", StaticFiles(directory=str(RESULTS_DIR)), name="results")


def _load_catalog():
    path = ASSETS_DIR / "catalog.json"
    if not path.exists():
        return []
    return json.loads(path.read_text())


def _load_garment_keypoints(
    garment: dict, img_w: int, img_h: int
) -> Dict[str, Tuple[float, float]]:
    """Return garment keypoints in pixels for the *actual* image size.

    Prefers normalized keypoints (resolution-independent), so the annotation
    canvas size does not have to match the garment image size. Falls back to
    raw pixel keypoints, rescaling from the stored canvas if it differs.
    """
    kp_path = ASSETS_DIR / garment["keypoints"]
    data = json.loads(kp_path.read_text())

    if "keypoints_norm" in data:
        return {k: (v[0] * img_w, v[1] * img_h) for k, v in data["keypoints_norm"].items()}

    # Fallback: rescale pixel keypoints from their stored canvas dimensions.
    cw, ch = data.get("canvas", [img_w, img_h])
    sx, sy = img_w / cw, img_h / ch
    return {k: (v[0] * sx, v[1] * sy) for k, v in data["keypoints_px"].items()}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"status": "ok", "mediapipe": mediapipe_available()}


@app.get("/api/garments")
def garments():
    return _load_catalog()


@app.post("/api/tryon/image")
async def tryon_image(
    garment_id: str = Form(...),
    photo: UploadFile = File(...),
    output_format: str = Form("png"),
    debug: bool = Form(False),
):
    catalog = _load_catalog()
    garment = next((g for g in catalog if g["id"] == garment_id), None)
    if garment is None:
        raise HTTPException(404, f"Unknown garment_id: {garment_id}")

    out_fmt = output_format.lower()
    if out_fmt not in ("png", "webp"):
        raise HTTPException(400, "output_format must be 'png' or 'webp'")

    raw = await photo.read()
    try:
        # PIL decodes png / jpg / webp transparently (libwebp bundled).
        pil = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:
        raise HTTPException(
            400, "Could not read uploaded image (supported: PNG, JPEG, WebP)"
        )

    user_rgb = np.array(pil)
    user_bgr = cv2.cvtColor(user_rgb, cv2.COLOR_RGB2BGR)

    body_kp = estimate_body_keypoints(user_rgb)
    if body_kp is None:
        raise HTTPException(422, "No person detected in the photo")

    garment_img = Image.open(ASSETS_DIR / garment["image"]).convert("RGBA")
    g_w, g_h = garment_img.size
    garment_rgba = np.array(garment_img)
    # PIL gives RGBA; warp expects channels in BGRA-style only for the BGR
    # slice. Convert RGB->BGR for the color channels, keep alpha.
    garment_rgba = np.dstack([
        cv2.cvtColor(garment_rgba[:, :, :3], cv2.COLOR_RGB2BGR),
        garment_rgba[:, :, 3],
    ])
    garment_kp = _load_garment_keypoints(garment, g_w, g_h)
    category = garment.get("category", "shirt")

    result_bgr = warp_and_composite(
        user_bgr, garment_rgba, garment_kp, body_kp, category
    )
    if debug:
        # Overlay detected landmarks + target quad so pose vs warp errors are
        # distinguishable.
        result_bgr = draw_debug(result_bgr, body_kp, category)

    out_id = uuid.uuid4().hex[:12]
    out_name = f"{out_id}.{out_fmt}"
    write_params = [cv2.IMWRITE_WEBP_QUALITY, 90] if out_fmt == "webp" else []
    cv2.imwrite(str(RESULTS_DIR / out_name), result_bgr, write_params)

    return JSONResponse({
        "result_id": out_id,
        "result_url": f"/results/{out_name}",
        "garment_id": garment_id,
        "pose_method": "mediapipe" if mediapipe_available() else "fallback_heuristic",
        "keypoints": {k: list(v) for k, v in body_kp.items()},
    })


@app.get("/api/result/{result_id}")
def get_result(result_id: str):
    for ext, mime in (("png", "image/png"), ("webp", "image/webp")):
        path = RESULTS_DIR / f"{result_id}.{ext}"
        if path.exists():
            return FileResponse(str(path), media_type=mime)
    raise HTTPException(404, "Result not found")
