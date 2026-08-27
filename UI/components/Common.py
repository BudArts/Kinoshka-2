"""Мелкие переиспользуемые элементы интерфейса."""

from __future__ import annotations

from typing import Callable, List, Optional

import flet as ft

from UI.themes.DarkTheme import ANIM, COLORS, FONT_BOLD, brand_gradient


class SearchField(ft.Container):
    """Строка поиска с подсказками из недавних запросов."""

    def __init__(
        self,
        on_search: Callable[[str], None],
        placeholder: str = "Название или ссылка",
        suggestions: Optional[List[str]] = None,
        trailing: Optional[List[ft.Control]] = None,
    ):
        self._on_search = on_search

        self.field = ft.TextField(
            hint_text=placeholder,
            hint_style=ft.TextStyle(color=COLORS["muted"]),
            border_radius=24,
            border_color=ft.Colors.TRANSPARENT,
            focused_border_color=COLORS["gradient1"],
            bgcolor=COLORS["surface"],
            color=ft.Colors.WHITE,
            content_padding=ft.Padding(20, 14, 14, 14),
            prefix_icon=ft.Icons.SEARCH,
            expand=True,
            multiline=False,
            on_submit=self._submit,
        )

        controls: List[ft.Control] = [self.field]
        controls.append(
            ft.Container(
                content=ft.Text("Найти", color=ft.Colors.WHITE, font_family=FONT_BOLD),
                gradient=brand_gradient(),
                padding=ft.Padding(22, 14, 22, 14),
                border_radius=24,
                on_click=self._submit,
                ink=True,
            )
        )
        if trailing:
            controls.extend(trailing)

        body: List[ft.Control] = [ft.Row(controls=controls, spacing=10)]

        if suggestions:
            body.append(
                ft.Row(
                    controls=[
                        ft.Container(
                            content=ft.Text(text, size=12, color=COLORS["muted"]),
                            padding=ft.Padding(12, 6, 12, 6),
                            border_radius=16,
                            bgcolor=COLORS["surface"],
                            on_click=lambda e, t=text: self.run(t),
                            ink=True,
                        )
                        for text in suggestions[:6]
                    ],
                    spacing=8,
                    wrap=True,
                )
            )

        super().__init__(content=ft.Column(controls=body, spacing=10, tight=True))

    def _submit(self, e=None) -> None:
        self.run(self.field.value or "")

    def run(self, query: str) -> None:
        """Программно выполнить поиск (используется подсказками)."""
        query = (query or "").strip()
        if not query:
            return
        self.field.value = query
        try:
            self.field.update()
        except Exception:
            pass  # поле ещё не на странице
        self._on_search(query)


class SectionTitle(ft.Row):
    """Заголовок секции с опциональной кнопкой действия справа."""

    def __init__(
        self,
        text: str,
        action_text: Optional[str] = None,
        on_action: Optional[Callable] = None,
        icon: Optional[str] = None,
    ):
        controls: List[ft.Control] = []
        if icon:
            controls.append(ft.Icon(icon, color=COLORS["gradient1"], size=22))
        controls.append(
            ft.Text(text, size=20, color=ft.Colors.WHITE, font_family=FONT_BOLD)
        )
        row: List[ft.Control] = [ft.Row(controls=controls, spacing=8)]

        if action_text and on_action:
            row.append(
                ft.TextButton(
                    action_text,
                    on_click=lambda e: on_action(),
                    style=ft.ButtonStyle(color=COLORS["gradient2"]),
                )
            )

        super().__init__(
            controls=row,
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )


class EmptyState(ft.Container):
    """Заглушка для пустых экранов и ошибок — с понятным объяснением."""

    def __init__(
        self,
        title: str,
        description: str = "",
        icon: str = ft.Icons.INBOX_ROUNDED,
        action_text: Optional[str] = None,
        on_action: Optional[Callable] = None,
    ):
        controls: List[ft.Control] = [
            ft.Icon(icon, size=64, color=COLORS["dark_gray"]),
            ft.Text(title, size=18, color=ft.Colors.WHITE, font_family=FONT_BOLD,
                    text_align=ft.TextAlign.CENTER),
        ]
        if description:
            controls.append(
                ft.Text(
                    description,
                    size=13,
                    color=COLORS["muted"],
                    text_align=ft.TextAlign.CENTER,
                    width=420,
                )
            )
        if action_text and on_action:
            controls.append(
                ft.Container(
                    content=ft.Text(action_text, color=ft.Colors.WHITE),
                    gradient=brand_gradient(),
                    padding=ft.Padding(20, 12, 20, 12),
                    border_radius=20,
                    on_click=lambda e: on_action(),
                    ink=True,
                )
            )

        super().__init__(
            content=ft.Column(
                controls=controls,
                spacing=14,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            alignment=ft.Alignment.CENTER,
            padding=40,
            expand=True,
        )


class LoadingState(ft.Container):
    """Индикатор загрузки на весь экран."""

    def __init__(self, text: str = "Загружаем…"):
        super().__init__(
            content=ft.Column(
                controls=[
                    ft.ProgressRing(color=COLORS["gradient1"], width=42, height=42),
                    ft.Text(text, size=14, color=COLORS["muted"]),
                ],
                spacing=16,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            alignment=ft.Alignment.CENTER,
            padding=60,
            expand=True,
        )


class GradientButton(ft.Container):
    """Основная кнопка приложения."""

    def __init__(
        self,
        text: str,
        on_click: Optional[Callable] = None,
        icon: Optional[str] = None,
        width: Optional[int] = None,
        expand: bool = False,
    ):
        content: List[ft.Control] = []
        if icon:
            content.append(ft.Icon(icon, color=ft.Colors.WHITE, size=18))
        content.append(
            ft.Text(text, color=ft.Colors.WHITE, font_family=FONT_BOLD, size=14)
        )

        super().__init__(
            content=ft.Row(
                controls=content,
                spacing=8,
                alignment=ft.MainAxisAlignment.CENTER,
                tight=True,
            ),
            gradient=brand_gradient(),
            padding=ft.Padding(22, 14, 22, 14),
            border_radius=14,
            on_click=on_click,
            ink=True,
            width=width,
            expand=expand,
            animate_scale=ANIM,
        )


class OutlineButton(ft.Container):
    """Второстепенная кнопка."""

    def __init__(
        self,
        text: str,
        on_click: Optional[Callable] = None,
        icon: Optional[str] = None,
        color: Optional[str] = None,
    ):
        color = color or COLORS["muted"]
        content: List[ft.Control] = []
        if icon:
            content.append(ft.Icon(icon, color=color, size=18))
        content.append(ft.Text(text, color=color, size=14))

        super().__init__(
            content=ft.Row(controls=content, spacing=8, tight=True,
                           alignment=ft.MainAxisAlignment.CENTER),
            padding=ft.Padding(20, 12, 20, 12),
            border_radius=14,
            border=ft.Border.all(1, ft.Colors.with_opacity(0.25, ft.Colors.WHITE)),
            on_click=on_click,
            ink=True,
        )


class StatusChip(ft.Container):
    """Небольшой индикатор состояния (VPN, статус загрузки)."""

    def __init__(self, text: str, color: str, icon: Optional[str] = None):
        controls: List[ft.Control] = []
        if icon:
            controls.append(ft.Icon(icon, size=14, color=color))
        controls.append(ft.Text(text, size=12, color=color))

        super().__init__(
            content=ft.Row(controls=controls, spacing=6, tight=True),
            padding=ft.Padding(10, 5, 10, 5),
            border_radius=12,
            bgcolor=ft.Colors.with_opacity(0.14, color),
        )
