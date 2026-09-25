from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class FileRecord(Base):
    __tablename__ = "files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    original_filename: Mapped[str] = mapped_column(String(512))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    local_status: Mapped[str] = mapped_column(String(32), default="ok")
    replica_map_json: Mapped[str] = mapped_column(Text, default="{}")
    replication_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def get_replica_map(self) -> dict[str, str]:
        try:
            raw = json.loads(self.replica_map_json or "{}")
            return {str(k): str(v) for k, v in raw.items()}
        except json.JSONDecodeError:
            return {}

    def set_replica_map(self, replica_map: dict[int | str, str]) -> None:
        normalized = {str(k): v for k, v in replica_map.items()}
        self.replica_map_json = json.dumps(normalized, sort_keys=True)
