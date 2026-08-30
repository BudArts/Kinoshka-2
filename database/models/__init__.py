"""Базовый класс SQLAlchemy и реэкспорт всех моделей.

Импорт всех модулей моделей здесь обязателен: без него SQLAlchemy не сможет
разрешить строковые ссылки в relationship() (например "History") и
Base.metadata.create_all() создаст не все таблицы.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Общий декларативный базовый класс для всех моделей."""


# Импорты идут после объявления Base, иначе будет циклический импорт.
from database.models.User import User  # noqa: E402
from database.models.History import History  # noqa: E402
from database.models.Collection import Collection  # noqa: E402
from database.models.User_interests import (  # noqa: E402
    UserInterest,
    SearchHistory,
    VideoMetadata,
)

__all__ = [
    "Base",
    "User",
    "History",
    "Collection",
    "UserInterest",
    "SearchHistory",
    "VideoMetadata",
]
