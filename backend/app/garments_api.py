"""Garment CRUD + image/annotation API (Phase B).

Endpoints (mounted under /api/garments):
    GET    /{id}              one garment (catalog shape)
    POST   /                  create metadata
    PUT    /{id}              edit metadata (+ optional keypoints)
    DELETE /{id}              archive (soft delete)
    POST   /{id}/image        upload/replace image (multipart; optional role)
    POST   /{id}/annotation   save keypoints (JSON; optional role)

Images are stored on disk under assets/garments/ (served by /assets) and paths
recorded in the DB.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from . import storage
from .db import get_session
from .garments_repo import export_catalog, get_by_id, serialize, validate_keypoints
from .models import AnnotationVersion, Garment, GarmentPiece

router = APIRouter(prefix="/api/garments", tags=["garments"])


class GarmentCreate(BaseModel):
    id: str | None = None
    name: str
    category: str
    size_chart: dict | None = None
    fit_params: dict | None = None
    image_only: bool = False


class GarmentUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    size_chart: dict | None = None
    fit_params: dict | None = None  # per-garment warp overrides
    image_only: bool | None = None
    status: str | None = None
    keypoints: dict | None = None   # optional: re-annotate primary in one call


class AnnotationBody(BaseModel):
    keypoints: dict
    role: str | None = None


async def _reload(session: AsyncSession, gid: str) -> dict:
    # Keep catalog.json (worker + fallback source) in sync with the DB.
    await export_catalog(session)
    g = await get_by_id(session, gid)
    return serialize(g)


def _piece(g: Garment, role: str) -> GarmentPiece | None:
    return next((p for p in g.pieces if p.role == role), None)


@router.get("/{gid}")
async def get_one(gid: str, session: AsyncSession = Depends(get_session)):
    g = await get_by_id(session, gid)
    if not g:
        raise HTTPException(404, "garment not found")
    return serialize(g)


@router.post("")
async def create(body: GarmentCreate, session: AsyncSession = Depends(get_session)):
    from .models import _uuid
    gid = (body.id or _uuid()).strip()
    if await get_by_id(session, gid):
        raise HTTPException(409, f"garment id already exists: {gid}")
    g = Garment(id=gid, name=body.name, category=body.category,
                image_path="", size_chart=body.size_chart or {},
                fit_params=body.fit_params, image_only=body.image_only,
                status="active")
    session.add(g)
    await session.commit()
    return await _reload(session, gid)


@router.put("/{gid}")
async def update(gid: str, body: GarmentUpdate,
                 session: AsyncSession = Depends(get_session)):
    g = await get_by_id(session, gid)
    if not g:
        raise HTTPException(404, "garment not found")
    if body.name is not None:
        g.name = body.name
    if body.category is not None:
        g.category = body.category
    if body.size_chart is not None:
        g.size_chart = body.size_chart
    if body.fit_params is not None:
        g.fit_params = body.fit_params
    if body.image_only is not None:
        g.image_only = body.image_only
    if body.status is not None:
        g.status = body.status
    if body.keypoints is not None:
        try:
            validate_keypoints(g.category, body.keypoints)
        except ValueError as e:
            raise HTTPException(422, str(e))
        rel = storage.save_keypoints_json(gid, None, body.keypoints)
        g.keypoints_path = rel
        g.keypoints = body.keypoints
    await session.commit()
    return await _reload(session, gid)


@router.delete("/{gid}")
async def archive(gid: str, hard: bool = False,
                  session: AsyncSession = Depends(get_session)):
    """Archive (soft delete) a garment; `?hard=true` permanently deletes the
    DB row, its pieces and all files on disk."""
    g = await get_by_id(session, gid)
    if not g:
        raise HTTPException(404, "garment not found")
    if not hard:
        g.status = "archived"
        await session.commit()
        await export_catalog(session)
        return {"id": gid, "status": "archived"}

    rels = [g.image_path, g.keypoints_path,
            f"garments/{gid}_mannequin.png", f"garments/thumbs/{gid}.webp"]
    for p in g.pieces:
        rels += [p.image_path, p.keypoints_path]
    for rel in rels:
        storage.delete_rel(rel)
    from sqlalchemy import delete as sa_delete
    await session.execute(sa_delete(AnnotationVersion)
                          .where(AnnotationVersion.garment_id == gid))
    await session.delete(g)
    await session.commit()
    await export_catalog(session)
    return {"id": gid, "status": "deleted"}


@router.post("/{gid}/image")
async def upload_image(gid: str, photo: UploadFile = File(...),
                       role: str | None = Form(None),
                       remove_bg: bool = Form(False),
                       session: AsyncSession = Depends(get_session)):
    g = await get_by_id(session, gid)
    if not g:
        raise HTTPException(404, "garment not found")
    raw = await photo.read()
    try:
        w, h, has_alpha = storage.read_image_meta(raw)
    except Exception:
        raise HTTPException(400, "could not read image (png/webp/jpg)")
    ext = (photo.filename or "x.png").rsplit(".", 1)[-1].lower()
    # Optional background cutout → transparent PNG (opt-in via the checkbox).
    if remove_bg:
        try:
            raw = storage.remove_background(raw)
            ext = "png"
            has_alpha = True
        except Exception:
            pass  # fall back to the original image
    try:
        rel = storage.save_image(gid, role, ext, raw)
    except ValueError as e:
        raise HTTPException(400, str(e))
    thumb = storage.make_thumbnail(gid if not role else f"{gid}_{role}", rel)

    if role:
        p = _piece(g, role)
        if not p:
            p = GarmentPiece(role=role, image_path=rel); g.pieces.append(p)
        else:
            p.image_path = rel
    else:
        g.image_path = rel
    await session.commit()
    return {"ok": True, "image": rel, "thumbnail": thumb,
            "width": w, "height": h, "has_alpha": has_alpha,
            "warning": None if has_alpha else
            "image has no transparency — try-on will show a rectangle; use a cut-out"}


@router.post("/{gid}/annotation")
async def save_annotation(gid: str, body: AnnotationBody,
                          session: AsyncSession = Depends(get_session)):
    g = await get_by_id(session, gid)
    if not g:
        raise HTTPException(404, "garment not found")
    try:
        validate_keypoints(g.category, body.keypoints, body.role)
    except ValueError as e:
        raise HTTPException(422, str(e))
    rel = storage.save_keypoints_json(gid, body.role, body.keypoints)
    if body.role:
        p = _piece(g, body.role)
        if not p:
            raise HTTPException(400, f"upload the {body.role} image before annotating it")
        p.keypoints_path = rel
        p.keypoints = body.keypoints
    else:
        g.keypoints_path = rel
        g.keypoints = body.keypoints
    # Keep an edit history so a bad annotation can be reverted.
    session.add(AnnotationVersion(garment_id=gid, role=body.role, keypoints=body.keypoints))
    await session.commit()
    return await _reload(session, gid)


@router.get("/{gid}/versions")
async def list_versions(gid: str, session: AsyncSession = Depends(get_session)):
    res = await session.execute(
        select(AnnotationVersion)
        .where(AnnotationVersion.garment_id == gid)
        .order_by(AnnotationVersion.created_at.desc())
    )
    return [
        {"id": v.id, "role": v.role, "created_at": v.created_at.isoformat(),
         "keypoints": v.keypoints}
        for v in res.scalars().all()
    ]


@router.post("/{gid}/revert/{version_id}")
async def revert(gid: str, version_id: str, session: AsyncSession = Depends(get_session)):
    g = await get_by_id(session, gid)
    if not g:
        raise HTTPException(404, "garment not found")
    v = (await session.execute(
        select(AnnotationVersion).where(AnnotationVersion.id == version_id)
    )).scalars().first()
    if not v or v.garment_id != gid:
        raise HTTPException(404, "version not found")
    rel = storage.save_keypoints_json(gid, v.role, v.keypoints)
    if v.role:
        p = _piece(g, v.role)
        if p:
            p.keypoints_path = rel
            p.keypoints = v.keypoints
    else:
        g.keypoints_path = rel
        g.keypoints = v.keypoints
    # record the revert as a new version too (so history is linear)
    session.add(AnnotationVersion(garment_id=gid, role=v.role, keypoints=v.keypoints))
    await session.commit()
    return await _reload(session, gid)
