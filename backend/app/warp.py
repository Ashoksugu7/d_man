"""Garment warping & compositing.

Sprint 1 uses an affine fit driven by garment shoulder + hem keypoints mapped
onto body landmarks (shoulders + hips from pose estimation). TPS comes later.

Two accuracy adjustments matter for a natural fit:

* MediaPipe shoulder landmarks sit at the *joint* (inside the deltoid), which
  is narrower than where a shirt's shoulder seam actually rests. We widen the
  shoulder span outward so the garment isn't tight/"caped".
* The hip landmarks sit at the hip joints; a t-shirt hem falls a little below.
  We extend the hem target downward past the hips.

All factors are gathered in FitParams so they can be tuned per garment later.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple
import numpy as np
import cv2


def _to_np(pt) -> np.ndarray:
    return np.array([pt[0], pt[1]], dtype=np.float32)


@dataclass
class FitParams:
    shoulder_widen: float = 1.18   # widen shoulder span (joint -> seam)
    hip_widen: float = 1.10        # widen hip span for the hem line
    hem_extend: float = 1.30       # how far below shoulders the hem sits
                                   # (1.0 = at hips, >1 = below hips)
    neck_lift: float = 0.06        # raise the whole garment by this fraction
                                   # of shoulder->hip length (sit collar on neck)


@dataclass
class PantFitParams:
    waist_widen: float = 1.12      # waistband a bit wider than hip joints
    waist_lift: float = 0.10       # raise waistband above hips (fraction of
                                   # hip->ankle length) so it sits at the waist
    ankle_extend: float = 1.02     # nudge hem slightly past the ankle


TOP_CATEGORIES = {"shirt", "tshirt", "polo", "kurta", "henley", "top"}


def _body_quad(body_kp: Dict[str, Tuple[float, float]], p: FitParams):
    """Build the destination quad (shoulders + hem corners) on the body."""
    b_rs = _to_np(body_kp["right_shoulder"])
    b_ls = _to_np(body_kp["left_shoulder"])
    b_rh = _to_np(body_kp["right_hip"])
    b_lh = _to_np(body_kp["left_hip"])

    sh_mid = (b_rs + b_ls) / 2.0
    hip_mid = (b_rh + b_lh) / 2.0
    torso = hip_mid - sh_mid                      # shoulder -> hip vector
    lift = torso * p.neck_lift

    # Widen shoulders outward from their midline.
    rs = sh_mid + (b_rs - sh_mid) * p.shoulder_widen - lift
    ls = sh_mid + (b_ls - sh_mid) * p.shoulder_widen - lift

    # Hem line: extend down past hips, widen, keep left/right separation.
    hem_mid = sh_mid + torso * p.hem_extend - lift
    rh = hem_mid + (b_rh - hip_mid) * p.hip_widen
    lh = hem_mid + (b_lh - hip_mid) * p.hip_widen
    return rs, ls, rh, lh


def _lstsq_affine(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Plain least-squares 2x3 affine over N>=3 correspondences.

    We deliberately avoid cv2.estimateAffine2D's RANSAC/LMEDS: with few points
    and a real (slightly turned) pose those methods discard a point as an
    "outlier" and skew the fit. Least squares keeps every correspondence.
    """
    P = np.column_stack([src, np.ones(len(src))]).astype(np.float64)
    row1, *_ = np.linalg.lstsq(P, dst[:, 0].astype(np.float64), rcond=None)
    row2, *_ = np.linalg.lstsq(P, dst[:, 1].astype(np.float64), rcond=None)
    return np.array([row1, row2], dtype=np.float32)


def _pant_body_quad(body_kp: Dict[str, Tuple[float, float]], p: PantFitParams):
    """Destination quad for pants: waistband (at hips, lifted) + ankle hems."""
    rh = _to_np(body_kp["right_hip"])
    lh = _to_np(body_kp["left_hip"])
    ra = _to_np(body_kp["right_ankle"])
    la = _to_np(body_kp["left_ankle"])

    hip_mid = (rh + lh) / 2.0
    ankle_mid = (ra + la) / 2.0
    leg = ankle_mid - hip_mid
    lift = leg * p.waist_lift

    rw = hip_mid + (rh - hip_mid) * p.waist_widen - lift
    lw = hip_mid + (lh - hip_mid) * p.waist_widen - lift
    r_ank = hip_mid + (ra - hip_mid) * p.ankle_extend
    l_ank = hip_mid + (la - hip_mid) * p.ankle_extend
    return rw, lw, r_ank, l_ank


def compute_affine_pant(garment_kp: Dict[str, Tuple[float, float]],
                        body_kp: Dict[str, Tuple[float, float]],
                        p: PantFitParams | None = None) -> np.ndarray:
    """Least-squares affine mapping pant waist+ankle keypoints onto the body."""
    p = p or PantFitParams()
    g_rw = _to_np(garment_kp["right_waist"])
    g_lw = _to_np(garment_kp["left_waist"])
    g_ra = _to_np(garment_kp["right_ankle"])
    g_la = _to_np(garment_kp["left_ankle"])
    rw, lw, r_ank, l_ank = _pant_body_quad(body_kp, p)
    src = np.stack([g_rw, g_lw, g_ra, g_la])
    dst = np.stack([rw, lw, r_ank, l_ank])
    return _lstsq_affine(src, dst)


def compute_affine(garment_kp: Dict[str, Tuple[float, float]],
                   body_kp: Dict[str, Tuple[float, float]],
                   p: FitParams | None = None) -> np.ndarray:
    """Least-squares 2x3 affine mapping garment-space -> body-space.

    Uses four correspondences (both shoulders + both hem corners) so the
    garment's width is constrained at top *and* bottom, giving a far more
    natural fit than a single hem-midpoint.
    """
    p = p or FitParams()

    g_rs = _to_np(garment_kp["right_shoulder"])
    g_ls = _to_np(garment_kp["left_shoulder"])
    g_rh = _to_np(garment_kp["right_hem"])
    g_lh = _to_np(garment_kp["left_hem"])

    rs, ls, rh, lh = _body_quad(body_kp, p)

    src = np.stack([g_rs, g_ls, g_rh, g_lh])
    dst = np.stack([rs, ls, rh, lh])
    return _lstsq_affine(src, dst)


def affine_for(category: str,
               garment_kp: Dict[str, Tuple[float, float]],
               body_kp: Dict[str, Tuple[float, float]]) -> np.ndarray:
    """Pick the right warp for the garment category (top vs pant)."""
    if (category or "").lower() == "pant":
        return compute_affine_pant(garment_kp, body_kp)
    return compute_affine(garment_kp, body_kp)


def warp_and_composite(user_bgr: np.ndarray,
                       garment_rgba: np.ndarray,
                       garment_kp: Dict[str, Tuple[float, float]],
                       body_kp: Dict[str, Tuple[float, float]],
                       category: str = "shirt") -> np.ndarray:
    """Warp garment onto user photo and alpha-composite. Returns BGR image."""
    h, w = user_bgr.shape[:2]
    M = affine_for(category, garment_kp, body_kp)

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


def draw_debug(user_bgr: np.ndarray,
               body_kp: Dict[str, Tuple[float, float]],
               category: str = "shirt") -> np.ndarray:
    """Overlay detected body landmarks + the target garment quad, so pose
    errors can be told apart from warp errors."""
    out = user_bgr.copy()

    colors = {
        "left_shoulder": (0, 255, 0), "right_shoulder": (0, 255, 0),
        "left_hip": (255, 0, 0), "right_hip": (255, 0, 0),
        "left_ankle": (255, 128, 0), "right_ankle": (255, 128, 0),
        "neck": (0, 255, 255),
    }
    for name, col in colors.items():
        if name in body_kp:
            x, y = int(body_kp[name][0]), int(body_kp[name][1])
            cv2.circle(out, (x, y), 6, col, -1)
            cv2.putText(out, name, (x + 8, y), cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, col, 1, cv2.LINE_AA)

    if (category or "").lower() == "pant":
        rw, lw, ra, la = _pant_body_quad(body_kp, PantFitParams())
        quad = np.array([lw, rw, ra, la], dtype=np.int32)
    else:
        rs, ls, rh, lh = _body_quad(body_kp, FitParams())
        quad = np.array([ls, rs, rh, lh], dtype=np.int32)
    cv2.polylines(out, [quad], True, (0, 165, 255), 2)
    return out
