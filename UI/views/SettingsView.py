"""Панель настроек: профиль, воспроизведение, загрузки, данные — без VPN и ИИ."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional

import flet as ft

from config import APP_VERSION, DATA_DIR, QUALITY_TO_HEIGHT, settings
from core.profile_service import ProfileError, ProfileService
from UI.components.Common import OutlineButton, StatusChip
from UI.themes.DarkTheme import COLORS, FONT_BOLD
from UI.views.BaseView import BaseView


class SettingsView(BaseView):
    title = "Настройки"

    def __init__(self, session, app):
        super().__init__(session, app)

    def on_show(self) -> None:
        self._load()

    def _load(self) -> None:
        self.set_controls(
            [
                ft.Text("Настройки", size=26, color=ft.Colors.WHITE, font_family=FONT_BOLD),
                self._profile_card(),
                self._playback_card(),
                self._downloads_card(),
                self._data_card(),
                self._about_card(),
            ]
        )

    @staticmethod
    def _card(title: str, icon: str, *controls: ft.Control) -> ft.Control:
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(icon, color=COLORS["gradient1"], size=20),
                            ft.Text(title, size=17, color=ft.Colors.WHITE, font_family=FONT_BOLD),
                        ],
                        spacing=10,
                    ),
                    ft.Divider(height=1, color=ft.Colors.with_opacity(0.08, ft.Colors.WHITE)),
                    *controls,
                ],
                spacing=14,
                tight=True,
            ),
            padding=20,
            border_radius=16,
            bgcolor=COLORS["surface"],
        )

    @staticmethod
    def _row(label: str, control: ft.Control, hint: str = "") -> ft.Control:
        left: List[ft.Control] = [ft.Text(label, size=14, color=ft.Colors.WHITE)]
        if hint:
            left.append(ft.Text(hint, size=12, color=COLORS["muted"], max_lines=3))
        return ft.Row(
            controls=[ft.Column(controls=left, spacing=2, expand=True, tight=True), control],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _switch(self, key: str, on_change: Optional[Callable] = None) -> ft.Switch:
        def handler(e):
            settings.set(key, e.control.value)
            if on_change:
                on_change(e.control.value)

        return ft.Switch(value=bool(settings.get(key)), active_color=COLORS["gradient1"], on_change=handler)

    def _dropdown(self, key: str, options: List[str], width: int = 160) -> ft.Dropdown:
        def handler(e):
            settings.set(key, e.control.value)

        current = str(settings.get(key) or "")
        if current not in options and options:
            current = options[0]

        return ft.Dropdown(
            value=current,
            options=[ft.DropdownOption(key=o, text=o) for o in options],
            width=width,
            border_radius=10,
            bgcolor=COLORS["surface_alt"],
            border_color=ft.Colors.TRANSPARENT,
            color=ft.Colors.WHITE,
            on_select=handler,
        )

    def _text_input(self, key: str, width: int = 320, password: bool = False) -> ft.TextField:
        def handler(e):
            settings.set(key, e.control.value)

        return ft.TextField(
            value=str(settings.get(key) or ""),
            width=width,
            height=44,
            password=password,
            can_reveal_password=password,
            border_radius=10,
            bgcolor=COLORS["surface_alt"],
            border_color=ft.Colors.TRANSPARENT,
            focused_border_color=COLORS["gradient1"],
            color=ft.Colors.WHITE,
            content_padding=ft.Padding(12, 8, 12, 8),
            on_blur=handler,
            on_submit=handler,
        )

    def _profile_card(self) -> ft.Control:
        user = self.session.user
        if user is None:
            return ft.Container()

        stats = ProfileService.summary(user.id)
        return self._card(
            "Профиль",
            ft.Icons.PERSON_ROUNDED,
            ft.Row(
                controls=[
                    ft.Container(
                        width=56,
                        height=56,
                        border_radius=16,
                        bgcolor=user.color or COLORS["gradient1"],
                        alignment=ft.Alignment.CENTER,
                        content=ft.Text(user.initials, size=22, color=ft.Colors.WHITE, font_family=FONT_BOLD),
                    ),
                    ft.Column(
                        controls=[
                            ft.Text(user.display_name, size=17, color=ft.Colors.WHITE, font_family=FONT_BOLD),
                            ft.Text(
                                f"{stats['history']} просмотров • {stats['downloads']} загрузок • {stats['interests']} интересов",
                                size=12,
                                color=COLORS["muted"],
                            ),
                        ],
                        spacing=2,
                        expand=True,
                        tight=True,
                    ),
                ],
                spacing=16,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Row(
                controls=[
                    OutlineButton("Сменить пароль", icon=ft.Icons.LOCK_RESET_ROUNDED, on_click=lambda e: self._password_dialog()),
                    OutlineButton("Сменить аккаунт", icon=ft.Icons.SWITCH_ACCOUNT_ROUNDED, on_click=lambda e: self.app.switch_user()),
                ],
                spacing=10,
                wrap=True,
            ),
            self._interests_block(),
        )

    def _interests_block(self) -> ft.Control:
        try:
            interests = self.session.recommendations.get_user_interests(self.session.user_id, limit=8)
        except Exception:
            interests = []
        if not interests:
            return ft.Container()
        chips = [StatusChip(f"{i['category']} · {i['weight']:.1f}", COLORS["gradient2"] if i["weight"] > 1.5 else COLORS["muted"]) for i in interests]
        return ft.Column(
            controls=[
                ft.Text("Ваши интересы (обновляются автоматически)", size=13, color=COLORS["muted"]),
                ft.Row(chips, spacing=8, wrap=True, run_spacing=8),
            ],
            spacing=8,
            tight=True,
        )

    def _playback_card(self) -> ft.Control:
        volume_label = ft.Text(f"{int(settings.get('default_volume', 80))}%", size=13, color=COLORS["muted"])

        def on_volume(e):
            try:
                value = int(e.control.value)
                settings.set("default_volume", value)
                volume_label.value = f"{value}%"
                volume_label.update()
            except Exception:
                pass

        return self._card(
            "Воспроизведение",
            ft.Icons.PLAY_CIRCLE_ROUNDED,
            self._row("Качество по умолчанию", self._dropdown("preferred_quality", list(QUALITY_TO_HEIGHT.keys()))),
            self._row("Автовоспроизведение", self._switch("autoplay")),
            self._row(
                "Громкость",
                ft.Row(
                    controls=[
                        ft.Slider(min=0, max=100, divisions=20, value=float(settings.get("default_volume", 80)), width=200, active_color=COLORS["gradient1"], on_change=on_volume),
                        volume_label,
                    ],
                    spacing=8,
                    tight=True,
                ),
            ),
            self._row("Вести историю просмотров", self._switch("save_history")),
        )

    def _downloads_card(self) -> ft.Control:
        return self._card(
            "Загрузки",
            ft.Icons.DOWNLOAD_ROUNDED,
            self._row(
                "Папка загрузок",
                ft.Row(
                    controls=[
                        ft.Text(str(settings.get("download_dir"))[-42:], size=12, color=COLORS["muted"]),
                        ft.IconButton(icon=ft.Icons.FOLDER_OPEN_ROUNDED, icon_color=COLORS["muted"], icon_size=18, tooltip="Открыть папку", on_click=lambda e: self._open_downloads()),
                    ],
                    spacing=6,
                    tight=True,
                ),
            ),
            self._row("Качество загрузки", self._dropdown("download_quality", list(QUALITY_TO_HEIGHT.keys()))),
            self._row("Формат аудио", self._dropdown("audio_format", ["mp3", "m4a", "opus"], 120)),
            self._row("Одновременных загрузок", self._dropdown("max_parallel_downloads", ["1", "2", "3", "4"], 100)),
            self._row("Встраивать обложку в аудио", self._switch("embed_thumbnail")),
        )

    def _open_downloads(self) -> None:
        folder = Path(settings.get("download_dir"))
        folder.mkdir(parents=True, exist_ok=True)
        try:
            self.page.launch_url(folder.as_uri())
        except Exception:
            self.app.toast(f"Папка загрузок: {folder}")

    def _data_card(self) -> ft.Control:
        return self._card(
            "Данные",
            ft.Icons.STORAGE_ROUNDED,
            self._row("Папка данных", ft.Text(str(DATA_DIR), size=12, color=COLORS["muted"], max_lines=2)),
            self._row("Рекомендаций на странице", self._dropdown("recommendations_count", ["12", "24", "36", "48"], 100)),
            ft.Row(
                controls=[
                    OutlineButton("Очистить историю", icon=ft.Icons.DELETE_SWEEP_ROUNDED, on_click=lambda e: self.app.navigate("history"), color=COLORS["warning"]),
                    OutlineButton("Сбросить настройки", icon=ft.Icons.RESTART_ALT_ROUNDED, on_click=lambda e: self._confirm_reset(), color=COLORS["error"]),
                ],
                spacing=10,
                wrap=True,
            ),
        )

    def _about_card(self) -> ft.Control:
        return self._card(
            "О программе",
            ft.Icons.INFO_OUTLINE_ROUNDED,
            ft.Text(f"Kinoshka {APP_VERSION}", size=14, color=ft.Colors.WHITE),
            ft.Text("Видео с YouTube, фильмы и сериалы с RuTube, музыка с Яндекс Музыки — онлайн и офлайн. Разработано Budin's industries.", size=13, color=COLORS["muted"]),
        )

    def _password_dialog(self) -> None:
        old_field = ft.TextField(label="Текущий пароль", password=True, can_reveal_password=True, width=300)
        new_field = ft.TextField(label="Новый пароль", password=True, can_reveal_password=True, width=300)
        error = ft.Text("", color=COLORS["error"], size=12, visible=False)

        def save(e):
            try:
                ProfileService.change_password(self.session.user_id, old_field.value, new_field.value)
            except ProfileError as exc:
                error.value = str(exc)
                error.visible = True
                try:
                    error.update()
                except Exception:
                    pass
                return
            try:
                self.page.close(dialog)
            except Exception:
                pass
            self.app.toast("Пароль обновлён")

        dialog = ft.AlertDialog(
            modal=True,
            bgcolor=COLORS["surface"],
            title=ft.Text("Смена пароля", color=ft.Colors.WHITE),
            content=ft.Column([old_field, new_field, error], spacing=12, tight=True, height=180),
            actions=[ft.TextButton("Отмена", on_click=lambda e: self.page.close(dialog)), ft.TextButton("Сохранить", on_click=save)],
        )
        self.page.open(dialog)

    def _confirm_reset(self) -> None:
        def confirm(e):
            settings.reset()
            try:
                self.page.close(dialog)
            except Exception:
                pass
            self.app.toast("Настройки сброшены")
            self._load()

        dialog = ft.AlertDialog(
            modal=True,
            bgcolor=COLORS["surface"],
            title=ft.Text("Сбросить настройки?", color=ft.Colors.WHITE),
            content=ft.Text("Все параметры вернутся к значениям по умолчанию. Профили, история и скачанные файлы не пострадают.", color=COLORS["muted"]),
            actions=[ft.TextButton("Отмена", on_click=lambda e: self.page.close(dialog)), ft.TextButton("Сбросить", on_click=confirm, style=ft.ButtonStyle(color=COLORS["error"]))],
        )
        self.page.open(dialog)
