"""Провайдер RuTube — основной источник фильмов и сериалов.

Важное отличие от YouTube: у yt-dlp есть экстракторы воспроизведения RuTube
(rutube, rutube:movie, rutube:playlist), но **нет экстрактора поиска**.
Поэтому поиск идёт через публичный JSON API самого RuTube, а получение
видеопотока — через yt-dlp.

VPN для RuTube не нужен: в России он открывается напрямую.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, ExtractorError

from config import QUALITY_TO_HEIGHT, settings
from core.media import MediaItem
from core.providers.base import BaseProvider
from core.vpn import vpn_manager

log = logging.getLogger(__name__)

SEARCH_API = "https://rutube.ru/api/search/video/"
TRENDS_API = "https://rutube.ru/api/video/trends/"
VIDEO_API = "https://rutube.ru/api/video/{video_id}/"

#: Заголовки обычного браузера — без них API иногда отвечает 403.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "ru-RU,ru;q=0.9",
}

#: Слова в названии, по которым отличаем сериал от полного метра.
SERIES_MARKERS = ("сезон", "серия", "серии", "эпизод", "season", "episode")


class RuTubeProvider(BaseProvider):
    """Поиск, рекомендации и воспроизведение фильмов и сериалов с RuTube."""

    name = "rutube"
    content_type = "film"
    requires_vpn = False

    def __init__(self, vpn=None):
        self.vpn = vpn or vpn_manager
        self._session = requests.Session()
        self._session.headers.update(HEADERS)

    # ------------------------------------------------------------------ #
    #  HTTP
    # ------------------------------------------------------------------ #
    def _get_json(self, url: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """GET с таймаутом и мягкой обработкой ошибок сети."""
        try:
            response = self._session.get(
                url,
                params=params,
                timeout=settings.get("request_timeout", 20),
                proxies=self.vpn.requests_proxies(),
            )
            if response.status_code != 200:
                log.warning("RuTube ответил %s на %s", response.status_code, url)
                return None
            return response.json()
        except requests.RequestException as exc:
            log.warning("Сетевая ошибка RuTube (%s): %s", url, exc)
            return None
        except ValueError as exc:
            log.warning("RuTube вернул не JSON (%s): %s", url, exc)
            return None

    # ------------------------------------------------------------------ #
    #  Публичный интерфейс
    # ------------------------------------------------------------------ #
    def search(self, query: str, limit: int = 20) -> List[MediaItem]:
        """Поиск по каталогу RuTube."""
        query = (query or "").strip()
        if not query:
            return []

        if query.startswith(("http://", "https://")):
            item = self.get_item(query)
            return [item] if item else []

        data = self._get_json(
            SEARCH_API, {"query": query, "page": 1, "limit": min(limit, 50)}
        )
        if not data:
            return []
        return self._parse_results(data.get("results") or [], limit)

    def recommendations(self, queries: List[str], limit: int = 24) -> List[MediaItem]:
        """Лента: по интересам пользователя, а для новичка — тренды RuTube."""
        if not queries:
            return self.trending(limit)

        per_query = max(2, limit // max(len(queries), 1))
        collected: List[MediaItem] = []
        seen: set[str] = set()

        for query in queries:
            for item in self.search(query, limit=per_query):
                if item.id in seen:
                    continue
                seen.add(item.id)
                if query not in item.categories:
                    item.categories.append(query)
                collected.append(item)
            if len(collected) >= limit:
                break

        return collected[:limit] if collected else self.trending(limit)

    def trending(self, limit: int = 24) -> List[MediaItem]:
        """Актуальное на RuTube — стартовая лента раздела."""
        data = self._get_json(TRENDS_API, {"page": 1, "limit": min(limit, 50)})
        if not data:
            return []
        return self._parse_results(data.get("results") or [], limit)

    def get_item(self, video_id_or_url: str) -> Optional[MediaItem]:
        """Метаданные одного видео + прямая ссылка на поток."""
        video_id = self.extract_video_id(video_id_or_url)

        # Сначала пробуем лёгкий JSON API — он быстрее yt-dlp.
        if video_id:
            data = self._get_json(VIDEO_API.format(video_id=video_id))
            if data:
                item = self._parse_one(data)
                if item:
                    item.stream_url = self.get_stream_url(item.url)
                    return item

        # Не вышло — полный разбор через yt-dlp.
        return self._item_via_ytdlp(self._to_url(video_id_or_url))

    def get_stream_url(self, video_id_or_url: str, quality: str = "720p") -> Optional[str]:
        """Прямая ссылка на поток (RuTube отдаёт HLS)."""
        info = self._extract(self._to_url(video_id_or_url), quality)
        return self._pick_stream(info) if info else None

    def related(self, video_id_or_url: str, limit: int = 12) -> List[MediaItem]:
        """Похожее: ищем по названию исходного видео."""
        item = self.get_item(video_id_or_url)
        if not item:
            return []
        query = " ".join(item.title.split()[:5])
        return [r for r in self.search(query, limit=limit + 1) if r.id != item.id][:limit]

    def is_available(self) -> bool:
        return self._get_json(TRENDS_API, {"limit": 1}) is not None

    # ------------------------------------------------------------------ #
    #  yt-dlp
    # ------------------------------------------------------------------ #
    def _extract(self, url: str, quality: str = "720p") -> Optional[Dict[str, Any]]:
        height = QUALITY_TO_HEIGHT.get(quality)
        opts: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "skip_download": True,
            "socket_timeout": settings.get("request_timeout", 20),
            "retries": 2,
        }
        if height:
            opts["format"] = f"best[height<={height}]/best"
        proxy = self.vpn.proxy_url()
        if proxy:
            opts["proxy"] = proxy

        try:
            with YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)
        except (DownloadError, ExtractorError) as exc:
            log.warning("yt-dlp не смог обработать RuTube %s: %s", url, exc)
            return None
        except Exception as exc:
            log.exception("Ошибка RuTube: %s", exc)
            return None

    def _item_via_ytdlp(self, url: str) -> Optional[MediaItem]:
        info = self._extract(url)
        if not info:
            return None
        return MediaItem(
            id=info.get("id") or url,
            title=info.get("title") or "Без названия",
            url=info.get("webpage_url") or url,
            platform=self.name,
            content_type=self._guess_type(info.get("title") or ""),
            author=info.get("uploader") or info.get("channel"),
            thumbnail=info.get("thumbnail"),
            description=info.get("description"),
            duration=int(info["duration"]) if info.get("duration") else None,
            view_count=info.get("view_count"),
            stream_url=self._pick_stream(info),
        )

    @staticmethod
    def _pick_stream(info: Dict[str, Any]) -> Optional[str]:
        """RuTube отдаёт HLS-манифест — он играется напрямую."""
        if info.get("url"):
            return info["url"]
        formats = [f for f in (info.get("formats") or []) if f.get("url")]
        if not formats:
            return None
        # Предпочитаем HLS: один манифест вместо раздельных дорожек.
        hls = [f for f in formats if f.get("protocol", "").startswith("m3u8")]
        pool = hls or formats
        return max(pool, key=lambda f: f.get("height") or f.get("tbr") or 0).get("url")

    # ------------------------------------------------------------------ #
    #  Разбор ответов API
    # ------------------------------------------------------------------ #
    def _parse_results(self, results: List[Dict], limit: int) -> List[MediaItem]:
        items: List[MediaItem] = []
        for raw in results:
            item = self._parse_one(raw)
            if item:
                items.append(item)
            if len(items) >= limit:
                break
        return items

    def _parse_one(self, raw: Dict) -> Optional[MediaItem]:
        """Запись из API RuTube -> MediaItem."""
        if not raw:
            return None
        video_id = raw.get("id")
        title = raw.get("title")
        if not video_id or not title:
            return None

        author = None
        author_raw = raw.get("author")
        if isinstance(author_raw, dict):
            author = author_raw.get("name")

        categories: List[str] = []
        category_raw = raw.get("category")
        if isinstance(category_raw, dict) and category_raw.get("name"):
            categories.append(category_raw["name"])

        return MediaItem(
            id=str(video_id),
            title=title,
            url=raw.get("video_url") or self._to_url(str(video_id)),
            platform=self.name,
            content_type=self._guess_type(title, categories),
            author=author,
            thumbnail=raw.get("thumbnail_url"),
            description=raw.get("description"),
            duration=int(raw["duration"]) if raw.get("duration") else None,
            view_count=raw.get("hits"),
            year=self._parse_year(raw.get("created_ts")),
            categories=categories,
            extra={"is_adult": raw.get("is_adult", False)},
        )

    @staticmethod
    def _parse_year(timestamp: Optional[str]) -> Optional[int]:
        """Дата публикации приходит как ISO-строка."""
        if not timestamp:
            return None
        try:
            return datetime.fromisoformat(str(timestamp).replace("Z", "+00:00")).year
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _guess_type(title: str, categories: Optional[List[str]] = None) -> str:
        """Сериал или фильм — по маркерам в названии и категории.

        Точного признака у API нет, поэтому смотрим на «сезон»/«серия».
        """
        haystack = f"{title} {' '.join(categories or [])}".lower()
        if any(marker in haystack for marker in SERIES_MARKERS):
            return "series"
        return "film"

    # ------------------------------------------------------------------ #
    @staticmethod
    def _to_url(video_id_or_url: str) -> str:
        value = (video_id_or_url or "").strip()
        if value.startswith(("http://", "https://")):
            return value
        return f"https://rutube.ru/video/{value}/"

    @staticmethod
    def extract_video_id(url: str) -> Optional[str]:
        """Достать 32-символьный hex-id из ссылки RuTube."""
        import re

        value = (url or "").strip()
        if re.fullmatch(r"[0-9a-f]{32}", value):
            return value
        match = re.search(r"rutube\.ru/(?:video|play/embed)/([0-9a-f]{32})", value)
        return match.group(1) if match else None
