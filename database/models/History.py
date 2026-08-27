"""История просмотров и прослушиваний."""

from __future__ import annotations

import json
from datetime import datetime
from typing import List

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


class History(Base):
    """Одна запись истории: что, где, когда и сколько смотрели.

    Используется и для вкладки «История», и как источник сигнала для
    RecommendationEngine (см. core/recomendation_engine.py).
    """

    __tablename__ = "history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # --- основная информация ---
    type = Column(String, nullable=False)      # video / music / film / series
    platform = Column(String, nullable=True)   # youtube / rutube / web / local
    video_id = Column(String, nullable=True)   # идентификатор на площадке
    link = Column(String, nullable=False)
    title = Column(String, nullable=False)
    thumbnail = Column(String, nullable=True)
    author = Column(String, nullable=True)

    # --- данные просмотра ---
    watch_duration = Column(Integer, nullable=True, default=0)   # секунд просмотрено
    total_duration = Column(Integer, nullable=True, default=0)   # всего секунд
    position = Column(Integer, nullable=True, default=0)         # для «продолжить смотреть»
    completed = Column(Boolean, default=False, nullable=False)

    # --- метаданные для рекомендаций (JSON-массивы в строке) ---
    categories = Column(String, nullable=True)
    tags = Column(String, nullable=True)

    # --- временные метки ---
    date = Column(DateTime, nullable=False, default=datetime.now)
    time_key = Column(Time, nullable=True)

    user = relationship("User", back_populates="history")

    __table_args__ = (
        Index("ix_history_user_date", "user_id", "date"),
        Index("ix_history_user_video", "user_id", "video_id"),
    )

    # -- удобный доступ к JSON-полям ---------------------------------------- #
    @property
    def category_list(self) -> List[str]:
        return _load_json_list(self.categories)

    @category_list.setter
    def category_list(self, value: List[str]) -> None:
        self.categories = json.dumps(value or [], ensure_ascii=False)

    @property
    def tag_list(self) -> List[str]:
        return _load_json_list(self.tags)

    @tag_list.setter
    def tag_list(self, value: List[str]) -> None:
        self.tags = json.dumps(value or [], ensure_ascii=False)

    @property
    def completion_rate(self) -> float:
        if not self.total_duration:
            return 0.0
        return min((self.watch_duration or 0) / self.total_duration, 1.0)

    def __repr__(self) -> str:
        return f"<History(id={self.id}, type='{self.type}', title='{self.title}')>"


def _load_json_list(raw: str | None) -> List[str]:
    """Безопасно распарсить JSON-массив, лежащий в строковой колонке."""
    if not raw:
        return []
    try:
        value = json.loads(raw)
        return value if isinstance(value, list) else []
    except (json.JSONDecodeError, TypeError):
        return []
