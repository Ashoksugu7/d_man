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

import os
from dataclasses import dataclass
from typing import Dict, Tuple
import numpy as np
import cv2

# Phase 6 realism toggles (CPU, no GPU). Override per-call or via env.
TRYON_OCCLUDE = os.getenv("TRYON_OCCLUDE", "1") in ("1", "true", "True")
TRYON_LIGHTING = os.getenv("TRYON_LIGHTING", "0") in ("1", "true", "True")
# Experimental TPS refinement for tops (bends sleeves toward the arms). Opt-in;
# affine is the stable default.
TRYON_TPS = os.getenv("TRYON_TPS", "0") in ("1", "true", "True")


def _to_np(pt) -> np.ndarray:
    return np.array([pt[0], pt[1]], dtype=np.float32)


def forearm_occlusion_mask(shape, body_kp: Dict[str, Tuple[float, float]]) -> np.ndarray:
    """Mask of the forearms + hands (elbow->wrist + a hand blob), so they can be
    kept IN FRONT of the garment (folded arms shouldn't be painted over).

    Only arms that are actually CROSSED IN FRONT of the torso are masked:
    the wrist must sit inside the torso's horizontal span and above the hip
    line. Arms hanging at the sides are beside/behind the garment — erasing
    the garment there just punches transparent holes near the hands and hips.
    """
    h, w = shape[:2]
    m = np.zeros((h, w), np.uint8)
    th = max(10, w // 18)

    lh = body_kp.get("left_hip")
    rh = body_kp.get("right_hip")
    ls = body_kp.get("left_shoulder")
    rs = body_kp.get("right_shoulder")
    if not (lh and rh and ls and rs):
        return m
    x_lo = min(lh[0], rh[0], ls[0], rs[0])
    x_hi = max(lh[0], rh[0], ls[0], rs[0])
    inset = 0.10 * (x_hi - x_lo)              # wrist must be clearly inside
    hip_y = max(lh[1], rh[1])

    for side in ("left", "right"):
        el = body_kp.get(f"{side}_elbow")
        wr = body_kp.get(f"{side}_wrist")
        if not (el and wr):
            continue
        crossed = (x_lo + inset < wr[0] < x_hi - inset) and wr[1] < hip_y
        if not crossed:
            continue
        cv2.line(m, (int(el[0]), int(el[1])), (int(wr[0]), int(wr[1])), 255, th)
        cv2.circle(m, (int(wr[0]), int(wr[1])), int(th * 1.2), 255, -1)  # hand
    if th > 2 and m.any():
        m = cv2.GaussianBlur(m, (0, 0), th * 0.25)
    return m


def _apply_M(M: np.ndarray, pt) -> Tuple[float, float]:
    x, y = pt
    return (M[0, 0] * x + M[0, 1] * y + M[0, 2],
            M[1, 0] * x + M[1, 1] * y + M[1, 2])


def tps_refine_top(warped_rgba: np.ndarray, M: np.ndarray,
                   garment_kp: Dict[str, Tuple[float, float]],
                   body_kp: Dict[str, Tuple[float, float]],
                   p: FitParams) -> np.ndarray:
    """TPS refinement (CPU) on the already-affine-warped top: bend the sleeves
    toward the elbows and seat the collar at the neck. Needs elbows; returns the
    input unchanged if the required points are missing or TPS is unavailable."""
    need = ("collar", "left_shoulder", "right_shoulder", "left_sleeve",
            "right_sleeve", "left_hem", "right_hem")
    if not all(k in garment_kp for k in need):
        return warped_rgba
    if not all(k in body_kp for k in ("left_elbow", "right_elbow")):
        return warped_rgba
    try:
        rs, ls, rh, lh = _body_quad(body_kp, p)
        neck = (_to_np(body_kp["left_shoulder"]) + _to_np(body_kp["right_shoulder"])) / 2
        # current positions of garment landmarks after the affine fit
        cur = [_apply_M(M, garment_kp[k]) for k in
               ("right_shoulder", "left_shoulder", "collar",
                "right_sleeve", "left_sleeve", "right_hem", "left_hem")]
        tgt = [tuple(rs), tuple(ls),
               (float(neck[0]), float(neck[1])),
               tuple(_to_np(body_kp["right_elbow"])),
               tuple(_to_np(body_kp["left_elbow"])),
               tuple(rh), tuple(lh)]
        tps = cv2.createThinPlateSplineShapeTransformer()
        src = np.array(cur, np.float32).reshape(1, -1, 2)
        dst = np.array(tgt, np.float32).reshape(1, -1, 2)
        matches = [cv2.DMatch(i, i, 0) for i in range(len(cur))]
        tps.estimateTransformation(dst, src, matches)
        return tps.warpImage(warped_rgba)
    except Exception:
        return warped_rgba  # never let TPS break a working render


def match_lighting(result_bgr: np.ndarray, user_bgr: np.ndarray,
                   garment_alpha: np.ndarray) -> np.ndarray:
    """Scale the garment region's brightness toward the scene's level under it,
    so a flat garment doesn't look pasted. Gentle, clamped."""
    region = garment_alpha > 25
    if int(region.sum()) < 50:
        return result_bgr
    g_orig = cv2.cvtColor(user_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    g_cur = cv2.cvtColor(result_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    cur_mean = float(g_cur[region].mean())
    if cur_mean < 1:
        return result_bgr
    ratio = float(np.clip(g_orig[region].mean() / cur_mean, 0.7, 1.3))
    out = result_bgr.astype(np.float32)
    out[region] = np.clip(out[region] * ratio, 0, 255)
    return out.astype(np.uint8)


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


TOP_CATEGORIES = {"shirt", "tshirt", "fullsleeve", "polo", "henley", "top"}
PANT_CATEGORIES = {"pant", "trouser", "trousers"}


def _top_params(category: str) -> FitParams:
    return FitParams()


def _pant_params(category: str) -> PantFitParams:
    return PantFitParams()


def category_kind(category: str) -> str:
    """Map a garment category to the warp kind: top | pant."""
    c = (category or "").lower()
    if c in PANT_CATEGORIES:
        return "pant"
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


def _override(params, overrides: dict | None):
    """Apply per-garment fit overrides (only known fields) onto a params dataclass."""
    if overrides:
        for k, v in overrides.items():
            if hasattr(params, k):
                try:
                    setattr(params, k, float(v))
                except (TypeError, ValueError):
                    pass
    return params


def affine_for(category: str,
               garment_kp: Dict[str, Tuple[float, float]],
               body_kp: Dict[str, Tuple[float, float]],
               fit_overrides: dict | None = None) -> np.ndarray:
    """Pick the right warp for the garment category (top/pant)."""
    kind = category_kind(category)
    if kind == "pant":
        return compute_affine_pant(garment_kp, body_kp,
                                   _override(_pant_params(category), fit_overrides))
    return compute_affine(garment_kp, body_kp,
                          _override(_top_params(category), fit_overrides))


def warp_and_composite(user_bgr: np.ndarray,
                       garment_rgba: np.ndarray,
                       garment_kp: Dict[str, Tuple[float, float]],
                       body_kp: Dict[str, Tuple[float, float]],
                       category: str = "shirt",
                       occlude: bool | None = None,
                       lighting: bool | None = None,
                       tps: bool | None = None,
                       fit_overrides: dict | None = None) -> np.ndarray:
    """Warp garment onto user photo and alpha-composite. Returns BGR image.

    occlude  : keep forearms/hands in front of the garment (default TRYON_OCCLUDE).
    lighting : match garment brightness to the scene (default TRYON_LIGHTING).
    tps      : TPS refinement for tops (default TRYON_TPS; affine otherwise).
    fit_overrides : per-garment FitParams overrides (hem_extend, shoulder_widen…).
    """
    occlude = TRYON_OCCLUDE if occlude is None else occlude
    lighting = TRYON_LIGHTING if lighting is None else lighting
    tps = TRYON_TPS if tps is None else tps
    h, w = user_bgr.shape[:2]
    M = affine_for(category, garment_kp, body_kp, fit_overrides)

    warped = cv2.warpAffine(
        garment_rgba, M, (w, h),
        flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )
    if tps and category_kind(category) == "top":
        warped = tps_refine_top(warped, M, garment_kp, body_kp, _top_params(category))

    alpha = (warped[:, :, 3:4].astype(np.float32)) / 255.0
    if occlude:
        amask = forearm_occlusion_mask((h, w), body_kp).astype(np.float32) / 255.0
        alpha = alpha * (1.0 - amask[:, :, None])   # arms/hands show through
    fg = warped[:, :, :3].astype(np.float32)
    bg = user_bgr.astype(np.float32)
    out = (fg * alpha + bg * (1.0 - alpha)).astype(np.uint8)
    if lighting:
        out = match_lighting(out, user_bgr, (alpha[:, :, 0] * 255).astype(np.uint8))
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
    else:
        rs, ls, rh, lh = _body_quad(body_kp, _top_params(category))
        quad = np.array([ls, rs, rh, lh], dtype=np.int32)
    cv2.polylines(out, [quad], True, (0, 165, 255), 2)
    return out
