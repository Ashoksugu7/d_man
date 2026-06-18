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


@dataclass
class SkirtFitParams:
    waist_widen: float = 1.10      # waistband at the hips
    waist_lift: float = 0.06       # raise slightly above the hip joints
    hem_drop: float = 0.85         # hem position along hip->ankle (1.0 = ankle)
    hem_flare: float = 2.4         # how wide the hem flares vs the waist width


TOP_CATEGORIES = {"shirt", "tshirt", "polo", "kurta", "henley", "top",
                  "dupatta", "blouse"}
PANT_CATEGORIES = {"pant", "salwar", "palazzo", "trouser", "trousers"}

# Per-category fit overrides (Phase 5 Indian attire reuses the top/pant warps
# with tuned proportions).
_TOP_FIT = {
    "kurta": FitParams(hem_extend=2.35, shoulder_widen=1.15, neck_lift=0.05),
    "dupatta": FitParams(hem_extend=1.75, shoulder_widen=1.28, neck_lift=0.0),
    "blouse": FitParams(hem_extend=0.95, shoulder_widen=1.15, neck_lift=0.05),
}
_PANT_FIT = {
    "salwar": PantFitParams(waist_widen=1.18, ankle_extend=1.06),
    "palazzo": PantFitParams(waist_widen=1.22, ankle_extend=1.10),
}


def _top_params(category: str) -> FitParams:
    return _TOP_FIT.get((category or "").lower(), FitParams())


def _pant_params(category: str) -> PantFitParams:
    return _PANT_FIT.get((category or "").lower(), PantFitParams())


def category_kind(category: str) -> str:
    """Map a garment category to the warp kind: top | pant | skirt | lehenga."""
    c = (category or "").lower()
    if c in PANT_CATEGORIES:
        return "pant"
    if c in ("skirt", "saree"):
        # saree's single-piece (HD) fallback uses its drape, which is skirt-like
        return "skirt"
    if c == "lehenga":
        return "lehenga"
    return "top"


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


def _skirt_body_quad(body_kp: Dict[str, Tuple[float, float]], p: SkirtFitParams):
    """Destination quad for a (flared) skirt: waist at hips + flared hem."""
    rh = _to_np(body_kp["right_hip"])
    lh = _to_np(body_kp["left_hip"])
    ra = _to_np(body_kp["right_ankle"])
    la = _to_np(body_kp["left_ankle"])

    hip_mid = (rh + lh) / 2.0
    ankle_mid = (ra + la) / 2.0
    down = ankle_mid - hip_mid
    lift = down * p.waist_lift

    rw = hip_mid + (rh - hip_mid) * p.waist_widen - lift
    lw = hip_mid + (lh - hip_mid) * p.waist_widen - lift

    hem_center = hip_mid + down * p.hem_drop
    half = (lh - rh) / 2.0 * p.hem_flare   # flare the hem wide
    r_hem = hem_center - half
    l_hem = hem_center + half
    return rw, lw, r_hem, l_hem


def compute_affine_skirt(garment_kp: Dict[str, Tuple[float, float]],
                         body_kp: Dict[str, Tuple[float, float]],
                         p: SkirtFitParams | None = None) -> np.ndarray:
    """Least-squares affine mapping skirt waist+hem keypoints onto the body."""
    p = p or SkirtFitParams()
    g_rw = _to_np(garment_kp["right_waist"])
    g_lw = _to_np(garment_kp["left_waist"])
    g_rh = _to_np(garment_kp["right_hem"])
    g_lh = _to_np(garment_kp["left_hem"])
    rw, lw, r_hem, l_hem = _skirt_body_quad(body_kp, p)
    src = np.stack([g_rw, g_lw, g_rh, g_lh])
    dst = np.stack([rw, lw, r_hem, l_hem])
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
    """Pick the right warp for the garment category (top/pant/skirt)."""
    kind = category_kind(category)
    if kind == "pant":
        return compute_affine_pant(garment_kp, body_kp, _pant_params(category))
    if kind in ("skirt", "lehenga"):
        # Single-piece call (e.g. HD engines) treats the lehenga as its skirt.
        return compute_affine_skirt(garment_kp, body_kp)
    # top, plus attire that reuses the top warp (kurta, dupatta, blouse)
    return compute_affine(garment_kp, body_kp, _top_params(category))


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


def warp_lehenga(user_bgr: np.ndarray,
                 blouse_rgba: np.ndarray, blouse_kp,
                 skirt_rgba: np.ndarray, skirt_kp,
                 body_kp: Dict[str, Tuple[float, float]]) -> np.ndarray:
    """Two-piece lehenga: warp the flared skirt (hips->hem), then the blouse
    (cropped top) on top, compositing both onto the photo."""
    out = warp_and_composite(user_bgr, skirt_rgba, skirt_kp, body_kp, "skirt")
    out = warp_and_composite(out, blouse_rgba, blouse_kp, body_kp, "blouse")
    return out


def _pallu_body_quad(body_kp: Dict[str, Tuple[float, float]]):
    """Where the pallu drapes: over the wearer's LEFT shoulder, diagonally down
    across the front toward the RIGHT hip."""
    ls = _to_np(body_kp["left_shoulder"])
    rs = _to_np(body_kp["right_shoulder"])
    rh = _to_np(body_kp["right_hip"])
    lh = _to_np(body_kp["left_hip"])
    neck = (ls + rs) / 2.0
    hip_mid = (rh + lh) / 2.0

    top_inner = ls                              # on the left shoulder
    top_outer = ls + (ls - neck) * 0.8          # just outside the left shoulder
    hem_outer = rh + (rh - hip_mid) * 0.2       # hanging by the right hip
    hem_inner = hip_mid + (rh - hip_mid) * 0.2  # toward the front center
    # drop the hem down a bit
    drop = (hip_mid - neck) * 0.45
    return top_outer, top_inner, hem_outer + drop, hem_inner + drop


def compute_affine_pallu(garment_kp, body_kp) -> np.ndarray:
    g = garment_kp
    src = np.stack([_to_np(g["top_left"]), _to_np(g["top_right"]),
                    _to_np(g["right_hem"]), _to_np(g["left_hem"])])
    a, b, c, d = _pallu_body_quad(body_kp)
    dst = np.stack([a, b, c, d])
    return _lstsq_affine(src, dst)


def _warp_piece(user_bgr, garment_rgba, M):
    h, w = user_bgr.shape[:2]
    warped = cv2.warpAffine(garment_rgba, M, (w, h), flags=cv2.INTER_LINEAR,
                            borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    alpha = warped[:, :, 3:4].astype(np.float32) / 255.0
    out = warped[:, :, :3].astype(np.float32) * alpha + \
        user_bgr.astype(np.float32) * (1.0 - alpha)
    return out.astype(np.uint8)


def warp_saree(user_bgr: np.ndarray,
               blouse_rgba, blouse_kp,
               drape_rgba, drape_kp,
               pallu_rgba, pallu_kp,
               body_kp: Dict[str, Tuple[float, float]]) -> np.ndarray:
    """Three-region saree (image mode only): lower drape, then blouse, then the
    pallu draped diagonally over the left shoulder. Geometric approximation."""
    out = warp_and_composite(user_bgr, drape_rgba, drape_kp, body_kp, "skirt")
    out = warp_and_composite(out, blouse_rgba, blouse_kp, body_kp, "blouse")
    out = _warp_piece(out, pallu_rgba, compute_affine_pallu(pallu_kp, body_kp))
    return out


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

    kind = category_kind(category)
    if kind == "pant":
        rw, lw, ra, la = _pant_body_quad(body_kp, _pant_params(category))
        quad = np.array([lw, rw, ra, la], dtype=np.int32)
    elif kind in ("skirt", "lehenga"):
        rw, lw, rh, lh = _skirt_body_quad(body_kp, SkirtFitParams())
        quad = np.array([lw, rw, rh, lh], dtype=np.int32)
    else:
        rs, ls, rh, lh = _body_quad(body_kp, _top_params(category))
        quad = np.array([ls, rs, rh, lh], dtype=np.int32)
    cv2.polylines(out, [quad], True, (0, 165, 255), 2)
    return out
