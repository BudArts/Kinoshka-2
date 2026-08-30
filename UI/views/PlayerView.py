"""Просмотр — максимально просто, с плеером внутри программы."""

from __future__ import annotations

import logging
import time
from typing import List, Optional

import flet as ft

from config import settings
from core.media import MediaItem
from UI.components.Common import GradientButton, OutlineButton, SectionTitle, StatusChip
from UI.themes.DarkTheme import COLORS, FONT_BOLD
from UI.views.BaseView import BaseView

log = logging.getLogger(__name__)


class PlayerView(BaseView):
    title = "Просмотр"

    def __init__(self, session, app):
        super().__init__(session, app)
        self.item: Optional[MediaItem] = None
        self._started_at: Optional[float] = None

    def on_show(self, item: Optional[MediaItem] = None) -> None:
        if item is not None:
            self.item = item
        if self.item is None:
            self.show_empty("Нечего показывать", "Выберите видео.")
            return
        self._open(self.item)

    def on_hide(self) -> None:
        self._flush()

    def _open(self, item: MediaItem) -> None:
        self._started_at = None
        if item.local_path:
            self._render(item, item.local_path)
            return
        if item.stream_url:
            self._render(item, item.stream_url)
            return
        self.show_loading("Получаем ссылку…")
        self.run_async(work=lambda: self._resolve(item), on_done=lambda url: self._render(item, url), loading_text=None)

    def _resolve(self, item: MediaItem) -> Optional[str]:
        provider = self.session.provider_for(item.content_type)
        try:
            return provider.get_stream_url(item.url or item.id, quality=settings.get("preferred_quality", "720p"))
        except Exception as exc:
            log.warning("resolve fail: %s", exc)
            return None

    def _render(self, item: MediaItem, stream_url) -> None:
        if isinstance(stream_url, Exception):
            stream_url = None

        # Плеер
        if stream_url:
            try:
                import flet_video as ftv

                video = ftv.Video(
                    playlist=[ftv.VideoMedia(resource=stream_url)],
                    autoplay=True,
                    volume=int(settings.get("default_volume", 80)),
                    show_controls=True,
                    aspect_ratio=16 / 9,
                    fit=ft.BoxFit.CONTAIN,
                )
                player = ft.Container(content=video, bgcolor=ft.Colors.BLACK, height=400)
            except Exception as exc:
                log.debug("video fail %s", exc)
                player = ft.Container(
                    bgcolor=COLORS["surface"],
                    height=300,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Column(
                        controls=[
                            ft.Icon(ft.Icons.ERROR_OUTLINE, color=COLORS["error"], size=48),
                            ft.Text("Не удалось запустить плеер, откройте в браузере", color=COLORS["muted"], text_align=ft.TextAlign.CENTER),
                            ft.ElevatedButton(content=ft.Text("Открыть в браузере"), on_click=lambda e: self.page.launch_url(item.url)),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=10,
                    ),
                )
        else:
            player = ft.Container(
                bgcolor=COLORS["surface"],
                height=300,
                alignment=ft.Alignment.CENTER,
                content=ft.Column(
                    controls=[
                        ft.Icon(ft.Icons.VIDEOCAM_OFF_ROUNDED, color=COLORS["muted"], size=48),
                        ft.Text("Поток не найден. Попробуйте скачать или открыть в браузере.", color=COLORS["muted"], text_align=ft.TextAlign.CENTER),
                        ft.Row(
                            controls=[
                                GradientButton("Скачать", icon=ft.Icons.DOWNLOAD_ROUNDED, on_click=lambda e: self.app.download_item(item)),
                                OutlineButton("Открыть в браузере", icon=ft.Icons.OPEN_IN_NEW_ROUNDED, on_click=lambda e: self.page.launch_url(item.url)),
                            ],
                            spacing=10,
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=12,
                ),
            )

        self.set_controls([self._toolbar(), player, self._info(item), self._related_placeholder()])

        self._started_at = time.monotonic()
        self._load_related(item)

    def _toolbar(self):
        return ft.Row(
            controls=[
                ft.IconButton(icon=ft.Icons.ARROW_BACK_ROUNDED, icon_color=ft.Colors.WHITE, on_click=lambda e: self.app.go_back()),
                ft.Text("Просмотр", size=14, color=COLORS["muted"]),
            ],
            spacing=6,
        )

    def _info(self, item: MediaItem):
        chips = []
        if item.author:
            chips.append(StatusChip(item.author, COLORS["gradient2"], ft.Icons.PERSON_ROUNDED))
        if item.duration:
            chips.append(StatusChip(item.duration_human, COLORS["muted"], ft.Icons.SCHEDULE_ROUNDED))
        chips.append(StatusChip(item.platform.upper(), COLORS["muted"], ft.Icons.PUBLIC_ROUNDED))

        actions = [
            GradientButton("Смотреть", icon=ft.Icons.PLAY_ARROW_ROUNDED, on_click=lambda e: self._open(item)),
            OutlineButton("Скачать", icon=ft.Icons.DOWNLOAD_ROUNDED, on_click=lambda e: self.app.download_item(item)),
            OutlineButton("Открыть в браузере", icon=ft.Icons.OPEN_IN_NEW_ROUNDED, on_click=lambda e: self.page.launch_url(item.url)),
        ]

        controls = [
            ft.Text(item.title, size=20, color=ft.Colors.WHITE, font_family=FONT_BOLD, max_lines=3),
            ft.Row(chips, spacing=8, wrap=True),
            ft.Row(actions, spacing=8, wrap=True),
        ]
        if item.description:
            controls.append(ft.Container(content=ft.Text(item.description[:1200], size=13, color=COLORS["muted"], selectable=True), bgcolor=COLORS["surface"], padding=12, border_radius=8))

        return ft.Column(controls=controls, spacing=10, tight=True)

    def _related_placeholder(self):
        self._related_box = ft.Column(controls=[SectionTitle("Смотрите также")], spacing=10, tight=True)
        return ft.Container(content=self._related_box, bgcolor=ft.Colors.TRANSPARENT, padding=ft.Padding(0, 12, 0, 0))

    def _load_related(self, item: MediaItem):
        def render(items):
            if isinstance(items, Exception) or not items:
                self._related_box.controls = [SectionTitle("Смотрите также"), ft.Text("Нет похожих", size=12, color=COLORS["muted"])]
            else:
                self._related_box.controls = [SectionTitle("Смотрите также"), self.media_row(items, on_play=lambda it: self.app.open_player(it))]
            self.safe_update()

        provider = self.session.provider_for(item.content_type)
        self.run_async(work=lambda: provider.related(item.url or item.id, limit=8), on_done=render, loading_text=None)

    def _elapsed(self) -> int:
        if self._started_at is None:
            return 0
        return int(time.monotonic() - self._started_at)

    def _flush(self):
        if self.item is None:
            return
        watched = self._elapsed()
        if watched < 10:
            return
        try:
            self.session.track_watch(self.item, watched, self.item.duration)
        except Exception:
            pass
        self._started_at = None
