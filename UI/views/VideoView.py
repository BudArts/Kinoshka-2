"""Раздел «Видео» — YouTube: рекомендации, поиск, фильтры."""

from __future__ import annotations

from typing import List, Optional

import flet as ft

from UI.components.Common import EmptyState, SearchField, SectionTitle
from UI.themes.DarkTheme import COLORS, FONT_BOLD
from UI.views.BaseView import BaseView


class VideoView(BaseView):
    """Лента YouTube и поиск по нему."""

    title = "Видео"
    content_type = "video"
    source_name = "YouTube"

    def __init__(self, session, app):
        super().__init__(session, app)
        self._query: Optional[str] = None
        self._results_container = ft.Column(spacing=14, expand=True)
        self._search_field: Optional[SearchField] = None

    # ------------------------------------------------------------------ #
    def on_show(self, query: Optional[str] = None) -> None:
        """Показать ленту или сразу результаты поиска (если пришёл запрос)."""
        self._build_shell()
        if query:
            self.search(query)
        else:
            self.load_feed()

    def _build_shell(self) -> None:
        """Каркас экрана: заголовок + поиск + область результатов."""
        self._search_field = SearchField(
            on_search=self.search,
            placeholder=f"Поиск на {self.source_name} — название или ссылка",
            suggestions=self._suggestions(),
        )
        self.set_controls(
            [
                ft.Row(
                    controls=[
                        ft.Text(self.title, size=26, color=ft.Colors.WHITE,
                                font_family=FONT_BOLD),
                        ft.Container(
                            content=ft.Text(self.source_name, size=12,
                                            color=COLORS["muted"]),
                            padding=ft.Padding(10, 4, 10, 4),
                            border_radius=10,
                            bgcolor=COLORS["surface"],
                        ),
                    ],
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                self._search_field,
                self._results_container,
            ]
        )

    def _suggestions(self) -> List[str]:
        if not self.session.user_id:
            return []
        try:
            return self.session.recommendations.recent_searches(
                self.session.user_id, limit=6
            )
        except Exception:
            return []

    # ------------------------------------------------------------------ #
    #  Лента рекомендаций
    # ------------------------------------------------------------------ #
    def load_feed(self) -> None:
        self._query = None
        self._set_results(self._loading_block("Подбираем рекомендации…"))
        self.run_async(
            work=lambda: self.session.feed(self.content_type),
            on_done=lambda items: self._render(items, heading="Рекомендации для вас"),
            loading_text=None,
        )

    # ------------------------------------------------------------------ #
    #  Поиск
    # ------------------------------------------------------------------ #
    def search(self, query: str) -> None:
        query = (query or "").strip()
        if not query:
            return
        self._query = query
        if self._search_field:
            self._search_field.field.value = query
            try:
                self._search_field.field.update()
            except Exception:
                pass

        self._set_results(self._loading_block(f"Ищем «{query}»…"))
        self.run_async(
            work=lambda: self.session.search(query, self.content_type),
            on_done=lambda items: self._render(items, heading=f"Результаты: «{query}»"),
            loading_text=None,
        )

    # ------------------------------------------------------------------ #
    def _render(self, items, heading: str) -> None:
        """Отрисовать выдачу либо объяснить, почему её нет."""
        if isinstance(items, Exception):
            self._set_results(
                EmptyState(
                    "Что-то пошло не так",
                    f"Ошибка при обращении к {self.source_name}: {items}",
                    icon=ft.Icons.ERROR_OUTLINE_ROUNDED,
                    action_text="Повторить",
                    on_action=self._retry,
                )
            )
            return

        if not items:
            if self._query:
                self._set_results(
                    EmptyState(
                        f"По запросу «{self._query}» ничего не найдено",
                        f"Проверьте написание или попробуйте другой запрос. "
                        f"Если {self.source_name} недоступен — включите VPN в настройках.",
                        icon=ft.Icons.SEARCH_OFF_ROUNDED,
                        action_text="Настройки VPN",
                        on_action=lambda: self.app.navigate("settings"),
                    )
                )
            else:
                self._set_results(self.offline_notice(self.source_name))
            return

        self._set_results(
            SectionTitle(
                heading,
                action_text="Обновить" if not self._query else "К рекомендациям",
                on_action=self._retry if not self._query else self.load_feed,
            ),
            self.media_grid(items),
        )

    def _retry(self) -> None:
        if self._query:
            self.search(self._query)
        else:
            self.load_feed()

    def _set_results(self, *controls: ft.Control) -> None:
        self._results_container.controls = list(controls)
        self.safe_update()

    @staticmethod
    def _loading_block(text: str) -> ft.Control:
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.ProgressRing(color=COLORS["gradient1"], width=26, height=26),
                    ft.Text(text, size=14, color=COLORS["muted"]),
                ],
                spacing=14,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            padding=40,
            alignment=ft.Alignment.CENTER,
        )
