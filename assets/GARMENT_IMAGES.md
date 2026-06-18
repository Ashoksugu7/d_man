# Garment images for HD try-on (read this if results look bad)

VTON models (CatVTON, IDM-VTON) are trained on **in-shop garment photos** — the
flat product shots you see on shopping sites. They reproduce *exactly* the
garment image you give them. A bad garment image → a bad result, no matter the
engine. The cartoon placeholder PNGs in this folder (`shirt_red.png`, etc.) are
for **wiring/testing only** — they will never produce a realistic try-on.

## What a GOOD garment image looks like

- **One garment, front-facing**, laid flat or on a "ghost / invisible mannequin".
- **Plain white (or transparent) background.** No props, no busy scene.
- **Whole garment in frame**, filling most of it, not cropped.
- **Not worn by a person** (ideally). A model wearing it confuses the transfer.
- **Minimal wrinkles**, even lighting, decent resolution (≥768 px tall).
- **Right category** — top vs bottom vs dress (matches our `category` field).

Think: the product image on an e-commerce listing, on white.

## What's BAD (causes the smears/blobs you saw)

- Cartoon / flat-color drawings (our placeholders).
- Garment on a textured or colored background.
- Garment worn by a person, or only partly visible / cropped.
- Low resolution or heavy folds.

## Where to get suitable images

- **Your own / e-commerce product photos** (rights permitting) — the listing
  image on white is exactly right.
- **VITON-HD** and **DressCode** datasets — their "cloth" / in-shop images are
  the *exact* format these models were trained on. Best for testing, and they
  come with matching person images.
- Free product mockups / stock with plain backgrounds.

## Validate the pipeline separately from your garments

Before blaming the engine, run CatVTON on a **known-good VITON-HD pair** (their
person image + their cloth image). If that looks good, the pipeline works and
the issue is your garment image. If it still looks bad, it's a setup/engine
problem — send the worker log.

## Adding a real garment here

1. Save the product image as `assets/garments/<id>.png` (or `.webp`),
   transparent or white background.
2. Annotate keypoints with `tools/annotate.html` (pick the right category) and
   save `<id>.json`.
3. Add the catalog entry (the annotator exports a snippet) to
   `assets/catalog.json`.
4. Restart the backend; it appears in the picker and works in every engine.

Tip: `wt.png` (a real white-tee photo) is a far better test garment than the
cartoon `shirt_*` placeholders — compare them.
