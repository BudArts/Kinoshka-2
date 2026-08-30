"""Каркас приложения: маршрутизация, шапка, меню, общие действия.

App — единственный объект, который знает обо всех экранах. Экраны обращаются
к нему за навигацией (navigate), загрузкой (download_item), плеером
(open_player) и уведомлениями (toast).
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

import flet as ft

from config import APP_NAME, APP_VERSION, ensure_dirs, settings
from core.media import MediaItem
from core.session import AppSession
from database.models import User
from UI.components.AppBar import AppBar
from UI.components.Navigation_bar import Navigator
from UI.themes.DarkTheme import COLORS, FONT_BOLD
from UI.views.HistoryView import HistoryView
from UI.views.HomeView import HomeView
from UI.views.LibraryView import LibraryView
from UI.views.FilmsView import FilmsView
from UI.views.MusicView import MusicView
from UI.views.PlayerView import PlayerView
from UI.views.ProfileView import ProfileView
from UI.views.SettingsView import SettingsView
from UI.views.VideoView import VideoView

log = logging.getLogger(__name__)

#: Ширина окна, ниже которой боковое меню сворачивается в иконки.
COLLAPSE_BREAKPOINT = 1000
#: Ширина, ниже которой меню прячется целиком (открывается кнопкой в шапке).
HIDE_BREAKPOINT = 720


class App:
    """Главный контроллер приложения."""

    def __init__(self, page: ft.Page):
        ensure_dirs()
        self.page = page
        self.session = AppSession()

        self._views: Dict[str, object] = {}
        self._history: List[str] = []
        self._current_route: Optional[str] = None
        self._menu_hidden = False

        self._setup_page()

        # Пока профиль не выбран, показываем только экран профилей.
        if self.session.try_restore_session() is None:
            self._show_profile_screen()
        else:
            self._show_main_ui()

    # ================================================================== #
    #  Страница
    # ================================================================== #
    def _setup_page(self) -> None:
        from UI.themes.DarkTheme import DarkTheme

        page = self.page
        page.title = f"{APP_NAME} — видео, фильмы и музыка"
        page.theme = DarkTheme()
        page.theme_mode = ft.ThemeMode.DARK
        page.bgcolor = COLORS["bg"]
        page.padding = 0
        page.spacing = 0
        page.fonts = {
            "A": "fonts/Product Sans/ProductSans-Medium.ttf",
            "B": "fonts/Product Sans/ProductSans-Bold.ttf",
        }
        page.window.min_width = 640
        page.window.min_height = 520
        page.on_resized = self._on_resized
        page.on_close = self._on_close
        # Очищаем overlay от возможных остатков FilePicker из старых версий,
        # чтобы не было красного блока "Unknown control: FilePicker"
        try:
            page.overlay.clear()
        except Exception:
            pass

    @property
    def content_width(self) -> int:
        """Ширина области контента (окно минус боковое меню)."""
        width = int(self.page.width or 1280)
        if self._menu_hidden:
            return width
        return max(width - (72 if self._nav_collapsed() else 225), 320)

    def _nav_collapsed(self) -> bool:
        return (self.page.width or 1280) < COLLAPSE_BREAKPOINT

    # ================================================================== #
    #  Экран профилей
    # ================================================================== #
    def _show_profile_screen(self) -> None:
        """Полноэкранный выбор профиля — без меню и шапки."""
        self.page.appbar = None
        self.page.controls.clear()
        profile_view = ProfileView(self.session, on_logged_in=self._on_logged_in)
        self.page.add(profile_view.build())
        self.page.update()

    def _on_logged_in(self, user: User) -> None:
        self._show_main_ui()
        self.toast(f"С возвращением, {user.name}!")

    def switch_user(self) -> None:
        """Смена аккаунта: остановить экран, разлогиниться, показать выбор."""
        current = self._views.get(self._current_route)
        if current is not None:
            try:
                current.on_hide()
            except Exception:
                pass
        self.session.logout()
        # Экраны хранят данные прошлого профиля — пересоздаём их.
        self._views.clear()
        self._history.clear()
        self._current_route = None
        self._show_profile_screen()

    # ================================================================== #
    #  Основной интерфейс
    # ================================================================== #
    def _show_main_ui(self) -> None:
        user = self.session.user
        user_name = user.name if user else "Профиль"

        self.appbar = AppBar(
            on_profile_click=lambda: self.navigate("settings"),
            on_switch_user=self.switch_user,
            on_settings=lambda: self.navigate("settings"),
            on_menu_toggle=self._toggle_menu,
            user_name=user_name,
        )
        self.page.appbar = self.appbar

        self.navigator = Navigator(on_select=self.navigate, initial="home")
        self.nav_container = ft.Container(
            content=self.navigator.navigator,
            bgcolor=COLORS["secondary"],
            expand=False,
        )

        # Область контента — с тем же фоном, чтобы не было серых дыр
        self.content_area = ft.Container(expand=True, bgcolor=COLORS["bg"])

        self.page.controls.clear()
        self.page.add(
            ft.Row(
                controls=[
                    self.nav_container,
                    ft.VerticalDivider(
                        width=1, color=ft.Colors.with_opacity(0.1, ft.Colors.WHITE)
                    ),
                    self.content_area,
                ],
                expand=True,
                spacing=0,
                vertical_alignment=ft.CrossAxisAlignment.START,
            )
        )

        self._apply_responsive()
        self._sync_vpn_indicator()
        self.navigate(settings.get("start_page_route", "home"), push=False)
        self.page.update()

    # ================================================================== #
    #  Навигация
    # ================================================================== #
    def _view_for(self, route: str):
        """Ленивое создание экранов: создаём только то, что открыли."""
        if route in self._views:
            return self._views[route]

        factories = {
            "home": lambda: HomeView(self.session, self),
            "video": lambda: VideoView(self.session, self),
            "films": lambda: FilmsView(self.session, self),
            "music": lambda: MusicView(self.session, self),
            "history": lambda: HistoryView(self.session, self),
            "settings": lambda: SettingsView(self.session, self),
            "player": lambda: PlayerView(self.session, self),
            "my_video": lambda: LibraryView(self.session, self, "video", "Мои видео"),
            "my_films": lambda: LibraryView(self.session, self, "film", "Мои фильмы"),
            "my_music": lambda: LibraryView(self.session, self, "music", "Моя музыка"),
        }
        factory = factories.get(route)
        if factory is None:
            return None

        view = factory()
        self._views[route] = view
        return view

    def navigate(self, route: str, push: bool = True, **kwargs) -> None:
        """Перейти на экран. Дополнительные аргументы уходят в on_show()."""
        view = self._view_for(route)
        if view is None:
            log.warning("Неизвестный маршрут: %s", route)
            return

        # Уведомляем прошлый экран, что он скрыт (плеер остановится и т.п.).
        previous = self._views.get(self._current_route)
        if previous is not None and previous is not view:
            try:
                previous.on_hide()
            except Exception:
                log.debug("on_hide() упал", exc_info=True)

        if push and self._current_route and self._current_route != route:
            self._history.append(self._current_route)
        self._current_route = route

        self.content_area.content = view.build()
        try:
            self.content_area.update()
        except Exception:
            pass

        # Подсветить пункт меню (player/profile пунктов не имеют).
        if hasattr(self, "navigator"):
            self.navigator.select(route, notify=False)

        try:
            view.on_show(**kwargs)
        except TypeError:
            # Экран не принимает переданные аргументы — вызываем без них.
            view.on_show()
        except Exception:
            log.exception("Ошибка при открытии экрана %s", route)

    def go_back(self) -> None:
        """Вернуться на предыдущий экран."""
        route = self._history.pop() if self._history else "home"
        self.navigate(route, push=False)

    # ================================================================== #
    #  Общие действия
    # ================================================================== #
    def open_player(self, item: MediaItem) -> None:
        """Открыть плеер для элемента."""
        self.navigate("player", item=item)

    def download_item(self, item: MediaItem, audio_only: Optional[bool] = None) -> None:
        """Поставить элемент в очередь загрузки и сообщить пользователю."""
        if not self.session.is_authenticated:
            return
        if audio_only is None:
            audio_only = bool(item.extra.get("audio_only"))

        collection_id = self.session.download(item, audio_only=audio_only)
        if collection_id is None:
            self.toast("Не удалось начать загрузку", error=True)
            return

        target = "Моя музыка" if audio_only else (
            "Мои фильмы" if item.content_type in ("film", "series") else "Мои видео"
        )
        self.toast(f"«{item.title[:40]}…» в очереди. Прогресс — в разделе «{target}»")

    def toast(self, message: str, error: bool = False) -> None:
        """Всплывающее уведомление внизу окна."""
        try:
            self.page.open(
                ft.SnackBar(
                    content=ft.Text(message, color=ft.Colors.WHITE),
                    bgcolor=COLORS["error"] if error else COLORS["surface_alt"],
                    duration=3500,
                )
            )
        except Exception:
            log.debug("Не удалось показать уведомление: %s", message)

    # ================================================================== #
    #  Адаптивность
    # ================================================================== #
    def _on_resized(self, e) -> None:
        self._apply_responsive()
        view = self._views.get(self._current_route)
        if view is not None:
            try:
                view.on_resize(self.content_width)
            except Exception:
                pass

    def _apply_responsive(self) -> None:
        """Свернуть/спрятать меню в зависимости от ширины окна."""
        if not hasattr(self, "navigator"):
            return
        width = self.page.width or 1280

        should_hide = width < HIDE_BREAKPOINT
        if should_hide != self._menu_hidden:
            self._menu_hidden = should_hide
            self.nav_container.visible = not should_hide
            try:
                self.nav_container.update()
            except Exception:
                pass

        self.navigator.set_collapsed(width < COLLAPSE_BREAKPOINT)

    def _toggle_menu(self) -> None:
        """Кнопка-гамбургер в шапке."""
        self._menu_hidden = not self._menu_hidden
        self.nav_container.visible = not self._menu_hidden
        try:
            self.nav_container.update()
        except Exception:
            pass

    # ================================================================== #
    def _sync_vpn_indicator(self) -> None:
        """Показать в шапке текущее состояние туннеля и следить за ним."""
        if not settings.get("vpn_enabled"):
            self.appbar.set_vpn_status("off")
        elif self.session.vpn.is_connected:
            self.appbar.set_vpn_status("connected", self.session.vpn.active_config)
        else:
            self.appbar.set_vpn_status("disconnected")

        self.session.vpn.add_listener(
            lambda status, name: self.appbar.set_vpn_status(status, name)
        )

    def _on_close(self, e) -> None:
        """Корректное завершение: остановить загрузки, закрыть БД и туннель."""
        try:
            self.session.shutdown()
        except Exception:
            log.debug("Ошибка при завершении", exc_info=True)
