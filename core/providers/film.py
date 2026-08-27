"""Агрегатор источников для раздела «Фильмы и сериалы».

Реализует логику из технического задания:

  * основной источник просмотра — **RuTube**;
  * если на RuTube ничего не нашлось — включается **поиск по интернету**
    и видео подгружается оттуда;
  * метаданные (рейтинг, постер, год, жанры) берутся с **Кинопоиска**;
  * запрос пользователя предварительно разбирает **ИИ-поиск**.

Наружу выглядит как обычный провайдер, поэтому UI и рекомендательный движок
работают с ним так же, как с YouTube.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

from core.ai_search import SearchIntent, ai_search
from core.media import MediaItem
from core.providers.base import BaseProvider
from core.providers.kinopoisk import kinopoisk
from core.providers.rutube import RuTubeProvider
from core.providers.web import WebSearchProvider
from core.vpn import vpn_manager

log = logging.getLogger(__name__)


class FilmProvider(BaseProvider):
    """Фильмы и сериалы: RuTube + запасной веб-поиск + метаданные Кинопоиска."""

    name = "rutube"
    content_type = "film"
    requires_vpn = False

    def __init__(self, vpn=None):
        self.vpn = vpn or vpn_manager
        self.rutube = RuTubeProvider(vpn=self.vpn)
        self.web = WebSearchProvider(vpn=self.vpn)
        self.kinopoisk = kinopoisk
        #: Последнее разобранное намерение — UI показывает его пользователю.
        self.last_intent: Optional[SearchIntent] = None

    # ================================================================== #
    #  Поиск
    # ================================================================== #
    def search(self, query: str, limit: int = 20) -> List[MediaItem]:
        """Умный поиск фильма или сериала.

        Порядок: разбор запроса -> RuTube -> (если пусто) интернет ->
        обогащение метаданными Кинопоиска.
        """
        query = (query or "").strip()
        if not query:
            return []

        intent = ai_search.parse(query)
        self.last_intent = intent

        items = self._search_rutube(intent, limit)

        # Ничего на RuTube — идём искать по интернету, как требует ТЗ.
        if not items:
            log.info("На RuTube ничего не найдено, ищем по интернету: %s", query)
            items = self._search_web(intent, limit)

        # Фильтры из намерения применяем мягко: если после них пусто,
        # лучше показать что-то менее точное, чем пустой экран.
        if intent.has_filters:
            filtered = [item for item in items if intent.matches(item)]
            if filtered:
                items = filtered

        return self._enrich(items[:limit])

    def _search_rutube(self, intent: SearchIntent, limit: int) -> List[MediaItem]:
        """Поиск по всем вариантам запроса из намерения, без дублей."""
        collected: List[MediaItem] = []
        seen: set[str] = set()

        for query in intent.queries or []:
            for item in self.rutube.search(query, limit=limit):
                if item.id in seen:
                    continue
                seen.add(item.id)
                collected.append(item)
            # Первый запрос — самый точный; если он уже дал достаточно, хватит.
            if len(collected) >= limit:
                break
        return collected

    def _search_web(self, intent: SearchIntent, limit: int) -> List[MediaItem]:
        """Запасной поиск по интернету — только по основному запросу.

        Он медленный (каждую ссылку проверяем через yt-dlp), поэтому
        перебирать все варианты запроса нет смысла.
        """
        primary = intent.queries[0] if intent.queries else ""
        if not primary:
            return []
        return self.web.search(primary, limit=min(limit, 10))

    # ================================================================== #
    #  Лента
    # ================================================================== #
    def recommendations(self, queries: List[str], limit: int = 24) -> List[MediaItem]:
        """Персональная лента раздела.

        Если у Кинопоиска есть ключ, лента строится из актуальных новинок
        с высоким рейтингом; иначе — из трендов и интересов RuTube.
        """
        items: List[MediaItem] = []

        if self.kinopoisk.enabled:
            items = self.kinopoisk.popular(limit=limit)

        if not items:
            items = self.rutube.recommendations(queries, limit=limit)
            items = self._enrich(items)

        return items[:limit]

    def trending(self, limit: int = 24) -> List[MediaItem]:
        if self.kinopoisk.enabled:
            popular = self.kinopoisk.popular(limit=limit)
            if popular:
                return popular
        return self._enrich(self.rutube.trending(limit))

    # ================================================================== #
    #  Воспроизведение
    # ================================================================== #
    def get_item(self, video_id_or_url: str) -> Optional[MediaItem]:
        """Получить элемент для просмотра.

        Карточка с Кинопоиска не воспроизводится напрямую — по её названию
        сначала ищется реальное видео на RuTube или в интернете.
        """
        value = (video_id_or_url or "").strip()

        if value.startswith("kp") and value[2:].isdigit():
            return self._resolve_kinopoisk(value)

        if "kinopoisk.ru" in value:
            return self._resolve_kinopoisk(value)

        if "rutube.ru" in value or self.rutube.extract_video_id(value):
            return self.rutube.get_item(value)

        # Ссылка со стороннего сайта.
        if value.startswith(("http://", "https://")):
            return self.web.get_item(value)

        return self.rutube.get_item(value)

    def _resolve_kinopoisk(self, reference: str) -> Optional[MediaItem]:
        """Найти, где реально посмотреть фильм, известный по Кинопоиску."""
        title = None
        for item in self.kinopoisk.search(reference, limit=1):
            title = item.title
        if not title:
            log.warning("Не удалось определить название для %s", reference)
            return None

        candidates = self.rutube.search(title, limit=5) or self.web.search(title, limit=3)
        if not candidates:
            return None
        return self.get_item(candidates[0].url)

    def get_stream_url(self, video_id_or_url: str, quality: str = "720p") -> Optional[str]:
        item = self.get_item(video_id_or_url)
        if item and item.stream_url:
            return item.stream_url
        if item and item.platform == "rutube":
            return self.rutube.get_stream_url(item.url, quality)
        return None

    def related(self, video_id_or_url: str, limit: int = 12) -> List[MediaItem]:
        try:
            return self._enrich(self.rutube.related(video_id_or_url, limit))
        except Exception:
            return []

    def is_available(self) -> bool:
        return self.rutube.is_available()

    # ================================================================== #
    #  Метаданные
    # ================================================================== #
    def _enrich(self, items: List[MediaItem]) -> List[MediaItem]:
        """Дополнить карточки рейтингом и постером с Кинопоиска.

        Запросы идут параллельно: последовательно это заняло бы секунды
        на каждую карточку.
        """
        if not items or not self.kinopoisk.enabled:
            return items

        try:
            with ThreadPoolExecutor(max_workers=4) as pool:
                return list(pool.map(self._enrich_one, items))
        except Exception:
            log.debug("Обогащение метаданными не выполнено", exc_info=True)
            return items

    def _enrich_one(self, item: MediaItem) -> MediaItem:
        try:
            return self.kinopoisk.enrich(item)
        except Exception:
            return item
