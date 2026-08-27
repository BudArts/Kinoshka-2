"""Провайдеры контента."""

from core.providers.base import BaseProvider
from core.providers.youtube import YouTubeProvider

__all__ = ["BaseProvider", "YouTubeProvider"]
