"""Сессия приложения — единая точка доступа к сервисам и текущему профилю.

UI не создаёт сервисы сам, а берёт их отсюда. Это избавляет от передачи
десятка объектов по конструкторам и упрощает подмену в тестах.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, List, Optional

from config import settings
from core.downloader import download_manager
from core.media import MediaItem
from core.profile_service import ProfileService
from core.providers.film import FilmProvider
from core.providers.music import MusicProvider
from core.providers.youtube import YouTubeProvider
from core.recomendation_engine import RecommendationEngine
from core.vpn import vpn_manager
from database import get_session, init_db
from database.models import User

log = logging.getLogger(__name__)


class AppSession:
    """Состояние приложения: текущий профиль, провайдеры, сервисы."""

    def __init__(self):
        init_db()
        self.settings = settings
        self.vpn = vpn_manager
        # Вшитые конфигурации разворачиваем при первом запуске, чтобы YouTube
        # работал сразу после установки, без ручного импорта.
        try:
            self.vpn.ensure_bundled_installed()
        except Exception:
            log.debug("Не удалось развернуть вшитые VPN-конфигурации", exc_info=True)
        self.downloads = download_manager
        self.profiles = ProfileService()

        self.youtube = YouTubeProvider(vpn=self.vpn)
        self.films = FilmProvider(vpn=self.vpn)
        self.music = MusicProvider(vpn=self.vpn)

        self._user: Optional[User] = None
        self._lock = threading.RLock()
        self._user_listeners: List[Callable[[Optional[User]], None]] = []

        # Сессия SQLAlchemy живёт столько же, сколько приложение: SQLite
        # локальный, конкуренции почти нет, а рекомендательному движку удобно
        # работать с одной долгоживущей сессией.
        self._db = get_session()
        self.recommendations = RecommendationEngine(self._db)

    # ------------------------------------------------------------------ #
    #  Текущий профиль
    # ------------------------------------------------------------------ #
    @property
    def user(self) -> Optional[User]:
        return self._user

    @property
    def user_id(self) -> Optional[int]:
        return self._user.id if self._user else None

    @property
    def is_authenticated(self) -> bool:
        return self._user is not None

    def add_user_listener(self, callback: Callable[[Optional[User]], None]) -> None:
        """Подписаться на смену профиля (UI перерисовывает экраны)."""
        self._user_listeners.append(callback)

    def _notify_user_changed(self) -> None:
        for callback in list(self._user_listeners):
            try:
                callback(self._user)
            except Exception:
                log.debug("Слушатель смены профиля упал", exc_info=True)

    def login(self, user_id: int, password: Optional[str] = None) -> User:
        with self._lock:
            user = self.profiles.login(user_id, password)
            self._user = user
            # Раз в сеанс подчищаем протухшие интересы.
            try:
                self.recommendations.decay_old_interests(
                    user.id, days=int(settings.get("interest_decay_days", 30))
                )
            except Exception:
                log.debug("Затухание интересов не выполнено", exc_info=True)
        self._notify_user_changed()
        return user

    def logout(self) -> None:
        with self._lock:
            self._user = None
            self.profiles.logout()
        self._notify_user_changed()

    def try_restore_session(self) -> Optional[User]:
        """Автовход в профиль прошлого сеанса, если он без пароля."""
        user = self.profiles.last_user()
        if user is None or user.has_password:
            return None
        try:
            return self.login(user.id)
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    #  Контент
    # ------------------------------------------------------------------ #
    def provider_for(self, content_type: str):
        """Провайдер под тип контента.

        film/series ведут в FilmProvider (RuTube + веб-поиск + Кинопоиск),
        music — в MusicProvider, всё остальное — обычный YouTube.
        """
        return {
            "film": self.films,
            "series": self.films,
            "music": self.music,
        }.get(content_type, self.youtube)

    def search(
        self, query: str, content_type: str = "video", limit: int = 24
    ) -> List[MediaItem]:
        """Поиск с записью запроса в историю и персонализацией выдачи."""
        provider = self.provider_for(content_type)
        items = provider.search(query, limit=limit)

        if self.user_id and settings.get("save_history", True):
            try:
                self.recommendations.track_search(
                    self.user_id,
                    query,
                    platform=provider.name,
                    content_type=content_type,
                    results_count=len(items),
                )
            except Exception:
                log.debug("Не удалось записать поисковый запрос", exc_info=True)

        if self.user_id and items:
            # Для поиска не выкидываем просмотренное: человек мог искать
            # именно то, что уже смотрел.
            items = self.recommendations.personalize(
                self.user_id, items, drop_watched=False
            )
        return items

    def feed(self, content_type: str = "video", limit: Optional[int] = None) -> List[MediaItem]:
        """Персональная лента рекомендаций."""
        limit = limit or int(settings.get("recommendations_count", 24))
        provider = self.provider_for(content_type)

        seeds: List[str] = []
        if self.user_id:
            seeds = self.recommendations.build_query_seeds(
                self.user_id, count=6, content_type=content_type
            )

        items = provider.recommendations(seeds, limit=limit)
        if self.user_id and items:
            items = self.recommendations.personalize(self.user_id, items)
        return items

    def download(self, item: MediaItem, *, audio_only: bool = False) -> Optional[int]:
        """Поставить элемент в очередь загрузки."""
        if not self.user_id:
            return None
        return self.downloads.enqueue(self.user_id, item, audio_only=audio_only)

    def track_watch(
        self, item: MediaItem, watch_duration: int, total_duration: Optional[int] = None
    ) -> None:
        """Записать просмотр (если ведение истории не отключено)."""
        if not self.user_id or not settings.get("save_history", True):
            return
        try:
            self.recommendations.track_watch(
                self.user_id, item, watch_duration, total_duration
            )
        except Exception:
            log.debug("Не удалось записать просмотр", exc_info=True)

    # ------------------------------------------------------------------ #
    def shutdown(self) -> None:
        """Аккуратно закрыть загрузки, БД и туннель."""
        try:
            self.downloads.shutdown()
        except Exception:
            pass
        try:
            self._db.close()
        except Exception:
            pass
        try:
            if self.vpn.is_connected:
                self.vpn.disconnect()
        except Exception:
            pass
