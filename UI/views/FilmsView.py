"""Раздел «Фильмы и сериалы».

Особенности по сравнению с обычным видео:
  * поиск умный — запрос разбирает ИИ (или эвристика, если ИИ выключен),
    а разобранное намерение показывается пользователю;
  * если на RuTube пусто, агрегатор сам идёт искать по интернету, поэтому
    экран честно сообщает, откуда пришли результаты;
  * карточки показывают рейтинг и год, когда доступен Кинопоиск.
"""

from __future__ import annotations

from typing import List, Optional

import flet as ft

from config import settings
from core.media import MediaItem
from UI.components.Common import EmptyState, SearchField, SectionTitle, StatusChip
from UI.themes.DarkTheme import COLORS, FONT_BOLD
from UI.views.VideoView import VideoView

#: Быстрые фильтры-подборки раздела.
QUICK_FILTERS = [
    ("Новинки", "новинки кино"),
    ("Комедии", "комедия"),
    ("Боевики", "боевик"),
    ("Фантастика", "фантастика"),
    ("Сериалы", "сериал"),
    ("Мультфильмы", "мультфильм"),
]


class FilmsView(VideoView):
    """Фильмы и сериалы: RuTube, запасной поиск по интернету, ИИ-поиск."""

    title = "Фильмы и сериалы"
    content_type = "film"
    source_name = "RuTube"

    def __init__(self, session, app):
        super().__init__(session, app)
        self._intent_box = ft.Container(visible=False)

    # ------------------------------------------------------------------ #
    def _build_shell(self) -> None:
        """Каркас с подсказкой про ИИ и быстрыми фильтрами."""
        ai_on = bool(settings.get("ai_enabled")) and bool(settings.get("ai_api_key"))

        self._search_field = SearchField(
            on_search=self.search,
            placeholder=(
                "Опишите, что хотите посмотреть: «комедия про роботов с высоким рейтингом»"
                if ai_on
                else "Название фильма, сериала или ссылка"
            ),
            suggestions=self._suggestions(),
        )

        self.set_controls(
            [
                ft.Row(
                    controls=[
                        ft.Text(self.title, size=26, color=ft.Colors.WHITE,
                                font_family=FONT_BOLD),
                        ft.Row(
                            controls=[
                                StatusChip("RuTube", COLORS["muted"], ft.Icons.PUBLIC_ROUNDED),
                                StatusChip(
                                    "Поиск с ИИ" if ai_on else "ИИ выключен",
                                    COLORS["gradient2"] if ai_on else COLORS["muted"],
                                    ft.Icons.AUTO_AWESOME_ROUNDED,
                                ),
                            ],
                            spacing=8,
                        ),
                    ],
                    spacing=12,
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    wrap=True,
                ),
                self._search_field,
                self._quick_filters(),
                self._intent_box,
                self._results_container,
            ]
        )

    def _quick_filters(self) -> ft.Control:
        """Кнопки-подборки: быстрый способ начать без ввода запроса."""
        return ft.Row(
            controls=[
                ft.Container(
                    content=ft.Text(label, size=13, color=COLORS["muted"]),
                    padding=ft.Padding(14, 8, 14, 8),
                    border_radius=18,
                    bgcolor=COLORS["surface"],
                    on_click=lambda e, q=query: self.search(q),
                    ink=True,
                )
                for label, query in QUICK_FILTERS
            ],
            spacing=8,
            run_spacing=8,
            wrap=True,
        )

    # ------------------------------------------------------------------ #
    def search(self, query: str) -> None:
        """Поиск с показом того, как ИИ понял запрос."""
        query = (query or "").strip()
        if not query:
            return
        self._hide_intent()
        super().search(query)

    def _render(self, items, heading: str) -> None:
        """Дорисовать выдачу и объяснение разбора запроса."""
        self._show_intent()

        if isinstance(items, Exception):
            self._set_results(
                EmptyState(
                    "Ошибка поиска",
                    f"Не удалось получить результаты: {items}",
                    icon=ft.Icons.ERROR_OUTLINE_ROUNDED,
                    action_text="Повторить",
                    on_action=self._retry,
                )
            )
            return

        if not items:
            self._set_results(
                EmptyState(
                    f"Ничего не найдено по запросу «{self._query}»"
                    if self._query
                    else "Каталог недоступен",
                    "Мы искали на RuTube и в интернете, но ничего подходящего не нашли. "
                    "Попробуйте изменить формулировку или указать точное название.",
                    icon=ft.Icons.SEARCH_OFF_ROUNDED,
                    action_text="Показать актуальное",
                    on_action=self.load_feed,
                )
            )
            return

        # Показываем, откуда пришли результаты: с RuTube или из интернета.
        sources = {item.platform for item in items}
        note: List[ft.Control] = []
        if "web" in sources:
            note.append(
                StatusChip(
                    "Часть результатов найдена в интернете — на RuTube их нет",
                    COLORS["warning"],
                    ft.Icons.TRAVEL_EXPLORE_ROUNDED,
                )
            )

        self._set_results(
            SectionTitle(
                heading,
                action_text="К подборкам" if self._query else "Обновить",
                on_action=self.load_feed if self._query else self._retry,
            ),
            *note,
            self.media_grid(items),
        )

    # ------------------------------------------------------------------ #
    def _show_intent(self) -> None:
        """Показать, как система поняла запрос — это делает ИИ-поиск прозрачным."""
        intent = getattr(self.session.films, "last_intent", None)
        if intent is None or not self._query:
            self._hide_intent()
            return

        chips: List[ft.Control] = []
        if intent.genres:
            chips.append(StatusChip(", ".join(intent.genres), COLORS["gradient2"],
                                    ft.Icons.THEATER_COMEDY_ROUNDED))
        if intent.year_from:
            years = str(intent.year_from)
            if intent.year_to and intent.year_to != intent.year_from:
                years += f"–{intent.year_to}"
            chips.append(StatusChip(years, COLORS["muted"], ft.Icons.CALENDAR_MONTH_ROUNDED))
        if intent.min_rating:
            chips.append(StatusChip(f"рейтинг от {intent.min_rating}", COLORS["muted"],
                                    ft.Icons.STAR_ROUNDED))
        if intent.content_type:
            chips.append(
                StatusChip(
                    "сериалы" if intent.content_type == "series" else "фильмы",
                    COLORS["muted"],
                    ft.Icons.LIVE_TV_ROUNDED,
                )
            )

        if not chips and not intent.explanation:
            self._hide_intent()
            return

        header = ft.Row(
            controls=[
                ft.Icon(ft.Icons.AUTO_AWESOME_ROUNDED, size=16,
                        color=COLORS["gradient1"]),
                ft.Text(
                    "ИИ понял запрос так:" if intent.used_ai else "Запрос разобран так:",
                    size=13, color=ft.Colors.WHITE,
                ),
            ],
            spacing=8,
        )

        body: List[ft.Control] = [header]
        if chips:
            body.append(ft.Row(chips, spacing=8, wrap=True, run_spacing=8))
        if intent.explanation:
            body.append(ft.Text(intent.explanation, size=12, color=COLORS["muted"]))

        self._intent_box.content = ft.Column(body, spacing=8, tight=True)
        self._intent_box.padding = 14
        self._intent_box.border_radius = 12
        self._intent_box.bgcolor = COLORS["surface"]
        self._intent_box.visible = True
        try:
            self._intent_box.update()
        except Exception:
            pass

    def _hide_intent(self) -> None:
        self._intent_box.visible = False
        try:
            self._intent_box.update()
        except Exception:
            pass
