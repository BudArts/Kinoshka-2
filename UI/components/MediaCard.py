"""Карточка единицы контента для лент и результатов поиска."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from core.media import MediaItem
from UI.themes.DarkTheme import ANIM_FAST, COLORS, FONT_BOLD, brand_gradient

#: Соотношение сторон превью 16:9.
THUMB_RATIO = 16 / 9


class MediaCard(ft.Container):
    """Плитка видео/фильма/трека: превью, длительность, заголовок, действия."""

    def __init__(
        self,
        item: MediaItem,
        on_play: Optional[Callable[[MediaItem], None]] = None,
        on_download: Optional[Callable[[MediaItem], None]] = None,
        width: int = 260,
        compact: bool = False,
    ):
        self.item = item
        self._on_play = on_play
        self._on_download = on_download
        self._compact = compact

        thumb_height = int(width / THUMB_RATIO)

        # --- превью с бейджем длительности -----------------------------
        self._thumb = ft.Container(
            width=width,
            height=thumb_height,
            border_radius=12,
            bgcolor=COLORS["surface_alt"],
            content=ft.Stack(
                controls=[
                    ft.Image(
                        src=item.thumbnail or "",
                        width=width,
                        height=thumb_height,
                        fit=ft.BoxFit.COVER,
                        border_radius=12,
                        # Пока грузится превью — фирменный градиент вместо дыры.
                        error_content=ft.Container(
                            width=width,
                            height=thumb_height,
                            border_radius=12,
                            gradient=brand_gradient(),
                            alignment=ft.Alignment.CENTER,
                            content=ft.Icon(
                                self._placeholder_icon(), color=ft.Colors.WHITE, size=36
                            ),
                        ),
                    ),
                    self._duration_badge(),
                    self._play_overlay(width, thumb_height),
                ]
            ),
        )

        # --- текстовая часть -------------------------------------------
        self._title = ft.Text(
            item.title,
            size=14,
            color=ft.Colors.WHITE,
            max_lines=2,
            overflow=ft.TextOverflow.ELLIPSIS,
            font_family=FONT_BOLD,
        )
        self._subtitle = ft.Text(
            item.subtitle or "",
            size=12,
            color=COLORS["muted"],
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

        info_column = ft.Column(
            controls=[self._title, self._subtitle],
            spacing=2,
            tight=True,
        )

        body_controls = [self._thumb, info_column]
        if not compact:
            body_controls.append(self._actions_row())

        super().__init__(
            content=ft.Column(controls=body_controls, spacing=8, tight=True),
            width=width,
            padding=8,
            border_radius=14,
            animate=ANIM_FAST,
            animate_scale=ANIM_FAST,
            on_hover=self._hover,
            on_click=self._play,
            tooltip=item.title,
            ink=False,
        )

    # ------------------------------------------------------------------ #
    def _placeholder_icon(self) -> str:
        return {
            "music": ft.Icons.MUSIC_NOTE,
            "film": ft.Icons.MOVIE,
            "series": ft.Icons.LIVE_TV,
        }.get(self.item.content_type, ft.Icons.PLAY_CIRCLE_OUTLINE)

    def _duration_badge(self) -> ft.Control:
        return ft.Container(
            content=ft.Text(
                self.item.duration_human, size=11, color=ft.Colors.WHITE
            ),
            bgcolor=ft.Colors.with_opacity(0.78, ft.Colors.BLACK),
            padding=ft.Padding(6, 2, 6, 2),
            border_radius=6,
            right=6,
            bottom=6,
        )

    def _play_overlay(self, width: int, height: int) -> ft.Control:
        """Затемнение с кнопкой Play, проявляющееся при наведении."""
        self._overlay = ft.Container(
            width=width,
            height=height,
            border_radius=12,
            bgcolor=ft.Colors.with_opacity(0.45, ft.Colors.BLACK),
            alignment=ft.Alignment.CENTER,
            content=ft.Icon(ft.Icons.PLAY_CIRCLE_FILL, size=52, color=ft.Colors.WHITE),
            opacity=0,
            animate_opacity=ANIM_FAST,
        )
        return self._overlay

    def _actions_row(self) -> ft.Control:
        buttons = [
            ft.IconButton(
                icon=ft.Icons.PLAY_ARROW_ROUNDED,
                icon_color=ft.Colors.WHITE,
                icon_size=18,
                tooltip="Смотреть",
                on_click=self._play,
            ),
            ft.IconButton(
                icon=ft.Icons.DOWNLOAD_ROUNDED,
                icon_color=ft.Colors.WHITE,
                icon_size=18,
                tooltip="Скачать",
                on_click=self._download,
            ),
        ]
        if self.item.content_type != "music":
            buttons.append(
                ft.IconButton(
                    icon=ft.Icons.MUSIC_NOTE_ROUNDED,
                    icon_color=COLORS["muted"],
                    icon_size=18,
                    tooltip="Скачать только звук",
                    on_click=self._download_audio,
                )
            )
        return ft.Row(controls=buttons, spacing=0, alignment=ft.MainAxisAlignment.START)

    # ------------------------------------------------------------------ #
    def _hover(self, e: ft.HoverEvent) -> None:
        hovering = e.data == "true" or e.data is True
        self.bgcolor = COLORS["surface"] if hovering else None
        self.scale = 1.02 if hovering else 1.0
        self._overlay.opacity = 1 if hovering else 0
        self.update()

    def _play(self, e=None) -> None:
        if self._on_play:
            self._on_play(self.item)

    def _download(self, e=None) -> None:
        # stop_propagation недоступен — гасим всплытие, обнуляя обработчик клика
        if self._on_download:
            self._on_download(self.item)

    def _download_audio(self, e=None) -> None:
        if self._on_download:
            audio_item = MediaItem.from_dict(self.item.to_dict())
            audio_item.extra["audio_only"] = True
            self._on_download(audio_item)
