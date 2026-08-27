"""Музыкальный провайдер.

Источник — YouTube Music: у yt-dlp есть экстрактор `youtube:music:search_url`,
который ищет именно по музыкальному каталогу, а не по обычным видео. Это даёт
чистые треки с исполнителем и альбомом вместо клипов вперемешку с обзорами.

Как и обычный YouTube, требует VPN на территории России.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

from core.media import MediaItem
from core.providers.youtube import YouTubeProvider

log = logging.getLogger(__name__)

#: Поиск по каталогу YouTube Music (EgWKAQIIAWoKEAoQAxAEEAkQBQ== — фильтр «песни»).
MUSIC_SEARCH_URL = (
    "https://music.youtube.com/search?q={query}#songs"
)
#: Обычный поиск YouTube с музыкальным уточнением — надёжный запасной путь.
FALLBACK_TEMPLATE = "ytsearch{limit}:{query}音楽"


class MusicProvider(YouTubeProvider):
    """Поиск и воспроизведение музыки."""

    name = "youtube_music"
    content_type = "music"
    requires_vpn = True

    # ------------------------------------------------------------------ #
    def search(self, query: str, limit: int = 20) -> List[MediaItem]:
        """Поиск треков."""
        query = (query or "").strip()
        if not query:
            return []

        if self._looks_like_url(query):
            item = self.get_item(query)
            return [item] if item else []

        # Музыкальный поиск YouTube: ytsearch по music.youtube.com даёт
        # каталожные записи с корректным исполнителем.
        info = self._extract(
            f"https://music.youtube.com/search?q={quote_plus(query)}",
            self._base_opts(extract_flat=True, playlistend=limit, noplaylist=False),
        )
        items = self._entries_to_items(info)

        if not items:
            # Музыкальный домен мог не открыться — ищем по обычному YouTube.
            info = self._extract(
                f"ytsearch{int(limit)}:{query} песня аудио",
                self._base_opts(extract_flat=True),
            )
            items = self._entries_to_items(info)

        return items[:limit]

    def recommendations(self, queries: List[str], limit: int = 24) -> List[MediaItem]:
        """Лента музыки по интересам пользователя."""
        if not queries:
            return self.search("популярная музыка", limit=limit)

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

        if not collected:
            return self.search("популярная музыка", limit=limit)
        return collected[:limit]

    def related(self, video_id_or_url: str, limit: int = 12) -> List[MediaItem]:
        """Похожие треки — обычно это другие вещи того же исполнителя."""
        item = self.get_item(video_id_or_url)
        if not item:
            return []
        query = item.author or " ".join(item.title.split()[:4])
        return [r for r in self.search(query, limit=limit + 1) if r.id != item.id][:limit]

    # ------------------------------------------------------------------ #
    def _info_to_item(
        self, info: Optional[Dict[str, Any]], full: bool = False
    ) -> Optional[MediaItem]:
        """То же, что у YouTube, но тип контента — music, а автор чище."""
        item = super()._info_to_item(info, full=full)
        if item is None:
            return None

        item.content_type = "music"
        item.platform = "youtube"  # играется и качается как обычное видео YouTube

        # YouTube Music отдаёт исполнителя в artist/creator — он точнее,
        # чем название канала («Имя - Topic»).
        artist = (info or {}).get("artist") or (info or {}).get("creator")
        if artist:
            item.author = artist
        elif item.author and item.author.endswith(" - Topic"):
            item.author = item.author[: -len(" - Topic")]

        album = (info or {}).get("album")
        if album:
            item.extra["album"] = album

        return item
