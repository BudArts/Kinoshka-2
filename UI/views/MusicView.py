"""Раздел «Музыка» — теперь Яндекс Музыка."""

from __future__ import annotations

from typing import List

import flet as ft

from core.media import MediaItem
from UI.components.Common import EmptyState, SearchField, SectionTitle, StatusChip
from UI.components.MusicCard import MusicCard
from UI.themes.DarkTheme import COLORS, FONT_BOLD
from UI.views.VideoView import VideoView

QUICK_MOODS = [
    ("Популярное", "популярная музыка"),
    ("Русский рэп", "русский рэп"),
    ("Рок", "рок музыка"),
    ("Для работы", "музыка для работы без слов"),
    ("Спокойное", "спокойная музыка"),
    ("Танцевальное", "танцевальная музыка"),
]


class MusicView(VideoView):
    title = "Музыка"
    content_type = "music"
    source_name = "Яндекс Музыка"

    def _build_shell(self) -> None:
        self._search_field = SearchField(
            on_search=self.search,
            placeholder="Исполнитель, трек или ссылка",
            suggestions=self._suggestions(),
        )

        self.set_controls(
            [
                ft.Row(
                    controls=[
                        ft.Text(self.title, size=26, color=ft.Colors.WHITE, font_family=FONT_BOLD),
                        StatusChip(self.source_name, COLORS["muted"], ft.Icons.LIBRARY_MUSIC_ROUNDED),
                    ],
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                self._search_field,
                self._moods(),
                self._results_container,
            ]
        )

    def _moods(self) -> ft.Control:
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.ElevatedButton(
                        content=ft.Text(label, color=COLORS["muted"], size=13),
                        style=ft.ButtonStyle(bgcolor=COLORS["surface"], shape=ft.RoundedRectangleBorder(radius=18), padding=ft.Padding(14, 8, 14, 8)),
                        on_click=lambda e, q=query: self.search(q),
                    )
                    for label, query in QUICK_MOODS
                ],
                spacing=8,
                run_spacing=8,
                wrap=True,
            ),
            bgcolor=ft.Colors.TRANSPARENT,
        )

    def media_grid(self, items, on_play=None, on_download=None) -> ft.Control:
        if not items:
            return ft.Container(bgcolor=ft.Colors.TRANSPARENT)
        on_play = on_play or self.app.open_player
        on_download = on_download or self._download_track
        return ft.Container(
            content=ft.Row(
                controls=[MusicCard(item, on_play=on_play, on_download=on_download, width=190) for item in items],
                wrap=True,
                spacing=12,
                run_spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            bgcolor=ft.Colors.TRANSPARENT,
        )

    def _download_track(self, item: MediaItem) -> None:
        self.app.download_item(item, audio_only=True)

    def _render(self, items, heading: str) -> None:
        if isinstance(items, Exception):
            self._set_results(
                EmptyState(
                    "Ошибка поиска",
                    f"Не удалось получить музыку: {items}",
                    icon=ft.Icons.ERROR_OUTLINE_ROUNDED,
                    action_text="Повторить",
                    on_action=self._retry,
                )
            )
            return

        if not items:
            if self._query:
                self._set_results(
                    EmptyState(
                        f"По запросу «{self._query}» ничего не найдено",
                        "Попробуйте указать имя исполнителя или название трека. Музыка ищется в Яндекс Музыке.",
                        icon=ft.Icons.MUSIC_OFF_ROUNDED,
                        action_text="К рекомендациям",
                        on_action=self.load_feed,
                    )
                )
            else:
                self._set_results(self.offline_notice(self.source_name))
            return

        self._set_results(
            SectionTitle(heading, action_text="Обновить" if not self._query else "К рекомендациям", on_action=self._retry if not self._query else self.load_feed, icon=ft.Icons.MUSIC_NOTE_ROUNDED),
            self.media_grid(items),
        )
