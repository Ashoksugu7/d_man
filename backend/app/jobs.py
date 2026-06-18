"""Celery async job pipeline for HD try-on.

The HTTP layer enqueues `run_hd_tryon` and returns a job id immediately; the
worker processes it and reports progress via Celery's custom task state. The
frontend polls GET /api/tryon/hd/{job_id}.

Local dev without a broker: set CELERY_TASK_ALWAYS_EAGER=1 and tasks run inline
in the API process (no worker/redis needed) — used by the test suite.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Tuple

import cv2
import numpy as np
from celery import Celery
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BASE_DIR.parent
ASSETS_DIR = Path(os.getenv("ASSETS_DIR", REPO_DIR / "assets"))
RESULTS_DIR = Path(os.getenv("RESULTS_DIR", BASE_DIR / "storage" / "results"))
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

EAGER = os.getenv("CELERY_TASK_ALWAYS_EAGER", "0") in ("1", "true", "True")
BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
# In eager mode (tests / no-broker dev) keep results in-process so update_state
# and result retrieval don't require a running Redis.
RESULT_BACKEND = os.getenv(
    "CELERY_RESULT_BACKEND",
    "cache+memory://" if EAGER else BROKER_URL,
)

celery_app = Celery("tryon", broker=BROKER_URL, backend=RESULT_BACKEND)
celery_app.conf.update(
    task_always_eager=EAGER,
    task_eager_propagates=True,
    task_store_eager_result=True,
    broker_connection_retry_on_startup=True,  # silence Celery 6.0 deprecation
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
)


# --- shared helpers (kept here so the worker has no FastAPI dependency) ------
def _load_catalog():
    path = ASSETS_DIR / "catalog.json"
    return json.loads(path.read_text()) if path.exists() else []


def _garment_keypoints(garment: dict, img_w: int, img_h: int) -> Dict[str, Tuple[float, float]]:
    data = json.loads((ASSETS_DIR / garment["keypoints"]).read_text())
    if "keypoints_norm" in data:
        return {k: (v[0] * img_w, v[1] * img_h) for k, v in data["keypoints_norm"].items()}
    cw, ch = data.get("canvas", [img_w, img_h])
    sx, sy = img_w / cw, img_h / ch
    return {k: (v[0] * sx, v[1] * sy) for k, v in data["keypoints_px"].items()}


@celery_app.task(bind=True, name="run_hd_tryon")
def run_hd_tryon(self, garment_id: str, photo_path: str, output_format: str = "png"):
    """Worker task: pose -> HD inference engine -> save result.

    Reports progress with self.update_state(state='PROGRESS', meta={...}).
    Returns {result_url, result_id} on success.
    """
    # Imports are inside the task so the worker only loads heavy deps when it
    # actually runs (and so EAGER mode in tests stays light).
    from .pose import estimate_body_keypoints
    from .inference import get_engine

    def progress(pct: int, msg: str):
        self.update_state(state="PROGRESS", meta={"progress": pct, "message": msg})

    progress(2, "Queued")
    garment = next((g for g in _load_catalog() if g["id"] == garment_id), None)
    if garment is None:
        raise ValueError(f"Unknown garment_id: {garment_id}")

    pil = Image.open(photo_path).convert("RGB")
    user_bgr = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)

    progress(8, "Detecting pose")
    body_kp = estimate_body_keypoints(np.array(pil))
    if body_kp is None:
        raise ValueError("No person detected in the photo")

    g_img = Image.open(ASSETS_DIR / garment["image"]).convert("RGBA")
    g_w, g_h = g_img.size
    g_arr = np.array(g_img)
    garment_rgba = np.dstack([
        cv2.cvtColor(g_arr[:, :, :3], cv2.COLOR_RGB2BGR), g_arr[:, :, 3],
    ])
    garment_kp = _garment_keypoints(garment, g_w, g_h)
    category = garment.get("category", "shirt")

    engine = get_engine()
    result_bgr = engine.generate(user_bgr, garment_rgba, garment_kp, body_kp,
                                 category, progress=progress)

    out_fmt = output_format if output_format in ("png", "webp") else "png"
    out_id = self.request.id or os.urandom(6).hex()
    out_name = f"hd_{out_id}.{out_fmt}"
    params = [cv2.IMWRITE_WEBP_QUALITY, 92] if out_fmt == "webp" else []
    cv2.imwrite(str(RESULTS_DIR / out_name), result_bgr, params)

    progress(100, "Done")
    return {"result_id": out_id, "result_url": f"/results/{out_name}",
            "garment_id": garment_id, "engine": engine.name}
