#!/usr/bin/env python3
"""Hard-delete every garment whose category is not in the keep list.

Removes DB rows (garment + pieces + annotation versions), their files under
assets/garments/, and re-exports catalog.json. Default keep list:
shirt, tshirt, fullsleeve.

Run from the backend directory with the backend venv:
    cd backend && ../.venv/bin/python scripts/cleanup_garments.py
    (add --dry-run to preview, --keep shirt,tshirt,fullsleeve to override)
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete as sa_delete, select  # noqa: E402

from app import storage  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.garments_repo import export_catalog  # noqa: E402
from app.models import AnnotationVersion, Garment  # noqa: E402

DEFAULT_KEEP = "shirt,tshirt,fullsleeve"


async def cleanup(keep: set[str], dry_run: bool) -> None:
    async with SessionLocal() as session:
        res = await session.execute(select(Garment))
        garments = res.scalars().all()
        doomed = [g for g in garments if (g.category or "").lower() not in keep]
        print(f"{len(garments)} garments; keeping "
              f"{len(garments) - len(doomed)}, deleting {len(doomed)}:")
        for g in doomed:
            print(f"  - {g.id} ({g.category})")
        if dry_run:
            print("dry run — nothing changed")
            return
        for g in doomed:
            rels = [g.image_path, g.keypoints_path,
                    f"garments/{g.id}_mannequin.png",
                    f"garments/thumbs/{g.id}.webp"]
            for p in g.pieces:
                rels += [p.image_path, p.keypoints_path]
            for rel in rels:
                storage.delete_rel(rel)
            await session.execute(sa_delete(AnnotationVersion)
                                  .where(AnnotationVersion.garment_id == g.id))
            await session.delete(g)
        await session.commit()
        n = await export_catalog(session)
        print(f"done — catalog.json now has {n} garments")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--keep", default=DEFAULT_KEEP,
                    help=f"comma-separated categories to keep (default: {DEFAULT_KEEP})")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    keep = {c.strip().lower() for c in args.keep.split(",") if c.strip()}
    asyncio.run(cleanup(keep, args.dry_run))


if __name__ == "__main__":
    main()
