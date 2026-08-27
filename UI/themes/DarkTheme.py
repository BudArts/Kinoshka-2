"""Тёмная тема Kinoshka.

Кроме объекта ft.Theme здесь лежит палитра и вспомогательные фабрики
(градиенты, тени), которыми пользуются все компоненты — чтобы фирменные
цвета не были размазаны хардкодом по экранам.
"""

from __future__ import annotations

import flet as ft

#: Фирменная палитра.
COLORS = {
    "bg": "#1b202b",           # основной фон приложения
    "surface": "#242a38",      # карточки, панели
    "surface_alt": "#2c3444",  # наведение, выделение
    "dark_gray": "#4e586e",    # AppBar, разделители
    "secondary": "#242a38",
    "muted": "#8b94a8",        # второстепенный текст
    "gradient1": "#f54b64",
    "gradient2": "#f78361",
    "success": "#43e97b",
    "warning": "#ffd86f",
    "error": "#ff5468",
}

FONT_REGULAR = "A"
FONT_BOLD = "B"

#: Стандартная анимация интерфейса.
ANIM = ft.Animation(duration=250, curve=ft.AnimationCurve.EASE_OUT)
ANIM_FAST = ft.Animation(duration=150, curve=ft.AnimationCurve.EASE_OUT)


def brand_gradient(
    begin: ft.Alignment | None = None, end: ft.Alignment | None = None
) -> ft.LinearGradient:
    """Фирменный красно-оранжевый градиент."""
    return ft.LinearGradient(
        begin=begin or ft.Alignment.BOTTOM_LEFT,
        end=end or ft.Alignment.TOP_RIGHT,
        colors=[COLORS["gradient1"], COLORS["gradient2"]],
        tile_mode=ft.GradientTileMode.CLAMP,
    )


def card_shadow() -> ft.BoxShadow:
    """Мягкая тень под карточками."""
    return ft.BoxShadow(
        spread_radius=0,
        blur_radius=14,
        color=ft.Colors.with_opacity(0.35, ft.Colors.BLACK),
        offset=ft.Offset(0, 4),
    )


class DarkTheme(ft.Theme):
    """Тёмная тема приложения."""

    #: Палитра доступна и на классе, и на экземпляре.
    _main_colors = COLORS

    def __init__(self):
        self.font_family_name = FONT_REGULAR
        self._main_colors = COLORS

        super().__init__(
            color_scheme_seed=COLORS["gradient1"],
            color_scheme=ft.ColorScheme(
                primary=COLORS["gradient1"],
                secondary=COLORS["gradient2"],
                surface=COLORS["surface"],
                on_surface=ft.Colors.WHITE,
                error=COLORS["error"],
            ),
            font_family=FONT_REGULAR,
            text_theme=ft.TextTheme(
                headline_medium=ft.TextStyle(
                    size=26, color=ft.Colors.WHITE, font_family=FONT_BOLD
                ),
                title_large=ft.TextStyle(
                    size=20, color=ft.Colors.WHITE, font_family=FONT_BOLD
                ),
                title_medium=ft.TextStyle(size=16, color=ft.Colors.WHITE),
                body_medium=ft.TextStyle(size=14, color=ft.Colors.WHITE),
                body_small=ft.TextStyle(size=12, color=COLORS["muted"]),
                label_small=ft.TextStyle(size=11, color=COLORS["muted"]),
            ),
            appbar_theme=ft.AppBarTheme(
                bgcolor=COLORS["dark_gray"],
                color=ft.Colors.WHITE,
                elevation=0,
            ),
            scaffold_bgcolor=COLORS["bg"],
            divider_theme=ft.DividerTheme(color=ft.Colors.with_opacity(0.15, ft.Colors.WHITE)),
            card_theme=ft.CardTheme(color=COLORS["surface"], elevation=0),
            snackbar_theme=ft.SnackBarTheme(
                bgcolor=COLORS["surface_alt"],
                content_text_style=ft.TextStyle(color=ft.Colors.WHITE),
            ),
        )
