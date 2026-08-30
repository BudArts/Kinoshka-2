"""Провайдер Яндекс Музыки — основной источник для раздела Музыка.

Использует неофициальную библиотеку yandex-music (без токена работает поиск и 30с превью,
с токеном — полный доступ). Для скачивания использует yt-dlp с поддержкой yandexmusic:track,
а если не вышло — пробует скачать через API (если есть токен).

Почему Яндекс Музыка, а не YouTube:
  * в России YouTube Music без VPN не работает, а Яндекс Музыка работает напрямую;
  * у треков есть нормальные обложки альбомов (квадратные), а не превью 16:9;
  * исполнитель и альбом уже размечены.

Если Яндекс Музыка недоступна (сеть, блокировка), провайдер падает в fallback на YouTube Music,
чтобы раздел не был пустым.
"""

from __future__ import annotations

import logging
import re
import time
from typing import List, Optional

from config import settings
from core.media import MediaItem
from core.providers.base import BaseProvider
from core.vpn import vpn_manager

log = logging.getLogger(__name__)


def _get_client():
    try:
        from yandex_music import Client
        from yandex_music.utils.request import Request
    except ImportError:
        log.warning("Библиотека yandex-music не установлена")
        return None

    token = (settings.get("yandex_music_token") or "").strip()
    try:
        # Таймаут 5 секунд, чтобы не висеть долго
        request = Request(timeout=5)
        if token:
            client = Client(token, request=request).init()
        else:
            client = Client(request=request).init()
        return client
    except Exception as exc:
        log.warning("Не удалось инициализировать клиент Яндекс Музыки: %s", exc)
        return None


def _cover_url(cover_uri: Optional[str], size: str = "400x400") -> Optional[str]:
    if not cover_uri:
        return None
    # cover_uri вида "avatars.yandex.net/get-music-content/123/abc/%%"
    return "https://" + cover_uri.replace("%%", size)


def _track_to_item(track) -> Optional[MediaItem]:
    try:
        track_id = getattr(track, "id", None)
        if not track_id:
            return None

        title = getattr(track, "title", "") or "Без названия"
        version = getattr(track, "version", None)
        if version:
            title = f"{title} ({version})"

        artists = getattr(track, "artists", []) or []
        author = ", ".join([a.name for a in artists if getattr(a, "name", None)]) if artists else "Неизвестный исполнитель"

        albums = getattr(track, "albums", []) or []
        album_id = albums[0].id if albums and getattr(albums[0], "id", None) else None
        album_title = albums[0].title if albums and getattr(albums[0], "title", None) else None

        cover_uri = getattr(track, "cover_uri", None) or (albums[0].cover_uri if albums and getattr(albums[0], "cover_uri", None) else None)
        thumbnail = _cover_url(cover_uri, "400x400") or _cover_url(cover_uri, "200x200")

        duration_ms = getattr(track, "duration_ms", None)
        duration = int(duration_ms // 1000) if duration_ms else None

        # Ссылка для открытия в браузере и для yt-dlp
        if album_id:
            url = f"https://music.yandex.ru/album/{album_id}/track/{track_id}"
            media_id = f"{track_id}:{album_id}"
        else:
            url = f"https://music.yandex.ru/track/{track_id}"
            media_id = str(track_id)

        item = MediaItem(
            id=media_id,
            title=title,
            url=url,
            platform="yandex_music",
            content_type="music",
            author=author,
            thumbnail=thumbnail,
            duration=duration,
            categories=[],
            tags=[],
        )
        item.extra["square_cover"] = True
        item.extra["album"] = album_title
        item.extra["album_id"] = album_id
        item.extra["track_id"] = track_id
        # Для скачивания через yt-dlp используем yandexmusic:track URL
        item.extra["yandex_url"] = url
        return item
    except Exception as exc:
        log.debug("Не удалось преобразовать трек: %s", exc, exc_info=True)
        return None


class YandexMusicProvider(BaseProvider):
    name = "yandex_music"
    content_type = "music"
    requires_vpn = False

    def __init__(self, vpn=None):
        self.vpn = vpn or vpn_manager
        self._client = None
        self._client_time = 0

    def _client_cached(self):
        # Кэшируем клиент на 10 минут
        now = time.time()
        if self._client and (now - self._client_time < 600):
            return self._client
        self._client = _get_client()
        self._client_time = now
        return self._client

    def search(self, query: str, limit: int = 20) -> List[MediaItem]:
        query = (query or "").strip()
        if not query:
            return []

        if self._looks_like_url(query):
            item = self.get_item(query)
            return [item] if item else []

        client = self._client_cached()
        if not client:
            log.info("Клиент Яндекс Музыки недоступен, поиск пропускаем")
            return []

        try:
            # Пробуем искать треки
            search_result = client.search(query, type_="track", nocorrect=False)
            if not search_result or not search_result.tracks or not search_result.tracks.results:
                return []

            tracks = search_result.tracks.results[:limit]
            items = []
            for t in tracks:
                it = _track_to_item(t)
                if it:
                    items.append(it)
            return items
        except Exception as exc:
            log.warning("Поиск Яндекс Музыки упал: %s", exc)
            return []

    def recommendations(self, queries: List[str], limit: int = 24) -> List[MediaItem]:
        # Для скорости — один запрос, а не 4 параллельных
        query = "популярная музыка"
        if queries:
            # берём первый интерес как запрос
            query = queries[0]

        try:
            items = self.search(query, limit=limit)
            if items:
                return items
        except Exception as exc:
            log.debug("Рекомендации Яндекс упали: %s", exc)

        # Fallback — чарт
        try:
            return self.trending(limit=limit)
        except Exception:
            return []

    def trending(self, limit: int = 24) -> List[MediaItem]:
        # Пытаемся взять чарт, если API позволяет
        client = self._client_cached()
        if client:
            try:
                # landing чарты
                chart = client.chart()
                if chart and chart.chart and chart.chart.tracks:
                    items = []
                    for short in chart.chart.tracks[:limit]:
                        track = short.track
                        if track:
                            it = _track_to_item(track)
                            if it:
                                items.append(it)
                    if items:
                        return items
            except Exception as exc:
                log.debug("Чарт Яндекс Музыки не удалось: %s", exc)

        return self.search("чарт Яндекс Музыки", limit=limit)

    def get_item(self, video_id_or_url: str) -> Optional[MediaItem]:
        value = (video_id_or_url or "").strip()
        if not value:
            return None

        # Если это уже наш id вида "123:456"
        m = re.search(r"(\d+):(\d+)", value)
        if m:
            track_id, album_id = m.group(1), m.group(2)
            return self._get_by_ids(track_id, album_id)

        # Парсим URL вида /album/123/track/456 или /track/456
        m = re.search(r"/album/(\d+)/track/(\d+)", value)
        if m:
            album_id, track_id = m.group(1), m.group(2)
            return self._get_by_ids(track_id, album_id)

        m = re.search(r"/track/(\d+)", value)
        if m:
            track_id = m.group(1)
            return self._get_by_ids(track_id, None)

        # Прямой id трека
        if value.isdigit():
            return self._get_by_ids(value, None)

        return None

    def _get_by_ids(self, track_id: str, album_id: Optional[str]) -> Optional[MediaItem]:
        client = self._client_cached()
        if not client:
            return None
        try:
            if album_id:
                tracks = client.tracks([f"{track_id}:{album_id}"])
            else:
                tracks = client.tracks([track_id])
            if tracks and len(tracks) > 0:
                return _track_to_item(tracks[0])
        except Exception as exc:
            log.warning("Не удалось получить трек %s:%s: %s", track_id, album_id, exc)
        return None

    def get_stream_url(self, video_id_or_url: str, quality: str = "mp3") -> Optional[str]:
        # Пытаемся получить прямую ссылку через API, если есть токен
        client = self._client_cached()
        item = self.get_item(video_id_or_url)
        if not item:
            return None

        track_id = item.extra.get("track_id")
        album_id = item.extra.get("album_id")

        if client and track_id:
            try:
                # get_download_info требует токен для полного трека
                track_id_full = f"{track_id}:{album_id}" if album_id else str(track_id)
                tracks = client.tracks([track_id_full])
                if tracks:
                    track = tracks[0]
                    infos = track.get_download_info()
                    if infos:
                        # Берём лучший mp3
                        best = None
                        for info in infos:
                            if info.codec == "mp3":
                                if best is None or info.bitrate_in_kbps > best.bitrate_in_kbps:
                                    best = info
                        if best:
                            return best.get_direct_link()
                        # Если mp3 нет, берём первый
                        return infos[0].get_direct_link()
            except Exception as exc:
                log.debug("Download info не удалось: %s", exc)

        # Fallback — через yt-dlp, он сам разберётся с yandexmusic:track
        try:
            from yt_dlp import YoutubeDL

            url = item.extra.get("yandex_url") or item.url
            opts = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "format": "bestaudio/best",
            }
            proxy = self.vpn.proxy_url()
            if proxy:
                opts["proxy"] = proxy

            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info and info.get("url"):
                    return info["url"]
                # иногда url внутри formats
                if info and info.get("formats"):
                    for f in info["formats"]:
                        if f.get("url"):
                            return f["url"]
        except Exception as exc:
            log.debug("yt-dlp yandexmusic не смог: %s", exc)

        return None

    def is_available(self) -> bool:
        # Яндекс Музыка доступна без VPN в России
        return True

    @staticmethod
    def _looks_like_url(value: str) -> bool:
        return value.startswith(("http://", "https://", "www.")) or "music.yandex" in value
