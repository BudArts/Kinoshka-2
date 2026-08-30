"""Главная: сводная лента по всем разделам."""

from __future__ import annotations

from typing import List

import flet as ft

from core.media import MediaItem
from UI.components.Common import EmptyState, SearchField, SectionTitle
from UI.themes.DarkTheme import COLORS, FONT_BOLD, brand_gradient
from UI.views.BaseView import BaseView


class HomeView(BaseView):
    title = "Главная"
    content_type = "video"

    def on_show(self) -> None:
        self._load()

    def _load(self) -> None:
        user_id = self.session.user_id
        if not user_id:
            return

        self.set_controls(self._static_blocks() + [self._feed_placeholder()])

        self.run_async(
            work=lambda: self.session.feed("video", limit=12),
            on_done=self._render_feed,
            loading_text=None,
        )

    def _static_blocks(self) -> List[ft.Control]:
        user = self.session.user
        name = user.name if user else "гость"

        blocks: List[ft.Control] = [
            self._hero(name),
            SearchField(
                on_search=lambda q: self.app.navigate("video", query=q),
                placeholder="Что посмотреть? Название или ссылка",
                suggestions=self.session.recommendations.recent_searches(self.session.user_id, limit=5) if self.session.user_id else None,
            ),
            self._quick_tiles(),
        ]

        continue_items = self._continue_watching()
        if continue_items:
            blocks.append(SectionTitle("Продолжить просмотр", icon=ft.Icons.HISTORY_ROUNDED))
            blocks.append(self.media_row(continue_items))

        return blocks

    def _hero(self, name: str) -> ft.Control:
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(f"Привет, {name}!", size=28, color=ft.Colors.WHITE, font_family=FONT_BOLD),
                    ft.Text("Видео с YouTube, фильмы и сериалы с RuTube, музыка — смотрите онлайн или скачивайте.", size=14, color=ft.Colors.with_opacity(0.85, ft.Colors.WHITE)),
                ],
                spacing=8,
                tight=True,
            ),
            gradient=brand_gradient(ft.Alignment.CENTER_LEFT, ft.Alignment.CENTER_RIGHT),
            padding=ft.Padding(28, 26, 28, 26),
            border_radius=18,
        )

    def _quick_tiles(self) -> ft.Control:
        tiles = [
            (ft.Icons.ONDEMAND_VIDEO_ROUNDED, "Видео", "YouTube", "video"),
            (ft.Icons.CAMERA_ROLL_ROUNDED, "Фильмы", "RuTube и другие", "films"),
            (ft.Icons.MUSIC_NOTE_ROUNDED, "Музыка", "Яндекс Музыка", "music"),
            (ft.Icons.DOWNLOAD_DONE_ROUNDED, "Загрузки", "Смотреть офлайн", "my_video"),
        ]

        def tile(icon, title, subtitle, route) -> ft.Control:
            # Используем Container без ink, чтобы избежать серых артефактов
            return ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Container(
                            width=44,
                            height=44,
                            border_radius=12,
                            bgcolor=ft.Colors.with_opacity(0.15, COLORS["gradient1"]),
                            alignment=ft.Alignment.CENTER,
                            content=ft.Icon(icon, color=COLORS["gradient1"], size=22),
                        ),
                        ft.Column(
                            controls=[
                                ft.Text(title, size=15, color=ft.Colors.WHITE, font_family=FONT_BOLD),
                                ft.Text(subtitle, size=12, color=COLORS["muted"]),
                            ],
                            spacing=1,
                            tight=True,
                        ),
                    ],
                    spacing=12,
                    tight=True,
                ),
                padding=14,
                border_radius=14,
                bgcolor=COLORS["surface"],
                width=230,
                on_click=lambda e, r=route: self.app.navigate(r),
            )

        return ft.Container(
            content=ft.Row(controls=[tile(*t) for t in tiles], spacing=12, run_spacing=12, wrap=True),
            bgcolor=ft.Colors.TRANSPARENT,
        )

    def _continue_watching(self) -> List[MediaItem]:
        if not self.session.user_id:
            return []
        try:
            entries = self.session.recommendations.get_continue_watching(self.session.user_id, limit=8)
        except Exception:
            return []
        return [
            MediaItem(
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
            for entry in entries
        ]

    def _feed_placeholder(self) -> ft.Control:
        self._feed_container = ft.Column(
            controls=[
                SectionTitle("Рекомендации для вас", icon=ft.Icons.AUTO_AWESOME_ROUNDED),
                ft.Container(
                    content=ft.Row(
                        controls=[ft.ProgressRing(color=COLORS["gradient1"], width=24, height=24), ft.Text("Подбираем видео…", size=13, color=COLORS["muted"])],
                        spacing=12,
                    ),
                    bgcolor=ft.Colors.TRANSPARENT,
                    padding=10,
                ),
            ],
            spacing=14,
            tight=True,
        )
        return ft.Container(content=self._feed_container, bgcolor=ft.Colors.TRANSPARENT)

    def _render_feed(self, items) -> None:
        if isinstance(items, Exception) or not items:
            body: ft.Control = EmptyState(
                "Лента пока пуста",
                "Не удалось получить видео. Проверьте интернет и попробуйте обновить.",
                icon=ft.Icons.CLOUD_OFF_ROUNDED,
                action_text="Обновить",
                on_action=self._load,
            )
        else:
            body = self.media_grid(items)

        self._feed_container.controls = [
            SectionTitle("Рекомендации для вас", action_text="Обновить", on_action=self._load, icon=ft.Icons.AUTO_AWESOME_ROUNDED),
            body,
        ]
        self.safe_update()
