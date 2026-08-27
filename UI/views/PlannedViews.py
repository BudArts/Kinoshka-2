"""Разделы, которые будут доработаны в следующих итерациях.

Экраны уже подключены к навигации и переиспользуют логику VideoView, но
провайдеры RuTube / Кинопоиска / музыки пока не реализованы — вместо пустого
экрана пользователю честно объясняется, что готово, а что нет.
"""

from __future__ import annotations

from typing import List, Optional

import flet as ft

from UI.components.Common import EmptyState, SearchField
from UI.themes.DarkTheme import COLORS, FONT_BOLD
from UI.views.VideoView import VideoView


class _PlannedView(VideoView):
    """Каркас раздела с пояснением о ходе разработки."""

    #: Пункты, которые появятся в разделе.
    roadmap: List[str] = []
    icon: str = ft.Icons.CONSTRUCTION_ROUNDED

    def on_show(self, query: Optional[str] = None) -> None:
        self._build_shell()
        self._set_results(self._roadmap_block())

    def _roadmap_block(self) -> ft.Control:
        items = [
            ft.Row(
                controls=[
                    ft.Icon(ft.Icons.CIRCLE, size=7, color=COLORS["gradient1"]),
                    ft.Text(text, size=13, color=COLORS["muted"], expand=True),
                ],
                spacing=10,
            )
            for text in self.roadmap
        ]

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Icon(self.icon, size=52, color=COLORS["dark_gray"]),
                    ft.Text(f"Раздел «{self.title}» в разработке", size=18,
                            color=ft.Colors.WHITE, font_family=FONT_BOLD),
                    ft.Text(
                        "Ядро приложения (профили, история, интересы, загрузчик, "
                        "плеер, VPN) уже работает и будет переиспользовано здесь. "
                        "Осталось подключить источники:",
                        size=13, color=COLORS["muted"], width=520,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Container(
                        content=ft.Column(items, spacing=8, tight=True),
                        padding=18,
                        border_radius=14,
                        bgcolor=COLORS["surface"],
                        width=560,
                    ),
                ],
                spacing=16,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            alignment=ft.Alignment.CENTER,
            padding=30,
        )


class FilmsView(_PlannedView):
    """Фильмы и сериалы: RuTube, Кинопоиск, поиск по интернету, ИИ-поиск."""

    title = "Фильмы и сериалы"
    content_type = "film"
    source_name = "RuTube"
    icon = ft.Icons.CAMERA_ROLL_ROUNDED
    roadmap = [
        "Провайдер RuTube: поиск и получение потока через yt-dlp",
        "Парсер Кинопоиска: рейтинги, постеры, год, жанры, актуальные новинки",
        "Запасной поиск по интернету, когда фильма нет на RuTube",
        "ИИ-поиск по смыслу запроса (OpenAI-совместимый API из настроек)",
        "Отслеживание серий: «продолжить с 4 серии 2 сезона»",
    ]


class MusicView(_PlannedView):
    """Музыка: поиск треков, плейлисты, скачивание в mp3."""

    title = "Музыка"
    content_type = "music"
    source_name = "Музыка"
    icon = ft.Icons.LIBRARY_MUSIC_ROUNDED
    roadmap = [
        "Поиск треков и альбомов через YouTube Music и другие источники",
        "Аудиоплеер с очередью, перемешиванием и повтором",
        "Скачивание в mp3 с обложкой и тегами (постпроцессор уже готов)",
        "Плейлисты пользователя и рекомендации по жанрам",
    ]


class JarvisView(_PlannedView):
    """Голосовой/текстовый ассистент по управлению приложением."""

    title = "Джарвис"
    content_type = "video"
    source_name = "Ассистент"
    icon = ft.Icons.ELECTRIC_BOLT_ROUNDED
    roadmap = [
        "Чат-ассистент: «включи что-нибудь смешное на 20 минут»",
        "Голосовые команды и озвучка ответов",
        "Умный подбор по настроению на основе ваших интересов",
        "Управление загрузками и плеером голосом",
    ]
