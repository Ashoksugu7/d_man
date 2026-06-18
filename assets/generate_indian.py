"""
Generate placeholder Indian-attire PNG assets + keypoints (Phase 5).
Categories: kurta (long top), salwar (wide pant), dupatta (translucent drape),
lehenga (two-piece: blouse + flared skirt). Replace with real images later.

Keypoint schemes:
  top/kurta/blouse : collar,left/right_shoulder,left/right_sleeve,left/right_hem
  pant/salwar      : left/right_waist,crotch,left/right_ankle
  dupatta          : left/right_shoulder,left/right_hem
  skirt            : left/right_waist,left/right_hem
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


# --- Kurta: long tunic ------------------------------------------------------
def kurta(body, accent):
    W, H = 620, 940
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = W / 2
    poly = [
        (cx - 60, 120), (190, 150), (140, 210), (70, 330), (140, 360),
        (185, 320), (180, 860), (440, 860), (435, 320), (480, 360),
        (550, 330), (480, 210), (430, 150), (cx + 60, 120),
    ]
    d.polygon(poly, fill=body)
    d.polygon([(cx - 55, 125), (cx, 185), (cx + 55, 125), (cx, 140)], fill=accent)
    d.line([(cx, 185), (cx, 700)], fill=accent, width=4)          # placket
    kp = {"collar": (cx, 120), "left_shoulder": (190, 150),
          "right_shoulder": (430, 150), "left_sleeve": (70, 330),
          "right_sleeve": (550, 330), "left_hem": (185, 860),
          "right_hem": (435, 860)}
    return img, kp, (W, H)


# --- Salwar: wide tapered trousers -----------------------------------------
def salwar(body, accent):
    W, H = 560, 820
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = W / 2
    poly = [
        (120, 70), (440, 70), (470, 360), (430, 780), (300, 780),
        (cx, 430), (260, 780), (130, 780), (90, 360),
    ]
    d.polygon(poly, fill=body)
    d.rectangle([120, 70, 440, 100], fill=accent)                  # drawstring waist
    kp = {"left_waist": (120, 80), "right_waist": (440, 80),
          "crotch": (cx, 430), "left_ankle": (175, 770),
          "right_ankle": (385, 770)}
    return img, kp, (W, H)


# --- Dupatta: translucent draped scarf -------------------------------------
def dupatta(body, accent):
    W, H = 760, 560
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    a = 150  # translucent
    fill = (body[0], body[1], body[2], a)
    d.polygon([(70, 60), (690, 60), (610, 520), (150, 520)], fill=fill)
    d.line([(70, 60), (150, 520)], fill=(accent[0], accent[1], accent[2], 200), width=8)
    d.line([(690, 60), (610, 520)], fill=(accent[0], accent[1], accent[2], 200), width=8)
    kp = {"left_shoulder": (90, 90), "right_shoulder": (670, 90),
          "left_hem": (160, 510), "right_hem": (600, 510)}
    return img, kp, (W, H)


# --- Lehenga blouse: cropped top -------------------------------------------
def blouse(body, accent):
    W, H = 520, 360
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = W / 2
    poly = [(cx - 50, 40), (170, 60), (90, 150), (150, 175), (185, 140),
            (180, 320), (340, 320), (335, 140), (370, 175), (430, 150),
            (350, 60), (cx + 50, 40)]
    d.polygon(poly, fill=body)
    d.polygon([(cx - 45, 45), (cx, 95), (cx + 45, 45)], fill=accent)
    kp = {"collar": (cx, 40), "left_shoulder": (170, 60),
          "right_shoulder": (350, 60), "left_sleeve": (90, 150),
          "right_sleeve": (430, 150), "left_hem": (185, 320),
          "right_hem": (335, 320)}
    return img, kp, (W, H)


# --- Lehenga skirt: flared (narrow waist -> very wide hem) ------------------
def skirt(body, accent):
    W, H = 820, 760
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = W / 2
    d.polygon([(300, 50), (520, 50), (770, 710), (50, 710)], fill=body)
    d.rectangle([300, 50, 520, 78], fill=accent)                   # waistband
    # decorative hem border
    d.line([(50, 700), (770, 700)], fill=accent, width=10)
    kp = {"left_waist": (300, 60), "right_waist": (520, 60),
          "left_hem": (60, 700), "right_hem": (760, 700)}
    return img, kp, (W, H)


KURTAS = [("kurta_cream", "Cream Cotton Kurta", (224, 214, 188, 255), (150, 120, 70, 255)),
          ("kurta_maroon", "Maroon Festive Kurta", (120, 40, 55, 255), (70, 20, 30, 255))]
SALWARS = [("salwar_white", "White Salwar", (238, 238, 240, 255), (200, 200, 205, 255)),
           ("salwar_navy", "Navy Palazzo", (40, 55, 95, 255), (28, 40, 72, 255))]
DUPATTAS = [("dupatta_red", "Red Dupatta", (200, 50, 60, 255), (150, 30, 40, 255)),
            ("dupatta_gold", "Gold Dupatta", (210, 175, 90, 255), (160, 130, 60, 255))]
LEHENGAS = [("lehenga_rose", "Rose Lehenga", (190, 70, 110, 255), (140, 40, 80, 255))]


def main():
    cat_path = os.path.join(OUT, "catalog.json")
    catalog = json.load(open(cat_path)) if os.path.exists(cat_path) else []
    have = {g["id"] for g in catalog}

    def add(entry):
        if entry["id"] not in have:
            catalog.append(entry)

    for gid, name, body, accent in KURTAS:
        img, kp, c = kurta(body, accent); save(gid, img, kp, c, "kurta")
        add({"id": gid, "name": name, "category": "kurta",
             "image": f"garments/{gid}.png", "keypoints": f"garments/{gid}.json",
             "size_chart": {"S": {"shoulder_cm": 42, "length_cm": 100},
                            "M": {"shoulder_cm": 45, "length_cm": 104},
                            "L": {"shoulder_cm": 48, "length_cm": 108},
                            "XL": {"shoulder_cm": 51, "length_cm": 112}}})

    for gid, name, body, accent in SALWARS:
        img, kp, c = salwar(body, accent); save(gid, img, kp, c, "salwar")
        add({"id": gid, "name": name, "category": "salwar",
             "image": f"garments/{gid}.png", "keypoints": f"garments/{gid}.json",
             "size_chart": {"S": {"waist_cm": 76, "inseam_cm": 74},
                            "M": {"waist_cm": 81, "inseam_cm": 76},
                            "L": {"waist_cm": 86, "inseam_cm": 78},
                            "XL": {"waist_cm": 91, "inseam_cm": 80}}})

    for gid, name, body, accent in DUPATTAS:
        img, kp, c = dupatta(body, accent); save(gid, img, kp, c, "dupatta")
        add({"id": gid, "name": name, "category": "dupatta",
             "image": f"garments/{gid}.png", "keypoints": f"garments/{gid}.json",
             "size_chart": {"M": {"length_cm": 230, "width_cm": 90}}})

    for gid, name, body, accent in LEHENGAS:
        b_img, b_kp, b_c = blouse(body, accent)
        s_img, s_kp, s_c = skirt(body, accent)
        save(f"{gid}_blouse", b_img, b_kp, b_c, "blouse")
        save(f"{gid}_skirt", s_img, s_kp, s_c, "skirt")
        add({"id": gid, "name": name, "category": "lehenga",
             "image": f"garments/{gid}_skirt.png",
             "keypoints": f"garments/{gid}_skirt.json",
             "blouse_image": f"garments/{gid}_blouse.png",
             "blouse_keypoints": f"garments/{gid}_blouse.json",
             "size_chart": {"S": {"waist_cm": 66}, "M": {"waist_cm": 71},
                            "L": {"waist_cm": 76}, "XL": {"waist_cm": 81}}})

    json.dump(catalog, open(cat_path, "w"), indent=2)
    print(f"catalog now has {len(catalog)} garments:",
          [(g['id'], g['category']) for g in catalog])


if __name__ == "__main__":
    main()
