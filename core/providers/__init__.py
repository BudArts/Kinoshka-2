"""Провайдеры контента."""

from core.providers.base import BaseProvider
from core.providers.film import FilmProvider
from core.providers.kinopoisk import KinopoiskClient, kinopoisk
from core.providers.music import MusicProvider
from core.providers.rutube import RuTubeProvider
from core.providers.web import WebSearchProvider
from core.providers.youtube import YouTubeProvider

__all__ = [
    "BaseProvider",
    "YouTubeProvider",
    "RuTubeProvider",
    "FilmProvider",
    "MusicProvider",
    "WebSearchProvider",
    "KinopoiskClient",
    "kinopoisk",
]
