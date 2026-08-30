"""Карточка — максимально просто, без Stack и анимаций."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from core.media import MediaItem
from UI.themes.DarkTheme import COLORS, FONT_BOLD


class MediaCard(ft.Container):
    def __init__(self, item: MediaItem, on_play: Optional[Callable] = None, on_download: Optional[Callable] = None, width: int = 260, compact: bool = False, square: Optional[bool] = None):
        self.item = item
        self._on_play = on_play
        self._on_download = on_download
        self._compact = compact
        if square is None:
            square = bool(item.extra.get("square_cover"))
        self._square = square

        cover_h = width if square else int(width * 9 / 16)

        # Обложка — просто Image, без Stack, без градиента, чтобы не было серого
        if item.thumbnail:
            cover = ft.Image(src=item.thumbnail, width=width, height=cover_h, fit=ft.BoxFit.COVER, border_radius=ft.BorderRadius(12, 12, 12, 12))
        else:
            cover = ft.Container(width=width, height=cover_h, bgcolor=COLORS["surface_alt"], border_radius=12, alignment=ft.Alignment.CENTER, content=ft.Icon(self._icon(), color=COLORS["muted"], size=36))

        title = ft.Text(item.title, size=14, color=ft.Colors.WHITE, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS, font_family=FONT_BOLD)
        subtitle = ft.Text(self._subtitle(), size=12, color=COLORS["muted"], max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)

        info = ft.Container(content=ft.Column(controls=[title, subtitle], spacing=2, tight=True), bgcolor=ft.Colors.TRANSPARENT)

        body = [cover, info]
        if not compact:
            body.append(self._actions())

        super().__init__(
            content=ft.Column(controls=body, spacing=6, tight=True),
            width=width,
            bgcolor=COLORS["surface"],
            border_radius=12,
            padding=6,
            on_click=self._play,
        )

    def _icon(self):
        return { "music": ft.Icons.MUSIC_NOTE_ROUNDED, "film": ft.Icons.MOVIE_ROUNDED, "series": ft.Icons.LIVE_TV_ROUNDED }.get(self.item.content_type, ft.Icons.PLAY_CIRCLE_OUTLINE)

    def _subtitle(self) -> str:
        item = self.item
        if item.content_type == "music":
            return " • ".join([p for p in [item.author, item.extra.get("album")] if p])
        parts = [item.author]
        if item.view_count:
            parts.append(item.views_human)
        if item.year:
            parts.append(str(item.year))
        return " • ".join([str(p) for p in parts if p])

    def _actions(self) -> ft.Control:
        btns = [
            ft.IconButton(icon=ft.Icons.PLAY_ARROW_ROUNDED, icon_color=ft.Colors.WHITE, tooltip="Смотреть", on_click=self._play),
            ft.IconButton(icon=ft.Icons.DOWNLOAD_ROUNDED, icon_color=COLORS["muted"], tooltip="Скачать", on_click=self._download),
        ]
        if self.item.content_type != "music":
            btns.append(ft.IconButton(icon=ft.Icons.MUSIC_NOTE_ROUNDED, icon_color=COLORS["muted"], tooltip="Только звук", on_click=self._download_audio))
        return ft.Row(controls=btns, spacing=0, tight=True)

    def _play(self, e=None):
        if self._on_play:
            self._on_play(self.item)

    def _download(self, e=None):
        if self._on_download:
            self._on_download(self.item)

    def _download_audio(self, e=None):
        if self._on_download:
            from core.media import MediaItem as MI
            ai = MI.from_dict(self.item.to_dict())
            ai.extra["audio_only"] = True
            self._on_download(ai)
