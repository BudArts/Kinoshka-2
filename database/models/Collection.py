"""Коллекция — скачанные локально файлы пользователя."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Time,
)
from sqlalchemy.orm import relationship

from database.models import Base


class Collection(Base):
    """Скачанный файл: «Мои видео», «Мои фильмы», «Моя музыка».

    Строка создаётся, когда загрузка встаёт в очередь (status="queued"),
    и обновляется по мере скачивания. Так пользователь видит прогресс
    и неудачные загрузки, а не только готовые файлы.
    """

    __tablename__ = "collection"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    type = Column(String, nullable=False)       # video / film / series / music
    path = Column(String, nullable=True)        # путь к файлу (пока качается — None)
    title = Column(String, nullable=False)
    author = Column(String, nullable=True)
    thumbnail = Column(String, nullable=True)

    source_url = Column(String, nullable=True)  # откуда качали
    platform = Column(String, nullable=True)    # youtube / rutube / web
    video_id = Column(String, nullable=True)

    duration = Column(Integer, nullable=True)   # секунд
    filesize = Column(Integer, nullable=True)   # байт
    quality = Column(String, nullable=True)

    status = Column(String, nullable=False, default="queued")
    # queued -> downloading -> done | error | canceled
    progress = Column(Integer, nullable=False, default=0)   # 0..100
    error = Column(String, nullable=True)

    date = Column(DateTime, nullable=False, default=datetime.now)
    time_key = Column(Time, nullable=True)
    favorite = Column(Boolean, nullable=False, default=False)

    user = relationship("User", back_populates="collection")

    __table_args__ = (
        Index("ix_collection_user_type", "user_id", "type"),
        Index("ix_collection_status", "status"),
    )

    # -- вспомогательные свойства ------------------------------------------- #
    @property
    def exists_on_disk(self) -> bool:
        return bool(self.path) and os.path.isfile(self.path)

    @property
    def filename(self) -> str:
        return Path(self.path).name if self.path else self.title

    @property
    def size_human(self) -> str:
        size = float(self.filesize or 0)
        for unit in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
            if size < 1024 or unit == "ТБ":
                return f"{size:.0f} {unit}" if unit == "Б" else f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} ТБ"

    def __repr__(self) -> str:
        return f"<Collection(id={self.id}, type='{self.type}', title='{self.title}')>"
