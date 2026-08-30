"""Карточка трека — только обложка, название, исполнитель."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from core.media import MediaItem
from UI.themes.DarkTheme import ANIM_FAST, COLORS, FONT_BOLD, brand_gradient


class MusicCard(ft.Container):
    def __init__(self, item: MediaItem, on_play: Optional[Callable] = None, on_download: Optional[Callable] = None, width: int = 190):
        self.item = item
        self._on_play = on_play
        self._on_download = on_download

        cover = self._build_cover(width)

        title = ft.Text(item.title, size=14, color=ft.Colors.WHITE, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS, font_family=FONT_BOLD)
        subtitle = ft.Text(self._subtitle(), size=12, color=COLORS["muted"], max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)

        info = ft.Container(
            content=ft.Column(controls=[title, subtitle], spacing=2, tight=True),
            height=48,
            padding=ft.Padding(2, 0, 2, 0),
        )

        # Кнопки — только скачать и играть аудио, без видео
        actions = ft.Row(
            controls=[
                ft.IconButton(icon=ft.Icons.PLAY_ARROW_ROUNDED, icon_color=ft.Colors.WHITE, icon_size=20, tooltip="Слушать", on_click=self._play),
                ft.IconButton(icon=ft.Icons.DOWNLOAD_ROUNDED, icon_color=COLORS["muted"], icon_size=18, tooltip="Скачать mp3", on_click=self._download),
            ],
            spacing=0,
        )

        super().__init__(
            content=ft.Column(controls=[cover, info, actions], spacing=6, tight=True),
            width=width,
            padding=8,
            border_radius=14,
            bgcolor=ft.Colors.TRANSPARENT,
            on_click=self._play,
            tooltip=item.title,
        )

    def _build_cover(self, width: int) -> ft.Control:
        placeholder = ft.Container(
            width=width,
            height=width,
            border_radius=12,
            gradient=brand_gradient(),
            alignment=ft.Alignment.CENTER,
            content=ft.Icon(ft.Icons.MUSIC_NOTE_ROUNDED, color=ft.Colors.WHITE, size=40),
        )

        if self.item.thumbnail:
            return ft.Container(
                width=width,
                height=width,
                border_radius=12,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                content=ft.Stack(
                    controls=[
                        placeholder,
                        ft.Image(src=self.item.thumbnail, width=width, height=width, fit=ft.BoxFit.COVER, border_radius=12, error_content=placeholder),
                    ]
                ),
            )
        return placeholder

    def _subtitle(self) -> str:
        parts = [self.item.author, self.item.extra.get("album")]
        return " • ".join([p for p in parts if p])

    def _play(self, e=None):
        if self._on_play:
            self._on_play(self.item)

    def _download(self, e=None):
        if self._on_download:
            self._on_download(self.item)
