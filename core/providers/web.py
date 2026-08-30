"""Запасной поиск видео по интернету.

Используется, когда фильма или сериала нет на RuTube. Логика такая:

1. ищем страницы по запросу через DuckDuckGo (html-версия, без API-ключа);
2. отбираем домены, которые умеет разбирать yt-dlp, либо страницы с
   видеоплеером;
3. проверяем ссылку через yt-dlp и превращаем в MediaItem.

Это принципиально «best effort»: сайты меняют вёрстку, часть ссылок окажется
нерабочей. Поэтому каждый шаг изолирован, а ошибки не всплывают в UI —
пользователь просто увидит меньше результатов.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional
from urllib.parse import parse_qs, quote_plus, urlparse

import requests
from bs4 import BeautifulSoup
from yt_dlp import YoutubeDL

from config import settings
from core.media import MediaItem
from core.providers.base import BaseProvider
from core.vpn import vpn_manager

log = logging.getLogger(__name__)

SEARCH_URL = "https://html.duckduckgo.com/html/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}

#: Домены-видеохостинги, которые yt-dlp разбирает надёжно.
TRUSTED_HOSTS = (
    "rutube.ru", "vk.com", "vkvideo.ru", "ok.ru", "my.mail.ru",
    "dzen.ru", "youtube.com", "youtu.be", "vimeo.com", "dailymotion.com",
)

#: Домены, которые точно не содержат видео, — не тратим на них время.
BLOCKED_HOSTS = (
    "wikipedia.org", "kinopoisk.ru", "imdb.com", "kino-teatr.ru",
    "facebook.com", "twitter.com", "x.com", "instagram.com",
    "pinterest.com", "market.yandex.ru", "ozon.ru", "wildberries.ru",
)


class WebSearchProvider(BaseProvider):
    """Поиск видео на сторонних сайтах, когда основной источник пуст."""

    name = "web"
    content_type = "film"
    requires_vpn = False

    def __init__(self, vpn=None):
        self.vpn = vpn or vpn_manager
        self._session = requests.Session()
        self._session.headers.update(HEADERS)

    # ------------------------------------------------------------------ #
    def search(self, query: str, limit: int = 10) -> List[MediaItem]:
        """Найти в интернете страницы с видео по запросу."""
        query = (query or "").strip()
        if not query:
            return []

        links = self._find_links(f"{query} смотреть онлайн", limit=limit * 3)
        if not links:
            return []

        items: List[MediaItem] = []
        seen: set[str] = set()

        for url in links:
            if len(items) >= limit:
                break
            item = self._probe(url)
            if item is None or item.id in seen:
                continue
            seen.add(item.id)
            items.append(item)

        return items

    def get_item(self, video_id_or_url: str) -> Optional[MediaItem]:
        return self._probe(video_id_or_url, full=True)

    def is_available(self) -> bool:
        return bool(self._find_links("test", limit=1))

    # ------------------------------------------------------------------ #
    #  Поисковая выдача
    # ------------------------------------------------------------------ #
    def _find_links(self, query: str, limit: int = 20) -> List[str]:
        """Ссылки из выдачи DuckDuckGo, отсортированные по надёжности домена."""
        try:
            response = self._session.post(
                SEARCH_URL,
                data={"q": query},
                timeout=settings.get("request_timeout", 20),
                proxies=self.vpn.requests_proxies(),
            )
            if response.status_code != 200:
                log.warning("Поисковик ответил %s", response.status_code)
                return []
        except requests.RequestException as exc:
            log.warning("Не удалось выполнить веб-поиск: %s", exc)
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        links: List[str] = []

        for anchor in soup.select("a.result__a, a.result__url"):
            href = anchor.get("href")
            url = self._clean_url(href)
            if url and self._is_useful(url) and url not in links:
                links.append(url)
            if len(links) >= limit:
                break

        # Проверенные видеохостинги — в начало очереди.
        links.sort(key=lambda u: 0 if self._is_trusted(u) else 1)
        return links

    @staticmethod
    def _clean_url(href: Optional[str]) -> Optional[str]:
        """DuckDuckGo заворачивает ссылки в редирект /l/?uddg=<url>."""
        if not href:
            return None
        if href.startswith("//"):
            href = f"https:{href}"
        parsed = urlparse(href)
        if parsed.path.startswith("/l/"):
            target = parse_qs(parsed.query).get("uddg")
            if target:
                return target[0]
            return None
        return href if href.startswith("http") else None

    @staticmethod
    def _is_trusted(url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        return any(host == h or host.endswith(f".{h}") for h in TRUSTED_HOSTS)

    @staticmethod
    def _is_useful(url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        if not host:
            return False
        return not any(host == h or host.endswith(f".{h}") for h in BLOCKED_HOSTS)

    # ------------------------------------------------------------------ #
    #  Проверка ссылки через yt-dlp
    # ------------------------------------------------------------------ #
    def _probe(self, url: str, full: bool = False) -> Optional[MediaItem]:
        """Проверить, что по ссылке действительно есть воспроизводимое видео."""
        opts: Dict = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "skip_download": True,
            # На чужих сайтах не ждём долго: битых ссылок много.
            "socket_timeout": 10,
            "retries": 0,
            "extract_flat": False,
        }
        proxy = self.vpn.proxy_url()
        if proxy:
            opts["proxy"] = proxy

        try:
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception:
            # Нормальная ситуация: на странице нет видео либо сайт не поддержан.
            log.debug("Ссылка не содержит видео: %s", url)
            return None

        if not info:
            return None
        # Плейлист вместо одного видео — берём первую запись.
        if info.get("_type") == "playlist":
            entries = [e for e in (info.get("entries") or []) if e]
            if not entries:
                return None
            info = entries[0]

        title = info.get("title")
        if not title:
            return None

        host = (urlparse(url).hostname or "web").replace("www.", "")

        return MediaItem(
            id=str(info.get("id") or url),
            title=title,
            url=info.get("webpage_url") or url,
            platform=self.name,
            content_type="film",
            author=info.get("uploader") or host,
            thumbnail=info.get("thumbnail"),
            description=info.get("description") if full else None,
            duration=int(info["duration"]) if info.get("duration") else None,
            view_count=info.get("view_count"),
            stream_url=self._pick_stream(info) if full else None,
            extra={"source_host": host},
        )

    @staticmethod
    def _pick_stream(info: Dict) -> Optional[str]:
        if info.get("url"):
            return info["url"]
        formats = [f for f in (info.get("formats") or []) if f.get("url")]
        if not formats:
            return None
        progressive = [
            f for f in formats
            if f.get("vcodec") not in (None, "none")
            and f.get("acodec") not in (None, "none")
        ]
        pool = progressive or formats
        return max(pool, key=lambda f: f.get("height") or f.get("tbr") or 0).get("url")
