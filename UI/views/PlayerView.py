"""Экран проигрывателя.

Играет и сетевые потоки (прямая ссылка от yt-dlp), и локальные скачанные
файлы. По ходу просмотра копит время и при уходе с экрана отдаёт его
рекомендательному движку — так обновляются интересы.
"""

from __future__ import annotations

import logging
import time
from typing import List, Optional

import flet as ft
import flet_video as ftv

from config import settings
from core.media import MediaItem
from UI.components.Common import GradientButton, OutlineButton, SectionTitle, StatusChip
from UI.themes.DarkTheme import COLORS, FONT_BOLD
from UI.views.BaseView import BaseView

log = logging.getLogger(__name__)


class PlayerView(BaseView):
    """Просмотр одной единицы контента."""

    title = "Просмотр"

    def __init__(self, session, app):
        super().__init__(session, app)
        self.item: Optional[MediaItem] = None
        self._video: Optional[ftv.Video] = None
        self._started_at: Optional[float] = None
        self._watched_seconds: int = 0
        self._last_position: int = 0

    # ------------------------------------------------------------------ #
    def on_show(self, item: Optional[MediaItem] = None) -> None:
        if item is not None:
            self.item = item
        if self.item is None:
            self.show_empty("Нечего показывать", "Выберите видео в любом разделе.")
            return
        self._open(self.item)

    def on_hide(self) -> None:
        """Уходя с экрана — остановить плеер и записать просмотр."""
        self._flush_watch_stats()
        if self._video is not None:
            try:
                self._video.pause()
            except Exception:
                pass
        self._video = None

    # ------------------------------------------------------------------ #
    def _open(self, item: MediaItem) -> None:
        self._started_at = None
        self._watched_seconds = 0
        self._last_position = int(item.extra.get("resume_position") or 0)

        # Локальный файл играем сразу, для сетевого нужно достать поток.
        if item.local_path:
            self._render(item, item.local_path)
            return
        if item.stream_url:
            self._render(item, item.stream_url)
            return

        self.show_loading("Готовим видео…")
        self.run_async(
            work=lambda: self._resolve_stream(item),
            on_done=lambda url: self._render(item, url),
            loading_text=None,
        )

    def _resolve_stream(self, item: MediaItem) -> Optional[str]:
        """Получить прямую ссылку на поток нужного качества."""
        provider = self.session.provider_for(item.content_type)
        quality = settings.get("preferred_quality", "720p")
        try:
            return provider.get_stream_url(item.url or item.id, quality=quality)
        except Exception as exc:
            log.warning("Не удалось получить поток: %s", exc)
            return None

    # ------------------------------------------------------------------ #
    def _render(self, item: MediaItem, stream_url) -> None:
        if isinstance(stream_url, Exception) or not stream_url:
            self.show_empty(
                "Не удалось воспроизвести",
                "Источник не отдал видеопоток. Возможные причины: нужен VPN, "
                "видео удалено или доступно только по подписке. "
                "Можно попробовать скачать его и посмотреть офлайн.",
                icon=ft.Icons.VIDEOCAM_OFF_ROUNDED,
                action_text="Назад",
                on_action=self.app.go_back,
            )
            return

        self._video = ftv.Video(
            playlist=[ftv.VideoMedia(resource=stream_url)],
            autoplay=settings.get("autoplay", True),
            volume=int(settings.get("default_volume", 80)),
            show_controls=True,
            aspect_ratio=16 / 9,
            fit=ft.BoxFit.CONTAIN,
            expand=True,
            filter_quality=ft.FilterQuality.HIGH,
            on_load=self._on_loaded,
            on_complete=self._on_completed,
            on_position_change=self._on_position,
            on_duration_change=self._on_duration,
            on_error=self._on_error,
        )
        self._started_at = time.monotonic()

        player_box = ft.Container(
            content=self._video,
            bgcolor=ft.Colors.BLACK,
            border_radius=16,
            height=self._player_height(),
            expand=False,
        )

        self.set_controls(
            [
                self._toolbar(),
                player_box,
                self._info_block(item),
                self._related_placeholder(item),
            ]
        )
        self._load_related(item)

    def _player_height(self) -> int:
        """Высота плеера под размер окна, но не больше разумного."""
        width = max(self.app.content_width - 48, 320)
        return int(min(width / (16 / 9), max(self.page.height * 0.62, 280)))

    def on_resize(self, width: int) -> None:
        # Пересчитывать высоту плеера на каждый пиксель дорого — только заметные
        # изменения размера окна.
        pass

    # ------------------------------------------------------------------ #
    def _toolbar(self) -> ft.Control:
        return ft.Row(
            controls=[
                ft.IconButton(
                    icon=ft.Icons.ARROW_BACK_ROUNDED,
                    icon_color=ft.Colors.WHITE,
                    tooltip="Назад",
                    on_click=lambda e: self.app.go_back(),
                ),
                ft.Text("Просмотр", size=16, color=COLORS["muted"]),
            ],
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _info_block(self, item: MediaItem) -> ft.Control:
        """Название, автор, кнопки действий и описание."""
        chips: List[ft.Control] = []
        if item.author:
            chips.append(StatusChip(item.author, COLORS["gradient2"], ft.Icons.PERSON_ROUNDED))
        if item.view_count:
            chips.append(
                StatusChip(f"{item.views_human} просмотров", COLORS["muted"],
                           ft.Icons.VISIBILITY_ROUNDED)
            )
        if item.duration:
            chips.append(
                StatusChip(item.duration_human, COLORS["muted"], ft.Icons.SCHEDULE_ROUNDED)
            )
        chips.append(
            StatusChip(item.platform.upper(), COLORS["muted"], ft.Icons.PUBLIC_ROUNDED)
        )

        actions: List[ft.Control] = [
            GradientButton(
                "Скачать",
                icon=ft.Icons.DOWNLOAD_ROUNDED,
                on_click=lambda e: self.app.download_item(item),
            )
        ]
        if item.content_type != "music":
            actions.append(
                OutlineButton(
                    "Только звук",
                    icon=ft.Icons.MUSIC_NOTE_ROUNDED,
                    on_click=lambda e: self.app.download_item(item, audio_only=True),
                )
            )
        actions.append(
            OutlineButton(
                "Открыть в браузере",
                icon=ft.Icons.OPEN_IN_NEW_ROUNDED,
                on_click=lambda e: self.page.launch_url(item.url),
            )
        )

        controls: List[ft.Control] = [
            ft.Text(item.title, size=22, color=ft.Colors.WHITE, font_family=FONT_BOLD,
                    max_lines=3),
            ft.Row(chips, spacing=8, wrap=True),
            ft.Row(actions, spacing=10, wrap=True),
        ]

        if item.description:
            controls.append(
                ft.Container(
                    content=ft.Text(
                        item.description[:1500],
                        size=13,
                        color=COLORS["muted"],
                        selectable=True,
                    ),
                    padding=14,
                    border_radius=12,
                    bgcolor=COLORS["surface"],
                )
            )

        return ft.Column(controls=controls, spacing=14, tight=True)

    # ------------------------------------------------------------------ #
    def _related_placeholder(self, item: MediaItem) -> ft.Control:
        self._related_box = ft.Column(
            controls=[SectionTitle("Смотрите также")],
            spacing=12,
        )
        return self._related_box

    def _load_related(self, item: MediaItem) -> None:
        """Похожее подгружаем фоном — оно не блокирует просмотр."""

        def render(items):
            if isinstance(items, Exception) or not items:
                self._related_box.controls = []
            else:
                self._related_box.controls = [
                    SectionTitle("Смотрите также"),
                    self.media_row(items, on_play=self._switch_to),
                ]
            self.safe_update()

        provider = self.session.provider_for(item.content_type)
        self.run_async(
            work=lambda: provider.related(item.url or item.id, limit=10),
            on_done=render,
            loading_text=None,
        )

    def _switch_to(self, item: MediaItem) -> None:
        """Переключиться на другое видео, не выходя из плеера."""
        self._flush_watch_stats()
        self.item = item
        self._open(item)

    # ------------------------------------------------------------------ #
    #  Учёт просмотра
    # ------------------------------------------------------------------ #
    def _on_loaded(self, e) -> None:
        self._started_at = time.monotonic()

    def _on_error(self, e) -> None:
        """Поток отвалился по ходу — сообщаем и предлагаем скачать."""
        self.app.toast(
            "Воспроизведение прервано. Попробуйте другое качество или скачайте видео.",
            error=True,
        )

    def _on_duration(self, e) -> None:
        """Плеер узнал длительность — уточняем её у элемента."""
        duration = self._event_seconds(e)
        if duration and self.item and not self.item.duration:
            self.item.duration = duration

    def _on_position(self, e) -> None:
        """Позиция воспроизведения. Это точнее таймера: пауза и перемотка
        не засчитываются как просмотр."""
        position = self._event_seconds(e)
        if position is None:
            return
        # Считаем только движение вперёд не более чем на 5 секунд за событие —
        # так перемотка вперёд не накручивает время просмотра.
        delta = position - self._last_position
        if 0 < delta <= 5:
            self._watched_seconds += int(delta)
        self._last_position = int(position)

    @staticmethod
    def _event_seconds(e) -> Optional[float]:
        """Достать секунды из события плеера (может прийти мс или timedelta)."""
        value = getattr(e, "position", None)
        if value is None:
            value = getattr(e, "duration", None)
        if value is None:
            value = getattr(e, "data", None)
        if value is None:
            return None
        if hasattr(value, "total_seconds"):
            return value.total_seconds()
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        # Значения больше суток почти наверняка приходят в миллисекундах.
        return number / 1000 if number > 86_400 else number

    def _on_completed(self, e) -> None:
        """Видео доиграло до конца — самый сильный сигнал для интересов."""
        if self.item:
            total = self.item.duration or self._elapsed()
            self.session.track_watch(self.item, total, total)
            self._started_at = None
            self._watched_seconds = 0
            self._last_position = 0

    def _elapsed(self) -> int:
        """Сколько реально просмотрено.

        Основной источник — события позиции плеера; если их не было
        (например, плеер не успел их прислать), берём время на экране.
        """
        if self._watched_seconds > 0:
            return self._watched_seconds
        if self._started_at is None:
            return 0
        return int(time.monotonic() - self._started_at)

    def _flush_watch_stats(self) -> None:
        """Записать накопленное время просмотра в историю."""
        if self.item is None:
            return
        watched = self._elapsed()
        # Меньше 10 секунд — это случайный клик, не сигнал вкуса.
        if watched < 10:
            self._started_at = None
            return
        self.session.track_watch(self.item, watched, self.item.duration)
        self._started_at = None
        self._watched_seconds = 0
        self._last_position = 0
