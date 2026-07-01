"""Garment repository: serialize DB rows to the catalog JSON shape, list active
garments, and seed the DB from assets/catalog.json (idempotent)."""
from __future__ import annotations

import json
import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Garment, GarmentPiece

BASE_DIR = Path(__file__).resolve().parent.parent          # backend/
REPO_DIR = BASE_DIR.parent
ASSETS_DIR = Path(os.getenv("ASSETS_DIR", REPO_DIR / "assets"))

# role -> (image_field, keypoints_field) in the catalog JSON shape
_PIECE_FIELDS = {
    "blouse": ("blouse_image", "blouse_keypoints"),
    "pallu": ("pallu_image", "pallu_keypoints"),
}


def serialize(g: Garment) -> dict:
    """Reproduce the exact catalog.json entry shape the try-on expects."""
    d: dict = {
        "id": g.id,
        "name": g.name,
        "category": g.category,
        "image": g.image_path,
        "keypoints": g.keypoints_path,
        "size_chart": g.size_chart or {},
    }
    # Include a thumbnail path if one was generated (Phase D grid).
    thumb = f"garments/thumbs/{g.id}.webp"
    if (ASSETS_DIR / thumb).exists():
        d["thumbnail"] = thumb
    if g.image_only:
        d["image_only"] = True
    if g.fit_params:
        d["fit_params"] = g.fit_params
    for p in g.pieces:
        fields = _PIECE_FIELDS.get(p.role)
        if fields:
            d[fields[0]] = p.image_path
            d[fields[1]] = p.keypoints_path
    return d


async def get_serialized(session: AsyncSession, gid: str) -> dict | None:
    g = await get_by_id(session, gid)
    return serialize(g) if g else None


async def export_catalog(session: AsyncSession, catalog_path: Path | None = None) -> int:
    """Write active garments back to assets/catalog.json so the Celery worker and
    the catalog fallback stay in sync with the DB (DB is the system of record)."""
    path = catalog_path or (ASSETS_DIR / "catalog.json")
    items = await list_active(session)
    path.write_text(json.dumps(items, indent=2))
    return len(items)


async def list_active(session: AsyncSession) -> list[dict]:
    res = await session.execute(
        select(Garment).where(Garment.status == "active").order_by(Garment.created_at)
    )
    return [serialize(g) for g in res.scalars().all()]


async def get_by_id(session: AsyncSession, gid: str) -> Garment | None:
    res = await session.execute(select(Garment).where(Garment.id == gid))
    return res.scalars().first()


# --- keypoint validation per category --------------------------------------
_REQUIRED_KP = {
    "top": {"left_shoulder", "right_shoulder", "left_hem", "right_hem"},
    "pant": {"left_waist", "right_waist", "left_ankle", "right_ankle"},
    "skirt": {"left_waist", "right_waist", "left_hem", "right_hem"},
    "dupatta": {"left_shoulder", "right_shoulder", "left_hem", "right_hem"},
    "pallu": {"top_left", "top_right", "left_hem", "right_hem"},
}
_PANT_CATS = {"pant", "salwar", "palazzo", "trouser", "trousers"}
_SKIRT_CATS = {"skirt", "lehenga", "saree"}


def _kp_kind(category: str, role: str | None = None) -> str:
    c = (role or category or "").lower()
    if c in _PANT_CATS:
        return "pant"
    if c in _SKIRT_CATS:
        return "skirt"
    if c == "dupatta":
        return "dupatta"
    if c == "pallu":
        return "pallu"
    return "top"


def validate_keypoints(category: str, keypoints: dict, role: str | None = None) -> None:
    """Raise ValueError if the required anchors for the category are missing."""
    norm = (keypoints or {}).get("keypoints_norm") or (keypoints or {}).get("keypoints_px")
    if not norm:
        raise ValueError("keypoints must include keypoints_norm or keypoints_px")
    need = _REQUIRED_KP[_kp_kind(category, role)]
    missing = need - set(norm.keys())
    if missing:
        raise ValueError(f"missing keypoints for {role or category}: {sorted(missing)}")


async def count(session: AsyncSession) -> int:
    res = await session.execute(select(Garment.id))
    return len(res.scalars().all())


def _load_kp(rel_path: str | None) -> dict | None:
    if not rel_path:
        return None
    p = ASSETS_DIR / rel_path
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


async def seed_from_catalog(session: AsyncSession, catalog_path: Path | None = None) -> int:
    """Import assets/catalog.json into the DB. Idempotent: skips existing ids.
    Returns the number of garments inserted."""
    path = catalog_path or (ASSETS_DIR / "catalog.json")
    if not path.exists():
        return 0
    catalog = json.loads(path.read_text())

    existing = set((await session.execute(select(Garment.id))).scalars().all())
    inserted = 0
    for e in catalog:
        if e["id"] in existing:
            continue
        g = Garment(
            id=e["id"], name=e.get("name", e["id"]),
            category=e.get("category", "shirt"),
            image_path=e["image"], keypoints_path=e.get("keypoints"),
            keypoints=_load_kp(e.get("keypoints")),
            size_chart=e.get("size_chart") or {},
            fit_params=e.get("fit_params"),
            image_only=bool(e.get("image_only", False)),
            status="active",
        )
        for role, (img_f, kp_f) in _PIECE_FIELDS.items():
            if e.get(img_f):
                g.pieces.append(GarmentPiece(
                    role=role, image_path=e[img_f], keypoints_path=e.get(kp_f),
                    keypoints=_load_kp(e.get(kp_f)),
                ))
        session.add(g)
        inserted += 1
    await session.commit()
    return inserted
