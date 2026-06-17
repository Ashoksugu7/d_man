"""Smoke test: generate a synthetic person photo, run the try-on pipeline,
assert garment pixels land on the torso. Runs without a server."""
import os
import sys
import numpy as np
import cv2
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.pose import estimate_body_keypoints  # noqa: E402
from app.warp import warp_and_composite        # noqa: E402

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")


def make_person(w=480, h=640):
    img = Image.new("RGB", (w, h), (225, 225, 225))
    d = ImageDraw.Draw(img)
    d.ellipse([w/2-40, 60, w/2+40, 140], fill=(200, 170, 150))   # head
    d.polygon([(w*0.30, 200), (w*0.70, 200), (w*0.66, 470),
               (w*0.34, 470)], fill=(120, 120, 130))             # torso
    return np.array(img)


def main():
    user_rgb = make_person()
    user_bgr = cv2.cvtColor(user_rgb, cv2.COLOR_RGB2BGR)

    body_kp = estimate_body_keypoints(user_rgb)
    assert body_kp is not None, "no keypoints"
    print("body keypoints:", {k: (round(v[0]), round(v[1])) for k, v in body_kp.items()})

    g = Image.open(os.path.join(ASSETS, "garments", "shirt_red.png")).convert("RGBA")
    g_arr = np.array(g)
    garment_rgba = np.dstack([cv2.cvtColor(g_arr[:, :, :3], cv2.COLOR_RGB2BGR), g_arr[:, :, 3]])

    import json
    kp = json.load(open(os.path.join(ASSETS, "garments", "shirt_red.json")))
    garment_kp = {k: (v[0], v[1]) for k, v in kp["keypoints_px"].items()}

    result = warp_and_composite(user_bgr, garment_rgba, garment_kp, body_kp)

    # Check red garment pixels appear near torso center
    cx, cy = result.shape[1] // 2, int(result.shape[0] * 0.5)
    patch = result[cy-20:cy+20, cx-20:cx+20]
    mean_bgr = patch.reshape(-1, 3).mean(0)
    print("center patch mean BGR:", mean_bgr.round(1))
    is_reddish = mean_bgr[2] > mean_bgr[0] + 30 and mean_bgr[2] > 80
    assert is_reddish, f"garment not composited on torso (got {mean_bgr})"

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "storage", "results")
    os.makedirs(out, exist_ok=True)
    cv2.imwrite(os.path.join(out, "test_result.png"), result)
    print("PASS - result written to storage/results/test_result.png")


if __name__ == "__main__":
    main()
