"""Affine garment warping & compositing.

Sprint 1 uses a similarity/affine transform driven by 3 correspondences
(left shoulder, right shoulder, mid-hem -> body landmarks). This is the
"affine transform only" milestone; TPS comes in a later phase.
"""
from __future__ import annotations

from typing import Dict, Tuple
import numpy as np
import cv2


def _to_np(pt) -> np.ndarray:
    return np.array([pt[0], pt[1]], dtype=np.float32)


def compute_affine(garment_kp: Dict[str, Tuple[float, float]],
                   body_kp: Dict[str, Tuple[float, float]]) -> np.ndarray:
    """Estimate 2x3 affine mapping garment-space -> body-space.

    Source points (garment PNG pixel coords): right_shoulder, left_shoulder,
    and the midpoint of the hem.
    Destination points (user photo): shoulders, plus an estimated torso
    bottom derived from the hips.
    """
    g_rs = _to_np(garment_kp["right_shoulder"])
    g_ls = _to_np(garment_kp["left_shoulder"])
    g_hem = (_to_np(garment_kp["left_hem"]) + _to_np(garment_kp["right_hem"])) / 2.0

    b_rs = _to_np(body_kp["right_shoulder"])
    b_ls = _to_np(body_kp["left_shoulder"])
    b_hip = (_to_np(body_kp["left_hip"]) + _to_np(body_kp["right_hip"])) / 2.0

    # Extend a bit past the hips so the shirt hem sits naturally.
    shoulder_mid = (b_rs + b_ls) / 2.0
    b_hem = shoulder_mid + (b_hip - shoulder_mid) * 1.15

    src = np.stack([g_rs, g_ls, g_hem]).astype(np.float32)
    dst = np.stack([b_rs, b_ls, b_hem]).astype(np.float32)
    return cv2.getAffineTransform(src, dst)


def warp_and_composite(user_bgr: np.ndarray,
                       garment_rgba: np.ndarray,
                       garment_kp: Dict[str, Tuple[float, float]],
                       body_kp: Dict[str, Tuple[float, float]]) -> np.ndarray:
    """Warp garment onto user photo and alpha-composite. Returns BGR image."""
    h, w = user_bgr.shape[:2]
    M = compute_affine(garment_kp, body_kp)

    warped = cv2.warpAffine(
        garment_rgba, M, (w, h),
        flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )

    alpha = (warped[:, :, 3:4].astype(np.float32)) / 255.0
    fg = warped[:, :, :3].astype(np.float32)
    bg = user_bgr.astype(np.float32)
    out = fg * alpha + bg * (1.0 - alpha)
    return out.astype(np.uint8)
