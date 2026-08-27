"""История просмотров с фильтрами по типу контента."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Optional

import flet as ft

from core.media import MediaItem
from database.models import History
from UI.components.Common import EmptyState, OutlineButton, SectionTitle
from UI.themes.DarkTheme import COLORS, FONT_BOLD
from UI.views.BaseView import BaseView

#: Вкладки фильтра: подпись -> значение content_type (None = всё).
FILTERS = [
    ("Всё", None),
    ("Видео", "video"),
    ("Фильмы", "film"),
    ("Музыка", "music"),
]


class HistoryView(BaseView):
    """Что и когда смотрел пользователь."""

    title = "История"

    def __init__(self, session, app):
        super().__init__(session, app)
        self._filter: Optional[str] = None

    def on_show(self, content_type: Optional[str] = None) -> None:
        self._filter = content_type
        self._load()

    # ------------------------------------------------------------------ #
    def _load(self) -> None:
        user_id = self.session.user_id
        if not user_id:
            return

        entries = self.session.recommendations.get_history(
            user_id, content_type=self._filter, limit=300
        )

        controls: List[ft.Control] = [self._header(len(entries)), self._filter_row()]

        if not entries:
            controls.append(
                EmptyState(
                    "История пуста",
                    "Здесь появится всё, что вы смотрели и слушали. "
                    "История также помогает подбирать рекомендации.",
                    icon=ft.Icons.HISTORY_ROUNDED,
                    action_text="Перейти к видео",
                    on_action=lambda: self.app.navigate("video"),
                )
            )
            self.set_controls(controls)
            return

        # Группируем по дням: «Сегодня», «Вчера», затем даты.
        for group_title, group_entries in self._group_by_day(entries).items():
            controls.append(SectionTitle(group_title))
            controls.append(
                ft.Column(
                    controls=[self._row(entry) for entry in group_entries],
                    spacing=8,
                )
            )

        self.set_controls(controls)

    def _header(self, count: int) -> ft.Control:
        return ft.Row(
            controls=[
                ft.Text("История просмотров", size=26, color=ft.Colors.WHITE,
                        font_family=FONT_BOLD),
                ft.Row(
                    controls=[
                        ft.Text(f"{count} записей", size=13, color=COLORS["muted"]),
                        OutlineButton("Очистить", icon=ft.Icons.DELETE_SWEEP_ROUNDED,
                                      on_click=lambda e: self._confirm_clear(),
                                      color=COLORS["error"]),
                    ],
                    spacing=12,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            wrap=True,
        )

    def _filter_row(self) -> ft.Control:
        chips: List[ft.Control] = []
        for label, value in FILTERS:
            active = value == self._filter
            chips.append(
                ft.Container(
                    content=ft.Text(
                        label, size=13,
                        color=ft.Colors.WHITE if active else COLORS["muted"],
                    ),
                    padding=ft.Padding(16, 8, 16, 8),
                    border_radius=18,
                    bgcolor=ft.Colors.with_opacity(0.18, COLORS["gradient1"])
                    if active else COLORS["surface"],
                    border=ft.Border.all(
                        1, COLORS["gradient1"] if active else ft.Colors.TRANSPARENT
                    ),
                    on_click=lambda e, v=value: self._set_filter(v),
                    ink=True,
                )
            )
        return ft.Row(controls=chips, spacing=8, wrap=True)

    def _set_filter(self, value: Optional[str]) -> None:
        self._filter = value
        self._load()

    # ------------------------------------------------------------------ #
    @staticmethod
    def _group_by_day(entries: List[History]) -> Dict[str, List[History]]:
        """Разложить записи по дням с человеческими подписями."""
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        groups: Dict[str, List[History]] = {}

        for entry in entries:
            day = entry.date.date() if entry.date else today
            if day == today:
                key = "Сегодня"
            elif day == yesterday:
                key = "Вчера"
            else:
                key = day.strftime("%d.%m.%Y")
            groups.setdefault(key, []).append(entry)
        return groups

    def _row(self, entry: History) -> ft.Control:
        """Одна запись истории с индикатором досмотренности."""
        progress = entry.completion_rate
        time_text = entry.date.strftime("%H:%M") if entry.date else ""

        thumb = ft.Container(
            width=104, height=59, border_radius=8, bgcolor=COLORS["surface_alt"],
            content=ft.Stack(
                controls=[
                    ft.Image(
                        src=entry.thumbnail or "", width=104, height=59,
                        fit=ft.BoxFit.COVER, border_radius=8,
                        error_content=ft.Icon(ft.Icons.PLAY_CIRCLE_OUTLINE,
                                              color=COLORS["muted"]),
                    ),
                    # Полоска прогресса просмотра поверх превью.
                    ft.Container(
                        bottom=0, left=0,
                        width=max(int(104 * progress), 2), height=3,
                        bgcolor=COLORS["gradient1"],
                        border_radius=2,
                    ),
                ]
            ),
        )

        meta = " • ".join(
            p for p in (
                entry.author,
                (entry.platform or "").upper() or None,
                f"просмотрено {int(progress * 100)}%" if progress else None,
                time_text,
            ) if p
        )

        return ft.Container(
            content=ft.Row(
                controls=[
                    thumb,
                    ft.Column(
                        controls=[
                            ft.Text(entry.title, size=14, color=ft.Colors.WHITE,
                                    max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                            ft.Text(meta, size=12, color=COLORS["muted"], max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS),
                        ],
                        spacing=3, expand=True, tight=True,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.PLAY_ARROW_ROUNDED, icon_color=ft.Colors.WHITE,
                        tooltip="Смотреть снова",
                        on_click=lambda e, en=entry: self._replay(en),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.DOWNLOAD_ROUNDED, icon_color=COLORS["muted"],
                        tooltip="Скачать",
                        on_click=lambda e, en=entry: self.app.download_item(
                            self._to_item(en)
                        ),
                    ),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=10,
            border_radius=12,
            bgcolor=COLORS["surface"],
            on_click=lambda e, en=entry: self._replay(en),
            ink=True,
        )

    @staticmethod
    def _to_item(entry: History) -> MediaItem:
        return MediaItem(
            id=entry.video_id or entry.link,
            title=entry.title,
            url=entry.link,
            platform=entry.platform or "youtube",
            content_type=entry.type,
            author=entry.author,
            thumbnail=entry.thumbnail,
            duration=entry.total_duration,
            categories=entry.category_list,
            tags=entry.tag_list,
            extra={"resume_position": entry.position or 0},
        )

    def _replay(self, entry: History) -> None:
        self.app.open_player(self._to_item(entry))

    # ------------------------------------------------------------------ #
    def _confirm_clear(self) -> None:
        scope = "всю историю" if self._filter is None else "историю этого раздела"

        def confirm(e):
            self.session.recommendations.clear_history(
                self.session.user_id, self._filter
            )
            self.page.close(dialog)
            self.app.toast("История очищена")
            self._load()

        dialog = ft.AlertDialog(
            modal=True,
            bgcolor=COLORS["surface"],
            title=ft.Text("Очистить историю?", color=ft.Colors.WHITE),
            content=ft.Text(
                f"Будет удалена {scope}. Это может ухудшить точность "
                "рекомендаций — они строятся в том числе на просмотрах.",
                color=COLORS["muted"],
            ),
            actions=[
                ft.TextButton("Отмена", on_click=lambda e: self.page.close(dialog)),
                ft.TextButton("Очистить", on_click=confirm,
                              style=ft.ButtonStyle(color=COLORS["error"])),
            ],
        )
        self.page.open(dialog)
