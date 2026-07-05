"""Body size estimation & fit feedback (Phase 4).

Pure-geometry, no-GPU. From pose keypoints (pixels) and a user-supplied
standing height in cm we recover an approximate pixel->cm scale and read off a
few body measurements. We then compare those measurements against each
garment's size chart to recommend a size and a fit label.

IMPORTANT — accuracy caveat
---------------------------
These numbers are *approximate*. They come from a single 2D photo via a
pixel-ratio calibration, so they ignore camera perspective, body depth, pose
lean, clothing bulk and limb foreshortening. Treat the output as a helpful
hint, not a tailor's tape. All assumptions below are deliberately explicit so
they can be tuned later.
"""
from __future__ import annotations

import math
from typing import Dict, Optional, Tuple

# ---------------------------------------------------------------------------
# Calibration assumptions (documented, tunable)
# ---------------------------------------------------------------------------
# We measure the on-image vertical span from the nose down to the ankle
# midpoint. In a standing adult that span is *not* the full stature: the top of
# the head sits above the nose, and the floor sits below the ankle. From
# standard anthropometry the nose/eye line is ~0.93 of stature above the floor,
# and the ankle is ~0.04 of stature above the floor. So the nose->ankle span
# covers roughly 0.93 - 0.04 = 0.89 of the person's standing height.
NOSE_FROM_FLOOR_FRAC = 0.93
ANKLE_FROM_FLOOR_FRAC = 0.04
NOSE_TO_ANKLE_FRAC = NOSE_FROM_FLOOR_FRAC - ANKLE_FROM_FLOOR_FRAC  # ~0.89

# Pose shoulder landmarks sit at the acromion/joint (biacromial breadth). A
# shirt's "shoulder_cm" on a size chart is measured flat, seam-to-seam, and is
# typically a touch wider than the bare biacromial breadth. We nudge the body
# shoulder measurement up to compare like-with-like.
SHOULDER_BODY_TO_GARMENT = 1.05

# The lower torso is modelled as an ellipse to turn the front-view hip *width*
# into a waist *circumference*. We only observe width from a single frontal
# photo, so we assume body depth ~= 0.70 * width (typical adult ratio) and use
# Ramanujan's first perimeter approximation. The waistband generally sits a bit
# above and is slightly narrower than the hip joints, captured by WAIST_TAPER.
HIP_DEPTH_TO_WIDTH = 0.70
WAIST_TAPER = 0.92  # waist circumference ~= 0.92 * hip-ellipse circumference

# Fit tolerance: within +/- this many cm of the chart value counts as a clean fit.
FIT_TOLERANCE_CM = 3.0

TOP_CATEGORIES = {"shirt", "tshirt", "fullsleeve", "polo", "henley", "top"}
PANT_CATEGORIES = {"pant", "pants", "trouser", "trousers", "jeans", "chino"}


def _dist(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _mid(a: Tuple[float, float], b: Tuple[float, float]) -> Tuple[float, float]:
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)


def _ellipse_perimeter(width: float, depth: float) -> float:
    """Ramanujan's first approximation for an ellipse of given width & depth."""
    a = width / 2.0
    b = depth / 2.0
    return math.pi * (3 * (a + b) - math.sqrt((3 * a + b) * (a + 3 * b)))


def estimate_measurements(
    body_kp: Dict[str, Tuple[float, float]],
    height_cm: float,
) -> Optional[Dict[str, float]]:
    """Estimate body measurements (cm) from pose keypoints + standing height.

    Requires nose + both ankles to establish the pixel->cm scale. If the full
    body is not visible (missing nose or ankles) we return None so the caller
    can surface a clear "stand back so your whole body is in frame" message.

    Returns a dict with:
      cm_per_px, shoulder_width_cm, torso_length_cm, hip_width_cm,
      inseam_cm, waist_circumference_cm
    """
    if height_cm is None or height_cm <= 0:
        return None

    need = ("nose", "left_shoulder", "right_shoulder", "left_hip", "right_hip",
            "left_ankle", "right_ankle")
    if not all(k in body_kp for k in need):
        return None

    nose = body_kp["nose"]
    ankle_mid = _mid(body_kp["left_ankle"], body_kp["right_ankle"])

    nose_to_ankle_px = abs(ankle_mid[1] - nose[1])
    if nose_to_ankle_px < 1e-3:
        return None

    # Recover full standing-height pixels, then cm per pixel.
    full_height_px = nose_to_ankle_px / NOSE_TO_ANKLE_FRAC
    cm_per_px = height_cm / full_height_px

    shoulder_px = _dist(body_kp["left_shoulder"], body_kp["right_shoulder"])
    hip_px = _dist(body_kp["left_hip"], body_kp["right_hip"])

    sh_mid = _mid(body_kp["left_shoulder"], body_kp["right_shoulder"])
    hip_mid = _mid(body_kp["left_hip"], body_kp["right_hip"])
    torso_px = _dist(sh_mid, hip_mid)
    inseam_px = _dist(hip_mid, ankle_mid)

    shoulder_width_cm = shoulder_px * cm_per_px * SHOULDER_BODY_TO_GARMENT
    hip_width_cm = hip_px * cm_per_px
    torso_length_cm = torso_px * cm_per_px
    inseam_cm = inseam_px * cm_per_px

    # Waist circumference from the frontal hip width via an ellipse model.
    waist_circumference_cm = (
        _ellipse_perimeter(hip_width_cm, hip_width_cm * HIP_DEPTH_TO_WIDTH)
        * WAIST_TAPER
    )

    return {
        "cm_per_px": round(cm_per_px, 4),
        "shoulder_width_cm": round(shoulder_width_cm, 1),
        "torso_length_cm": round(torso_length_cm, 1),
        "hip_width_cm": round(hip_width_cm, 1),
        "inseam_cm": round(inseam_cm, 1),
        "waist_circumference_cm": round(waist_circumference_cm, 1),
    }


def _fit_label(delta: float, tol: float = FIT_TOLERANCE_CM) -> str:
    """delta = body_measurement - garment_measurement.

    Garment smaller than the body (positive delta beyond tolerance) -> too tight.
    Garment larger than the body (negative delta beyond tolerance) -> too loose.
    """
    if delta > tol:
        return "too_tight"
    if delta < -tol:
        return "too_loose"
    return "fits_well"


def recommend_size(
    measurements: Dict[str, float],
    size_chart: Dict[str, Dict[str, float]],
    category: str,
) -> Optional[Dict[str, object]]:
    """Pick the best size + fit label for one garment.

    Tops are matched on shoulder width; pants on a waist-circumference proxy.
    Returns {recommended_size, fit, body_cm, dimension, per_size_deltas} or None
    if measurements/size_chart are unusable.
    """
    if not measurements or not size_chart:
        return None

    cat = (category or "").lower()
    if cat in PANT_CATEGORIES:
        dimension = "waist_cm"
        body_cm = measurements.get("waist_circumference_cm")
    else:  # default to top behaviour
        dimension = "shoulder_cm"
        body_cm = measurements.get("shoulder_width_cm")

    if body_cm is None:
        return None

    per_size_deltas: Dict[str, float] = {}
    best_size = None
    best_abs = None
    for size, dims in size_chart.items():
        chart_val = dims.get(dimension)
        if chart_val is None:
            continue
        delta = round(body_cm - chart_val, 1)
        per_size_deltas[size] = delta
        if best_abs is None or abs(delta) < best_abs:
            best_abs = abs(delta)
            best_size = size

    if best_size is None:
        return None

    return {
        "recommended_size": best_size,
        "fit": _fit_label(per_size_deltas[best_size]),
        "dimension": dimension,
        "body_cm": round(body_cm, 1),
        "per_size_deltas": per_size_deltas,
    }
