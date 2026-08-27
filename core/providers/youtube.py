"""Провайдер YouTube на базе yt-dlp.

Официальный Data API требует ключ и квоты, поэтому используется yt-dlp:
он же нужен для скачивания, так что зависимость одна на всё.

Особенности реализации:
  * все сетевые вызовы проходят через VpnManager.ensure_connected(), т.к. в
    России YouTube без туннеля недоступен;
  * поиск и списки тянутся в «плоском» режиме (extract_flat) — это на порядок
    быстрее, полные метаданные догружаются только для открытого видео;
  * при сетевой ошибке делается одна попытка со сменой VPN-конфигурации.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, ExtractorError

from config import QUALITY_TO_HEIGHT, settings
from core.media import MediaItem
from core.providers.base import BaseProvider
from core.vpn import vpn_manager

log = logging.getLogger(__name__)

#: Ленты, из которых берётся «холодный старт» рекомендаций.
TRENDING_URL = "https://www.youtube.com/feed/trending"

_YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


class YouTubeProvider(BaseProvider):
    """Поиск, рекомендации и метаданные YouTube."""

    name = "youtube"
    content_type = "video"
    requires_vpn = True

    def __init__(self, vpn=None):
        self.vpn = vpn or vpn_manager

    # ------------------------------------------------------------------ #
    #  Настройки yt-dlp
    # ------------------------------------------------------------------ #
    def _base_opts(self, **overrides: Any) -> Dict[str, Any]:
        opts: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "skip_download": True,
            "socket_timeout": settings.get("request_timeout", 20),
            "extractor_args": {
                # web-клиент чаще всего отдаёт метаданные без проверки бота
                "youtube": {"player_client": ["web", "android"]},
            },
            "retries": 2,
        }
        proxy = self.vpn.proxy_url()
        if proxy:
            opts["proxy"] = proxy
        opts.update(overrides)
        return opts

    def _ensure_network(self) -> None:
        """Поднять VPN, если он включён в настройках."""
        if self.requires_vpn:
            self.vpn.ensure_connected()

    def _extract(self, target: str, opts: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Обёртка над yt-dlp с одной повторной попыткой через другой туннель."""
        self._ensure_network()
        try:
            with YoutubeDL(opts) as ydl:
                return ydl.extract_info(target, download=False)
        except (DownloadError, ExtractorError) as exc:
            log.warning("yt-dlp не смог обработать %s: %s", target, exc)
            # Возможно, конкретный выходной узел заблокирован — пробуем другой.
            if settings.get("vpn_enabled") and self.vpn.rotate():
                try:
                    with YoutubeDL(opts) as ydl:
                        return ydl.extract_info(target, download=False)
                except Exception as retry_exc:
                    log.warning("Повтор после смены VPN не помог: %s", retry_exc)
            return None
        except Exception as exc:  # неожиданные ошибки не должны ронять UI
            log.exception("Ошибка обращения к YouTube: %s", exc)
            return None

    # ------------------------------------------------------------------ #
    #  Публичный интерфейс
    # ------------------------------------------------------------------ #
    def search(self, query: str, limit: int = 20) -> List[MediaItem]:
        """Поиск видео. Пустой результат означает недоступность источника."""
        query = (query or "").strip()
        if not query:
            return []

        # Если пользователь вставил ссылку — сразу отдаём это видео.
        if self._looks_like_url(query):
            item = self.get_item(query)
            return [item] if item else []

        info = self._extract(
            f"ytsearch{int(limit)}:{query}",
            self._base_opts(extract_flat=True),
        )
        return self._entries_to_items(info)

    def recommendations(self, queries: List[str], limit: int = 24) -> List[MediaItem]:
        """Лента рекомендаций.

        Если интересы уже накоплены — собираем ленту по ним; если пользователь
        новый, показываем тренды, чтобы главная не была пустой.
        """
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
                # Запрос-интерес становится категорией — так рекомендации
                # сами себя размечают для движка интересов.
                if query not in item.categories:
                    item.categories.append(query)
                collected.append(item)
            if len(collected) >= limit:
                break

        if not collected:
            return self.trending(limit)
        return collected[:limit]

    def trending(self, limit: int = 24) -> List[MediaItem]:
        """Тренды YouTube — стартовая лента для нового профиля."""
        info = self._extract(
            TRENDING_URL,
            self._base_opts(extract_flat=True, playlistend=limit, noplaylist=False),
        )
        return self._entries_to_items(info)[:limit]

    def get_item(self, video_id_or_url: str) -> Optional[MediaItem]:
        """Полные метаданные одного видео (включая прямую ссылку на поток)."""
        url = self._to_url(video_id_or_url)
        info = self._extract(url, self._base_opts())
        if not info:
            return None
        return self._info_to_item(info, full=True)

    def get_stream_url(self, video_id_or_url: str, quality: str = "720p") -> Optional[str]:
        """Прямая ссылка на поток нужного качества (video+audio одним файлом)."""
        url = self._to_url(video_id_or_url)
        info = self._extract(
            url, self._base_opts(format=self._format_selector(quality))
        )
        if not info:
            return None
        return self._pick_stream(info)

    def related(self, video_id_or_url: str, limit: int = 12) -> List[MediaItem]:
        """Похожие видео.

        yt-dlp не отдаёт блок related напрямую, поэтому используем название
        и автора исходного видео как поисковый запрос — практически это даёт
        близкую выдачу.
        """
        item = self.get_item(video_id_or_url)
        if not item:
            return []
        query = " ".join(filter(None, [item.author, *item.title.split()[:4]]))
        return [r for r in self.search(query, limit=limit + 1) if r.id != item.id][:limit]

    def is_available(self) -> bool:
        return self.vpn.check_connection()

    # ------------------------------------------------------------------ #
    #  Преобразование ответов yt-dlp
    # ------------------------------------------------------------------ #
    def _entries_to_items(self, info: Optional[Dict[str, Any]]) -> List[MediaItem]:
        if not info:
            return []
        entries = info.get("entries") or []
        items: List[MediaItem] = []
        for entry in entries:
            if not entry:
                continue
            # У вложенных плейлистов (например, на странице трендов)
            # записи лежат ещё на уровень глубже.
            if entry.get("_type") == "playlist" and entry.get("entries"):
                for nested in entry["entries"]:
                    item = self._info_to_item(nested)
                    if item:
                        items.append(item)
                continue
            item = self._info_to_item(entry)
            if item:
                items.append(item)
        return items

    def _info_to_item(
        self, info: Optional[Dict[str, Any]], full: bool = False
    ) -> Optional[MediaItem]:
        """Словарь yt-dlp -> MediaItem."""
        if not info:
            return None
        video_id = info.get("id")
        title = info.get("title")
        if not video_id or not title or title in ("[Private video]", "[Deleted video]"):
            return None

        item = MediaItem(
            id=video_id,
            title=title,
            url=info.get("webpage_url") or self._to_url(video_id),
            platform=self.name,
            content_type="video",
            author=info.get("uploader") or info.get("channel"),
            thumbnail=self._pick_thumbnail(info),
            description=(info.get("description") or None) if full else None,
            duration=int(info["duration"]) if info.get("duration") else None,
            view_count=info.get("view_count"),
            upload_date=info.get("upload_date"),
            categories=list(info.get("categories") or []),
            tags=list(info.get("tags") or [])[:15],
        )
        if full:
            item.stream_url = self._pick_stream(info)
            item.extra["channel_id"] = info.get("channel_id")
            item.extra["like_count"] = info.get("like_count")
        return item

    @staticmethod
    def _pick_thumbnail(info: Dict[str, Any]) -> Optional[str]:
        """Наиболее подходящая превьюшка (не гигантская, но и не мыло)."""
        if info.get("thumbnail"):
            return info["thumbnail"]
        thumbnails = info.get("thumbnails") or []
        if not thumbnails:
            video_id = info.get("id")
            return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" if video_id else None
        # Берём самую большую из тех, что не шире 640 px.
        suitable = [t for t in thumbnails if (t.get("width") or 0) <= 640]
        best = max(suitable or thumbnails, key=lambda t: t.get("width") or 0)
        return best.get("url")

    @staticmethod
    def _pick_stream(info: Dict[str, Any]) -> Optional[str]:
        """Ссылка на поток: сначала готовый url, иначе лучший совместимый формат."""
        if info.get("url"):
            return info["url"]

        formats = info.get("formats") or []
        # Приоритет — прогрессивные mp4 (видео+звук в одном файле), их умеет
        # проиграть любой встроенный плеер без склейки потоков.
        progressive = [
            f
            for f in formats
            if f.get("vcodec") not in (None, "none")
            and f.get("acodec") not in (None, "none")
            and f.get("url")
        ]
        if progressive:
            best = max(progressive, key=lambda f: f.get("height") or 0)
            return best.get("url")
        with_url = [f for f in formats if f.get("url")]
        if with_url:
            return max(with_url, key=lambda f: f.get("tbr") or 0).get("url")
        return None

    @staticmethod
    def _format_selector(quality: str) -> str:
        """Строка выбора формата для yt-dlp по человеческому названию качества."""
        height = QUALITY_TO_HEIGHT.get(quality)
        if height is None:
            return "best[ext=mp4]/best"
        return (
            f"best[height<={height}][ext=mp4]/"
            f"best[height<={height}]/"
            f"bestvideo[height<={height}]+bestaudio/best"
        )

    # ------------------------------------------------------------------ #
    @staticmethod
    def _looks_like_url(value: str) -> bool:
        return value.startswith(("http://", "https://", "www."))

    @staticmethod
    def _to_url(video_id_or_url: str) -> str:
        """Принять и ID, и полную ссылку."""
        value = (video_id_or_url or "").strip()
        if YouTubeProvider._looks_like_url(value):
            return value if value.startswith("http") else f"https://{value}"
        if _YOUTUBE_ID_RE.match(value):
            return f"https://www.youtube.com/watch?v={value}"
        return value

    @staticmethod
    def extract_video_id(url: str) -> Optional[str]:
        """Достать ID видео из любой формы ссылки YouTube."""
        if _YOUTUBE_ID_RE.match(url or ""):
            return url
        patterns = (
            r"(?:v=|/v/|youtu\.be/|/embed/|/shorts/|/live/)([A-Za-z0-9_-]{11})",
        )
        for pattern in patterns:
            match = re.search(pattern, url or "")
            if match:
                return match.group(1)
        return None
