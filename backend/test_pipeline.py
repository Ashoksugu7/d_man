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


def test_webp():
    """webp garment + webp user photo should flow through identically."""
    from PIL import features
    assert features.check("webp"), "libwebp not available in Pillow"

    # webp user photo
    user_rgb = make_person()
    Image.fromarray(user_rgb).save("/tmp/_user.webp", "WEBP")
    reload_rgb = np.array(Image.open("/tmp/_user.webp").convert("RGB"))
    user_bgr = cv2.cvtColor(reload_rgb, cv2.COLOR_RGB2BGR)
    body_kp = estimate_body_keypoints(reload_rgb)
    assert body_kp is not None

    # webp garment (with alpha)
    g = Image.open(os.path.join(ASSETS, "garments", "shirt_blue.png")).convert("RGBA")
    g.save("/tmp/_g.webp", "WEBP")
    g_arr = np.array(Image.open("/tmp/_g.webp").convert("RGBA"))
    assert g_arr.shape[2] == 4, "webp garment lost alpha"
    garment_rgba = np.dstack([cv2.cvtColor(g_arr[:, :, :3], cv2.COLOR_RGB2BGR), g_arr[:, :, 3]])

    import json
    kp = json.load(open(os.path.join(ASSETS, "garments", "shirt_blue.json")))
    garment_kp = {k: (v[0], v[1]) for k, v in kp["keypoints_px"].items()}

    result = warp_and_composite(user_bgr, garment_rgba, garment_kp, body_kp)

    # webp output round-trips
    ok = cv2.imwrite("/tmp/_out.webp", result, [cv2.IMWRITE_WEBP_QUALITY, 90])
    assert ok and os.path.exists("/tmp/_out.webp"), "webp output failed"
    print("PASS - webp input + webp output round-trip OK")


if __name__ == "__main__":
    main()
    test_webp()
