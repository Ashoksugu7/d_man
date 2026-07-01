"""Seed the garment DB from assets/catalog.json (idempotent).

Usage (from backend/, with DATABASE_URL set to your Postgres, or defaulting to
the configured one):
    python scripts/seed_garments.py
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import create_all, SessionLocal  # noqa: E402
from app.garments_repo import seed_from_catalog, count  # noqa: E402


async def main() -> None:
    await create_all()
    async with SessionLocal() as session:
        inserted = await seed_from_catalog(session)
        total = await count(session)
    print(f"Seed complete: inserted {inserted}, total garments now {total}")


if __name__ == "__main__":
    asyncio.run(main())
