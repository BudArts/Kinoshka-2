"""Боковая навигация.

Адаптивна: в широком окне показывает иконки с подписями, в узком
сворачивается до одних иконок (подписи уезжают в подсказки).
"""

from __future__ import annotations

from typing import Callable, List, Optional

import flet as ft

from UI.themes.DarkTheme import ANIM, COLORS, FONT_BOLD, brand_gradient

#: Пункты меню: (иконка, подпись, ключ маршрута).
NAV_ITEMS = [
    (ft.Icons.HOME_ROUNDED, "Главная", "home"),
    (ft.Icons.ONDEMAND_VIDEO_OUTLINED, "Видео", "video"),
    (ft.Icons.CAMERA_ROLL_ROUNDED, "Фильмы и сериалы", "films"),
    (ft.Icons.MUSIC_NOTE_SHARP, "Музыка", "music"),
    (ft.Icons.VIDEO_LIBRARY, "Мои видео", "my_video"),
    (ft.Icons.VIDEO_FILE, "Мои фильмы", "my_films"),
    (ft.Icons.LIBRARY_MUSIC, "Моя музыка", "my_music"),
    (ft.Icons.ELECTRIC_BOLT, "Джарвис", "jarvis"),
    (ft.Icons.HISTORY_ROUNDED, "История", "history"),
    (ft.Icons.SETTINGS_ROUNDED, "Настройки", "settings"),
]

EXPANDED_WIDTH = 225
COLLAPSED_WIDTH = 72


class NavLayout:
    """Один пункт меню с подсветкой выбора и анимацией наведения."""

    def __init__(
        self,
        icon: str,
        text: str,
        route: str,
        navigator: "Navigator",
        selected: bool = False,
    ):
        self._text = text
        self._route = route
        self._icon = icon
        self._navigator = navigator
        self._selected = selected

        self._bar = ft.Container(
            height=38,
            width=8 if selected else 0,
            border_radius=6,
            gradient=brand_gradient(),
            animate=ANIM,
        )
        self._icon_control = ft.Icon(
            icon,
            color=ft.Colors.WHITE if selected else COLORS["muted"],
            size=22,
            animate_scale=ANIM,
        )
        self._label = ft.Text(
            text,
            color=ft.Colors.WHITE if selected else COLORS["muted"],
            size=14,
            max_lines=2,
            overflow=ft.TextOverflow.ELLIPSIS,
            font_family=FONT_BOLD if selected else "A",
            width=120,
            animate_opacity=ANIM,
        )

        self.layout = ft.Container(
            content=ft.Row(
                controls=[self._bar, self._icon_control, self._label],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            border_radius=10,
            height=48,
            padding=ft.Padding(6, 0, 6, 0),
            bgcolor=COLORS["surface"] if selected else None,
            on_hover=self._hover,
            on_click=self._click,
            animate=ANIM,
            tooltip=text,
            data=route,
        )

    # ------------------------------------------------------------------ #
    def set_collapsed(self, collapsed: bool) -> None:
        """Спрятать/показать подписи при смене ширины окна."""
        self._label.visible = not collapsed
        self._label.opacity = 0 if collapsed else 1

    def _hover(self, e: ft.HoverEvent) -> None:
        if self._selected:
            return
        hovering = e.data == "true" or e.data is True
        self._bar.width = 8 if hovering else 0
        self._icon_control.color = ft.Colors.WHITE if hovering else COLORS["muted"]
        self._label.color = ft.Colors.WHITE if hovering else COLORS["muted"]
        self.layout.bgcolor = COLORS["surface_alt"] if hovering else None
        self._safe_update()

    def _click(self, e) -> None:
        self._navigator.select(self._route)

    def select(self) -> None:
        self._selected = True
        self._bar.width = 8
        self._icon_control.color = ft.Colors.WHITE
        self._icon_control.scale = 1.1
        self._label.color = ft.Colors.WHITE
        self._label.font_family = FONT_BOLD
        self.layout.bgcolor = COLORS["surface"]

    def unselect(self) -> None:
        self._selected = False
        self._bar.width = 0
        self._icon_control.color = COLORS["muted"]
        self._icon_control.scale = 1.0
        self._label.color = COLORS["muted"]
        self._label.font_family = "A"
        self.layout.bgcolor = None

    def _safe_update(self) -> None:
        """update() до добавления на страницу бросает исключение — гасим его."""
        try:
            self.layout.update()
        except Exception:
            pass


class Navigator:
    """Боковое меню целиком."""

    def __init__(
        self,
        on_select: Optional[Callable[[str], None]] = None,
        initial: str = "home",
    ):
        self.on_select = on_select
        self.current = initial
        self._collapsed = False

        self.nav_items: List[NavLayout] = [
            NavLayout(icon, text, route, self, selected=(route == initial))
            for icon, text, route in NAV_ITEMS
        ]

        self.navigator = ft.Container(
            content=ft.Column(
                controls=[item.layout for item in self.nav_items],
                spacing=4,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
            width=EXPANDED_WIDTH,
            padding=ft.Padding(10, 12, 10, 12),
            animate=ANIM,
        )

    # ------------------------------------------------------------------ #
    def select(self, route: str, notify: bool = True) -> None:
        """Выбрать пункт меню по ключу маршрута."""
        for item in self.nav_items:
            if item._route == route:
                item.select()
            elif item._selected:
                item.unselect()
            item._safe_update()

        self.current = route
        if notify and self.on_select:
            self.on_select(route)

    def set_collapsed(self, collapsed: bool) -> None:
        """Свернуть меню до иконок (для узких окон)."""
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
