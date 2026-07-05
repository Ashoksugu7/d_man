"""Pose estimation wrapper around MediaPipe Pose.

Improvements over the original version:
- The detector is created ONCE and reused (model load per request was the
  main cost); calls are serialized with a lock (MediaPipe graphs are not
  thread-safe).
- Landmarks below a visibility threshold (env ``POSE_MIN_VISIBILITY``,
  default 0.3) are dropped instead of returning garbage coordinates for
  occluded joints. Shoulders and hips are required — if either pair is
  unreliable the whole detection is rejected (the warp needs them).
- Supports the modern MediaPipe **Tasks API** (``PoseLandmarker``) when a
  model file is provided via env ``POSE_LANDMARKER_MODEL`` — this works on
  mediapipe >= 0.10.35 where ``mp.solutions`` was removed. Otherwise falls
  back to the legacy solutions API, then to a heuristic layout.
- Runtime failures are logged (once) instead of silently swallowed.

Public API (unchanged): ``estimate_body_keypoints``, ``mediapipe_available``.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Dict, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------- config

_MIN_VISIBILITY = float(os.environ.get("POSE_MIN_VISIBILITY", "0.3"))
_TASKS_MODEL = os.environ.get("POSE_LANDMARKER_MODEL", "")  # path to .task file
_MODEL_COMPLEXITY = int(os.environ.get("POSE_MODEL_COMPLEXITY", "1"))

# MediaPipe Pose landmark indices we care about (same for both APIs)
_LM = {
    "left_shoulder": 11,
    "right_shoulder": 12,
    "left_elbow": 13,
    "right_elbow": 14,
    "left_wrist": 15,
    "right_wrist": 16,
    "left_hip": 23,
    "right_hip": 24,
    "left_knee": 25,
    "right_knee": 26,
    "left_ankle": 27,
    "right_ankle": 28,
    "nose": 0,
}
# joints the affine warp cannot work without
_REQUIRED = ("left_shoulder", "right_shoulder", "left_hip", "right_hip")
# optional joints: dropped individually when below the visibility threshold
_OPTIONAL = ("left_elbow", "right_elbow", "left_wrist", "right_wrist",
             "left_knee", "right_knee", "left_ankle", "right_ankle", "nose")

# ---------------------------------------------------------------- backends

_lock = threading.Lock()
_backend: Optional[str] = None      # "tasks" | "legacy" | None
_detector = None                    # cached detector instance
_init_done = False


def _init_backend() -> None:
    """Pick and initialize a MediaPipe backend once. Never raises."""
    global _backend, _detector, _init_done
    if _init_done:
        return
    _init_done = True

    # 1) modern Tasks API (mediapipe >= 0.10; required on >= 0.10.35)
    if _TASKS_MODEL:
        if not os.path.exists(_TASKS_MODEL):
            logger.warning("POSE_LANDMARKER_MODEL set but not found: %s", _TASKS_MODEL)
        else:
            try:
                from mediapipe.tasks import python as mp_python  # type: ignore
                from mediapipe.tasks.python import vision  # type: ignore
                opts = vision.PoseLandmarkerOptions(
                    base_options=mp_python.BaseOptions(model_asset_path=_TASKS_MODEL),
                    running_mode=vision.RunningMode.IMAGE,
                    min_pose_detection_confidence=0.4,
                )
                _detector = vision.PoseLandmarker.create_from_options(opts)
                _backend = "tasks"
                logger.info("pose backend: Tasks API (%s)", os.path.basename(_TASKS_MODEL))
                return
            except Exception:
                logger.exception("Tasks API init failed; trying legacy solutions API")

    # 2) legacy solutions API (mediapipe < 0.10.35)
    try:
        import mediapipe as mp  # type: ignore
        pose_mod = getattr(getattr(mp, "solutions", None), "pose", None)
        if pose_mod is not None and hasattr(pose_mod, "Pose"):
            _detector = pose_mod.Pose(
                static_image_mode=True,
                model_complexity=_MODEL_COMPLEXITY,
                enable_segmentation=False,
                min_detection_confidence=0.4,
            )
            _backend = "legacy"
            logger.info("pose backend: legacy solutions API")
            return
        logger.warning("mediapipe present but mp.solutions.pose unavailable "
                       "(>=0.10.35?) — set POSE_LANDMARKER_MODEL to use the Tasks API")
    except Exception:
        logger.warning("mediapipe not available; using heuristic keypoints", exc_info=True)

    _backend = None


def _disable_backend(exc: Exception) -> None:
    """A runtime failure: log once, drop to heuristic for future calls."""
    global _backend, _detector
    logger.error("pose backend '%s' failed at runtime; falling back to "
                 "heuristic keypoints: %s", _backend, exc)
    try:
        if _detector is not None and hasattr(_detector, "close"):
            _detector.close()
    except Exception:
        pass
    _backend, _detector = None, None


def _detect(image_rgb: np.ndarray):
    """Run the active backend. Returns list of landmarks or None."""
    if _backend == "tasks":
        import mediapipe as mp  # type: ignore
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB,
                          data=np.ascontiguousarray(image_rgb))
        res = _detector.detect(mp_img)
        if not res.pose_landmarks:
            return None
        return res.pose_landmarks[0]
    if _backend == "legacy":
        res = _detector.process(image_rgb)
        if not res.pose_landmarks:
            return None
        return res.pose_landmarks.landmark
    return None


# ---------------------------------------------------------------- public API

def estimate_body_keypoints(image_rgb: np.ndarray) -> Optional[Dict[str, Tuple[float, float]]]:
    """Return body keypoints in pixel coords, or None if no person detected.

    Always contains: left/right_shoulder, left/right_hip, neck (+ nose and
    limb joints when confidently visible). MediaPipe 'left' is the subject's
    left = image right; the warp handles orientation consistently.
    """
    h, w = image_rgb.shape[:2]

    with _lock:
        _init_backend()
        if _backend is None:
            pts = _heuristic_keypoints(w, h)
        else:
            try:
                lm = _detect(image_rgb)
            except Exception as exc:  # pragma: no cover - runtime-specific
                _disable_backend(exc)
                pts = _heuristic_keypoints(w, h)
            else:
                if lm is None:
                    return None
                pts = _filter_landmarks(lm, w, h)
                if pts is None:      # person found but core joints unreliable
                    return None

    neck = (
        (pts["left_shoulder"][0] + pts["right_shoulder"][0]) / 2,
        (pts["left_shoulder"][1] + pts["right_shoulder"][1]) / 2,
    )
    out: Dict[str, Tuple[float, float]] = {k: pts[k] for k in _REQUIRED}
    out["neck"] = neck
    for k in _OPTIONAL:
        if k in pts:
            out[k] = pts[k]
    return out


def _filter_landmarks(lm, w: int, h: int) -> Optional[Dict[str, Tuple[float, float]]]:
    """Pixel coords for confident landmarks; None if core joints are weak."""
    pts: Dict[str, Tuple[float, float]] = {}
    for name, idx in _LM.items():
        p = lm[idx]
        vis = getattr(p, "visibility", 1.0)
        required = name in _REQUIRED
        if not required and vis < _MIN_VISIBILITY:
            continue
        # required joints get a laxer bar — reject only if clearly absent
        if required and vis < min(_MIN_VISIBILITY, 0.15):
            return None
        pts[name] = (float(p.x) * w, float(p.y) * h)
    return pts


def mediapipe_available() -> bool:
    with _lock:
        _init_backend()
        return _backend is not None


def pose_backend() -> str:
    """'tasks' | 'legacy' | 'heuristic' — for /api/health introspection."""
    with _lock:
        _init_backend()
        return _backend or "heuristic"


def _heuristic_keypoints(w: int, h: int) -> Dict[str, Tuple[float, float]]:
    """Fallback: assume a centered, upright, full-body person."""
    return {
        "left_shoulder": (w * 0.62, h * 0.28),
        "right_shoulder": (w * 0.38, h * 0.28),
        "left_elbow": (w * 0.66, h * 0.45),
        "right_elbow": (w * 0.34, h * 0.45),
        "left_wrist": (w * 0.62, h * 0.58),
        "right_wrist": (w * 0.38, h * 0.58),
        "left_hip": (w * 0.58, h * 0.62),
        "right_hip": (w * 0.42, h * 0.62),
        "left_knee": (w * 0.56, h * 0.80),
        "right_knee": (w * 0.44, h * 0.80),
        "left_ankle": (w * 0.55, h * 0.96),
        "right_ankle": (w * 0.45, h * 0.96),
        "nose": (w * 0.5, h * 0.15),
    }
