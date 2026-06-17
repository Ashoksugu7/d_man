"""
Generate 5 placeholder shirt PNG assets with transparent backgrounds and
keypoint annotations. Replace these with real garment cut-outs later.

Each shirt is drawn on a fixed canvas so keypoints are stable & known.
Keypoints (normalized 0..1 within the PNG):
    collar, left_shoulder, right_shoulder, left_hem, right_hem,
    left_sleeve, right_sleeve
"""
import json
import os
from PIL import Image, ImageDraw

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
GARMENT_DIR = os.path.join(OUT_DIR, "garments")
os.makedirs(GARMENT_DIR, exist_ok=True)

W, H = 600, 700  # canvas size

# Five shirts: (id, name, body color, accent/collar color)
SHIRTS = [
    ("shirt_red", "Classic Red Tee", (210, 50, 55, 255), (170, 30, 35, 255)),
    ("shirt_blue", "Navy Polo", (35, 60, 120, 255), (25, 45, 95, 255)),
    ("shirt_green", "Forest Henley", (40, 120, 75, 255), (30, 95, 60, 255)),
    ("shirt_black", "Black Crew", (35, 35, 40, 255), (20, 20, 25, 255)),
    ("shirt_white", "White Oxford", (240, 240, 245, 255), (205, 205, 215, 255)),
]


def shirt_polygon():
    """Return the outline of a front-facing short-sleeve shirt and keypoints
    in pixel coordinates."""
    cx = W / 2
    # Key landmarks in pixels
    collar = (cx, 110)
    l_sh = (180, 150)   # left shoulder (image-left = wearer's right)
    r_sh = (420, 150)   # right shoulder
    l_sleeve = (70, 300)
    r_sleeve = (530, 300)
    l_hem = (185, 620)
    r_hem = (415, 620)

    # Build outline polygon (clockwise from collar-left)
    poly = [
        (cx - 55, 120),          # collar left
        l_sh,                    # left shoulder
        (130, 200),              # left sleeve top
        l_sleeve,                # left sleeve end (outer)
        (140, 330),              # left sleeve bottom
        (175, 300),              # left armpit
        l_hem,                   # left hem
        r_hem,                   # right hem
        (425, 300),              # right armpit
        (460, 330),              # right sleeve bottom
        r_sleeve,                # right sleeve end (outer)
        (470, 200),              # right sleeve top
        r_sh,                    # right shoulder
        (cx + 55, 120),          # collar right
    ]
    kp = {
        "collar": collar,
        "left_shoulder": l_sh,
        "right_shoulder": r_sh,
        "left_sleeve": l_sleeve,
        "right_sleeve": r_sleeve,
        "left_hem": l_hem,
        "right_hem": r_hem,
    }
    return poly, kp


def draw_shirt(body, accent):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    poly, kp = shirt_polygon()
    d.polygon(poly, fill=body)
    # collar accent
    cx = W / 2
    d.polygon(
        [(cx - 55, 120), (cx, 175), (cx + 55, 120), (cx, 135)],
        fill=accent,
    )
    # sleeve cuffs + hem accent line
    d.line([kp["left_hem"], kp["right_hem"]], fill=accent, width=6)
    return img, kp


def main():
    catalog = []
    for gid, name, body, accent in SHIRTS:
        img, kp = draw_shirt(body, accent)
        png_path = os.path.join(GARMENT_DIR, f"{gid}.png")
        img.save(png_path)

        # normalized keypoints
        norm_kp = {k: [round(x / W, 4), round(y / H, 4)] for k, (x, y) in kp.items()}
        kp_path = os.path.join(GARMENT_DIR, f"{gid}.json")
        with open(kp_path, "w") as f:
            json.dump({"id": gid, "keypoints_px": {k: list(v) for k, v in kp.items()},
                       "keypoints_norm": norm_kp, "canvas": [W, H]}, f, indent=2)

        catalog.append({
            "id": gid,
            "name": name,
            "category": "shirt",
            "image": f"garments/{gid}.png",
            "keypoints": f"garments/{gid}.json",
            "size_chart": {
                "S": {"shoulder_cm": 42, "length_cm": 68},
                "M": {"shoulder_cm": 45, "length_cm": 71},
                "L": {"shoulder_cm": 48, "length_cm": 74},
                "XL": {"shoulder_cm": 51, "length_cm": 77},
            },
        })

    with open(os.path.join(OUT_DIR, "catalog.json"), "w") as f:
        json.dump(catalog, f, indent=2)
    print(f"Generated {len(catalog)} shirts in {GARMENT_DIR}")


if __name__ == "__main__":
    main()
