"""Музыкальный провайдер — теперь Яндекс Музыка как основной источник.

Порядок:
  1. Яндекс Музыка (работает без VPN в России, квадратные обложки)
  2. YouTube Music (fallback, требует VPN)
  3. Обычный YouTube с фильтром «только музыка» (последний запасной)
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

from core.media import MediaItem
from core.providers.youtube import YouTubeProvider

log = logging.getLogger(__name__)

SONGS_FILTER = "EgWKAQIIAWoKEAoQAxAEEAkQBQ%3D%3D"
NON_MUSIC_MARKERS = (
    "обзор", "реакция", "reaction", "разбор", "интервью", "подкаст",
    "трейлер", "прохождение", "стрим", "туториал", "как играть",
    "lyrics video review", "караоке минус",
)
MAX_TRACK_SECONDS = 15 * 60


class MusicProvider(YouTubeProvider):
    """Музыка: Яндекс Музыка -> YouTube Music -> YouTube."""

    name = "yandex_music"
    content_type = "music"
    requires_vpn = False

    def __init__(self, vpn=None):
        super().__init__(vpn=vpn)
        # Лениво создаём Яндекс-провайдер, чтобы не тянуть зависимость если не нужна
        self._yandex = None

    def _get_yandex(self):
        if self._yandex is None:
            try:
                from core.providers.yandex_music import YandexMusicProvider

                self._yandex = YandexMusicProvider(vpn=self.vpn)
            except Exception as exc:
                log.debug("Яндекс Музыка провайдер не создался: %s", exc)
                self._yandex = False
        return self._yandex if self._yandex is not False else None

    def search(self, query: str, limit: int = 20) -> List[MediaItem]:
        query = (query or "").strip()
        if not query:
            return []

        if self._looks_like_url(query):
            # Пробуем все источники
            yandex = self._get_yandex()
            if yandex:
                item = yandex.get_item(query)
                if item:
                    return [item]
            item = self.get_item(query)
            return [item] if item else []

        # 1. Яндекс Музыка
        yandex = self._get_yandex()
        if yandex:
            try:
                items = yandex.search(query, limit=limit)
                if items:
                    log.info("Музыка найдена в Яндекс Музыке: %s -> %s", query, len(items))
                    return items
            except Exception as exc:
                log.debug("Яндекс Музыка поиск упал: %s", exc)

        # 2. YouTube Music
        try:
            url = f"https://music.youtube.com/search?q={quote_plus(query)}&sp={SONGS_FILTER}"
            info = self._extract(url, self._base_opts(extract_flat=True, playlistend=limit * 2, noplaylist=False))
            items = self._entries_to_items(info)
            if items:
                return items[:limit]
        except Exception as exc:
            log.debug("YouTube Music поиск упал: %s", exc)

        # 3. Обычный YouTube
        try:
            info = self._extract(f"ytsearch{int(limit * 2)}:{query} аудио трек", self._base_opts(extract_flat=True))
            items = [i for i in self._entries_to_items(info) if self._looks_like_music(i)]
            return items[:limit]
        except Exception:
            return []

    def recommendations(self, queries: List[str], limit: int = 24) -> List[MediaItem]:
        # Сначала пробуем Яндекс
        yandex = self._get_yandex()
        if yandex:
            try:
                items = yandex.recommendations(queries, limit=limit)
                if items:
                    return items
            except Exception as exc:
                log.debug("Яндекс рекомендации упали: %s", exc)

        # Fallback — старый параллельный поиск по YouTube Music
        if not queries:
            return self.search("популярная музыка", limit=limit)

        queries = queries[:4]
        per_query = max(2, limit // max(len(queries), 1))
        collected: List[MediaItem] = []
        seen: set[str] = set()

        import concurrent.futures

        def search_one(q: str):
            try:
                return q, self.search(q, limit=per_query)
            except Exception:
                return q, []

        with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(queries))) as ex:
            futures = [ex.submit(search_one, q) for q in queries]
            for fut in concurrent.futures.as_completed(futures):
                try:
                    q, items = fut.result()
                except Exception:
                    continue
                for it in items:
                    if it.id in seen:
                        continue
                    seen.add(it.id)
                    if q not in it.categories:
                        it.categories.append(q)
                    collected.append(it)
                    if len(collected) >= limit:
                        break
                if len(collected) >= limit:
                    break

        if not collected:
            return self.search("популярная музыка", limit=limit)
        return collected[:limit]

    def get_item(self, video_id_or_url: str) -> Optional[MediaItem]:
        # Сначала Яндекс
        yandex = self._get_yandex()
        if yandex:
            try:
                item = yandex.get_item(video_id_or_url)
                if item:
                    return item
            except Exception:
                pass
        return super().get_item(video_id_or_url)

    def get_stream_url(self, video_id_or_url: str, quality: str = "mp3") -> Optional[str]:
        yandex = self._get_yandex()
        if yandex:
            try:
                url = yandex.get_stream_url(video_id_or_url, quality=quality)
                if url:
                    return url
            except Exception:
                pass
        return super().get_stream_url(video_id_or_url, quality=quality)

    @staticmethod
    def _looks_like_music(item: MediaItem) -> bool:
        if item.duration and item.duration > MAX_TRACK_SECONDS:
            return False
        title = (item.title or "").lower()
        return not any(marker in title for marker in NON_MUSIC_MARKERS)

    def _info_to_item(self, info: Optional[Dict[str, Any]], full: bool = False) -> Optional[MediaItem]:
        item = super()._info_to_item(info, full=full)
        if item is None:
            return None
        info = info or {}
        item.content_type = "music"
        artist = info.get("artist") or info.get("creator") or info.get("uploader")
        if artist:
            item.author = self._clean_artist(artist)
        album = info.get("album")
        if album:
            item.extra["album"] = album
        item.thumbnail = self._square_cover(item.thumbnail, item.id)
        item.extra["square_cover"] = True
        return item

    @staticmethod
    def _clean_artist(name: str) -> str:
        cleaned = re.sub(r"\s*-\s*Topic$", "", name or "").strip()
        return cleaned or name

    @staticmethod
    def _square_cover(url: Optional[str], video_id: str) -> Optional[str]:
        if not url:
            return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" if video_id else None
        if "googleusercontent.com" in url:
            return re.sub(r"=w\d+-h\d+", "=w400-h400", url)
        return url
