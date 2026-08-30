"""Экран профилей — максимально просто."""

from __future__ import annotations

from typing import Callable, List, Optional

import flet as ft

from core.profile_service import ProfileError, ProfileService
from core.recomendation_engine import RecommendationEngine
from core.session import AppSession
from database.models import User
from UI.components.Common import GradientButton, OutlineButton
from UI.themes.DarkTheme import COLORS, FONT_BOLD


class ProfileView:
    def __init__(self, session: AppSession, on_logged_in: Callable[[User], None]):
        self.session = session
        self.on_logged_in = on_logged_in
        self._selected_interests: set[str] = set()
        self.container = ft.Container(expand=True, alignment=ft.Alignment.CENTER, bgcolor=COLORS["bg"], padding=20)

    def build(self) -> ft.Control:
        if ProfileService.is_first_run():
            self.show_create(first_run=True)
        else:
            self.show_picker()
        return self.container

    def _render(self, *controls: ft.Control) -> None:
        self.container.content = ft.Column(controls=list(controls), spacing=16, horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER, scroll=ft.ScrollMode.AUTO)
        try:
            self.container.update()
        except Exception:
            pass

    @staticmethod
    def _logo() -> ft.Control:
        return ft.Column(
            controls=[
                ft.Container(width=64, height=64, border_radius=16, bgcolor=COLORS["gradient1"], alignment=ft.Alignment.CENTER, content=ft.Icon(ft.Icons.MOVIE_FILTER_ROUNDED, size=32, color=ft.Colors.WHITE)),
                ft.Text("Kinoshka", size=28, color=COLORS["gradient1"], font_family=FONT_BOLD),
            ],
            spacing=8,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def show_picker(self) -> None:
        profiles = ProfileService.list_profiles()
        tiles: List[ft.Control] = [self._profile_tile(user) for user in profiles]
        tiles.append(self._add_tile())
        self._render(
            self._logo(),
            ft.Text("Кто смотрит?", size=20, color=ft.Colors.WHITE, font_family=FONT_BOLD),
            ft.Row(controls=tiles, spacing=16, wrap=True, alignment=ft.MainAxisAlignment.CENTER),
            ft.TextButton("Управление профилями", icon=ft.Icons.MANAGE_ACCOUNTS_ROUNDED, on_click=lambda e: self.show_manage(), style=ft.ButtonStyle(color=COLORS["muted"])),
        )

    def _profile_tile(self, user: User) -> ft.Control:
        avatar = ft.Container(width=90, height=90, border_radius=18, bgcolor=user.color or COLORS["gradient1"], alignment=ft.Alignment.CENTER, content=ft.Text(user.initials, size=32, color=ft.Colors.WHITE, font_family=FONT_BOLD))
        return ft.Container(
            content=ft.Column(controls=[avatar, ft.Text(user.name, size=13, color=ft.Colors.WHITE, max_lines=1)], spacing=8, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            on_click=lambda e, u=user: self._pick(u),
            padding=6,
            border_radius=16,
        )

    def _add_tile(self) -> ft.Control:
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Container(width=90, height=90, border_radius=18, border=ft.Border.all(2, COLORS["dark_gray"]), alignment=ft.Alignment.CENTER, content=ft.Icon(ft.Icons.ADD_ROUNDED, size=36, color=COLORS["muted"])),
                    ft.Text("Новый профиль", size=13, color=COLORS["muted"]),
                ],
                spacing=8,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            on_click=lambda e: self.show_create(),
            padding=6,
            border_radius=16,
        )

    def _pick(self, user: User) -> None:
        if user.has_password:
            self.show_password_prompt(user)
        else:
            self._do_login(user.id, None)

    def show_password_prompt(self, user: User) -> None:
        error_text = ft.Text("", color=COLORS["error"], size=12, visible=False)
        password_field = ft.TextField(label="Пароль", password=True, can_reveal_password=True, width=300, border_radius=12, bgcolor=COLORS["surface"], border_color=ft.Colors.TRANSPARENT, focused_border_color=COLORS["gradient1"], autofocus=True)

        def submit(e=None):
            try:
                ProfileService.login(user.id, password_field.value)
            except ProfileError as exc:
                error_text.value = str(exc)
                error_text.visible = True
                try:
                    error_text.update()
                except Exception:
                    pass
                return
            self._do_login(user.id, password_field.value)

        password_field.on_submit = submit

        self._render(
            ft.Container(width=90, height=90, border_radius=18, bgcolor=user.color or COLORS["gradient1"], alignment=ft.Alignment.CENTER, content=ft.Text(user.initials, size=32, color=ft.Colors.WHITE, font_family=FONT_BOLD)),
            ft.Text(user.display_name, size=18, color=ft.Colors.WHITE, font_family=FONT_BOLD),
            password_field,
            error_text,
            ft.Row(controls=[OutlineButton("Назад", on_click=lambda e: self.show_picker()), GradientButton("Войти", on_click=submit, icon=ft.Icons.LOGIN_ROUNDED)], spacing=10, alignment=ft.MainAxisAlignment.CENTER),
        )

    def show_create(self, first_run: bool = False) -> None:
        self._selected_interests = set()
        error_text = ft.Text("", color=COLORS["error"], size=12, visible=False)

        def make_field(label: str, **kwargs) -> ft.TextField:
            return ft.TextField(label=label, width=320, border_radius=12, bgcolor=COLORS["surface"], border_color=ft.Colors.TRANSPARENT, focused_border_color=COLORS["gradient1"], **kwargs)

        name_field = make_field("Имя *", autofocus=True)
        last_name_field = make_field("Фамилия")
        password_field = make_field("Пароль (необязательно)", password=True, can_reveal_password=True)

        def submit(e=None):
            try:
                user = ProfileService.create(name=name_field.value, last_name=last_name_field.value, password=password_field.value or None, interests=sorted(self._selected_interests) or None)
            except ProfileError as exc:
                error_text.value = str(exc)
                error_text.visible = True
                try:
                    error_text.update()
                except Exception:
                    pass
                return
            self._do_login(user.id, password_field.value or None)

        heading = "Добро пожаловать! Создадим профиль" if first_run else "Новый профиль"

        self._render(
            self._logo(),
            ft.Text(heading, size=20, color=ft.Colors.WHITE, font_family=FONT_BOLD),
            ft.Column([name_field, last_name_field, password_field], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            self._interest_chips(),
            error_text,
            GradientButton("Создать профиль", on_click=submit, icon=ft.Icons.CHECK_ROUNDED),
        )

    def _interest_chips(self) -> ft.Control:
        chips: List[ft.Control] = []
        for category in RecommendationEngine.DEFAULT_CATEGORIES:
            chip = ft.Container(content=ft.Text(category, size=12, color=COLORS["muted"]), padding=ft.Padding(12, 6, 12, 6), border_radius=16, bgcolor=COLORS["surface"])

            def toggle(e, c=chip, cat=category):
                if cat in self._selected_interests:
                    self._selected_interests.discard(cat)
                    c.bgcolor = COLORS["surface"]
                    c.content.color = COLORS["muted"]
                else:
                    self._selected_interests.add(cat)
                    c.bgcolor = COLORS["gradient1"]
                    c.content.color = ft.Colors.WHITE
                try:
                    c.update()
                except Exception:
                    pass

            chip.on_click = toggle
            chips.append(chip)

        return ft.Row(controls=chips, spacing=6, run_spacing=6, wrap=True, width=500, alignment=ft.MainAxisAlignment.CENTER)

    def show_manage(self) -> None:
        profiles = ProfileService.list_profiles()
        rows: List[ft.Control] = []
        for user in profiles:
            stats = ProfileService.summary(user.id)
            rows.append(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Container(width=40, height=40, border_radius=10, bgcolor=user.color or COLORS["gradient1"], alignment=ft.Alignment.CENTER, content=ft.Text(user.initials, color=ft.Colors.WHITE, font_family=FONT_BOLD)),
                            ft.Column(controls=[ft.Text(user.display_name, size=13, color=ft.Colors.WHITE), ft.Text(f"{stats['history']} просмотров", size=11, color=COLORS["muted"])], spacing=2, expand=True, tight=True),
                            ft.IconButton(icon=ft.Icons.DELETE_OUTLINE_ROUNDED, icon_color=COLORS["error"], on_click=lambda e, u=user: self._confirm_delete(u)),
                        ],
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=10,
                    border_radius=10,
                    bgcolor=COLORS["surface"],
                    width=400,
                )
            )

        self._render(
            ft.Text("Управление профилями", size=18, color=ft.Colors.WHITE, font_family=FONT_BOLD),
            ft.Column(rows, spacing=8, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            OutlineButton("Назад", on_click=lambda e: self.show_picker()),
        )

    def _confirm_delete(self, user: User) -> None:
        page = self.container.page
        if page is None:
            return

        def confirm(e):
            ProfileService.delete(user.id)
            page.close(dialog)
            if ProfileService.is_first_run():
                self.show_create(first_run=True)
            else:
                self.show_manage()

        dialog = ft.AlertDialog(
            modal=True,
            bgcolor=COLORS["surface"],
            title=ft.Text(f"Удалить профиль «{user.name}»?", color=ft.Colors.WHITE),
            content=ft.Text("История и интересы удалятся, файлы останутся.", color=COLORS["muted"]),
            actions=[ft.TextButton("Отмена", on_click=lambda e: page.close(dialog)), ft.TextButton("Удалить", on_click=confirm, style=ft.ButtonStyle(color=COLORS["error"]))],
        )
        page.open(dialog)

    def _do_login(self, user_id: int, password: Optional[str]) -> None:
        user = self.session.login(user_id, password)
        self.on_logged_in(user)
