"""Боковая навигация — максимально просто."""

from __future__ import annotations

from typing import Callable, List, Optional

import flet as ft

from UI.themes.DarkTheme import COLORS, FONT_BOLD

NAV_ITEMS = [
    (ft.Icons.HOME_ROUNDED, "Главная", "home"),
    (ft.Icons.ONDEMAND_VIDEO_OUTLINED, "Видео", "video"),
    (ft.Icons.CAMERA_ROLL_ROUNDED, "Фильмы и сериалы", "films"),
    (ft.Icons.MUSIC_NOTE_SHARP, "Музыка", "music"),
    (ft.Icons.VIDEO_LIBRARY, "Мои видео", "my_video"),
    (ft.Icons.VIDEO_FILE, "Мои фильмы", "my_films"),
    (ft.Icons.LIBRARY_MUSIC, "Моя музыка", "my_music"),
    (ft.Icons.HISTORY_ROUNDED, "История", "history"),
    (ft.Icons.SETTINGS_ROUNDED, "Настройки", "settings"),
]

EXPANDED_WIDTH = 220
COLLAPSED_WIDTH = 64


class NavLayout:
    def __init__(self, icon: str, text: str, route: str, navigator: "Navigator", selected: bool = False):
        self._text = text
        self._route = route
        self._navigator = navigator
        self._selected = selected

        self._icon_control = ft.Icon(icon, color=ft.Colors.WHITE if selected else COLORS["muted"], size=20)
        self._label = ft.Text(text, color=ft.Colors.WHITE if selected else COLORS["muted"], size=13, max_lines=2, font_family=FONT_BOLD if selected else "A", width=120)

        self.layout = ft.Container(
            content=ft.Row(controls=[self._icon_control, self._label], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            border_radius=8,
            height=44,
            padding=ft.Padding(10, 0, 10, 0),
            bgcolor=COLORS["surface"] if selected else ft.Colors.TRANSPARENT,
            on_click=self._click,
            tooltip=text,
        )

    def set_collapsed(self, collapsed: bool) -> None:
        self._label.visible = not collapsed

    def _click(self, e) -> None:
        self._navigator.select(self._route)

    def select(self) -> None:
        self._selected = True
        self._icon_control.color = ft.Colors.WHITE
        self._label.color = ft.Colors.WHITE
        self._label.font_family = FONT_BOLD
        self.layout.bgcolor = COLORS["surface"]
        self._safe_update()

    def unselect(self) -> None:
        self._selected = False
        self._icon_control.color = COLORS["muted"]
        self._label.color = COLORS["muted"]
        self._label.font_family = "A"
        self.layout.bgcolor = ft.Colors.TRANSPARENT
        self._safe_update()

    def _safe_update(self) -> None:
        try:
            self.layout.update()
        except Exception:
            pass


class Navigator:
    def __init__(self, on_select: Optional[Callable[[str], None]] = None, initial: str = "home"):
        self.on_select = on_select
        self.current = initial
        self._collapsed = False
        self.nav_items: List[NavLayout] = [NavLayout(icon, text, route, self, selected=(route == initial)) for icon, text, route in NAV_ITEMS]
        self.navigator = ft.Container(
            content=ft.Column(controls=[item.layout for item in self.nav_items], spacing=2, scroll=ft.ScrollMode.AUTO, expand=True),
            width=EXPANDED_WIDTH,
            padding=ft.Padding(8, 10, 8, 10),
            bgcolor=COLORS["secondary"],
        )

    def select(self, route: str, notify: bool = True) -> None:
        for item in self.nav_items:
            if item._route == route:
                item.select()
            elif item._selected:
                item.unselect()
        self.current = route
        if notify and self.on_select:
            self.on_select(route)

    def set_collapsed(self, collapsed: bool) -> None:
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        self.navigator.width = COLLAPSED_WIDTH if collapsed else EXPANDED_WIDTH
        for item in self.nav_items:
            item.set_collapsed(collapsed)
        try:
            self.navigator.update()
        except Exception:
            pass

    @property
    def collapsed(self) -> bool:
        return self._collapsed
