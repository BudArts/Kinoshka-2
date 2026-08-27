"""Панель настроек: профиль, VPN, воспроизведение, загрузки, ИИ, данные."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, List, Optional

import flet as ft

from config import APP_VERSION, DATA_DIR, QUALITY_TO_HEIGHT, settings
from core.profile_service import ProfileError, ProfileService
from core.vpn import VpnError, vpn_manager
from UI.components.Common import (
    GradientButton,
    OutlineButton,
    SectionTitle,
    StatusChip,
)
from UI.themes.DarkTheme import COLORS, FONT_BOLD
from UI.views.BaseView import BaseView


class SettingsView(BaseView):
    """Все настройки приложения на одном экране, разбитые на карточки."""

    title = "Настройки"

    def __init__(self, session, app):
        super().__init__(session, app)
        self._file_picker: Optional[ft.FilePicker] = None
        self._vpn_status_text = ft.Text("", size=13, color=COLORS["muted"])
        self._vpn_list = ft.Column(spacing=8)

    # ------------------------------------------------------------------ #
    def on_show(self) -> None:
        self._ensure_file_picker()
        self._load()

    def _ensure_file_picker(self) -> None:
        """FilePicker должен жить в overlay страницы (в Flet 0.86 — сервис)."""
        if self._file_picker is None:
            self._file_picker = ft.FilePicker()
            self.page.overlay.append(self._file_picker)
            try:
                self.page.update()
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    def _load(self) -> None:
        self.set_controls(
            [
                ft.Text("Настройки", size=26, color=ft.Colors.WHITE,
                        font_family=FONT_BOLD),
                self._profile_card(),
                self._vpn_card(),
                self._playback_card(),
                self._downloads_card(),
                self._ai_card(),
                self._data_card(),
                self._about_card(),
            ]
        )

    # ================================================================== #
    #  Карточки
    # ================================================================== #
    @staticmethod
    def _card(title: str, icon: str, *controls: ft.Control) -> ft.Control:
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(icon, color=COLORS["gradient1"], size=20),
                            ft.Text(title, size=17, color=ft.Colors.WHITE,
                                    font_family=FONT_BOLD),
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
        """Строка настройки: подпись слева, элемент управления справа."""
        left: List[ft.Control] = [ft.Text(label, size=14, color=ft.Colors.WHITE)]
        if hint:
            left.append(ft.Text(hint, size=12, color=COLORS["muted"], max_lines=2))

        return ft.Row(
            controls=[
                ft.Column(controls=left, spacing=2, expand=True, tight=True),
                control,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _switch(self, key: str, on_change: Optional[Callable] = None) -> ft.Switch:
        def handler(e):
            settings.set(key, e.control.value)
            if on_change:
                on_change(e.control.value)

        return ft.Switch(
            value=bool(settings.get(key)),
            active_color=COLORS["gradient1"],
            on_change=handler,
        )

    def _dropdown(self, key: str, options: List[str], width: int = 160) -> ft.Dropdown:
        def handler(e):
            # В Flet 0.86 у Dropdown событие называется on_select, а значение
            # приходит в e.control.value.
            settings.set(key, e.control.value)

        return ft.Dropdown(
            value=str(settings.get(key)),
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

    # ------------------------------------------------------------------ #
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
                        width=56, height=56, border_radius=16,
                        bgcolor=user.color or COLORS["gradient1"],
                        alignment=ft.Alignment.CENTER,
                        content=ft.Text(user.initials, size=22, color=ft.Colors.WHITE,
                                        font_family=FONT_BOLD),
                    ),
                    ft.Column(
                        controls=[
                            ft.Text(user.display_name, size=17, color=ft.Colors.WHITE,
                                    font_family=FONT_BOLD),
                            ft.Text(
                                f"{stats['history']} просмотров • "
                                f"{stats['downloads']} загрузок • "
                                f"{stats['interests']} интересов",
                                size=12, color=COLORS["muted"],
                            ),
                        ],
                        spacing=2, expand=True, tight=True,
                    ),
                ],
                spacing=16,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Row(
                controls=[
                    OutlineButton("Сменить пароль", icon=ft.Icons.LOCK_RESET_ROUNDED,
                                  on_click=lambda e: self._password_dialog()),
                    OutlineButton("Сменить аккаунт", icon=ft.Icons.SWITCH_ACCOUNT_ROUNDED,
                                  on_click=lambda e: self.app.switch_user()),
                ],
                spacing=10, wrap=True,
            ),
            self._interests_block(),
        )

    def _interests_block(self) -> ft.Control:
        """Топ интересов — показываем, на чём строятся рекомендации."""
        try:
            interests = self.session.recommendations.get_user_interests(
                self.session.user_id, limit=8
            )
        except Exception:
            interests = []

        if not interests:
            return ft.Container()

        chips = [
            StatusChip(
                f"{i['category']} · {i['weight']:.1f}",
                COLORS["gradient2"] if i["weight"] > 1.5 else COLORS["muted"],
            )
            for i in interests
        ]
        return ft.Column(
            controls=[
                ft.Text("Ваши интересы (обновляются автоматически)", size=13,
                        color=COLORS["muted"]),
                ft.Row(chips, spacing=8, wrap=True, run_spacing=8),
            ],
            spacing=8, tight=True,
        )

    # ------------------------------------------------------------------ #
    def _vpn_card(self) -> ft.Control:
        self._refresh_vpn_list()

        backend_ok = vpn_manager.backend_available()
        backend_note = (
            "Системный клиент WireGuard найден."
            if backend_ok
            else "Клиент WireGuard не найден. Установите его с wireguard.com "
                 "или используйте прокси ниже."
        )

        return self._card(
            "VPN для YouTube",
            ft.Icons.VPN_LOCK_ROUNDED,
            ft.Text(
                "В России YouTube не открывается напрямую. Импортируйте .conf-файлы "
                "WireGuard — приложение будет поднимать туннель само перед запросами.",
                size=13, color=COLORS["muted"],
            ),
            StatusChip(
                backend_note,
                COLORS["success"] if backend_ok else COLORS["warning"],
                ft.Icons.INFO_OUTLINE_ROUNDED,
            ),
            self._row(
                "Использовать VPN",
                self._switch("vpn_enabled", on_change=lambda v: self._toggle_vpn(v)),
                "Автоматически включать туннель для YouTube",
            ),
            self._row(
                "Подключаться автоматически",
                self._switch("vpn_auto_connect"),
                "Поднимать туннель при первом запросе к источнику",
            ),
            ft.Row(
                controls=[
                    GradientButton("Импортировать .conf", icon=ft.Icons.UPLOAD_FILE_ROUNDED,
                                   on_click=self._on_import_click),
                    OutlineButton("Проверить соединение", icon=ft.Icons.NETWORK_CHECK_ROUNDED,
                                  on_click=lambda e: self._check_connection()),
                    OutlineButton("Открыть папку конфигов", icon=ft.Icons.FOLDER_ROUNDED,
                                  on_click=lambda e: self._open_vpn_folder()),
                ],
                spacing=10, wrap=True,
            ),
            self._vpn_status_text,
            self._vpn_list,
            self._row(
                "Прокси (запасной вариант)",
                self._text_input("proxy_url"),
                "http://user:pass@host:port или socks5://host:port",
            ),
        )

    def _refresh_vpn_list(self) -> None:
        """Перечитать список импортированных конфигураций."""
        configs = vpn_manager.list_configs()
        active = settings.get("vpn_active_config")

        if not configs:
            self._vpn_list.controls = [
                ft.Container(
                    content=ft.Text(
                        "Конфигурации не добавлены. Нажмите «Импортировать .conf» "
                        "и выберите файлы, которые вам выдал провайдер VPN.",
                        size=13, color=COLORS["muted"],
                    ),
                    padding=14,
                    border_radius=10,
                    bgcolor=COLORS["surface_alt"],
                )
            ]
        else:
            rows: List[ft.Control] = []
            for config in configs:
                is_active = config.name == active
                connected = vpn_manager.active_config == config.name
                rows.append(
                    ft.Container(
                        content=ft.Row(
                            controls=[
                                ft.Icon(
                                    ft.Icons.CHECK_CIRCLE_ROUNDED if connected
                                    else ft.Icons.RADIO_BUTTON_UNCHECKED,
                                    size=18,
                                    color=COLORS["success"] if connected
                                    else (COLORS["gradient1"] if is_active
                                          else COLORS["muted"]),
                                ),
                                ft.Column(
                                    controls=[
                                        ft.Text(config.name, size=14,
                                                color=ft.Colors.WHITE),
                                        ft.Text(f"сервер: {config.location_hint}",
                                                size=12, color=COLORS["muted"]),
                                    ],
                                    spacing=1, expand=True, tight=True,
                                ),
                                ft.TextButton(
                                    "Отключить" if connected else "Подключить",
                                    on_click=(
                                        lambda e: self._disconnect_vpn()
                                    ) if connected else (
                                        lambda e, n=config.name: self._connect_vpn(n)
                                    ),
                                    style=ft.ButtonStyle(color=COLORS["gradient2"]),
                                ),
                                ft.IconButton(
                                    icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                                    icon_color=COLORS["error"], icon_size=18,
                                    tooltip="Удалить конфигурацию",
                                    on_click=lambda e, n=config.name: self._delete_config(n),
                                ),
                            ],
                            spacing=12,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=ft.Padding(14, 10, 8, 10),
                        border_radius=10,
                        bgcolor=COLORS["surface_alt"],
                        border=ft.Border.all(
                            1, COLORS["gradient1"] if is_active else ft.Colors.TRANSPARENT
                        ),
                    )
                )
            self._vpn_list.controls = rows

        try:
            self._vpn_list.update()
        except Exception:
            pass

    # -- действия VPN -------------------------------------------------- #
    async def _on_import_click(self, e) -> None:
        """Обработчик кнопки импорта — асинхронный, т.к. диалог выбора файлов
        в Flet 0.86 возвращает результат через await."""
        await self._pick_configs()

    async def _pick_configs(self) -> None:
        """Выбор .conf-файлов. В Flet 0.86 pick_files() — корутина, которая
        сама возвращает выбранные файлы, без отдельного события on_result."""
        self._ensure_file_picker()
        try:
            files = await self._file_picker.pick_files(
                dialog_title="Выберите конфигурации WireGuard",
                allowed_extensions=["conf"],
                allow_multiple=True,
            )
        except Exception as exc:
            self.app.toast(f"Не удалось открыть диалог выбора файлов: {exc}", error=True)
            return
        self._import_picked([f.path for f in (files or []) if getattr(f, "path", None)])

    def _import_picked(self, paths: List[str]) -> None:
        """Скопировать выбранные конфигурации в каталог приложения."""
        if not paths:
            return
        imported = vpn_manager.import_many(paths)
        if imported:
            # Первую импортированную сразу делаем активной, если активной не было.
            if not settings.get("vpn_active_config"):
                settings.set("vpn_active_config", imported[0].name)
            settings.set("vpn_enabled", True)
            self.app.toast(f"Добавлено конфигураций: {len(imported)}")
        else:
            self.app.toast("Не удалось прочитать выбранные файлы", error=True)
        self._load()

    def _connect_vpn(self, name: str) -> None:
        """Подключение выполняется в фоне — wg-quick работает несколько секунд."""
        self._set_vpn_status("Подключаемся…", COLORS["warning"])
        self.app.appbar.set_vpn_status("connecting")

        def work():
            try:
                vpn_manager.connect(name)
                return None
            except VpnError as exc:
                return exc

        def done(error):
            if error is None:
                self._set_vpn_status(f"Подключено: {name}", COLORS["success"])
                self.app.appbar.set_vpn_status("connected", name)
                self.app.toast(f"VPN подключён: {name}")
            else:
                self._set_vpn_status(str(error), COLORS["error"])
                self.app.appbar.set_vpn_status("error")
                self.app.toast(str(error), error=True)
            self._refresh_vpn_list()

        threading.Thread(
            target=lambda: done(work()), daemon=True
        ).start()

    def _disconnect_vpn(self) -> None:
        vpn_manager.disconnect()
        self._set_vpn_status("Туннель отключён", COLORS["muted"])
        self.app.appbar.set_vpn_status("disconnected")
        self._refresh_vpn_list()

    def _toggle_vpn(self, enabled: bool) -> None:
        if not enabled and vpn_manager.is_connected:
            self._disconnect_vpn()
        elif enabled and settings.get("vpn_active_config"):
            self._connect_vpn(settings.get("vpn_active_config"))

    def _check_connection(self) -> None:
        self._set_vpn_status("Проверяем доступ к YouTube…", COLORS["warning"])

        def work():
            return vpn_manager.check_connection(), vpn_manager.public_ip()

        def done(result):
            ok, ip = result
            if ok:
                self._set_vpn_status(
                    f"YouTube доступен. Внешний IP: {ip or 'неизвестен'}",
                    COLORS["success"],
                )
            else:
                self._set_vpn_status(
                    "YouTube недоступен. Включите VPN или проверьте интернет.",
                    COLORS["error"],
                )

        threading.Thread(target=lambda: done(work()), daemon=True).start()

    def _delete_config(self, name: str) -> None:
        vpn_manager.delete_config(name)
        self.app.toast(f"Конфигурация «{name}» удалена")
        self._load()

    def _open_vpn_folder(self) -> None:
        from config import VPN_DIR

        VPN_DIR.mkdir(parents=True, exist_ok=True)
        try:
            self.page.launch_url(VPN_DIR.as_uri())
        except Exception:
            self.app.toast(f"Папка конфигураций: {VPN_DIR}")

    def _set_vpn_status(self, text: str, color: str) -> None:
        self._vpn_status_text.value = text
        self._vpn_status_text.color = color
        try:
            self._vpn_status_text.update()
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    def _playback_card(self) -> ft.Control:
        volume_label = ft.Text(
            f"{int(settings.get('default_volume', 80))}%", size=13, color=COLORS["muted"]
        )

        def on_volume(e):
            value = int(e.control.value)
            settings.set("default_volume", value)
            volume_label.value = f"{value}%"
            volume_label.update()

        return self._card(
            "Воспроизведение",
            ft.Icons.PLAY_CIRCLE_ROUNDED,
            self._row(
                "Качество по умолчанию",
                self._dropdown("preferred_quality", list(QUALITY_TO_HEIGHT.keys())),
                "Чем выше качество, тем больше трафика через VPN",
            ),
            self._row("Автовоспроизведение", self._switch("autoplay")),
            self._row(
                "Громкость",
                ft.Row(
                    controls=[
                        ft.Slider(
                            min=0, max=100, divisions=20,
                            value=float(settings.get("default_volume", 80)),
                            width=200,
                            active_color=COLORS["gradient1"],
                            on_change=on_volume,
                        ),
                        volume_label,
                    ],
                    spacing=8, tight=True,
                ),
            ),
            self._row(
                "Вести историю просмотров",
                self._switch("save_history"),
                "История нужна для персональных рекомендаций",
            ),
        )

    def _downloads_card(self) -> ft.Control:
        return self._card(
            "Загрузки",
            ft.Icons.DOWNLOAD_ROUNDED,
            self._row(
                "Папка загрузок",
                ft.Row(
                    controls=[
                        ft.Text(
                            str(settings.get("download_dir"))[-42:],
                            size=12, color=COLORS["muted"],
                        ),
                        ft.IconButton(
                            icon=ft.Icons.FOLDER_OPEN_ROUNDED,
                            icon_color=COLORS["muted"], icon_size=18,
                            tooltip="Открыть папку",
                            on_click=lambda e: self._open_downloads(),
                        ),
                    ],
                    spacing=6, tight=True,
                ),
            ),
            self._row(
                "Качество загрузки",
                self._dropdown("download_quality", list(QUALITY_TO_HEIGHT.keys())),
            ),
            self._row("Формат аудио", self._dropdown("audio_format", ["mp3", "m4a", "opus"], 120)),
            self._row(
                "Одновременных загрузок",
                self._dropdown("max_parallel_downloads", ["1", "2", "3", "4"], 100),
                "Изменение вступит в силу после перезапуска",
            ),
            self._row(
                "Встраивать обложку в аудио",
                self._switch("embed_thumbnail"),
                "Требуется установленный ffmpeg",
            ),
        )

    def _open_downloads(self) -> None:
        folder = Path(settings.get("download_dir"))
        folder.mkdir(parents=True, exist_ok=True)
        try:
            self.page.launch_url(folder.as_uri())
        except Exception:
            self.app.toast(f"Папка загрузок: {folder}")

    def _ai_card(self) -> ft.Control:
        return self._card(
            "Поиск с ИИ и метаданные",
            ft.Icons.AUTO_AWESOME_ROUNDED,
            ft.Text(
                "Умный поиск понимает запросы вроде «комедия про роботов с высоким "
                "рейтингом». Нужен ключ OpenAI-совместимого API. Без ключа поиск "
                "работает по упрощённому разбору запроса — жанры, годы и рейтинг "
                "определяются по ключевым словам.",
                size=13, color=COLORS["muted"],
            ),
            self._row("Включить ИИ-поиск", self._switch("ai_enabled")),
            self._row("Адрес API", self._text_input("ai_base_url")),
            self._row("Ключ API", self._text_input("ai_api_key", password=True)),
            self._row("Модель", self._text_input("ai_model", width=220)),
            ft.Divider(height=1, color=ft.Colors.with_opacity(0.08, ft.Colors.WHITE)),
            ft.Text(
                "Кинопоиск добавляет к фильмам рейтинг, постер, год и жанры. "
                "Бесплатный ключ выдаётся на kinopoisk.dev — без него раздел "
                "работает, но без этих данных.",
                size=13, color=COLORS["muted"],
            ),
            self._row(
                "Ключ Кинопоиска",
                self._text_input("kinopoisk_api_key", password=True),
                "kinopoisk.dev — бесплатный тариф",
            ),
        )

    def _data_card(self) -> ft.Control:
        return self._card(
            "Данные",
            ft.Icons.STORAGE_ROUNDED,
            self._row(
                "Папка данных",
                ft.Text(str(DATA_DIR), size=12, color=COLORS["muted"], max_lines=2),
                "Здесь лежат база, настройки и VPN-конфигурации",
            ),
            self._row(
                "Рекомендаций на странице",
                self._dropdown("recommendations_count", ["12", "24", "36", "48"], 100),
            ),
            ft.Row(
                controls=[
                    OutlineButton("Очистить историю", icon=ft.Icons.DELETE_SWEEP_ROUNDED,
                                  on_click=lambda e: self.app.navigate("history"),
                                  color=COLORS["warning"]),
                    OutlineButton("Сбросить настройки", icon=ft.Icons.RESTART_ALT_ROUNDED,
                                  on_click=lambda e: self._confirm_reset(),
                                  color=COLORS["error"]),
                ],
                spacing=10, wrap=True,
            ),
        )

    def _about_card(self) -> ft.Control:
        return self._card(
            "О программе",
            ft.Icons.INFO_OUTLINE_ROUNDED,
            ft.Text(f"Kinoshka {APP_VERSION}", size=14, color=ft.Colors.WHITE),
            ft.Text(
                "Видео с YouTube, фильмы и сериалы с RuTube, музыка — онлайн "
                "и офлайн. Разработано Budin's industries.",
                size=13, color=COLORS["muted"],
            ),
        )

    # ------------------------------------------------------------------ #
    def _password_dialog(self) -> None:
        old_field = ft.TextField(label="Текущий пароль", password=True,
                                 can_reveal_password=True, width=300)
        new_field = ft.TextField(label="Новый пароль", password=True,
                                 can_reveal_password=True, width=300)
        error = ft.Text("", color=COLORS["error"], size=12, visible=False)

        def save(e):
            try:
                ProfileService.change_password(
                    self.session.user_id, old_field.value, new_field.value
                )
            except ProfileError as exc:
                error.value = str(exc)
                error.visible = True
                error.update()
                return
            self.page.close(dialog)
            self.app.toast("Пароль обновлён")

        dialog = ft.AlertDialog(
            modal=True,
            bgcolor=COLORS["surface"],
            title=ft.Text("Смена пароля", color=ft.Colors.WHITE),
            content=ft.Column([old_field, new_field, error], spacing=12, tight=True,
                              height=180),
            actions=[
                ft.TextButton("Отмена", on_click=lambda e: self.page.close(dialog)),
                ft.TextButton("Сохранить", on_click=save),
            ],
        )
        self.page.open(dialog)

    def _confirm_reset(self) -> None:
        def confirm(e):
            settings.reset()
            self.page.close(dialog)
            self.app.toast("Настройки сброшены")
            self._load()

        dialog = ft.AlertDialog(
            modal=True,
            bgcolor=COLORS["surface"],
            title=ft.Text("Сбросить настройки?", color=ft.Colors.WHITE),
            content=ft.Text(
                "Все параметры вернутся к значениям по умолчанию. Профили, "
                "история и скачанные файлы не пострадают.",
                color=COLORS["muted"],
            ),
            actions=[
                ft.TextButton("Отмена", on_click=lambda e: self.page.close(dialog)),
                ft.TextButton("Сбросить", on_click=confirm,
                              style=ft.ButtonStyle(color=COLORS["error"])),
            ],
        )
        self.page.open(dialog)
