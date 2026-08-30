"""Базовый класс экрана.

Каждый экран получает ссылку на AppSession и объект-роутер приложения,
умеет асинхронно подгружать данные в фоновом потоке (чтобы не морозить UI)
и обновлять себя после этого.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, List, Optional

import flet as ft

from core.media import MediaItem
from core.session import AppSession
from UI.components.Common import EmptyState, LoadingState
from UI.components.MediaCard import MediaCard
from UI.themes.DarkTheme import COLORS

log = logging.getLogger(__name__)


class BaseView:
    """Общая логика всех экранов."""

    #: Заголовок экрана (для шапки контента).
    title: str = ""
    #: Тип контента экрана: video / film / music.
    content_type: str = "video"

    def __init__(self, session: AppSession, app):
        self.session = session
        self.app = app
        self.page: ft.Page = app.page

        self.body = ft.Column(
            controls=[],
            spacing=18,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )
        self.content = ft.Container(
            content=self.body,
            padding=ft.Padding(24, 16, 24, 24),
            expand=True,
            bgcolor=COLORS["bg"],
        )

    # ------------------------------------------------------------------ #
    #  Жизненный цикл
    # ------------------------------------------------------------------ #
    def build(self) -> ft.Control:
        """Собрать экран. Вызывается при каждом переходе на него."""
        return self.content

    def on_show(self) -> None:
        """Хук: экран стал видимым. Здесь удобно запускать подгрузку."""

    def on_hide(self) -> None:
        """Хук: с экрана ушли (остановить плеер, отписаться и т.п.)."""

    def on_resize(self, width: int) -> None:
        """Хук адаптивности: ширина окна изменилась."""

    # ------------------------------------------------------------------ #
    #  Работа с содержимым
    # ------------------------------------------------------------------ #
    def set_controls(self, controls: List[ft.Control]) -> None:
        """Заменить содержимое экрана и перерисовать его."""
        self.body.controls = controls
        self.safe_update()

    def show_loading(self, text: str = "Загружаем…") -> None:
        self.set_controls([LoadingState(text)])

    def show_empty(self, title: str, description: str = "", **kwargs) -> None:
        self.set_controls([EmptyState(title, description, **kwargs)])

    def safe_update(self) -> None:
        """update() безопасно даже если экран ещё не на странице."""
        try:
            self.content.update()
        except Exception:
            log.debug("update() до монтирования экрана", exc_info=True)

    # ------------------------------------------------------------------ #
    #  Фоновая загрузка
    # ------------------------------------------------------------------ #
    def run_async(
        self,
        work: Callable[[], object],
        on_done: Callable[[object], None],
        loading_text: Optional[str] = "Загружаем…",
    ) -> None:
        """Выполнить work() в фоне, затем on_done(результат) в UI.

        Сеть (yt-dlp) отвечает медленно, поэтому любые запросы уходят
        в отдельный поток — иначе окно приложения зависает.
        """
        if loading_text is not None:
            self.show_loading(loading_text)

        def worker() -> None:
            try:
                result = work()
            except Exception as exc:
                log.exception("Фоновая задача экрана %s упала", type(self).__name__)
                result = exc
            try:
                on_done(result)
            except Exception:
                log.exception("Обработчик результата упал")

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------ #
    #  Общие блоки
    # ------------------------------------------------------------------ #
    def media_grid(
        self,
        items: List[MediaItem],
        on_play: Optional[Callable[[MediaItem], None]] = None,
        on_download: Optional[Callable[[MediaItem], None]] = None,
    ) -> ft.Control:
        if not items:
            return ft.Container(bgcolor=ft.Colors.TRANSPARENT)
        on_play = on_play or self.app.open_player
        on_download = on_download or self.app.download_item
        card_width = self._card_width()

        if items and items[0].content_type == "music":
            try:
                from UI.components.MusicCard import MusicCard

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
            except Exception:
                pass

        return ft.Container(
            content=ft.Row(
                controls=[MediaCard(item, on_play=on_play, on_download=on_download, width=card_width) for item in items],
                wrap=True,
                spacing=12,
                run_spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            bgcolor=ft.Colors.TRANSPARENT,
        )

    def media_row(
        self,
        items: List[MediaItem],
        on_play: Optional[Callable[[MediaItem], None]] = None,
    ) -> ft.Control:
        if not items:
            return ft.Container(bgcolor=ft.Colors.TRANSPARENT)
        on_play = on_play or self.app.open_player

        # Для музыки — только обложки, без видео
        if items and items[0].content_type == "music":
            try:
                from UI.components.MusicCard import MusicCard

                return ft.Container(
                    content=ft.Row(
                        controls=[MusicCard(item, on_play=on_play, on_download=self.app.download_item, width=160) for item in items],
                        spacing=12,
                        scroll=ft.ScrollMode.AUTO,
                        wrap=False,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    ),
                    bgcolor=ft.Colors.TRANSPARENT,
                )
            except Exception:
                pass

        return ft.Container(
            content=ft.Row(
                controls=[MediaCard(item, on_play=on_play, on_download=self.app.download_item, width=220, compact=True) for item in items],
                spacing=12,
                scroll=ft.ScrollMode.AUTO,
                wrap=False,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            bgcolor=ft.Colors.TRANSPARENT,
        )

    def _card_width(self) -> int:
        """Ширина карточки под текущий размер окна."""
        width = self.app.content_width
        if width < 720:
            return 200
        if width < 1100:
            return 230
        if width < 1500:
            return 250
        return 270

    def offline_notice(self, source: str = "YouTube") -> ft.Control:
        return EmptyState(
            f"{source} недоступен",
            "Похоже, нет соединения с источником. Проверьте интернет и попробуйте обновить.",
            icon=ft.Icons.WIFI_OFF_ROUNDED,
            action_text="Обновить",
            on_action=lambda: self.app.navigate("home"),
        )
