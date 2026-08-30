"""Общие структуры данных ядра.

MediaItem — единый формат единицы контента для всех источников
(YouTube, RuTube, музыка, локальные файлы). UI работает только с ним и
ничего не знает о том, откуда пришли данные.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class MediaItem:
    """Единица контента: видео, фильм, серия или трек."""

    #: Идентификатор на площадке ("dQw4w9WgXcQ", "rutube:abc123", путь к файлу).
    id: str
    title: str
    url: str

    platform: str = "youtube"      # youtube / rutube / web / local / kinopoisk
    content_type: str = "video"    # video / film / series / music

    author: Optional[str] = None
    thumbnail: Optional[str] = None
    description: Optional[str] = None
    duration: Optional[int] = None        # секунд
    view_count: Optional[int] = None
    upload_date: Optional[str] = None     # YYYYMMDD
    year: Optional[int] = None
    rating: Optional[float] = None

    categories: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    #: Прямая ссылка на поток, если провайдер её уже вычислил.
    stream_url: Optional[str] = None
    #: Локальный путь, если файл уже скачан.
    local_path: Optional[str] = None
    #: Всё, что не влезло в общую схему (сырой ответ провайдера и т.п.).
    extra: Dict[str, Any] = field(default_factory=dict)

    # -- представление ------------------------------------------------------ #
    @property
    def duration_human(self) -> str:
        """Длительность в виде 1:02:03 или 4:21."""
        total = int(self.duration or 0)
        if total <= 0:
            return "--:--"
        hours, rem = divmod(total, 3600)
        minutes, seconds = divmod(rem, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    @property
    def views_human(self) -> str:
        """Просмотры в виде 1,2 млн / 340 тыс."""
        count = self.view_count or 0
        if count >= 1_000_000_000:
            return f"{count / 1_000_000_000:.1f} млрд".replace(".", ",")
        if count >= 1_000_000:
            return f"{count / 1_000_000:.1f} млн".replace(".", ",")
        if count >= 1_000:
            return f"{count / 1_000:.0f} тыс."
        return str(count)

    @property
    def subtitle(self) -> str:
        """Строка под заголовком карточки."""
        parts = [p for p in (self.author, self.views_human if self.view_count else None) if p]
        return " • ".join(parts)

    @property
    def is_local(self) -> bool:
        return self.platform == "local" or bool(self.local_path)

    # -- сериализация ------------------------------------------------------- #
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_history_payload(self) -> Dict[str, Any]:
        """Формат, который ждёт RecommendationEngine.track_watch()."""
        return {
            "video_id": self.id,
            "title": self.title,
            "platform": self.platform,
            "type": self.content_type,
            "link": self.url,
            "author": self.author,
            "thumbnail": self.thumbnail,
            "categories": self.categories,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MediaItem":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        extra = {k: v for k, v in data.items() if k not in known}
        payload = {k: v for k, v in data.items() if k in known}
        item = cls(**payload)
        if extra:
            item.extra.update(extra)
        return item


@dataclass
class SearchResult:
    """Результат поиска вместе с контекстом (для аналитики и пагинации)."""

    query: str
    items: List[MediaItem] = field(default_factory=list)
    source: str = "youtube"
    total: Optional[int] = None
    error: Optional[str] = None

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self):
        return iter(self.items)

    @property
    def ok(self) -> bool:
        return self.error is None
