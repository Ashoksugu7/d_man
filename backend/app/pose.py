"""Pose estimation wrapper around MediaPipe Pose.

Falls back gracefully if mediapipe is unavailable so the rest of the app
(and tests) can still run with a manual/heuristic keypoint estimate.
"""
from __future__ import annotations

from typing import Optional, Dict, Tuple
import numpy as np

try:
    import mediapipe as mp  # type: ignore
    _MP_AVAILABLE = True
except Exception:  # pragma: no cover - optional dep at runtime
    _MP_AVAILABLE = False


# MediaPipe Pose landmark indices we care about
_LM = {
    "left_shoulder": 11,
    "right_shoulder": 12,
    "left_hip": 23,
    "right_hip": 24,
    "left_knee": 25,
    "right_knee": 26,
    "left_ankle": 27,
    "right_ankle": 28,
    "nose": 0,
}


def estimate_body_keypoints(image_rgb: np.ndarray) -> Optional[Dict[str, Tuple[float, float]]]:
    """Return body keypoints in pixel coords, or None if no person detected.

    Keys: left_shoulder, right_shoulder, left_hip, right_hip, neck.
    Note: MediaPipe 'left' is the subject's left = image right. We keep
    MediaPipe's naming and let the warp handle orientation consistently.
    """
    h, w = image_rgb.shape[:2]

    if _MP_AVAILABLE:
        with mp.solutions.pose.Pose(
            static_image_mode=True, model_complexity=1,
            enable_segmentation=False, min_detection_confidence=0.4,
        ) as pose:
            res = pose.process(image_rgb)
        if not res.pose_landmarks:
            return None
        lm = res.pose_landmarks.landmark
        pts = {name: (lm[idx].x * w, lm[idx].y * h) for name, idx in _LM.items()}
    else:
        # Heuristic fallback: assume a centered, upright, full-body person.
        pts = {
            "left_shoulder": (w * 0.62, h * 0.28),
            "right_shoulder": (w * 0.38, h * 0.28),
            "left_hip": (w * 0.58, h * 0.62),
            "right_hip": (w * 0.42, h * 0.62),
            "left_knee": (w * 0.56, h * 0.80),
            "right_knee": (w * 0.44, h * 0.80),
            "left_ankle": (w * 0.55, h * 0.96),
            "right_ankle": (w * 0.45, h * 0.96),
            "nose": (w * 0.5, h * 0.15),
        }

    neck = (
        (pts["left_shoulder"][0] + pts["right_shoulder"][0]) / 2,
        (pts["left_shoulder"][1] + pts["right_shoulder"][1]) / 2,
    )
    out = {
        "left_shoulder": pts["left_shoulder"],
        "right_shoulder": pts["right_shoulder"],
        "left_hip": pts["left_hip"],
        "right_hip": pts["right_hip"],
        "neck": neck,
    }
    # 'nose' (head reference) is used by the Phase 4 height calibration.
    if "nose" in pts:
        out["nose"] = pts["nose"]
    for k in ("left_knee", "right_knee", "left_ankle", "right_ankle"):
        if k in pts:
            out[k] = pts[k]
    return out


def mediapipe_available() -> bool:
    return _MP_AVAILABLE
