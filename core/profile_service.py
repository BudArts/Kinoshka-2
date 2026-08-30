"""Работа с локальными профилями: создание, вход, смена аккаунта."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from config import settings
from core.recomendation_engine import RecommendationEngine
from database import session_scope
from database.models import Collection, History, SearchHistory, User, UserInterest

log = logging.getLogger(__name__)

#: Палитра для плиток профилей на экране выбора.
PROFILE_COLORS = [
    "#f54b64", "#f78361", "#4facfe", "#43e97b",
    "#a18cd1", "#ffd86f", "#fc6076", "#30cfd0",
]


class ProfileError(RuntimeError):
    """Ошибка при работе с профилем (занятое имя, неверный пароль и т.п.)."""


class ProfileService:
    """CRUD профилей и логика первого запуска."""

    # ------------------------------------------------------------------ #
    #  Чтение
    # ------------------------------------------------------------------ #
    @staticmethod
    def list_profiles() -> List[User]:
        """Все профили, недавно использованные — первыми."""
        with session_scope() as session:
            users = (
                session.query(User)
                .order_by(User.last_login.desc().nullslast(), User.created_at.asc())
                .all()
            )
            for user in users:
                session.expunge(user)
            return users

    @staticmethod
    def get(user_id: int) -> Optional[User]:
        with session_scope() as session:
            user = session.get(User, user_id)
            if user is not None:
                session.expunge(user)
            return user

    @staticmethod
    def count() -> int:
        with session_scope() as session:
            return session.query(User).count()

    @staticmethod
    def is_first_run() -> bool:
        """Ни одного профиля — значит программу запустили впервые."""
        return ProfileService.count() == 0

    # ------------------------------------------------------------------ #
    #  Создание и изменение
    # ------------------------------------------------------------------ #
    @staticmethod
    def create(
        name: str,
        *,
        password: Optional[str] = None,
        last_name: Optional[str] = None,
        patronymic: Optional[str] = None,
        email: Optional[str] = None,
        avatar: Optional[str] = None,
        interests: Optional[List[str]] = None,
    ) -> User:
        """Создать профиль и сразу задать стартовые интересы."""
        name = (name or "").strip()
        if not name:
            raise ProfileError("Введите имя профиля")
        if len(name) > 40:
            raise ProfileError("Имя слишком длинное (максимум 40 символов)")

        with session_scope() as session:
            exists = (
                session.query(User)
                .filter(func_lower(User.name) == name.lower())
                .first()
            )
            if exists:
                raise ProfileError(f"Профиль «{name}» уже существует")
            if email:
                email_taken = session.query(User).filter(User.email == email).first()
                if email_taken:
                    raise ProfileError("Этот e-mail уже привязан к другому профилю")

            index = session.query(User).count()
            user = User(
                name=name,
                last_name=(last_name or "").strip() or None,
                patronymic=(patronymic or "").strip() or None,
                email=(email or "").strip() or None,
                avatar=avatar or "PERSON",
                color=PROFILE_COLORS[index % len(PROFILE_COLORS)],
                is_first_run=True,
                created_at=datetime.now(),
            )
            user.set_password(password)
            session.add(user)
            session.flush()

            RecommendationEngine(session).setup_initial_interests(user.id, interests)

            session.refresh(user)
            session.expunge(user)
            return user

    @staticmethod
    def update(user_id: int, **fields) -> User:
        """Обновить поля профиля. Пароль передаётся как password=..."""
        password = fields.pop("password", ...)
        with session_scope() as session:
            user = session.get(User, user_id)
            if user is None:
                raise ProfileError("Профиль не найден")

            if "name" in fields:
                new_name = (fields["name"] or "").strip()
                if not new_name:
                    raise ProfileError("Имя не может быть пустым")
                clash = (
                    session.query(User)
                    .filter(func_lower(User.name) == new_name.lower(), User.id != user_id)
                    .first()
                )
                if clash:
                    raise ProfileError(f"Профиль «{new_name}» уже существует")
                fields["name"] = new_name

            for key, value in fields.items():
                if hasattr(user, key):
                    setattr(user, key, value)

            if password is not ...:
                user.set_password(password)

            session.flush()
            session.refresh(user)
            session.expunge(user)
            return user

    @staticmethod
    def change_password(user_id: int, old_password: str, new_password: str) -> None:
        """Сменить пароль с проверкой старого."""
        with session_scope() as session:
            user = session.get(User, user_id)
            if user is None:
                raise ProfileError("Профиль не найден")
            if user.has_password and not user.check_password(old_password):
                raise ProfileError("Текущий пароль указан неверно")
            user.set_password(new_password)

    @staticmethod
    def delete(user_id: int) -> None:
        """Удалить профиль вместе со всей его историей и интересами."""
        with session_scope() as session:
            user = session.get(User, user_id)
            if user is None:
                return
            session.delete(user)
        if settings.get("last_user_id") == user_id:
            settings.set("last_user_id", None)

    # ------------------------------------------------------------------ #
    #  Вход
    # ------------------------------------------------------------------ #
    @staticmethod
    def login(user_id: int, password: Optional[str] = None) -> User:
        """Войти в профиль. Бросает ProfileError при неверном пароле."""
        with session_scope() as session:
            user = session.get(User, user_id)
            if user is None:
                raise ProfileError("Профиль не найден")
            if not user.check_password(password):
                raise ProfileError("Неверный пароль")

            user.last_login = datetime.now()
            session.flush()
            session.refresh(user)
            session.expunge(user)

        settings.set("last_user_id", user_id)
        return user

    @staticmethod
    def last_user() -> Optional[User]:
        """Профиль из прошлого сеанса — чтобы не выбирать его каждый раз."""
        user_id = settings.get("last_user_id")
        return ProfileService.get(user_id) if user_id else None

    @staticmethod
    def logout() -> None:
        settings.set("last_user_id", None)

    # ------------------------------------------------------------------ #
    #  Статистика профиля
    # ------------------------------------------------------------------ #
    @staticmethod
    def summary(user_id: int) -> dict:
        """Короткая сводка для карточки профиля."""
        with session_scope() as session:
            return {
                "history": session.query(History)
                .filter(History.user_id == user_id)
                .count(),
                "downloads": session.query(Collection)
                .filter(Collection.user_id == user_id, Collection.status == "done")
                .count(),
                "interests": session.query(UserInterest)
                .filter(UserInterest.user_id == user_id)
                .count(),
                "searches": session.query(SearchHistory)
                .filter(SearchHistory.user_id == user_id)
                .count(),
            }


def func_lower(column):
    """Регистронезависимое сравнение имён профилей."""
    from sqlalchemy import func

    return func.lower(column)
