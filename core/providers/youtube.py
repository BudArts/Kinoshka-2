"""YouTube провайдер — максимально простой и быстрый, Piped первым."""

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

_YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
TRENDING_URL = "https://www.youtube.com/feed/trending"


class YouTubeProvider(BaseProvider):
    name = "youtube"
    content_type = "video"
    requires_vpn = False  # теперь пробуем без VPN через Piped

    def __init__(self, vpn=None):
        self.vpn = vpn or vpn_manager

    def _base_opts(self, **overrides: Any) -> Dict[str, Any]:
        opts: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "skip_download": True,
            "socket_timeout": 8,
            "retries": 1,
            "extractor_args": {"youtube": {"player_client": ["web"]}},
        }
        proxy = self.vpn.proxy_url()
        if proxy:
            opts["proxy"] = proxy
        opts.update(overrides)
        return opts

    def _extract(self, target: str, opts: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            with YoutubeDL(opts) as ydl:
                return ydl.extract_info(target, download=False)
        except Exception as exc:
            log.debug("yt-dlp fail %s: %s", target, exc)
            return None

    def search(self, query: str, limit: int = 20) -> List[MediaItem]:
        query = (query or "").strip()
        if not query:
            return []
        if self._looks_like_url(query):
            # прямая ссылка — пробуем получить инфо
            item = self.get_item(query)
            if item:
                return [item]
            # если это youtube id, делаем объект без сети
            vid = self.extract_video_id(query)
            if vid:
                return [MediaItem(id=vid, title=query, url=f"https://www.youtube.com/watch?v={vid}", platform="youtube", content_type="video", thumbnail=f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg")]

        # 1. Piped — быстро и без VPN
        piped = self._search_via_piped(query, limit=limit)
        if piped:
            return piped

        # 2. yt-dlp как fallback
        info = self._extract(f"ytsearch{int(limit)}:{query}", self._base_opts(extract_flat=True))
        items = self._entries_to_items(info)
        if items:
            return items

        return []

    def _search_via_piped(self, query: str, limit: int = 20) -> List[MediaItem]:
        import requests

        instances = [
            "https://pipedapi.kavin.rocks",
            "https://pipedapi.tokhmi.xyz",
            "https://api.piped.projectsegfau.lt",
            "https://pipedapi.syncpundit.io",
        ]

        for base in instances:
            try:
                r = requests.get(f"{base}/search", params={"q": query}, timeout=5, proxies=self.vpn.requests_proxies())
                if r.status_code != 200:
                    continue
                data = r.json()
                items = data.get("items") or []
                result: List[MediaItem] = []
                for entry in items[:limit]:
                    if not entry or entry.get("type") != "stream":
                        continue
                    # url вида /watch?v=xxx
                    url = entry.get("url") or ""
                    vid = ""
                    if "v=" in url:
                        vid = url.split("v=")[-1].split("&")[0]
                    else:
                        vid = url.split("/")[-1]
                    if not vid or len(vid) < 5:
                        continue
                    result.append(
                        MediaItem(
                            id=vid,
                            title=entry.get("title") or "Без названия",
                            url=f"https://www.youtube.com/watch?v={vid}",
                            platform="youtube",
                            content_type="video",
                            author=entry.get("uploaderName") or "",
                            thumbnail=entry.get("thumbnail") or f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                            duration=int(entry.get("duration")) if entry.get("duration") else None,
                        )
                    )
                if result:
                    return result
            except Exception:
                continue
        return []

    def recommendations(self, queries: List[str], limit: int = 12) -> List[MediaItem]:
        # Максимально просто: один запрос, без параллели
        if not queries:
            return self.trending(limit)
        q = queries[0]
        items = self.search(q, limit=limit)
        if items:
            return items[:limit]
        return self.trending(limit)

    def trending(self, limit: int = 12) -> List[MediaItem]:
        # Пробуем Piped тренды
        piped = self._search_via_piped("топ видео сегодня", limit=limit)
        if piped:
            return piped
        # Fallback yt-dlp
        info = self._extract(TRENDING_URL, self._base_opts(extract_flat=True, playlistend=limit, noplaylist=False))
        return self._entries_to_items(info)[:limit]

    def get_item(self, video_id_or_url: str) -> Optional[MediaItem]:
        url = self._to_url(video_id_or_url)
        vid = self.extract_video_id(url) or self.extract_video_id(video_id_or_url)
        # Сначала пробуем yt-dlp быстро
        info = self._extract(url, self._base_opts())
        if info:
            return self._info_to_item(info, full=True)
        # Fallback — создаём минимальный объект без сети
        if vid:
            return MediaItem(
                id=vid,
                title=f"Видео {vid}",
                url=f"https://www.youtube.com/watch?v={vid}",
                platform="youtube",
                content_type="video",
                thumbnail=f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
            )
        return None

    def get_stream_url(self, video_id_or_url: str, quality: str = "720p") -> Optional[str]:
        vid = self.extract_video_id(video_id_or_url) or self.extract_video_id(self._to_url(video_id_or_url))
        if not vid:
            vid = video_id_or_url

        # 1. Piped streams — самый надёжный способ без VPN
        stream = self._get_stream_via_piped(vid, quality)
        if stream:
            return stream

        # 2. yt-dlp fallback
        url = self._to_url(video_id_or_url)
        info = self._extract(url, self._base_opts(format=self._format_selector(quality)))
        if not info:
            return None
        return self._pick_stream(info)

    def _get_stream_via_piped(self, video_id: str, quality: str = "720p") -> Optional[str]:
        import requests

        instances = [
            "https://pipedapi.kavin.rocks",
            "https://pipedapi.tokhmi.xyz",
            "https://api.piped.projectsegfau.lt",
        ]
        target_height = QUALITY_TO_HEIGHT.get(quality) or 720

        for base in instances:
            try:
                r = requests.get(f"{base}/streams/{video_id}", timeout=6, proxies=self.vpn.requests_proxies())
                if r.status_code != 200:
                    continue
                data = r.json()
                # videoStreams
                vstreams = data.get("videoStreams") or []
                # ищем mp4 с нужной высотой
                best = None
                for vs in vstreams:
                    if not vs.get("url"):
                        continue
                    # ищем прогрессивный (с аудио) или хотя бы видео
                    h = vs.get("height") or 0
                    if h <= target_height + 100:
                        if best is None or h > (best.get("height") or 0):
                            best = vs
                if best and best.get("url"):
                    return best["url"]
                # fallback — любой url
                if vstreams and vstreams[0].get("url"):
                    return vstreams[0]["url"]
                # пробуем audioStreams для музыки
                astreams = data.get("audioStreams") or []
                if astreams and astreams[0].get("url"):
                    return astreams[0]["url"]
            except Exception:
                continue
        return None

    def related(self, video_id_or_url: str, limit: int = 8) -> List[MediaItem]:
        # Просто поиск по первым словам названия
        item = self.get_item(video_id_or_url)
        if not item:
            return []
        q = " ".join(item.title.split()[:3]) if item.title else "популярное"
        return self.search(q, limit=limit)[:limit]

    def is_available(self) -> bool:
        return True

    def _entries_to_items(self, info: Optional[Dict[str, Any]]) -> List[MediaItem]:
        if not info:
            return []
        entries = info.get("entries") or []
        items: List[MediaItem] = []
        for entry in entries:
            if not entry:
                continue
            if entry.get("_type") == "playlist" and entry.get("entries"):
                for nested in entry["entries"]:
                    it = self._info_to_item(nested)
                    if it:
                        items.append(it)
                continue
            it = self._info_to_item(entry)
            if it:
                items.append(it)
        return items

    def _info_to_item(self, info: Optional[Dict[str, Any]], full: bool = False) -> Optional[MediaItem]:
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
        )
        if full:
            item.stream_url = self._pick_stream(info)
        return item

    @staticmethod
    def _pick_thumbnail(info: Dict[str, Any]) -> Optional[str]:
        if info.get("thumbnail"):
            return info["thumbnail"]
        thumbnails = info.get("thumbnails") or []
        if not thumbnails:
            vid = info.get("id")
            return f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if vid else None
        suitable = [t for t in thumbnails if (t.get("width") or 0) <= 640]
        best = max(suitable or thumbnails, key=lambda t: t.get("width") or 0)
        return best.get("url")

    @staticmethod
    def _pick_stream(info: Dict[str, Any]) -> Optional[str]:
        if info.get("url"):
            return info["url"]
        formats = info.get("formats") or []
        progressive = [f for f in formats if f.get("vcodec") not in (None, "none") and f.get("acodec") not in (None, "none") and f.get("url")]
        if progressive:
            best = max(progressive, key=lambda f: f.get("height") or 0)
            return best.get("url")
        with_url = [f for f in formats if f.get("url")]
        if with_url:
            return max(with_url, key=lambda f: f.get("tbr") or 0).get("url")
        return None

    @staticmethod
    def _format_selector(quality: str) -> str:
        height = QUALITY_TO_HEIGHT.get(quality)
        if height is None:
            return "best[ext=mp4]/best"
        return f"best[height<={height}][ext=mp4]/best[height<={height}]/bestvideo[height<={height}]+bestaudio/best"

    @staticmethod
    def _looks_like_url(value: str) -> bool:
        return value.startswith(("http://", "https://", "www."))

    @staticmethod
    def _to_url(video_id_or_url: str) -> str:
        value = (video_id_or_url or "").strip()
        if YouTubeProvider._looks_like_url(value):
            return value if value.startswith("http") else f"https://{value}"
        if _YOUTUBE_ID_RE.match(value):
            return f"https://www.youtube.com/watch?v={value}"
        return value

    @staticmethod
    def extract_video_id(url: str) -> Optional[str]:
        if _YOUTUBE_ID_RE.match(url or ""):
            return url
        patterns = (r"(?:v=|/v/|youtu\.be/|/embed/|/shorts/|/live/)([A-Za-z0-9_-]{11})",)
        for pat in patterns:
            m = re.search(pat, url or "")
            if m:
                return m.group(1)
        return None
