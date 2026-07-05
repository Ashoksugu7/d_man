"""ORM models for the garment service (Phase A).

A single-piece garment uses `Garment` only. `GarmentPiece` remains for schema
compatibility (multi-piece garments are no longer supported).

Keypoints are stored both as a file path (kept working with the existing
/assets static mount + try-on loaders) and inline as JSON, so later phases can
serve them straight from the DB.
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, TABLE_PREFIX

# JSONB on Postgres, plain JSON elsewhere (so tests can run on sqlite).
JsonType = JSON().with_variant(JSONB, "postgresql")


def _uuid() -> str:
    return uuid.uuid4().hex[:12]


class Garment(Base):
    __tablename__ = f"{TABLE_PREFIX}garment"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    image_path: Mapped[str] = mapped_column(Text, nullable=False)
    keypoints_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    keypoints: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    size_chart: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    fit_params: Mapped[dict | None] = mapped_column(JsonType, nullable=True)  # per-garment warp overrides
    image_only: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    pieces: Mapped[list["GarmentPiece"]] = relationship(
        back_populates="garment", cascade="all, delete-orphan", lazy="selectin")


class GarmentPiece(Base):
    __tablename__ = f"{TABLE_PREFIX}garment_piece"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    garment_id: Mapped[str] = mapped_column(
        ForeignKey(f"{TABLE_PREFIX}garment.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    image_path: Mapped[str] = mapped_column(Text, nullable=False)
    keypoints_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    keypoints: Mapped[dict | None] = mapped_column(JsonType, nullable=True)

    garment: Mapped["Garment"] = relationship(back_populates="pieces")


class AnnotationVersion(Base):
    """History of keypoint edits, so a bad annotation can be reverted."""
    __tablename__ = f"{TABLE_PREFIX}annotation_version"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    garment_id: Mapped[str] = mapped_column(
        ForeignKey(f"{TABLE_PREFIX}garment.id", ondelete="CASCADE"), index=True)
    role: Mapped[str | None] = mapped_column(String(20), nullable=True)  # None = primary
    keypoints: Mapped[dict] = mapped_column(JsonType, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
