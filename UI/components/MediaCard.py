"""Карточка единицы контента для лент и результатов поиска."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from core.media import MediaItem
from UI.themes.DarkTheme import ANIM_FAST, COLORS, FONT_BOLD, brand_gradient


class MediaCard(ft.Container):
    """Плитка видео/фильма/трека: обложка, длительность, заголовок, действия.

    Высота текстового блока фиксирована, поэтому карточки в сетке
    выравниваются ровно независимо от длины названия.
    """

    def __init__(
        self,
        item: MediaItem,
        on_play: Optional[Callable[[MediaItem], None]] = None,
        on_download: Optional[Callable[[MediaItem], None]] = None,
        width: int = 260,
        compact: bool = False,
        square: Optional[bool] = None,
    ):
        self.item = item
        self._on_play = on_play
        self._on_download = on_download
        self._compact = compact

        # Музыкальные обложки квадратные, видео — 16:9.
        if square is None:
            square = bool(item.extra.get("square_cover"))
        self._square = square

        cover_height = width if square else int(width * 9 / 16)

        self._cover = self._build_cover(width, cover_height)
        self._title = ft.Text(
            item.title,
            size=14,
            color=ft.Colors.WHITE,
            max_lines=2,
            overflow=ft.TextOverflow.ELLIPSIS,
            font_family=FONT_BOLD,
        )
        self._subtitle = ft.Text(
            self._subtitle_text(),
            size=12,
            color=COLORS["muted"],
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

        # Фиксированная высота под текст: две строки заголовка + подпись.
        info_block = ft.Container(
            content=ft.Column(
                controls=[self._title, self._subtitle],
                spacing=3,
                tight=True,
            ),
            height=58,
            padding=ft.Padding(2, 0, 2, 0),
        )

        body: list[ft.Control] = [self._cover, info_block]
        if not compact:
            body.append(self._actions_row())

        super().__init__(
            content=ft.Column(controls=body, spacing=8, tight=True),
            width=width,
            padding=8,
            border_radius=14,
            bgcolor=ft.Colors.TRANSPARENT,
            animate=ANIM_FAST,
            animate_scale=ANIM_FAST,
            on_hover=self._hover,
            on_click=self._play,
            tooltip=item.title,
        )

    # ------------------------------------------------------------------ #
    #  Обложка
    # ------------------------------------------------------------------ #
    def _build_cover(self, width: int, height: int) -> ft.Control:
        """Обложка с бейджем длительности и затемнением при наведении.

        Под изображением всегда лежит фирменный градиент, поэтому пока
        превью грузится (или если оно не открылось) не видно серых дыр.
        """
        placeholder = ft.Container(
            width=width,
            height=height,
            border_radius=12,
            gradient=brand_gradient(),
            alignment=ft.Alignment.CENTER,
            content=ft.Icon(self._placeholder_icon(), color=ft.Colors.WHITE, size=38),
        )

        self._overlay = ft.Container(
            width=width,
            height=height,
            border_radius=12,
            bgcolor=ft.Colors.with_opacity(0.45, ft.Colors.BLACK),
            alignment=ft.Alignment.CENTER,
            content=ft.Icon(ft.Icons.PLAY_CIRCLE_FILL, size=50, color=ft.Colors.WHITE),
            opacity=0,
            animate_opacity=ANIM_FAST,
        )

        layers: list[ft.Control] = [placeholder]
        if self.item.thumbnail:
            layers.append(
                ft.Image(
                    src=self.item.thumbnail,
                    width=width,
                    height=height,
                    fit=ft.BoxFit.COVER,
                    border_radius=12,
                    gapless_playback=True,
                    # Ошибку рисуем прозрачной: под ней уже лежит градиент.
                    error_content=ft.Container(width=width, height=height),
                )
            )
        layers.append(self._duration_badge())
        layers.append(self._overlay)

        return ft.Container(
            width=width,
            height=height,
            border_radius=12,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            content=ft.Stack(controls=layers),
        )

    def _placeholder_icon(self) -> str:
        return {
            "music": ft.Icons.MUSIC_NOTE_ROUNDED,
            "film": ft.Icons.MOVIE_ROUNDED,
            "series": ft.Icons.LIVE_TV_ROUNDED,
        }.get(self.item.content_type, ft.Icons.PLAY_CIRCLE_OUTLINE)

    def _duration_badge(self) -> ft.Control:
        """Бейдж длительности. Для неизвестной длительности не рисуем вовсе."""
        if not self.item.duration:
            return ft.Container(width=0, height=0)
        return ft.Container(
            content=ft.Text(self.item.duration_human, size=11, color=ft.Colors.WHITE),
            bgcolor=ft.Colors.with_opacity(0.8, ft.Colors.BLACK),
            padding=ft.Padding(6, 2, 6, 2),
            border_radius=6,
            right=6,
            bottom=6,
        )

    # ------------------------------------------------------------------ #
    def _subtitle_text(self) -> str:
        """Подпись: исполнитель и альбом для музыки, автор и просмотры для видео."""
        item = self.item
        if item.content_type == "music":
            parts = [item.author, item.extra.get("album")]
        else:
            parts = [item.author]
            if item.rating:
                parts.append(f"★ {item.rating:.1f}")
            elif item.view_count:
                parts.append(item.views_human)
            if item.year:
                parts.append(str(item.year))
        return " • ".join(str(p) for p in parts if p)

    def _actions_row(self) -> ft.Control:
        """Кнопки действий.

        Для музыки основное действие — скачать трек, поэтому лишняя кнопка
        «только звук» там не нужна.
        """
        buttons = [
            ft.IconButton(
                icon=ft.Icons.PLAY_ARROW_ROUNDED,
                icon_color=ft.Colors.WHITE,
                icon_size=18,
                tooltip="Слушать" if self.item.content_type == "music" else "Смотреть",
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
        return ft.Row(controls=buttons, spacing=0)

    # ------------------------------------------------------------------ #
    def _hover(self, e: ft.HoverEvent) -> None:
        hovering = e.data == "true" or e.data is True
        self.bgcolor = COLORS["surface"] if hovering else ft.Colors.TRANSPARENT
        self.scale = 1.02 if hovering else 1.0
        self._overlay.opacity = 1 if hovering else 0
        try:
            self.update()
        except Exception:
            pass

    def _play(self, e=None) -> None:
        if self._on_play:
            self._on_play(self.item)

    def _download(self, e=None) -> None:
        if self._on_download:
            self._on_download(self.item)

    def _download_audio(self, e=None) -> None:
        if self._on_download:
            audio_item = MediaItem.from_dict(self.item.to_dict())
            audio_item.extra["audio_only"] = True
            self._on_download(audio_item)
