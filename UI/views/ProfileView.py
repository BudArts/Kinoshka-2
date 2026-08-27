"""Экран профилей: первый запуск, выбор аккаунта, вход по паролю.

Показывается поверх всего приложения, пока пользователь не вошёл, а также
по команде «Сменить аккаунт».
"""

from __future__ import annotations

from typing import Callable, List, Optional

import flet as ft

from core.profile_service import ProfileError, ProfileService
from core.recomendation_engine import RecommendationEngine
from core.session import AppSession
from database.models import User
from UI.components.AppBar import gradient_text
from UI.components.Common import GradientButton, OutlineButton
from UI.themes.DarkTheme import ANIM, COLORS, FONT_BOLD, brand_gradient


class ProfileView:
    """Полноэкранный выбор/создание профиля."""

    def __init__(self, session: AppSession, on_logged_in: Callable[[User], None]):
        self.session = session
        self.on_logged_in = on_logged_in
        self._selected_interests: set[str] = set()

        self.container = ft.Container(
            expand=True,
            alignment=ft.Alignment.CENTER,
            bgcolor=COLORS["bg"],
            padding=40,
        )

    # ------------------------------------------------------------------ #
    def build(self) -> ft.Control:
        """Первый запуск ведёт сразу к созданию профиля, иначе — к выбору."""
        if ProfileService.is_first_run():
            self.show_create(first_run=True)
        else:
            self.show_picker()
        return self.container

    def _render(self, *controls: ft.Control) -> None:
        self.container.content = ft.Column(
            controls=list(controls),
            spacing=24,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            scroll=ft.ScrollMode.AUTO,
        )
        try:
            self.container.update()
        except Exception:
            pass

    @staticmethod
    def _logo() -> ft.Control:
        return ft.Column(
            controls=[
                ft.Container(
                    width=76,
                    height=76,
                    border_radius=24,
                    gradient=brand_gradient(),
                    alignment=ft.Alignment.CENTER,
                    content=ft.Icon(ft.Icons.MOVIE_FILTER_ROUNDED, size=42,
                                    color=ft.Colors.WHITE),
                ),
                gradient_text("Kinoshka", size=32),
            ],
            spacing=12,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

    # ================================================================== #
    #  Выбор профиля
    # ================================================================== #
    def show_picker(self) -> None:
        profiles = ProfileService.list_profiles()

        tiles: List[ft.Control] = [self._profile_tile(user) for user in profiles]
        tiles.append(self._add_tile())

        self._render(
            self._logo(),
            ft.Text("Кто смотрит?", size=22, color=ft.Colors.WHITE, font_family=FONT_BOLD),
            ft.Row(
                controls=tiles,
                spacing=20,
                wrap=True,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            ft.TextButton(
                "Управление профилями",
                icon=ft.Icons.MANAGE_ACCOUNTS_ROUNDED,
                on_click=lambda e: self.show_manage(),
                style=ft.ButtonStyle(color=COLORS["muted"]),
            ),
        )

    def _profile_tile(self, user: User) -> ft.Control:
        """Плитка профиля с аватаром-инициалами."""
        avatar = ft.Container(
            width=110,
            height=110,
            border_radius=24,
            bgcolor=user.color or COLORS["gradient1"],
            alignment=ft.Alignment.CENTER,
            content=ft.Text(user.initials, size=42, color=ft.Colors.WHITE,
                            font_family=FONT_BOLD),
            animate_scale=ANIM,
        )

        name_row: List[ft.Control] = [
            ft.Text(user.name, size=15, color=ft.Colors.WHITE, max_lines=1)
        ]
        if user.has_password:
            name_row.append(ft.Icon(ft.Icons.LOCK_ROUNDED, size=13, color=COLORS["muted"]))

        tile = ft.Container(
            content=ft.Column(
                controls=[
                    avatar,
                    ft.Row(name_row, spacing=5, alignment=ft.MainAxisAlignment.CENTER),
                ],
                spacing=10,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            on_click=lambda e, u=user: self._pick(u),
            ink=False,
            padding=6,
            border_radius=20,
            animate=ANIM,
        )

        def hover(e: ft.HoverEvent, a=avatar, t=tile):
            hovering = e.data == "true" or e.data is True
            a.scale = 1.07 if hovering else 1.0
            t.bgcolor = COLORS["surface"] if hovering else None
            try:
                t.update()
            except Exception:
                pass

        tile.on_hover = hover
        return tile

    def _add_tile(self) -> ft.Control:
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Container(
                        width=110,
                        height=110,
                        border_radius=24,
                        border=ft.Border.all(2, COLORS["dark_gray"]),
                        alignment=ft.Alignment.CENTER,
                        content=ft.Icon(ft.Icons.ADD_ROUNDED, size=46,
                                        color=COLORS["muted"]),
                    ),
                    ft.Text("Новый профиль", size=15, color=COLORS["muted"]),
                ],
                spacing=10,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            on_click=lambda e: self.show_create(),
            padding=6,
            border_radius=20,
        )

    def _pick(self, user: User) -> None:
        """Профиль без пароля пускает сразу, с паролем — просит его ввести."""
        if user.has_password:
            self.show_password_prompt(user)
        else:
            self._do_login(user.id, None)

    # ================================================================== #
    #  Ввод пароля
    # ================================================================== #
    def show_password_prompt(self, user: User) -> None:
        error_text = ft.Text("", color=COLORS["error"], size=13, visible=False)
        password_field = ft.TextField(
            label="Пароль",
            password=True,
            can_reveal_password=True,
            width=320,
            border_radius=12,
            bgcolor=COLORS["surface"],
            border_color=ft.Colors.TRANSPARENT,
            focused_border_color=COLORS["gradient1"],
            autofocus=True,
        )

        def submit(e=None):
            try:
                ProfileService.login(user.id, password_field.value)
            except ProfileError as exc:
                error_text.value = str(exc)
                error_text.visible = True
                password_field.value = ""
                try:
                    error_text.update()
                    password_field.update()
                except Exception:
                    pass
                return
            self._do_login(user.id, password_field.value)

        password_field.on_submit = submit

        self._render(
            ft.Container(
                width=110,
                height=110,
                border_radius=24,
                bgcolor=user.color or COLORS["gradient1"],
                alignment=ft.Alignment.CENTER,
                content=ft.Text(user.initials, size=42, color=ft.Colors.WHITE,
                                font_family=FONT_BOLD),
            ),
            ft.Text(user.display_name, size=20, color=ft.Colors.WHITE,
                    font_family=FONT_BOLD),
            password_field,
            error_text,
            ft.Row(
                controls=[
                    OutlineButton("Назад", on_click=lambda e: self.show_picker()),
                    GradientButton("Войти", on_click=submit, icon=ft.Icons.LOGIN_ROUNDED),
                ],
                spacing=12,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
        )

    # ================================================================== #
    #  Создание профиля
    # ================================================================== #
    def show_create(self, first_run: bool = False) -> None:
        self._selected_interests = set()

        error_text = ft.Text("", color=COLORS["error"], size=13, visible=False)

        def make_field(label: str, **kwargs) -> ft.TextField:
            return ft.TextField(
                label=label,
                width=340,
                border_radius=12,
                bgcolor=COLORS["surface"],
                border_color=ft.Colors.TRANSPARENT,
                focused_border_color=COLORS["gradient1"],
                **kwargs,
            )

        name_field = make_field("Имя *", autofocus=True)
        last_name_field = make_field("Фамилия")
        password_field = make_field(
            "Пароль (необязательно)", password=True, can_reveal_password=True
        )

        interests_chips = self._interest_chips()

        def submit(e=None):
            try:
                user = ProfileService.create(
                    name=name_field.value,
                    last_name=last_name_field.value,
                    password=password_field.value or None,
                    interests=sorted(self._selected_interests) or None,
                )
            except ProfileError as exc:
                error_text.value = str(exc)
                error_text.visible = True
                try:
                    error_text.update()
                except Exception:
                    pass
                return
            self._do_login(user.id, password_field.value or None)

        name_field.on_submit = submit

        heading = (
            "Добро пожаловать! Создадим профиль"
            if first_run
            else "Новый профиль"
        )
        subtitle = (
            "Профили нужны, чтобы у каждого, кто пользуется компьютером, "
            "были свои рекомендации, история и загрузки."
        )

        buttons: List[ft.Control] = []
        if not first_run:
            buttons.append(OutlineButton("Отмена", on_click=lambda e: self.show_picker()))
        buttons.append(
            GradientButton("Создать профиль", on_click=submit, icon=ft.Icons.CHECK_ROUNDED)
        )

        self._render(
            self._logo(),
            ft.Text(heading, size=22, color=ft.Colors.WHITE, font_family=FONT_BOLD),
            ft.Text(subtitle, size=13, color=COLORS["muted"], width=460,
                    text_align=ft.TextAlign.CENTER),
            ft.Column([name_field, last_name_field, password_field], spacing=12,
                      horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Text("Что вам интересно? (можно пропустить)", size=14,
                    color=ft.Colors.WHITE),
            interests_chips,
            error_text,
            ft.Row(buttons, spacing=12, alignment=ft.MainAxisAlignment.CENTER),
        )

    def _interest_chips(self) -> ft.Control:
        """Чипы стартовых интересов — задают первую ленту рекомендаций."""
        chips: List[ft.Control] = []

        for category in RecommendationEngine.DEFAULT_CATEGORIES:
            chip = ft.Container(
                content=ft.Text(category, size=13, color=COLORS["muted"]),
                padding=ft.Padding(14, 9, 14, 9),
                border_radius=18,
                bgcolor=COLORS["surface"],
                border=ft.Border.all(1, ft.Colors.TRANSPARENT),
                animate=ANIM,
            )

            def toggle(e, c=chip, cat=category):
                if cat in self._selected_interests:
                    self._selected_interests.discard(cat)
                    c.bgcolor = COLORS["surface"]
                    c.border = ft.Border.all(1, ft.Colors.TRANSPARENT)
                    c.content.color = COLORS["muted"]
                else:
                    self._selected_interests.add(cat)
                    c.bgcolor = ft.Colors.with_opacity(0.18, COLORS["gradient1"])
                    c.border = ft.Border.all(1, COLORS["gradient1"])
                    c.content.color = ft.Colors.WHITE
                try:
                    c.update()
                except Exception:
                    pass

            chip.on_click = toggle
            chips.append(chip)

        return ft.Row(
            controls=chips,
            spacing=8,
            run_spacing=8,
            wrap=True,
            width=620,
            alignment=ft.MainAxisAlignment.CENTER,
        )

    # ================================================================== #
    #  Управление профилями
    # ================================================================== #
    def show_manage(self) -> None:
        profiles = ProfileService.list_profiles()
        rows: List[ft.Control] = []

        for user in profiles:
            stats = ProfileService.summary(user.id)
            rows.append(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Container(
                                width=48, height=48, border_radius=14,
                                bgcolor=user.color or COLORS["gradient1"],
                                alignment=ft.Alignment.CENTER,
                                content=ft.Text(user.initials, color=ft.Colors.WHITE,
                                                font_family=FONT_BOLD),
                            ),
                            ft.Column(
                                controls=[
                                    ft.Text(user.display_name, size=15,
                                            color=ft.Colors.WHITE),
                                    ft.Text(
                                        f"{stats['history']} просмотров • "
                                        f"{stats['downloads']} загрузок",
                                        size=12, color=COLORS["muted"],
                                    ),
                                ],
                                spacing=2, expand=True, tight=True,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                                icon_color=COLORS["error"],
                                tooltip="Удалить профиль",
                                on_click=lambda e, u=user: self._confirm_delete(u),
                            ),
                        ],
                        spacing=14,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=12,
                    border_radius=14,
                    bgcolor=COLORS["surface"],
                    width=520,
                )
            )

        self._render(
            ft.Text("Управление профилями", size=22, color=ft.Colors.WHITE,
                    font_family=FONT_BOLD),
            ft.Column(rows, spacing=10,
                      horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Row(
                controls=[
                    OutlineButton("Назад", on_click=lambda e: self.show_picker()),
                    GradientButton("Добавить профиль", icon=ft.Icons.PERSON_ADD_ROUNDED,
                                   on_click=lambda e: self.show_create()),
                ],
                spacing=12, alignment=ft.MainAxisAlignment.CENTER,
            ),
        )

    def _confirm_delete(self, user: User) -> None:
        """Удаление профиля необратимо, поэтому спрашиваем подтверждение."""
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
            content=ft.Text(
                "Вместе с профилем удалится вся история просмотров, интересы "
                "и записи о загрузках. Скачанные файлы останутся на диске.",
                color=COLORS["muted"],
            ),
            actions=[
                ft.TextButton("Отмена", on_click=lambda e: page.close(dialog)),
                ft.TextButton(
                    "Удалить",
                    on_click=confirm,
                    style=ft.ButtonStyle(color=COLORS["error"]),
                ),
            ],
        )
        page.open(dialog)

    # ================================================================== #
    def _do_login(self, user_id: int, password: Optional[str]) -> None:
        user = self.session.login(user_id, password)
        self.on_logged_in(user)
