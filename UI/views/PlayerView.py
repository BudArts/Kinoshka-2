"""Экран просмотра — упрощён, без серых контейнеров."""

from __future__ import annotations

import logging
import time
from typing import List, Optional

import flet as ft

from config import settings
from core.media import MediaItem
from UI.components.Common import GradientButton, OutlineButton, SectionTitle, StatusChip
from UI.themes.DarkTheme import COLORS, FONT_BOLD, brand_gradient
from UI.views.BaseView import BaseView

log = logging.getLogger(__name__)


class PlayerView(BaseView):
    title = "Просмотр"

    def __init__(self, session, app):
        super().__init__(session, app)
        self.item: Optional[MediaItem] = None
        self._started_at: Optional[float] = None
        self._watched_seconds: int = 0
        self._last_position: int = 0

    def on_show(self, item: Optional[MediaItem] = None) -> None:
        if item is not None:
            self.item = item
        if self.item is None:
            self.show_empty("Нечего показывать", "Выберите видео в любом разделе.")
            return
        self._open(self.item)

    def on_hide(self) -> None:
        self._flush_watch_stats()

    def _open(self, item: MediaItem) -> None:
        self._started_at = None
        self._watched_seconds = 0
        self._last_position = int(item.extra.get("resume_position") or 0)

        if item.local_path:
            self._render(item, item.local_path, is_local=True)
            return
        if item.stream_url:
            self._render(item, item.stream_url, is_local=False)
            return

        self.show_loading("Готовим видео…")
        self.run_async(
            work=lambda: self._resolve_stream(item),
            on_done=lambda url: self._render(item, url, is_local=False),
            loading_text=None,
        )

    def _resolve_stream(self, item: MediaItem) -> Optional[str]:
        provider = self.session.provider_for(item.content_type)
        quality = settings.get("preferred_quality", "720p")
        try:
            return provider.get_stream_url(item.url or item.id, quality=quality)
        except Exception as exc:
            log.warning("Не удалось получить поток: %s", exc)
            return None

    def _render(self, item: MediaItem, stream_url, is_local: bool = False) -> None:
        if isinstance(stream_url, Exception):
            stream_url = None

        # Плеер — пробуем flet_video, если не вышло — показываем превью с кнопкой
        player_box = self._build_player(item, stream_url, is_local)

        self.set_controls(
            [
                self._toolbar(),
                player_box,
                self._info_block(item),
                self._related_placeholder(item),
            ]
        )
        self._started_at = time.monotonic()
        self._load_related(item)

    def _build_player(self, item: MediaItem, stream_url: Optional[str], is_local: bool) -> ft.Control:
        # Если есть поток — пробуем видео, иначе — красивый превью-блок
        if stream_url:
            try:
                import flet_video as ftv

                video = ftv.Video(
                    playlist=[ftv.VideoMedia(resource=stream_url)],
                    autoplay=settings.get("autoplay", True),
                    volume=int(settings.get("default_volume", 80)),
                    show_controls=True,
                    aspect_ratio=16 / 9,
                    fit=ft.BoxFit.CONTAIN,
                    expand=True,
                )
                return ft.Container(
                    content=video,
                    bgcolor=ft.Colors.BLACK,
                    border_radius=16,
                    height=self._player_height(),
                    clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                )
            except Exception as exc:
                log.debug("flet_video не удалось: %s", exc)

        # Fallback — превью с градиентом, без серых дыр
        thumb = item.thumbnail
        placeholder = ft.Container(
            width=self.app.content_width - 48,
            height=self._player_height(),
            border_radius=16,
            gradient=brand_gradient(),
            alignment=ft.Alignment.CENTER,
            content=ft.Column(
                controls=[
                    ft.Icon(ft.Icons.PLAY_CIRCLE_FILL, size=72, color=ft.Colors.WHITE),
                    ft.Text(item.title, size=16, color=ft.Colors.WHITE, text_align=ft.TextAlign.CENTER, max_lines=2, width=400),
                    ft.Text("Нажмите «Открыть в браузере» или «Скачать»", size=13, color=ft.Colors.with_opacity(0.8, ft.Colors.WHITE)),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=12,
            ),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        )

        if thumb:
            # Кладём градиент под картинку, чтобы не было серого при ошибке загрузки
            return ft.Container(
                width=self.app.content_width - 48,
                height=self._player_height(),
                border_radius=16,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                content=ft.Stack(
                    controls=[
                        placeholder,
                        ft.Image(src=thumb, width=self.app.content_width - 48, height=self._player_height(), fit=ft.BoxFit.COVER, border_radius=16, error_content=ft.Container()),
                    ]
                ),
            )
        return placeholder

    def _player_height(self) -> int:
        width = max(self.app.content_width - 48, 320)
        return int(min(width / (16 / 9), max((self.page.height or 700) * 0.55, 280)))

    def _toolbar(self) -> ft.Control:
        return ft.Row(
            controls=[
                ft.IconButton(icon=ft.Icons.ARROW_BACK_ROUNDED, icon_color=ft.Colors.WHITE, tooltip="Назад", on_click=lambda e: self.app.go_back()),
                ft.Text("Просмотр", size=16, color=COLORS["muted"]),
            ],
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _info_block(self, item: MediaItem) -> ft.Control:
        chips: List[ft.Control] = []
        if item.author:
            chips.append(StatusChip(item.author, COLORS["gradient2"], ft.Icons.PERSON_ROUNDED))
        if item.view_count:
            chips.append(StatusChip(f"{item.views_human} просмотров", COLORS["muted"], ft.Icons.VISIBILITY_ROUNDED))
        if item.duration:
            chips.append(StatusChip(item.duration_human, COLORS["muted"], ft.Icons.SCHEDULE_ROUNDED))
        chips.append(StatusChip(item.platform.upper(), COLORS["muted"], ft.Icons.PUBLIC_ROUNDED))

        actions: List[ft.Control] = [
            GradientButton("Скачать", icon=ft.Icons.DOWNLOAD_ROUNDED, on_click=lambda e: self.app.download_item(item)),
        ]
        if item.content_type != "music":
            actions.append(OutlineButton("Только звук", icon=ft.Icons.MUSIC_NOTE_ROUNDED, on_click=lambda e: self.app.download_item(item, audio_only=True)))
        actions.append(OutlineButton("Открыть в браузере", icon=ft.Icons.OPEN_IN_NEW_ROUNDED, on_click=lambda e: self.page.launch_url(item.url)))

        controls: List[ft.Control] = [
            ft.Text(item.title, size=22, color=ft.Colors.WHITE, font_family=FONT_BOLD, max_lines=3),
            ft.Row(chips, spacing=8, wrap=True),
            ft.Row(actions, spacing=10, wrap=True),
        ]

        if item.description:
            controls.append(
                ft.Container(
                    content=ft.Text(item.description[:1500], size=13, color=COLORS["muted"], selectable=True),
                    padding=14,
                    border_radius=12,
                    bgcolor=COLORS["surface"],
                )
            )

        return ft.Column(controls=controls, spacing=14, tight=True)

    def _related_placeholder(self, item: MediaItem) -> ft.Control:
        self._related_box = ft.Column(controls=[SectionTitle("Смотрите также")], spacing=12, tight=True)
        return ft.Container(content=self._related_box, bgcolor=ft.Colors.TRANSPARENT)

    def _load_related(self, item: MediaItem) -> None:
        def render(items):
            if isinstance(items, Exception) or not items:
                self._related_box.controls = [ft.Container(content=ft.Text("Похожих видео не нашлось", size=13, color=COLORS["muted"]), padding=12, bgcolor=COLORS["surface"], border_radius=10)]
            else:
                self._related_box.controls = [SectionTitle("Смотрите также"), self.media_row(items, on_play=self._switch_to)]
            self.safe_update()

        provider = self.session.provider_for(item.content_type)
        self.run_async(work=lambda: provider.related(item.url or item.id, limit=10), on_done=render, loading_text=None)

    def _switch_to(self, item: MediaItem) -> None:
        self._flush_watch_stats()
        self.item = item
        self._open(item)

    def _elapsed(self) -> int:
        if self._watched_seconds > 0:
            return self._watched_seconds
        if self._started_at is None:
            return 0
        return int(time.monotonic() - self._started_at)

    def _flush_watch_stats(self) -> None:
        if self.item is None:
            return
        watched = self._elapsed()
        if watched < 10:
            self._started_at = None
            return
        try:
            self.session.track_watch(self.item, watched, self.item.duration)
        except Exception:
            pass
        self._started_at = None
        self._watched_seconds = 0
