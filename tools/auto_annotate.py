#!/usr/bin/env python3
"""Auto-annotate garment images -> keypoint JSON (catalog schema).

Analyses the garment silhouette (alpha channel, or plain-background removal)
and places category-appropriate keypoints — the same schemes as
tools/annotate.html — writing `<image>.json` next to each image. Open the
result in annotate.html to review and drag-fix if needed.

Categories / schemes:
  top-like (shirt, tshirt, fullsleeve):
           collar, left/right_shoulder, left/right_sleeve, left/right_hem
  pant:    left/right_waist, left/right_hem

Usage:
  python tools/auto_annotate.py IMG [IMG ...] --category shirt
  python tools/auto_annotate.py assets/garments/red_*.png --category auto
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

import cv2
import numpy as np

TOP_LIKE = {"top", "shirt", "tshirt", "polo", "fullsleeve"}
PANT_LIKE = {"pant", "trouser", "trousers"}

FILENAME_HINTS = [("pant", "pant"), ("trouser", "pant"),
                  ("fullsleeve", "fullsleeve"), ("shirt", "shirt"),
                  ("tshirt", "tshirt"), ("tee", "tshirt")]


# ---------------------------------------------------------------- silhouette

def foreground_mask(img: np.ndarray) -> np.ndarray:
    """uint8 0/1 mask of the garment."""
    if img.ndim == 3 and img.shape[2] == 4 and (img[:, :, 3] < 250).any():
        return (img[:, :, 3] > 16).astype(np.uint8)
    bgr = img[:, :, :3] if img.ndim == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    h, w = bgr.shape[:2]
    b = max(2, min(h, w) // 50)
    border = np.concatenate([bgr[:b].reshape(-1, 3), bgr[-b:].reshape(-1, 3),
                             bgr[:, :b].reshape(-1, 3), bgr[:, -b:].reshape(-1, 3)])
    bg = np.median(border, axis=0)
    dist = np.linalg.norm(bgr.astype(np.float32) - bg[None, None], axis=2)
    mask = (dist > 34).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    if n > 1:
        biggest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        mask = (labels == biggest).astype(np.uint8)
    return mask


def _row_extent(mask, y0, y1):
    """(min_x, max_x) of the foreground between rows y0..y1, or None."""
    band = mask[max(0, y0):max(1, y1)]
    xs = np.where(band.any(axis=0))[0]
    if len(xs) == 0:
        return None
    return float(xs.min()), float(xs.max())


# ---------------------------------------------------------------- schemes

def kp_pant(mask):
    ys, xs = np.where(mask)
    top, bot = ys.min(), ys.max()
    h = bot - top
    wl, wr = _row_extent(mask, top, int(top + 0.05 * h) + 1)
    # hems: extreme of each leg — split the bottom band at the silhouette centre
    band = mask[int(bot - 0.06 * h):bot + 1]
    cxs = np.where(band.any(axis=0))[0]
    cx = int((cxs.min() + cxs.max()) / 2)
    left_xs = np.where(band[:, :cx].any(axis=0))[0]
    right_xs = np.where(band[:, cx:].any(axis=0))[0] + cx
    lh = float(np.median(left_xs)) if len(left_xs) else cxs.min()
    rh = float(np.median(right_xs)) if len(right_xs) else cxs.max()
    return {"left_waist": (wl, top + 0.02 * h), "right_waist": (wr, top + 0.02 * h),
            "left_hem": (lh, bot - 0.02 * h), "right_hem": (rh, bot - 0.02 * h)}


def kp_top(mask):
    ys, xs = np.where(mask)
    top, bot = ys.min(), ys.max()
    h = bot - top
    # collar: centre of the top edge span
    tl, tr = _row_extent(mask, top, int(top + 0.03 * h) + 1)
    collar = ((tl + tr) / 2, float(top))
    # shoulders: extent just below the collar line
    y_sh = int(top + 0.10 * h)
    sl, sr = _row_extent(mask, y_sh - 2, y_sh + 3)
    # sleeves: global extreme left/right points (at their own heights)
    col_l = np.where(mask.any(axis=0))[0].min()
    col_r = np.where(mask.any(axis=0))[0].max()
    y_l = float(np.median(np.where(mask[:, col_l:col_l + 3].any(axis=1))[0]))
    y_r = float(np.median(np.where(mask[:, col_r - 2:col_r + 1].any(axis=1))[0]))
    # hems: bottom band, pulled slightly inward
    hl, hr = _row_extent(mask, int(bot - 0.04 * h), bot + 1)
    inset = 0.06 * (hr - hl)
    return {"collar": collar,
            "left_shoulder": (sl, y_sh), "right_shoulder": (sr, y_sh),
            "left_sleeve": (float(col_l), y_l), "right_sleeve": (float(col_r), y_r),
            "left_hem": (hl + inset, bot - 0.02 * h), "right_hem": (hr - inset, bot - 0.02 * h)}


def estimate(mask: np.ndarray, category: str):
    c = category.lower()
    if c in PANT_LIKE:
        return kp_pant(mask)
    if c in TOP_LIKE:
        return kp_top(mask)
    raise SystemExit(f"unknown category: {category}")


def guess_category(path: str) -> str:
    name = os.path.basename(path).lower()
    for hint, cat in FILENAME_HINTS:
        if hint in name:
            return cat
    return "top"


# ---------------------------------------------------------------- output

def annotate_file(path: str, category: str, preview: bool):
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        print(f"skip (unreadable): {path}")
        return
    mask = foreground_mask(img)
    if mask.sum() < 100:
        print(f"skip (no garment found): {path}")
        return
    cat = guess_category(path) if category == "auto" else category
    kp = estimate(mask, cat)
    h, w = mask.shape
    gid = os.path.splitext(os.path.basename(path))[0]
    doc = {"id": gid, "category": cat,
           "keypoints_px": {k: [round(float(x), 1), round(float(y), 1)] for k, (x, y) in kp.items()},
           "keypoints_norm": {k: [round(x / w, 4), round(y / h, 4)] for k, (x, y) in kp.items()},
           "canvas": [w, h]}
    out = os.path.splitext(path)[0] + ".json"
    with open(out, "w") as f:
        json.dump(doc, f, indent=2)
    print(f"{gid}: {cat} -> {out}")
    if preview:
        vis = img[:, :, :3].copy() if img.ndim == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        if img.ndim == 3 and img.shape[2] == 4:          # show true silhouette
            a = img[:, :, 3:4].astype(np.float32) / 255.0
            vis = (vis * a + 255 * (1 - a)).astype(np.uint8)
        for name, (x, y) in kp.items():
            cv2.circle(vis, (int(x), int(y)), 7, (0, 0, 255), -1)
            cv2.putText(vis, name, (int(x) + 8, int(y) - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1)
        pv = os.path.splitext(path)[0] + "_kp_preview.png"
        cv2.imwrite(pv, vis)
        print(f"  preview -> {pv}")


def main():
    ap = argparse.ArgumentParser(description="Auto-annotate garment keypoints")
    ap.add_argument("images", nargs="*", help="garment images (globs ok)")
    ap.add_argument("--category", default="auto",
                    help="scheme: shirt/tshirt/fullsleeve/pant or 'auto'")
    ap.add_argument("--preview", action="store_true",
                    help="also write *_kp_preview.png with points drawn")
    args = ap.parse_args()

    files = []
    for pat in args.images:
        files.extend(sorted(glob.glob(pat)) or [pat])
    for f in files:
        annotate_file(f, args.category, args.preview)

    if not files:
        ap.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
