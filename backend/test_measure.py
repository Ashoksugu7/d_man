"""Smoke test for Phase 4 body-size estimation & fit feedback.

Builds a synthetic full-body figure with keypoints at known image positions,
runs measurement + size recommendation, and asserts the outputs are sane.
Runs without a server and without MediaPipe (pose has a heuristic fallback, but
here we feed keypoints directly so the geometry is deterministic)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.measure import (  # noqa: E402
    estimate_measurements,
    recommend_size,
    _fit_label,
)

ASSETS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets"
)


def make_fullbody_keypoints(w=480, h=900):
    """A centered, upright, full-body figure in an (w x h) image.

    Vertical layout (fractions of height): nose 0.10, shoulders 0.22,
    hips 0.50, ankles 0.95 — a realistic standing proportion so the
    nose->ankle span maps cleanly onto the calibration model.
    """
    return {
        "nose": (w * 0.50, h * 0.10),
        "left_shoulder": (w * 0.70, h * 0.22),
        "right_shoulder": (w * 0.30, h * 0.22),
        "left_hip": (w * 0.64, h * 0.50),
        "right_hip": (w * 0.36, h * 0.50),
        "left_knee": (w * 0.60, h * 0.73),
        "right_knee": (w * 0.40, h * 0.73),
        "left_ankle": (w * 0.54, h * 0.95),
        "right_ankle": (w * 0.46, h * 0.95),
        "neck": (w * 0.50, h * 0.22),
    }


def test_measurements_sane():
    kp = make_fullbody_keypoints()
    m = estimate_measurements(kp, height_cm=175.0)
    assert m is not None, "expected measurements for a full-body figure"
    print("measurements:", m)

    # All measurements must be positive and physically plausible for 175 cm.
    assert m["cm_per_px"] > 0
    assert 30 <= m["shoulder_width_cm"] <= 70, m["shoulder_width_cm"]
    assert 30 <= m["torso_length_cm"] <= 90, m["torso_length_cm"]
    assert 15 <= m["hip_width_cm"] <= 60, m["hip_width_cm"]
    assert 50 <= m["inseam_cm"] <= 110, m["inseam_cm"]
    assert 50 <= m["waist_circumference_cm"] <= 130, m["waist_circumference_cm"]
    print("PASS - measurements within sane ranges")


def test_missing_body_returns_none():
    kp = make_fullbody_keypoints()
    del kp["left_ankle"]
    del kp["right_ankle"]
    assert estimate_measurements(kp, 175.0) is None, "no ankles -> None"
    assert estimate_measurements(make_fullbody_keypoints(), 0) is None, "bad height -> None"
    print("PASS - graceful None when full body/height unavailable")


def test_fit_labels():
    assert _fit_label(0.0) == "fits_well"
    assert _fit_label(2.9) == "fits_well"
    assert _fit_label(5.0) == "too_tight"     # body bigger than garment
    assert _fit_label(-5.0) == "too_loose"    # garment bigger than body
    print("PASS - fit label thresholds")


def test_recommendation_against_catalog():
    catalog = json.load(open(os.path.join(ASSETS, "catalog.json")))
    kp = make_fullbody_keypoints()
    m = estimate_measurements(kp, height_cm=175.0)

    valid_fits = {"fits_well", "too_tight", "too_loose"}
    top = next(g for g in catalog if g["category"] in ("shirt", "tshirt"))
    pant = next(g for g in catalog if g["category"] == "pant")

    rec_top = recommend_size(m, top["size_chart"], top["category"])
    rec_pant = recommend_size(m, pant["size_chart"], pant["category"])
    print("top rec:", rec_top)
    print("pant rec:", rec_pant)

    for rec, garment in ((rec_top, top), (rec_pant, pant)):
        assert rec is not None
        assert rec["recommended_size"] in garment["size_chart"]
        assert rec["fit"] in valid_fits
        assert len(rec["per_size_deltas"]) == len(garment["size_chart"])
        # The recommended size must be the smallest-magnitude delta.
        best = min(rec["per_size_deltas"].values(), key=abs)
        assert abs(rec["per_size_deltas"][rec["recommended_size"]]) == abs(best)

    assert rec_top["dimension"] == "shoulder_cm"
    assert rec_pant["dimension"] == "waist_cm"
    print("PASS - recommendations valid against catalog")


if __name__ == "__main__":
    test_measurements_sane()
    test_missing_body_returns_none()
    test_fit_labels()
    test_recommendation_against_catalog()
    print("\nALL PASS")
