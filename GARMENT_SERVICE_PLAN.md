# Garment Service — Development Plan

Goal: replace the static `catalog.json` + loose files with a **DB-backed garment
service**. The annotation tool becomes part of the app (upload image → annotate →
persist image path + keypoints in the service), existing garments are editable,
and the try-on reads garments from the database.

## Target architecture

```
Next.js frontend
  ├── Try-On (reads garments from API → DB)
  └── Garment Manager (new): list / upload / annotate / edit / delete
        │  (in-app port of tools/annotate.html)
        ▼
FastAPI garment service
  ├── /api/garments        CRUD + list/filter
  ├── /api/garments/{id}/image      upload / replace
  ├── /api/garments/{id}/annotation save/edit keypoints
  ├── DB (SQLAlchemy)      SQLite (dev) → Postgres (prod)
  └── Object storage       local disk (dev) → S3/GCS (prod)
```

Keep the existing try-on/warp/HD pipeline unchanged — only the **garment source**
moves from `catalog.json` to the DB, behind the same `GET /api/garments` shape.

## Decisions (locked)
- **Database: PostgreSQL** via **async SQLAlchemy + asyncpg** (no SQLite step).
  Dev connection string (override with `DATABASE_URL` env):
  `postgresql+asyncpg://postgres:postgres@localhost:5432/doctor_appointment`
  (reusing an existing local Postgres instance). Use Alembic for migrations; use
  a dedicated schema or table prefix to stay isolated from other apps sharing
  that database.
- Async DB session throughout (FastAPI async endpoints).
- Status: **plan only for now — do not build yet** (per user).

## Data model (SQLAlchemy)

```
garment
  id            uuid / slug (pk)
  name          text
  category      text            # shirt|tshirt|kurta|pant|salwar|skirt|dupatta|
                                #  lehenga|saree|fullsleeve|...
  image_path    text            # storage key/URL of the primary piece
  keypoints     jsonb           # {keypoints_norm, keypoints_px, canvas}
  size_chart    jsonb
  image_only    bool            # sarees etc. (no live mode)
  status        text            # active | archived (soft delete)
  created_at / updated_at

garment_piece   # for multi-piece (lehenga, saree)
  id, garment_id (fk), role (blouse|skirt|drape|pallu),
  image_path, keypoints jsonb
```

Single-piece garments use `garment` only; multi-piece add `garment_piece` rows.
`GET /api/garments` serializes to the current catalog JSON shape so the try-on
frontend needs minimal change.

## API surface

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/garments` | list (filter by category/status, search) |
| GET | `/api/garments/{id}` | one garment (+ pieces) |
| POST | `/api/garments` | create (name/category/size_chart) |
| PUT | `/api/garments/{id}` | edit metadata / keypoints |
| DELETE | `/api/garments/{id}` | archive (soft delete) |
| POST | `/api/garments/{id}/image` | upload/replace image (multipart) |
| POST | `/api/garments/{id}/pieces` | add/replace a piece (multi-piece) |
| GET | `/media/{path}` | serve stored images (or S3 URL) |

## Phases

### STATUS: Phase A ✅ · B ✅ · C ✅ · D ✅ (verified; uncommitted).
### Phase E (production: auth, S3, Alembic, prod DB) — DEFERRED per user; not building now.
- D: try-on now reads garments from the **DB** (`tryon_image`, `measure`,
  `tryon_hd` via `_get_garment`/`_list_garments`, DB-first + catalog fallback).
  Mutations **auto-export `catalog.json`** so the Celery worker + fallback stay
  in sync (DB is system of record). Thumbnails generated on upload + surfaced in
  `GET /api/garments`. Grid: category tabs + search + lazy thumbnails. Verified:
  create-via-API → catalog exported w/ thumb → try-on finds garment from DB.
- C: in-app **Garment Manager** at `/manage` — list (thumbnails) + New/Edit/
  Archive; `components/Annotator.tsx` (click/drag/guess canvas), `lib/annotation.ts`
  (schemes), `lib/api.ts` garment-management client; nav link in the header.
  Create → upload → annotate → save via the Phase B API; Edit reloads image +
  keypoints. Multi-piece (lehenga/saree) annotates the primary piece (blouse/
  pallu via API for now). Next build passes (`/manage` route).
- A: `db.py`, `models.py` (Garment/GarmentPiece), `garments_repo.py`,
  `scripts/seed_garments.py`, DB-backed `GET /api/garments` (+catalog fallback).
- B: `storage.py` (disk + thumbnails), CRUD/upload/annotate router
  (`garments_api.py`) with per-category keypoint validation. Lifecycle verified:
  create → upload → annotate → edit → archive.

### Phase A — DB + storage foundation
- Add SQLAlchemy + a `storage` abstraction (local disk now, S3 later).
- Models + Alembic migrations. SQLite for dev (zero-setup), Postgres-ready.
- Seed/migrate script: import current `catalog.json` + `assets/garments/*` into
  the DB (idempotent).
- `GET /api/garments` reads from DB (same JSON shape). Keep a `SEED_FROM_JSON`
  fallback so nothing breaks mid-migration.
- **Done when:** try-on works unchanged, sourced from the DB.

### Phase B — Garment CRUD + image/annotation persistence
- Implement create / update / delete / image-upload / annotation-save endpoints.
- Server-side validation: image type (png/webp/jpg), size, transparency check,
  required keypoints per category; auto-thumbnail generation.
- Store image via the storage layer; write path + keypoints to DB.
- **Done when:** a garment can be created + annotated + edited entirely via API.

### Phase C — In-app Garment Manager (annotation UI)
- Port `tools/annotate.html` into a Next.js route `/manage`:
  - Upload image → canvas annotate (reuse existing schemes, auto-guess,
    drag-to-edit, multi-piece) → **POST to the service** (no manual file save).
  - Garment list with thumbnails; **Edit** loads existing image + keypoints back
    onto the canvas to adjust and re-save.
  - Delete/archive; category filter; search.
- **Done when:** the standalone HTML is replaced by an in-app, DB-backed editor.

### Phase D — Try-on integration polish
- Garment grid loads from DB with thumbnails, category tabs, search.
- Cache/ETag on `/api/garments`; lazy-load images.
- "Recently added" + fit badges continue to work.
- **Done when:** try-on and manager share one live garment source.

### Phase E — Production hardening
- Swap SQLite→Postgres; local disk→S3/GCS (signed URLs, CDN).
- Auth: admin-only garment management (JWT / session); public read for try-on.
- Rate limits, audit log (who changed what), backups.
- Docker compose: add the DB + storage services.

## Extra features — STATUS: 1,2,3,4 ✅ done (verified; uncommitted)
1. Background removal on upload — `storage.remove_background` (flood-fill) +
   `remove_bg` flag on `POST /{id}/image` + "Remove background" checkbox.
2. Live warp preview in the annotator — `Annotator.tsx` overlays the garment on
   a sample body via 3-point affine as points move.
3. Annotation versioning — `vton_annotation_version` table; every save records a
   version; `GET /{id}/versions` + `POST /{id}/revert/{ver}` + history UI.
4. Per-garment fit overrides — `Garment.fit_params` (JSONB); threaded into the
   warp (`fit_overrides`); PUT/create accept it; "Advanced fit" fields in
   /manage. (create_all adds the column on Postgres via ADD COLUMN IF NOT EXISTS.)

## Suggested extra features (worth adding)
1. **Background removal on upload** — auto-cutout to transparent (rembg / the
   existing flood-fill) so uploads don't need pre-made alpha. Big UX win.
2. **Live warp preview in the annotator** — overlay the garment on a sample body
   as you move points, so annotation quality is visible immediately.
3. **Annotation versioning** — keep history; revert a bad edit.
4. **Bulk import** — drop a folder / CSV of product images; queue for annotation.
5. **Auto-keypoint suggestion** — pose/segmentation-assisted guess beyond the
   current bbox heuristic.
6. **Garment tags + collections** (brand, color, season) for search/merchandising.
7. **Per-garment fit overrides** — store `FitParams` (hem_extend, widen) in the
   DB so tricky garments fit better without code changes.
8. **Soft delete + restore**, and **duplicate garment** for quick variants.
9. **Validation report** — flag low-res / non-transparent / off-center images at
   upload with guidance (ties into `assets/GARMENT_IMAGES.md`).

## Migration & risk notes
- Keep `catalog.json` as the seed source; migration is one-way and idempotent.
- Storage abstraction from day one avoids a painful S3 retrofit later.
- Serialize DB → existing catalog JSON shape to minimize try-on/frontend churn.
- DB/storage are all **no-GPU** — this whole plan is implementable + verifiable
  locally (unlike the diffusion/GPU items still pending).

## Recommended build order
A → B → C are the core (local, no-GPU, high value). D is polish. E is for
production. Extra features slot in after C (background removal + warp preview
give the most immediate value).
```
