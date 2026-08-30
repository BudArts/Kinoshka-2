"""Интересы пользователя, история поиска и кэш метаданных."""

from __future__ import annotations

import json
from datetime import datetime
from typing import List

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from database.models import Base


class UserInterest(Base):
    """Вес интереса пользователя к категории (0.0 – 5.0).

    Веса растут при просмотрах и поисках и медленно затухают со временем
    (RecommendationEngine.decay_old_interests).
    """

    __tablename__ = "user_interests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    category = Column(String, nullable=False)
    weight = Column(Float, default=1.0, nullable=False)
    #: Сколько раз категория встречалась — для отладки и аналитики.
    hits = Column(Integer, default=0, nullable=False)
    last_updated = Column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )

    user = relationship("User", back_populates="interests")

    __table_args__ = (
        UniqueConstraint("user_id", "category", name="uq_user_category"),
        Index("ix_interest_user_weight", "user_id", "weight"),
    )

    def __repr__(self) -> str:
        return (
            f"<UserInterest(user_id={self.user_id}, "
            f"category='{self.category}', weight={self.weight:.2f})>"
        )


class SearchHistory(Base):
    """Поисковый запрос пользователя."""

    __tablename__ = "search_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    query = Column(String, nullable=False)
    platform = Column(String, nullable=True)      # youtube / rutube / music
    #: Тип контента, в котором искали — video / film / music.
    content_type = Column(String, nullable=True)
    clicked_video_id = Column(String, nullable=True)
    results_count = Column(Integer, nullable=True)
    timestamp = Column(DateTime, default=datetime.now, nullable=False)

    user = relationship("User", back_populates="searches")

    __table_args__ = (Index("ix_search_user_time", "user_id", "timestamp"),)

    def __repr__(self) -> str:
        return f"<SearchHistory(user_id={self.user_id}, query='{self.query}')>"


class VideoMetadata(Base):
    """Кэш метаданных единицы контента.

    Нужен, чтобы не дёргать yt-dlp/API повторно и чтобы рекомендации могли
    работать офлайн — например, когда VPN ещё не поднялся.
    """

    __tablename__ = "video_metadata"

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(String, nullable=False)
    platform = Column(String, nullable=False)     # youtube / rutube / kinopoisk / web
    title = Column(String, nullable=False)
    author = Column(String, nullable=True)
    thumbnail = Column(String, nullable=True)
    url = Column(String, nullable=True)
    description = Column(String, nullable=True)

    categories = Column(String, nullable=True)    # JSON-массив
    tags = Column(String, nullable=True)          # JSON-массив
    duration = Column(Integer, nullable=True)     # секунд
    view_count = Column(Integer, nullable=True)
    rating = Column(Float, nullable=True)
    year = Column(Integer, nullable=True)
    content_type = Column(String, nullable=True)  # video / film / series / music

    last_updated = Column(DateTime, default=datetime.now, nullable=False)

    __table_args__ = (
        UniqueConstraint("video_id", "platform", name="uq_video_platform"),
    )

    @property
    def category_list(self) -> List[str]:
        return _json_list(self.categories)

    @property
    def tag_list(self) -> List[str]:
        return _json_list(self.tags)

    def __repr__(self) -> str:
        return (
            f"<VideoMetadata(video_id='{self.video_id}', "
            f"platform='{self.platform}')>"
        )


def _json_list(raw: str | None) -> List[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
        return value if isinstance(value, list) else []
    except (json.JSONDecodeError, TypeError):
        return []
