"""Музыкальный провайдер.

Источник — каталог YouTube Music. Ключевой момент: используется фильтр
«Songs» (`sp=EgWKAQIIAWoKEAoQAxAEEAkQBQ%3D%3D`), поэтому в выдачу попадают
именно аудиотреки с обложками альбомов, а не музыкальные клипы, обзоры
и живые выступления.

У треков из каталога:
  * обложка квадратная (артворк альбома), а не превью 16:9;
  * исполнитель лежит в поле artist, а не в названии канала.

Как и обычный YouTube, требует VPN на территории России.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

from core.media import MediaItem
from core.providers.youtube import YouTubeProvider

log = logging.getLogger(__name__)

#: Фильтр «Только песни» в поиске YouTube Music.
SONGS_FILTER = "EgWKAQIIAWoKEAoQAxAEEAkQBQ%3D%3D"

#: Слова, по которым отбрасываем не-музыку, если пришлось искать по обычному YouTube.
NON_MUSIC_MARKERS = (
    "обзор", "реакция", "reaction", "разбор", "интервью", "подкаст",
    "трейлер", "прохождение", "стрим", "туториал", "как играть",
    "lyrics video review", "караоке минус",
)

#: Треков длиннее этого почти наверняка не бывает — это сборники и часовые миксы.
MAX_TRACK_SECONDS = 15 * 60


class MusicProvider(YouTubeProvider):
    """Поиск и воспроизведение музыки из каталога YouTube Music."""

    name = "youtube_music"
    content_type = "music"
    requires_vpn = True

    # ------------------------------------------------------------------ #
    def search(self, query: str, limit: int = 20) -> List[MediaItem]:
        """Поиск треков (без клипов)."""
        query = (query or "").strip()
        if not query:
            return []

        if self._looks_like_url(query):
            item = self.get_item(query)
            return [item] if item else []

        # Основной путь: каталог YouTube Music с фильтром «только песни».
        url = (
            f"https://music.youtube.com/search"
            f"?q={quote_plus(query)}&sp={SONGS_FILTER}"
        )
        info = self._extract(
            url,
            self._base_opts(extract_flat=True, playlistend=limit * 2, noplaylist=False),
        )
        items = self._entries_to_items(info)

        if not items:
            # Музыкальный домен не открылся — ищем по обычному YouTube и
            # отфильтровываем очевидную не-музыку сами.
            log.info("YouTube Music не ответил, ищем по обычному YouTube")
            info = self._extract(
                f"ytsearch{int(limit * 2)}:{query} аудио трек",
                self._base_opts(extract_flat=True),
            )
            items = [i for i in self._entries_to_items(info) if self._looks_like_music(i)]

        return items[:limit]

    def recommendations(self, queries: List[str], limit: int = 24) -> List[MediaItem]:
        """Лента музыки по интересам — параллельно."""
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
                for item in items:
                    if item.id in seen:
                        continue
                    seen.add(item.id)
                    if q not in item.categories:
                        item.categories.append(q)
                    collected.append(item)
                    if len(collected) >= limit:
                        break
                if len(collected) >= limit:
                    break

        if not collected:
            return self.search("популярная музыка", limit=limit)
        return collected[:limit]

    def related(self, video_id_or_url: str, limit: int = 12) -> List[MediaItem]:
        """Похожие треки — обычно другие вещи того же исполнителя."""
        item = self.get_item(video_id_or_url)
        if not item:
            return []
        query = item.author or " ".join(item.title.split()[:4])
        return [r for r in self.search(query, limit=limit + 1) if r.id != item.id][:limit]

    # ------------------------------------------------------------------ #
    @staticmethod
    def _looks_like_music(item: MediaItem) -> bool:
        """Отсев не-музыки для запасного поиска по обычному YouTube."""
        if item.duration and item.duration > MAX_TRACK_SECONDS:
            return False
        title = (item.title or "").lower()
        return not any(marker in title for marker in NON_MUSIC_MARKERS)

    def _info_to_item(
        self, info: Optional[Dict[str, Any]], full: bool = False
    ) -> Optional[MediaItem]:
        """То же, что у YouTube, но с чистым исполнителем и квадратной обложкой."""
        item = super()._info_to_item(info, full=full)
        if item is None:
            return None

        info = info or {}
        item.content_type = "music"
        # Играется и качается как обычное видео YouTube.
        item.platform = "youtube"

        # В каталоге YouTube Music исполнитель лежит отдельно; название канала
        # там выглядит как «Имя - Topic», что показывать некрасиво.
        artist = info.get("artist") or info.get("creator") or info.get("uploader")
        if artist:
            item.author = self._clean_artist(artist)

        album = info.get("album")
        if album:
            item.extra["album"] = album

        item.thumbnail = self._square_cover(item.thumbnail, item.id)
        # Подсказка интерфейсу рисовать карточку квадратной.
        item.extra["square_cover"] = True
        return item

    @staticmethod
    def _clean_artist(name: str) -> str:
        """Убрать служебный суффикс тематического канала."""
        cleaned = re.sub(r"\s*-\s*Topic$", "", name or "").strip()
        return cleaned or name

    @staticmethod
    def _square_cover(url: Optional[str], video_id: str) -> Optional[str]:
        """Ссылка на квадратную обложку.

        Артворк из каталога уже квадратный (lh3.googleusercontent.com) —
        такие ссылки не трогаем, только просим размер побольше. Для превью
        с ytimg берём вариант, который обрезается в квадрат самим плеером.
        """
        if not url:
            return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" if video_id else None

        if "googleusercontent.com" in url:
            # У артворка размер задаётся суффиксом =w60-h60-l90-rj
            return re.sub(r"=w\d+-h\d+", "=w400-h400", url)
        return url
