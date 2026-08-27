"""Модель локального профиля пользователя."""

from __future__ import annotations

import hashlib
import os
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import relationship

from database.models import Base


class User(Base):
    """Локальный профиль.

    Приложение рассчитано на несколько человек за одним компьютером, поэтому
    аккаунт — это локальный профиль, а не запись на сервере. Обязательно
    только имя; e-mail и пароль опциональны (пароль нужен, если профиль
    хочется закрыть от других членов семьи).
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    patronymic = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    email = Column(String, unique=True, nullable=True)

    #: Хэш пароля в формате "pbkdf2_sha256$<итерации>$<соль_hex>$<хэш_hex>".
    #: NULL означает профиль без пароля — вход в один клик.
    password_hash = Column(String, nullable=True)

    #: Имя иконки Flet или путь к файлу-аватарке.
    avatar = Column(String, nullable=True, default="PERSON")
    #: Цвет плитки профиля на экране выбора.
    color = Column(String, nullable=True, default="#f54b64")

    is_first_run = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    last_login = Column(DateTime, nullable=True)

    history = relationship(
        "History", back_populates="user", cascade="all, delete-orphan"
    )
    collection = relationship(
        "Collection", back_populates="user", cascade="all, delete-orphan"
    )
    interests = relationship(
        "UserInterest", back_populates="user", cascade="all, delete-orphan"
    )
    searches = relationship(
        "SearchHistory", back_populates="user", cascade="all, delete-orphan"
    )

    # -- пароль ------------------------------------------------------------- #
    _ITERATIONS = 200_000

    @staticmethod
    def hash_password(password: str, salt: Optional[bytes] = None) -> str:
        """PBKDF2-HMAC-SHA256. Без внешних зависимостей — только stdlib."""
        salt = salt or os.urandom(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, User._ITERATIONS
        )
        return f"pbkdf2_sha256${User._ITERATIONS}${salt.hex()}${digest.hex()}"

    def set_password(self, password: Optional[str]) -> None:
        """Установить пароль. Пустая строка/None снимают защиту профиля."""
        self.password_hash = self.hash_password(password) if password else None

    def check_password(self, password: Optional[str]) -> bool:
        """Проверить пароль. Профиль без пароля пускает всегда."""
        if not self.password_hash:
            return True
        try:
            _, iterations, salt_hex, digest_hex = self.password_hash.split("$")
            digest = hashlib.pbkdf2_hmac(
                "sha256",
                (password or "").encode("utf-8"),
                bytes.fromhex(salt_hex),
                int(iterations),
            )
        except (ValueError, TypeError):
            return False
        # hmac.compare_digest защищает от атак по времени
        import hmac

        return hmac.compare_digest(digest.hex(), digest_hex)

    @property
    def has_password(self) -> bool:
        return bool(self.password_hash)

    @property
    def display_name(self) -> str:
        parts = [self.name, self.last_name]
        return " ".join(p for p in parts if p) or self.name

    @property
    def initials(self) -> str:
        letters = [p[0] for p in (self.name, self.last_name) if p]
        return "".join(letters).upper() or "?"

    def __repr__(self) -> str:
        return f"<User(id={self.id}, name='{self.name}')>"
