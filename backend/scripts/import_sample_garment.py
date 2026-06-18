"""Import a REAL example garment (from your cloned CatVTON repo) into the
catalog, so you can test HD try-on with a proper product image instead of the
cartoon placeholders.

Usage:
    export CATVTON_REPO=~/CatVTON           # the repo you cloned for the engine
    python backend/scripts/import_sample_garment.py
Then restart the backend and pick "Sample Real Shirt" in the garment grid.
"""
from __future__ import annotations

import glob
import json
import os
import shutil

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ASSETS = os.path.join(REPO_ROOT, "assets")
GARMENTS = os.path.join(ASSETS, "garments")


def find_example_garment(catvton_repo: str) -> str | None:
    """Look for an in-shop garment image inside the CatVTON repo's demo assets."""
    patterns = [
        "resource/demo/example/condition/**/*.jpg",
        "resource/demo/example/condition/**/*.png",
        "resource/demo/example/cloth/**/*.jpg",
        "resource/demo/**/*.jpg",
    ]
    for pat in patterns:
        hits = sorted(glob.glob(os.path.join(catvton_repo, pat), recursive=True))
        # prefer obvious upper-body cloth shots
        hits.sort(key=lambda p: (("upper" not in p.lower()), p))
        if hits:
            return hits[0]
    return None


def main():
    repo = os.getenv("CATVTON_REPO")
    if not repo or not os.path.isdir(repo):
        raise SystemExit(
            "Set CATVTON_REPO to your cloned CatVTON repo first "
            "(see backend/scripts/setup_catvton.sh)."
        )

    src = find_example_garment(repo)
    if not src:
        raise SystemExit(
            "Couldn't find an example garment in the repo. Look under "
            f"{repo}/resource/ and copy one into assets/garments/ manually, "
            "then add a catalog entry (see assets/GARMENT_IMAGES.md)."
        )

    gid = "sample_real"
    ext = os.path.splitext(src)[1].lstrip(".").lower() or "jpg"
    dst = os.path.join(GARMENTS, f"{gid}.{ext}")
    shutil.copyfile(src, dst)

    # In-shop garments are centered & upright; a centered keypoint guess works
    # for the affine/live modes (HD/CatVTON ignore keypoints anyway).
    kp_norm = {
        "collar": [0.5, 0.12], "left_shoulder": [0.74, 0.18],
        "right_shoulder": [0.26, 0.18], "left_sleeve": [0.9, 0.34],
        "right_sleeve": [0.1, 0.34], "left_hem": [0.72, 0.9],
        "right_hem": [0.28, 0.9],
    }
    with open(os.path.join(GARMENTS, f"{gid}.json"), "w") as f:
        json.dump({"id": gid, "category": "shirt",
                   "keypoints_norm": kp_norm, "canvas": [768, 1024]}, f, indent=2)

    catalog_path = os.path.join(ASSETS, "catalog.json")
    catalog = json.load(open(catalog_path)) if os.path.exists(catalog_path) else []
    catalog = [g for g in catalog if g["id"] != gid]
    catalog.insert(0, {
        "id": gid, "name": "Sample Real Shirt", "category": "shirt",
        "image": f"garments/{gid}.{ext}", "keypoints": f"garments/{gid}.json",
        "size_chart": {"S": {"shoulder_cm": 42, "length_cm": 68},
                       "M": {"shoulder_cm": 45, "length_cm": 71},
                       "L": {"shoulder_cm": 48, "length_cm": 74},
                       "XL": {"shoulder_cm": 51, "length_cm": 77}},
    })
    json.dump(catalog, open(catalog_path, "w"), indent=2)

    print(f"Imported real garment from: {src}")
    print(f"  -> {dst}")
    print("Restart the backend and pick 'Sample Real Shirt'. Compare its HD "
          "result to the cartoon placeholders.")


if __name__ == "__main__":
    main()
