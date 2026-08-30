"""Карточка трека — только обложка, название, исполнитель."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from core.media import MediaItem
from UI.themes.DarkTheme import COLORS, FONT_BOLD


class MusicCard(ft.Container):
    def __init__(self, item: MediaItem, on_play: Optional[Callable] = None, on_download: Optional[Callable] = None, width: int = 190):
        self.item = item
        self._on_play = on_play
        self._on_download = on_download

        if item.thumbnail:
            cover = ft.Image(src=item.thumbnail, width=width, height=width, fit=ft.BoxFit.COVER, border_radius=ft.BorderRadius(12, 12, 12, 12))
        else:
            cover = ft.Container(width=width, height=width, bgcolor=COLORS["surface_alt"], border_radius=12, alignment=ft.Alignment.CENTER, content=ft.Icon(ft.Icons.MUSIC_NOTE_ROUNDED, color=COLORS["muted"], size=36))

        title = ft.Text(item.title, size=13, color=ft.Colors.WHITE, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS, font_family=FONT_BOLD)
        subtitle = ft.Text(item.author or "", size=11, color=COLORS["muted"], max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)

        super().__init__(
            content=ft.Column(controls=[cover, title, subtitle, self._actions()], spacing=4, tight=True),
            width=width,
            bgcolor=COLORS["surface"],
            border_radius=12,
            padding=6,
            on_click=self._play,
        )

    def _actions(self):
        return ft.Row(
            controls=[
                ft.IconButton(icon=ft.Icons.PLAY_ARROW_ROUNDED, icon_color=ft.Colors.WHITE, icon_size=18, tooltip="Слушать", on_click=self._play),
                ft.IconButton(icon=ft.Icons.DOWNLOAD_ROUNDED, icon_color=COLORS["muted"], icon_size=16, tooltip="Скачать", on_click=self._download),
            ],
            spacing=0,
            tight=True,
        )

    def _play(self, e=None):
        if self._on_play:
            self._on_play(self.item)

    def _download(self, e=None):
        if self._on_download:
            self._on_download(self.item)
