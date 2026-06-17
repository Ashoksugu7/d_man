"""
Generate placeholder pant PNG assets with transparent backgrounds and
keypoint annotations. Replace with real garment cut-outs later.

Pant keypoints (normalized 0..1 within the PNG):
    left_waist, right_waist, crotch, left_ankle, right_ankle
Body landmarks they map onto (live + HD): hips (waist) and ankles (hem).
"""
import json
import os
from PIL import Image, ImageDraw

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
GARMENT_DIR = os.path.join(OUT_DIR, "garments")
os.makedirs(GARMENT_DIR, exist_ok=True)

W, H = 460, 760  # canvas

PANTS = [
    ("pant_blue", "Slim Blue Jeans", (52, 78, 120, 255), (40, 62, 98, 255)),
    ("pant_khaki", "Khaki Chinos", (181, 160, 120, 255), (150, 132, 96, 255)),
    ("pant_black", "Black Trousers", (45, 45, 50, 255), (28, 28, 33, 255)),
]


def pant_geometry():
    cx = W / 2
    waist_y = 70
    crotch_y = 330
    ankle_y = 720

    l_waist = (110, waist_y)   # image-left = wearer's right
    r_waist = (350, waist_y)
    crotch = (cx, crotch_y)
    # ankles (inner/outer averaged to a single point per leg)
    l_ankle = (150, ankle_y)
    r_ankle = (310, ankle_y)

    # Outline: waistband -> right outer leg -> right ankle -> crotch ->
    # left ankle -> left outer leg -> back to waist
    poly = [
        (108, waist_y),
        (352, waist_y),
        (338, 360),                 # right outer hip
        (322, ankle_y),             # right outer ankle
        (300, ankle_y),             # right inner ankle
        (cx + 8, crotch_y + 10),    # crotch right
        (cx - 8, crotch_y + 10),    # crotch left
        (160, ankle_y),             # left inner ankle
        (138, ankle_y),             # left outer ankle
        (122, 360),                 # left outer hip
    ]
    kp = {
        "left_waist": l_waist,
        "right_waist": r_waist,
        "crotch": crotch,
        "left_ankle": l_ankle,
        "right_ankle": r_ankle,
    }
    return poly, kp


def draw_pant(body, accent):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    poly, kp = pant_geometry()
    d.polygon(poly, fill=body)
    # waistband accent
    d.rectangle([108, 70, 352, 95], fill=accent)
    # center seam
    d.line([(W / 2, 95), (W / 2, 330)], fill=accent, width=3)
    return img, kp


def main():
    catalog_path = os.path.join(OUT_DIR, "catalog.json")
    catalog = json.load(open(catalog_path)) if os.path.exists(catalog_path) else []
    existing = {g["id"] for g in catalog}

    for gid, name, body, accent in PANTS:
        img, kp = draw_pant(body, accent)
        img.save(os.path.join(GARMENT_DIR, f"{gid}.png"))

        norm = {k: [round(x / W, 4), round(y / H, 4)] for k, (x, y) in kp.items()}
        with open(os.path.join(GARMENT_DIR, f"{gid}.json"), "w") as f:
            json.dump({"id": gid, "category": "pant",
                       "keypoints_px": {k: list(v) for k, v in kp.items()},
                       "keypoints_norm": norm, "canvas": [W, H]}, f, indent=2)

        if gid in existing:
            continue
        catalog.append({
            "id": gid, "name": name, "category": "pant",
            "image": f"garments/{gid}.png",
            "keypoints": f"garments/{gid}.json",
            "size_chart": {
                "S": {"waist_cm": 76, "inseam_cm": 76},
                "M": {"waist_cm": 81, "inseam_cm": 78},
                "L": {"waist_cm": 86, "inseam_cm": 80},
                "XL": {"waist_cm": 91, "inseam_cm": 81},
            },
        })

    json.dump(catalog, open(catalog_path, "w"), indent=2)
    print(f"Generated {len(PANTS)} pants; catalog now has {len(catalog)} garments")


if __name__ == "__main__":
    main()
