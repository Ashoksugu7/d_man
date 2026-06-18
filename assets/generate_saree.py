"""
Generate a placeholder saree (Phase 5, image-mode only).

A saree is a multi-region drape, so we model 3 pieces:
  blouse : cropped top (torso)            -> top keypoints
  drape  : lower body wrap (waist->ankle) -> skirt keypoints (waist + hem)
  pallu  : diagonal sash over one shoulder -> pallu keypoints (top + hem)

This is a rough geometric placeholder. Real saree try-on needs a learned warp +
saree-specific parsing (see PHASE5_NOTES.md). Replace with real images and use
the HD "dresses" engine for realistic output.
"""
import json
import os
from PIL import Image, ImageDraw

OUT = os.path.dirname(os.path.abspath(__file__))
GD = os.path.join(OUT, "garments")
os.makedirs(GD, exist_ok=True)


def save(gid, img, kp, canvas, category):
    img.save(os.path.join(GD, f"{gid}.png"))
    W, H = canvas
    norm = {k: [round(x / W, 4), round(y / H, 4)] for k, (x, y) in kp.items()}
    json.dump({"id": gid, "category": category,
               "keypoints_px": {k: list(v) for k, v in kp.items()},
               "keypoints_norm": norm, "canvas": list(canvas)},
              open(os.path.join(GD, f"{gid}.json"), "w"), indent=2)


def blouse(body, accent):
    W, H = 520, 330
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = W / 2
    d.polygon([(cx - 45, 40), (175, 60), (110, 150), (165, 165), (190, 135),
               (190, 300), (330, 300), (330, 135), (355, 165), (410, 150),
               (345, 60), (cx + 45, 40)], fill=body)
    d.polygon([(cx - 40, 45), (cx, 90), (cx + 40, 45)], fill=accent)
    kp = {"collar": (cx, 40), "left_shoulder": (175, 60),
          "right_shoulder": (345, 60), "left_sleeve": (110, 150),
          "right_sleeve": (410, 150), "left_hem": (190, 300),
          "right_hem": (330, 300)}
    return img, kp, (W, H)


def drape(body, accent):
    """Lower wrap: gently flared column with pleat lines."""
    W, H = 640, 820
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.polygon([(220, 50), (420, 50), (560, 770), (80, 770)], fill=body)
    d.rectangle([220, 50, 420, 78], fill=accent)
    for x in (260, 300, 340, 380):                     # pleats
        d.line([(x, 90), (x - (x - 320) * 0.6 + 320 - x, 760)], fill=accent, width=2)
    d.line([(80, 760), (560, 760)], fill=accent, width=8)  # border
    kp = {"left_waist": (220, 60), "right_waist": (420, 60),
          "left_hem": (90, 760), "right_hem": (550, 760)}
    return img, kp, (W, H)


def pallu(body, accent):
    """Diagonal sash that goes over the LEFT shoulder and drapes across."""
    W, H = 420, 720
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    a = 180  # slightly translucent
    fill = (body[0], body[1], body[2], a)
    d.polygon([(60, 40), (240, 40), (360, 680), (180, 680)], fill=fill)
    d.line([(240, 40), (360, 680)], fill=(accent[0], accent[1], accent[2], 220), width=10)
    # top edge = over the shoulder; hem = hanging end
    kp = {"top_left": (60, 50), "top_right": (240, 50),
          "left_hem": (180, 670), "right_hem": (360, 670)}
    return img, kp, (W, H)


SAREES = [("saree_teal", "Teal Silk Saree", (20, 110, 120, 255), (12, 80, 88, 255)),
          ("saree_pink", "Pink Festive Saree", (200, 70, 120, 255), (150, 40, 85, 255))]


def main():
    cat_path = os.path.join(OUT, "catalog.json")
    catalog = json.load(open(cat_path)) if os.path.exists(cat_path) else []
    have = {g["id"] for g in catalog}

    for gid, name, body, accent in SAREES:
        b_img, b_kp, b_c = blouse(body, accent)
        d_img, d_kp, d_c = drape(body, accent)
        p_img, p_kp, p_c = pallu(body, accent)
        save(f"{gid}_blouse", b_img, b_kp, b_c, "blouse")
        save(f"{gid}_drape", d_img, d_kp, d_c, "skirt")
        save(f"{gid}_pallu", p_img, p_kp, p_c, "pallu")
        if gid in have:
            continue
        catalog.append({
            "id": gid, "name": name, "category": "saree",
            "image": f"garments/{gid}_drape.png",
            "keypoints": f"garments/{gid}_drape.json",
            "blouse_image": f"garments/{gid}_blouse.png",
            "blouse_keypoints": f"garments/{gid}_blouse.json",
            "pallu_image": f"garments/{gid}_pallu.png",
            "pallu_keypoints": f"garments/{gid}_pallu.json",
            "image_only": True,
            "size_chart": {"S": {"length_cm": 550}, "M": {"length_cm": 550}},
        })

    json.dump(catalog, open(cat_path, "w"), indent=2)
    print(f"catalog now has {len(catalog)} garments; added sarees:",
          [g["id"] for g in catalog if g["category"] == "saree"])


if __name__ == "__main__":
    main()
