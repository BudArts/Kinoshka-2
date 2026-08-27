"""Базовый интерфейс провайдера контента.

Каждый источник (YouTube, RuTube, музыка, веб-поиск) реализует этот интерфейс,
поэтому UI и рекомендательный движок работают с любым источником одинаково.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from core.media import MediaItem


class BaseProvider(ABC):
    """Контракт источника контента."""

    #: Машинное имя площадки: youtube / rutube / web / local.
    name: str = "base"
    #: Тип контента по умолчанию: video / film / music.
    content_type: str = "video"
    #: Нужен ли этому источнику VPN.
    requires_vpn: bool = False

    @abstractmethod
    def search(self, query: str, limit: int = 20) -> List[MediaItem]:
        """Поиск по строке запроса."""

    @abstractmethod
    def get_item(self, video_id_or_url: str) -> Optional[MediaItem]:
        """Полные метаданные одной единицы контента."""

    def recommendations(self, queries: List[str], limit: int = 24) -> List[MediaItem]:
        """Лента рекомендаций по списку интересов пользователя.

        Реализация по умолчанию — объединение поисков по интересам.
        Источники с собственным API рекомендаций могут её переопределить.
        """
        if not queries:
            return []
        per_query = max(1, limit // len(queries))
        collected: List[MediaItem] = []
        seen: set[str] = set()
        for query in queries:
            for item in self.search(query, limit=per_query):
                if item.id in seen:
                    continue
                seen.add(item.id)
                collected.append(item)
        return collected[:limit]

    def get_stream_url(self, video_id_or_url: str, quality: str = "720p") -> Optional[str]:
        """Прямая ссылка на воспроизводимый поток."""
        item = self.get_item(video_id_or_url)
        return item.stream_url if item else None

    def related(self, video_id_or_url: str, limit: int = 12) -> List[MediaItem]:
        """Похожий контент (для панели «Смотрите также»)."""
        return []

    def is_available(self) -> bool:
        """Доступен ли источник прямо сейчас."""
        return True
