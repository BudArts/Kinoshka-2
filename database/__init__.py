"""Подключение к базе данных.

БД — SQLite в каталоге пользовательских данных (см. config.DATA_DIR).
Экспортирует engine, фабрику сессий, контекстный менеджер session_scope()
и init_db() для создания таблиц при старте приложения.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from config import DB_PATH, ensure_dirs

ensure_dirs()

#: check_same_thread=False — Flet выполняет обработчики в разных потоках,
#: поэтому одна сессия может использоваться не только из потока-создателя.
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    echo=False,
    future=True,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):  # pragma: no cover
    """Включаем внешние ключи и WAL — иначе cascade delete не работает."""
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()
    except Exception:
        # На не-SQLite соединениях просто ничего не делаем.
        pass


def init_db() -> None:
    """Создать все таблицы, если их ещё нет."""
    from database.models import Base  # локальный импорт: регистрирует модели

    ensure_dirs()
    Base.metadata.create_all(bind=engine)


def get_session() -> Session:
    """Новая сессия. Вызывающий отвечает за close()."""
    return SessionLocal()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Транзакционная область видимости вокруг серии операций."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


__all__ = ["engine", "SessionLocal", "init_db", "get_session", "session_scope"]
