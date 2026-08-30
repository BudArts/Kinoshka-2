"""Метаданные фильмов и сериалов с Кинопоиска.

Официальное API Кинопоиска платное и требует ключ, поэтому используется
неофициальный публичный API kinopoisk.dev с бесплатным тиром. Ключ задаётся
в настройках; без ключа модуль работает в «тихом» режиме и просто ничего не
возвращает — раздел фильмов при этом остаётся рабочим, но без рейтингов
и постеров.

Модуль занимается только метаданными: смотреть кино с Кинопоиска нельзя,
воспроизведение остаётся за RuTube и веб-поиском.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

import requests

from config import settings
from core.media import MediaItem

log = logging.getLogger(__name__)

API_BASE = "https://api.kinopoisk.dev/v1.4"
TIMEOUT = 15


class KinopoiskClient:
    """Поиск и актуальные подборки Кинопоиска."""

    def __init__(self):
        self._session = requests.Session()

    # ------------------------------------------------------------------ #
    @property
    def api_key(self) -> str:
        return (settings.get("kinopoisk_api_key") or "").strip()

    @property
    def enabled(self) -> bool:
        """Без ключа модуль отключён — это не ошибка, а штатный режим."""
        return bool(self.api_key)

    def _get(self, path: str, params: Dict) -> Optional[Dict]:
        if not self.enabled:
            return None
        try:
            response = self._session.get(
                f"{API_BASE}/{path}",
                params=params,
                headers={"X-API-KEY": self.api_key, "accept": "application/json"},
                timeout=TIMEOUT,
            )
            if response.status_code == 403:
                log.warning("Кинопоиск: ключ недействителен или исчерпан лимит")
                return None
            if response.status_code != 200:
                log.warning("Кинопоиск ответил %s", response.status_code)
                return None
            return response.json()
        except requests.RequestException as exc:
            log.warning("Сетевая ошибка Кинопоиска: %s", exc)
            return None
        except ValueError:
            return None

    # ------------------------------------------------------------------ #
    #  Публичный интерфейс
    # ------------------------------------------------------------------ #
    def search(self, query: str, limit: int = 20) -> List[MediaItem]:
        """Поиск по названию."""
        data = self._get(
            "movie/search", {"query": query, "limit": min(limit, 50), "page": 1}
        )
        return self._parse_docs(data)

    def popular(self, limit: int = 24, content_type: Optional[str] = None) -> List[MediaItem]:
        """Актуальные новинки с высоким рейтингом."""
        params: Dict = {
            "limit": min(limit, 50),
            "page": 1,
            "sortField": "votes.kp",
            "sortType": "-1",
            "rating.kp": "6-10",
            "year": f"{self._current_year() - 2}-{self._current_year()}",
        }
        if content_type == "series":
            params["type"] = "tv-series"
        elif content_type == "film":
            params["type"] = "movie"

        return self._parse_docs(self._get("movie", params))

    def enrich(self, item: MediaItem) -> MediaItem:
        """Дополнить элемент рейтингом, годом и жанрами с Кинопоиска.

        Название с видеохостингов часто «грязное» («Фильм 2023 HD 1080»),
        поэтому перед поиском его чистим.
        """
        if not self.enabled or item.rating:
            return item

        matches = self.search(self._clean_title(item.title), limit=1)
        if not matches:
            return item

        match = matches[0]
        item.rating = item.rating or match.rating
        item.year = item.year or match.year
        item.description = item.description or match.description
        # Постер Кинопоиска почти всегда лучше превью с видеохостинга.
        item.thumbnail = match.thumbnail or item.thumbnail
        for genre in match.categories:
            if genre not in item.categories:
                item.categories.append(genre)
        item.extra["kinopoisk_id"] = match.id
        return item

    # ------------------------------------------------------------------ #
    #  Разбор
    # ------------------------------------------------------------------ #
    def _parse_docs(self, data: Optional[Dict]) -> List[MediaItem]:
        if not data:
            return []
        return [
            item
            for item in (self._parse_one(doc) for doc in data.get("docs") or [])
            if item is not None
        ]

    @staticmethod
    def _parse_one(doc: Dict) -> Optional[MediaItem]:
        """Запись Кинопоиска -> MediaItem.

        url ведёт на страницу Кинопоиска: смотреть оттуда нельзя, поэтому
        карточка используется как «заявка» — плеер ищет фильм на RuTube.
        """
        movie_id = doc.get("id")
        title = doc.get("name") or doc.get("alternativeName") or doc.get("enName")
        if not movie_id or not title:
            return None

        poster = (doc.get("poster") or {}).get("previewUrl") or (
            doc.get("poster") or {}
        ).get("url")

        rating_raw = doc.get("rating") or {}
        rating = rating_raw.get("kp") or rating_raw.get("imdb")

        genres = [g.get("name") for g in (doc.get("genres") or []) if g.get("name")]

        is_series = doc.get("isSeries") or doc.get("type") == "tv-series"

        duration_minutes = doc.get("movieLength") or doc.get("seriesLength")

        return MediaItem(
            id=f"kp{movie_id}",
            title=title,
            url=f"https://www.kinopoisk.ru/film/{movie_id}/",
            platform="kinopoisk",
            content_type="series" if is_series else "film",
            thumbnail=poster,
            description=doc.get("description") or doc.get("shortDescription"),
            duration=int(duration_minutes) * 60 if duration_minutes else None,
            year=doc.get("year"),
            rating=float(rating) if rating else None,
            categories=genres,
            extra={
                "kinopoisk_id": movie_id,
                "countries": [
                    c.get("name") for c in (doc.get("countries") or []) if c.get("name")
                ],
                # Ключевой признак: смотреть надо искать на другом источнике.
                "needs_lookup": True,
            },
        )

    @staticmethod
    def _clean_title(title: str) -> str:
        """Убрать из названия технический мусор перед поиском."""
        import re

        cleaned = re.sub(
            r"\b(hd|full\s*hd|1080p?|720p?|4k|bdrip|webrip|смотреть|онлайн|"
            r"бесплатно|в\s+хорошем\s+качестве|сезон|серия)\b",
            " ",
            title,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"[\(\)\[\]{}«»\"]+", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" -—|.")
        return cleaned or title

    @staticmethod
    def _current_year() -> int:
        from datetime import datetime

        return datetime.now().year


#: Общий экземпляр.
kinopoisk = KinopoiskClient()
