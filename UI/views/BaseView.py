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

        #: Контейнер, в который экран кладёт своё содержимое.
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
        """Адаптивная сетка карточек: количество колонок зависит от ширины."""
        on_play = on_play or self.app.open_player
        on_download = on_download or self.app.download_item

        card_width = self._card_width()
        return ft.Row(
            controls=[
                MediaCard(item, on_play=on_play, on_download=on_download, width=card_width)
                for item in items
            ],
            wrap=True,
            spacing=12,
            run_spacing=12,
            # По верху — иначе карточки разной высоты дают рваные ряды.
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

    def media_row(
        self,
        items: List[MediaItem],
        on_play: Optional[Callable[[MediaItem], None]] = None,
    ) -> ft.Control:
        """Горизонтальная карусель (для блоков «Продолжить смотреть» и т.п.)."""
        on_play = on_play or self.app.open_player
        return ft.Row(
            controls=[
                MediaCard(
                    item,
                    on_play=on_play,
                    on_download=self.app.download_item,
                    width=220,
                    compact=True,
                )
                for item in items
            ],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
            wrap=False,
            vertical_alignment=ft.CrossAxisAlignment.START,
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
        """Подсказка, что источник недоступен без VPN."""
        return EmptyState(
            f"{source} недоступен",
            "Похоже, нет соединения с источником. В России YouTube требует VPN — "
            "включите туннель в настройках или проверьте интернет.",
            icon=ft.Icons.WIFI_OFF_ROUNDED,
            action_text="Открыть настройки VPN",
            on_action=lambda: self.app.navigate("settings"),
        )
