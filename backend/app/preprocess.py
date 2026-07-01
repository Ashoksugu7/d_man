"""Mac-friendly preprocessing for local diffusion try-on.

The official IDM-VTON/CatVTON pipelines build the garment-agnostic mask with
DensePose + SCHP (detectron2), which is CUDA-first and painful on macOS. We
avoid that entirely: the person silhouette comes from MediaPipe Selfie
Segmentation and the clothing region from the pose keypoints we already detect.

Output mask convention: uint8, 255 = "inpaint here" (the clothing area),
0 = keep the original pixels.
"""
from __future__ import annotations

from typing import Dict, Tuple
import numpy as np
import cv2

try:
    import mediapipe as mp
    _MP_SELFIE_SEGMENTATION = getattr(
        getattr(getattr(mp, "solutions", None), "selfie_segmentation", None),
        "SelfieSegmentation",
        None,
    )
    _MP = _MP_SELFIE_SEGMENTATION is not None
except Exception:  # pragma: no cover
    _MP_SELFIE_SEGMENTATION = None
    _MP = False


def person_silhouette(image_rgb: np.ndarray) -> np.ndarray:
    """Binary person mask (255=person) via MediaPipe Selfie Segmentation.

    Falls back to all-foreground if MediaPipe is unavailable.
    """
    h, w = image_rgb.shape[:2]
    if not _MP or _MP_SELFIE_SEGMENTATION is None:
        return np.full((h, w), 255, np.uint8)
    with _MP_SELFIE_SEGMENTATION(model_selection=1) as seg:
        res = seg.process(image_rgb)
    if res.segmentation_mask is None:
        return np.full((h, w), 255, np.uint8)
    return (res.segmentation_mask > 0.5).astype(np.uint8) * 255


def _poly_mask(shape, pts) -> np.ndarray:
    m = np.zeros(shape[:2], np.uint8)
    cv2.fillPoly(m, [np.array(pts, np.int32)], 255)
    return m


def clothing_region(image_shape, body_kp: Dict[str, Tuple[float, float]],
                    category: str) -> np.ndarray:
    """Coarse clothing area from pose keypoints.

    Tops  -> torso + upper arms (shoulders down to mid-hip, widened).
    Pants -> waist (hips) down to ankles.
    """
    h, w = image_shape[:2]

    def P(k):
        return np.array(body_kp[k], np.float32)

    if (category or "").lower() == "pant":
        lh, rh = P("left_hip"), P("right_hip")
        la, ra = P("left_ankle"), P("right_ankle")
        hip_mid = (lh + rh) / 2
        widen = 1.4
        lh2 = hip_mid + (lh - hip_mid) * widen
        rh2 = hip_mid + (rh - hip_mid) * widen
        pts = [rh2, lh2, la + (la - lh) * 0.1, ra + (ra - rh) * 0.1]
        # order: right hip, left hip, left ankle, right ankle
        pts = [rh2, lh2, la, ra]
    else:
        ls, rs = P("left_shoulder"), P("right_shoulder")
        lh, rh = P("left_hip"), P("right_hip")
        sh_mid = (ls + rs) / 2
        widen = 1.45  # include upper arms
        ls2 = sh_mid + (ls - sh_mid) * widen
        rs2 = sh_mid + (rs - sh_mid) * widen
        # extend a little above shoulders (collar) and past hips
        up = (sh_mid - (lh + rh) / 2) * 0.08
        ls2 += up
        rs2 += up
        hip_drop = ((lh + rh) / 2 - sh_mid) * 0.10
        lh2 = lh + hip_drop
        rh2 = rh + hip_drop
        pts = [rs2, ls2, lh2, rh2]

    pts = [(float(np.clip(p[0], 0, w)), float(np.clip(p[1], 0, h))) for p in pts]
    return _poly_mask(image_shape, pts)


def build_inpaint_mask(image_rgb: np.ndarray,
                       body_kp: Dict[str, Tuple[float, float]],
                       category: str) -> np.ndarray:
    """Final inpaint mask = clothing region ∩ person, cleaned + dilated."""
    region = clothing_region(image_rgb.shape, body_kp, category)
    person = person_silhouette(image_rgb)
    mask = cv2.bitwise_and(region, person)

    # Clean up and soften the boundary a touch.
    k = max(3, (min(image_rgb.shape[:2]) // 120) | 1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
    mask = cv2.dilate(mask, np.ones((k, k), np.uint8), iterations=1)
    return mask
