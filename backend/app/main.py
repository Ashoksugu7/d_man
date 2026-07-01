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
from .warp import warp_and_composite, warp_lehenga, warp_saree, draw_debug
from .measure import estimate_measurements, recommend_size

# ---------------------------------------------------------------------------
# Paths & config
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent          # backend/
REPO_DIR = BASE_DIR.parent                                  # repo root
ASSETS_DIR = Path(os.getenv("ASSETS_DIR", REPO_DIR / "assets"))
RESULTS_DIR = Path(os.getenv("RESULTS_DIR", BASE_DIR / "storage" / "results"))
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR = Path(os.getenv("UPLOADS_DIR", BASE_DIR / "storage" / "uploads"))
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

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

# Garment CRUD + image/annotation API (Phase B).
from .garments_api import router as garments_router  # noqa: E402
app.include_router(garments_router)


def _load_catalog():
    path = ASSETS_DIR / "catalog.json"
    if not path.exists():
        return []
    return json.loads(path.read_text())


async def _list_garments() -> list[dict]:
    """All active garments — from the DB when available, else catalog.json."""
    if getattr(app.state, "db_ready", False):
        try:
            from .db import SessionLocal
            from .garments_repo import list_active
            async with SessionLocal() as session:
                return await list_active(session)
        except Exception:
            pass
    return _load_catalog()


async def _get_garment(gid: str) -> dict | None:
    """One garment (catalog shape) — from the DB when available, else catalog."""
    if getattr(app.state, "db_ready", False):
        try:
            from .db import SessionLocal
            from .garments_repo import get_serialized
            async with SessionLocal() as session:
                g = await get_serialized(session, gid)
                if g:
                    return g
        except Exception:
            pass
    return next((g for g in _load_catalog() if g["id"] == gid), None)


async def _decode_photo(photo: UploadFile) -> np.ndarray:
    """Read an uploaded image into an RGB numpy array (raises HTTP 400)."""
    raw = await photo.read()
    try:
        # PIL decodes png / jpg / webp transparently (libwebp bundled).
        pil = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:
        raise HTTPException(
            400, "Could not read uploaded image (supported: PNG, JPEG, WebP)"
        )
    return np.array(pil)


def _load_piece(image_rel: str, keypoints_rel: str):
    """Load a garment piece -> (BGR+alpha numpy, keypoints in image pixels).

    Works for any single piece (shirt, pant, skirt, blouse, ...). Used directly
    and twice for the two-piece lehenga.
    """
    img = Image.open(ASSETS_DIR / image_rel).convert("RGBA")
    w, h = img.size
    arr = np.array(img)
    rgba = np.dstack([cv2.cvtColor(arr[:, :, :3], cv2.COLOR_RGB2BGR), arr[:, :, 3]])

    data = json.loads((ASSETS_DIR / keypoints_rel).read_text())
    if "keypoints_norm" in data:
        kp = {k: (v[0] * w, v[1] * h) for k, v in data["keypoints_norm"].items()}
    else:
        cw, ch = data.get("canvas", [w, h])
        kp = {k: (v[0] * w / cw, v[1] * h / ch) for k, v in data["keypoints_px"].items()}
    return rgba, kp


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


@app.on_event("startup")
async def _init_db():
    """Create tables + seed from catalog on startup. If the DB is unreachable,
    the app still runs and falls back to catalog.json (Phase A safety)."""
    app.state.db_ready = False
    try:
        from .db import create_all, SessionLocal
        from .garments_repo import seed_from_catalog, count
        await create_all()
        async with SessionLocal() as session:
            if await count(session) == 0:
                await seed_from_catalog(session)
        app.state.db_ready = True
    except Exception as e:  # pragma: no cover - depends on external DB
        print(f"[garment-db] unavailable, falling back to catalog.json: {e}")


@app.get("/api/garments")
async def garments():
    """Garments from the DB (Phase A); falls back to catalog.json if DB is down."""
    if getattr(app.state, "db_ready", False):
        try:
            from .db import SessionLocal
            from .garments_repo import list_active
            async with SessionLocal() as session:
                return await list_active(session)
        except Exception as e:
            print(f"[garment-db] read failed, using catalog.json: {e}")
    return _load_catalog()


@app.post("/api/tryon/image")
async def tryon_image(
    garment_id: str = Form(...),
    photo: UploadFile = File(...),
    output_format: str = Form("png"),
    debug: bool = Form(False),
    occlude: bool = Form(True),
    lighting: bool = Form(False),
    tps: bool = Form(False),
):
    garment = await _get_garment(garment_id)
    if garment is None:
        raise HTTPException(404, f"Unknown garment_id: {garment_id}")

    out_fmt = output_format.lower()
    if out_fmt not in ("png", "webp"):
        raise HTTPException(400, "output_format must be 'png' or 'webp'")

    user_rgb = await _decode_photo(photo)
    user_bgr = cv2.cvtColor(user_rgb, cv2.COLOR_RGB2BGR)

    body_kp = estimate_body_keypoints(user_rgb)
    if body_kp is None:
        raise HTTPException(422, "No person detected in the photo")

    category = garment.get("category", "shirt")

    if category == "lehenga":
        # Two-piece: warp the flared skirt, then the blouse on top.
        skirt_rgba, skirt_kp = _load_piece(garment["image"], garment["keypoints"])
        blouse_rgba, blouse_kp = _load_piece(
            garment["blouse_image"], garment["blouse_keypoints"]
        )
        result_bgr = warp_lehenga(user_bgr, blouse_rgba, blouse_kp,
                                  skirt_rgba, skirt_kp, body_kp)
    elif category == "saree":
        # Three-region: lower drape + blouse + pallu over the left shoulder.
        drape_rgba, drape_kp = _load_piece(garment["image"], garment["keypoints"])
        blouse_rgba, blouse_kp = _load_piece(
            garment["blouse_image"], garment["blouse_keypoints"])
        pallu_rgba, pallu_kp = _load_piece(
            garment["pallu_image"], garment["pallu_keypoints"])
        result_bgr = warp_saree(user_bgr, blouse_rgba, blouse_kp,
                                drape_rgba, drape_kp, pallu_rgba, pallu_kp, body_kp)
    else:
        garment_rgba, garment_kp = _load_piece(garment["image"], garment["keypoints"])
        result_bgr = warp_and_composite(
            user_bgr, garment_rgba, garment_kp, body_kp, category,
            occlude=occlude, lighting=lighting, tps=tps,
            fit_overrides=garment.get("fit_params"),
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


@app.post("/api/measure")
async def measure(
    photo: UploadFile = File(...),
    height_cm: float = Form(...),
):
    """Estimate body measurements from a full-body photo and recommend a size
    for every garment in the catalog.

    Returns 422 if no person is detected. If a person is found but the full
    body isn't in frame (missing ankles/nose), measurements come back null with
    a clear message and recommendations are omitted.
    """
    if height_cm <= 0 or height_cm > 260:
        raise HTTPException(400, "height_cm must be between 1 and 260")

    user_rgb = await _decode_photo(photo)

    body_kp = estimate_body_keypoints(user_rgb)
    if body_kp is None:
        raise HTTPException(422, "No person detected in the photo")

    measurements = estimate_measurements(body_kp, height_cm)

    if measurements is None:
        return JSONResponse({
            "ok": False,
            "measurements": None,
            "recommendations": {},
            "pose_method": "mediapipe" if mediapipe_available() else "fallback_heuristic",
            "message": (
                "Couldn't take measurements — make sure your whole body "
                "(head to ankles) is visible in the photo."
            ),
        })

    catalog = await _list_garments()
    recommendations = {}
    for g in catalog:
        rec = recommend_size(
            measurements, g.get("size_chart", {}), g.get("category", "shirt")
        )
        if rec is not None:
            recommendations[g["id"]] = rec

    return JSONResponse({
        "ok": True,
        "measurements": measurements,
        "recommendations": recommendations,
        "pose_method": "mediapipe" if mediapipe_available() else "fallback_heuristic",
        "note": (
            "Measurements are approximate, derived from a single 2D photo and "
            "your stated height. Use as a guide, not exact sizing."
        ),
    })


# ---------------------------------------------------------------------------
# HD (async, diffusion-ready) try-on — Phase 3
# ---------------------------------------------------------------------------
@app.post("/api/tryon/hd")
async def tryon_hd(
    garment_id: str = Form(...),
    photo: UploadFile = File(...),
    output_format: str = Form("png"),
):
    """Enqueue an HD try-on job and return its id immediately.

    The heavy work runs in a Celery worker (see app/jobs.py); poll
    GET /api/tryon/hd/{job_id} for status, progress, and the result URL.
    """
    if await _get_garment(garment_id) is None:
        raise HTTPException(404, f"Unknown garment_id: {garment_id}")

    raw = await photo.read()
    try:
        Image.open(io.BytesIO(raw)).verify()
    except Exception:
        raise HTTPException(400, "Could not read uploaded image")

    in_id = uuid.uuid4().hex[:12]
    in_path = UPLOADS_DIR / f"{in_id}"
    in_path.write_bytes(raw)

    from .jobs import run_hd_tryon
    async_result = run_hd_tryon.delay(garment_id, str(in_path), output_format)
    return JSONResponse({"job_id": async_result.id, "status": "queued"})


@app.get("/api/tryon/hd/{job_id}")
def tryon_hd_status(job_id: str):
    """Poll an HD job: returns status, progress%, and the result on success."""
    from .jobs import celery_app
    res = celery_app.AsyncResult(job_id)
    state = res.state  # PENDING | PROGRESS | SUCCESS | FAILURE | STARTED

    payload: dict = {"job_id": job_id, "status": state.lower()}
    if state == "PROGRESS" and isinstance(res.info, dict):
        payload["progress"] = res.info.get("progress", 0)
        payload["message"] = res.info.get("message", "")
    elif state == "SUCCESS":
        payload["progress"] = 100
        payload.update(res.result or {})
    elif state == "FAILURE":
        payload["error"] = str(res.info)
    elif state == "PENDING":
        payload["progress"] = 0
    return JSONResponse(payload)


@app.get("/api/result/{result_id}")
def get_result(result_id: str):
    for ext, mime in (("png", "image/png"), ("webp", "image/webp")):
        path = RESULTS_DIR / f"{result_id}.{ext}"
        if path.exists():
            return FileResponse(str(path), media_type=mime)
    raise HTTPException(404, "Result not found")
