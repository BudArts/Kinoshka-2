"""Верхняя панель — максимально просто."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from UI.themes.DarkTheme import COLORS, FONT_BOLD


class AppBar(ft.AppBar):
    def __init__(
        self,
        on_profile_click: Optional[Callable] = None,
        on_switch_user: Optional[Callable] = None,
        on_settings: Optional[Callable] = None,
        on_menu_toggle: Optional[Callable] = None,
        user_name: str = "Профиль",
    ):
        title = ft.Text("Kinoshka", size=24, color=COLORS["gradient1"], font_family=FONT_BOLD)

        self.vpn_icon = ft.Icon(ft.Icons.SHIELD_OUTLINED, visible=False)
        self.vpn_text = ft.Text("", visible=False)
        self.vpn_indicator = ft.Container(visible=False)

        self.profile_button = ft.PopupMenuButton(
            content=ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Container(width=32, height=32, border_radius=16, bgcolor=COLORS["gradient1"], alignment=ft.Alignment.CENTER, content=ft.Text((user_name or "?")[:1].upper(), color=ft.Colors.WHITE, size=15, font_family=FONT_BOLD)),
                        ft.Text(user_name, color=ft.Colors.WHITE, size=14),
                    ],
                    spacing=8,
                    tight=True,
                ),
                padding=ft.Padding(8, 4, 8, 4),
            ),
            items=[
                ft.PopupMenuItem(content=ft.Text("Мой профиль"), icon=ft.Icons.PERSON_ROUNDED, on_click=lambda e: on_profile_click() if on_profile_click else None),
                ft.PopupMenuItem(content=ft.Text("Сменить аккаунт"), icon=ft.Icons.SWITCH_ACCOUNT_ROUNDED, on_click=lambda e: on_switch_user() if on_switch_user else None),
                ft.PopupMenuItem(content=ft.Text("Настройки"), icon=ft.Icons.SETTINGS_ROUNDED, on_click=lambda e: on_settings() if on_settings else None),
            ],
        )

        leading = None
        if on_menu_toggle:
            leading = ft.IconButton(icon=ft.Icons.MENU_ROUNDED, icon_color=ft.Colors.WHITE, on_click=lambda e: on_menu_toggle())

        super().__init__(
            leading=leading,
            leading_width=56 if leading else None,
            title=title,
            center_title=True,
            toolbar_height=56,
            bgcolor=COLORS["dark_gray"],
            actions=[self.profile_button, ft.Container(width=8)],
        )

    def set_vpn_status(self, status: str, name: Optional[str] = None) -> None:
        pass

    def set_user(self, user_name: str) -> None:
        try:
            row = self.profile_button.content.content
            avatar, label = row.controls[0], row.controls[1]
            avatar.content.value = (user_name or "?")[:1].upper()
            label.value = user_name
            self.profile_button.update()
        except Exception:
            pass
