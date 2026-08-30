"""Верхняя панель: логотип, статус VPN и меню профиля."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from UI.themes.DarkTheme import COLORS, FONT_BOLD, brand_gradient


def gradient_text(
    text: str, size: int = 28, font_family: str = FONT_BOLD
) -> ft.Control:
    """Текст, залитый фирменным градиентом.

    Реализовано штатным ShaderMask: внешняя библиотека flet-gradient-text
    несовместима с Flet 0.86 (использует удалённый API ft.margin.only).
    BlendMode.SRC_IN заливает градиентом непрозрачные пиксели текста,
    поэтому сам текст должен быть белым.
    """
    return ft.ShaderMask(
        shader=ft.LinearGradient(
            begin=ft.Alignment.TOP_LEFT,
            end=ft.Alignment.BOTTOM_RIGHT,
            colors=[COLORS["gradient1"], COLORS["gradient2"]],
        ),
        blend_mode=ft.BlendMode.SRC_IN,
        content=ft.Text(
            text,
            size=size,
            color=ft.Colors.WHITE,
            font_family=font_family,
            no_wrap=True,
        ),
    )


class AppBar(ft.AppBar):
    """Панель приложения — без упоминаний VPN, как просил пользователь."""

    def __init__(
        self,
        on_profile_click: Optional[Callable] = None,
        on_switch_user: Optional[Callable] = None,
        on_settings: Optional[Callable] = None,
        on_menu_toggle: Optional[Callable] = None,
        user_name: str = "Профиль",
    ):
        self._on_profile_click = on_profile_click

        title: ft.Control = gradient_text("K i n o s h k a", size=28)

        # Индикатор VPN убран из интерфейса, но оставили заглушки методов для совместимости
        self.vpn_icon = ft.Icon(ft.Icons.SHIELD_OUTLINED, size=18, color=COLORS["muted"], visible=False)
        self.vpn_text = ft.Text("", size=12, color=COLORS["muted"], visible=False)
        self.vpn_indicator = ft.Container(visible=False)

        self.profile_button = ft.PopupMenuButton(
            content=ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Container(
                            width=32,
                            height=32,
                            border_radius=16,
                            gradient=brand_gradient(),
                            alignment=ft.Alignment.CENTER,
                            content=ft.Text(
                                (user_name or "?")[:1].upper(),
                                color=ft.Colors.WHITE,
                                size=15,
                                font_family=FONT_BOLD,
                            ),
                        ),
                        ft.Text(user_name, color=ft.Colors.WHITE, size=14),
                        ft.Icon(ft.Icons.ARROW_DROP_DOWN, color=ft.Colors.WHITE, size=18),
                    ],
                    spacing=8,
                    tight=True,
                ),
                padding=ft.Padding(8, 4, 8, 4),
                border_radius=20,
            ),
            items=[
                ft.PopupMenuItem(
                    content=ft.Text("Мой профиль"),
                    icon=ft.Icons.PERSON_ROUNDED,
                    on_click=lambda e: on_profile_click() if on_profile_click else None,
                ),
                ft.PopupMenuItem(
                    content=ft.Text("Сменить аккаунт"),
                    icon=ft.Icons.SWITCH_ACCOUNT_ROUNDED,
                    on_click=lambda e: on_switch_user() if on_switch_user else None,
                ),
                ft.PopupMenuItem(),
                ft.PopupMenuItem(
                    content=ft.Text("Настройки"),
                    icon=ft.Icons.SETTINGS_ROUNDED,
                    on_click=lambda e: on_settings() if on_settings else None,
                ),
            ],
        )

        leading = None
        if on_menu_toggle:
            leading = ft.IconButton(
                icon=ft.Icons.MENU_ROUNDED,
                icon_color=ft.Colors.WHITE,
                tooltip="Меню",
                on_click=lambda e: on_menu_toggle(),
            )

        super().__init__(
            leading=leading,
            leading_width=56 if leading else None,
            title=title,
            center_title=True,
            toolbar_height=58,
            bgcolor=COLORS["dark_gray"],
            actions=[
                self.profile_button,
                ft.Container(width=10),
            ],
        )

    def set_vpn_status(self, status: str, name: Optional[str] = None) -> None:
        # Заглушка — VPN теперь невидим в UI, но метод оставлен чтобы не падали вызовы
        pass

    def set_user(self, user_name: str) -> None:
        row = self.profile_button.content.content
        avatar, label = row.controls[0], row.controls[1]
        avatar.content.value = (user_name or "?")[:1].upper()
        label.value = user_name
        try:
            self.profile_button.update()
        except Exception:
            pass
