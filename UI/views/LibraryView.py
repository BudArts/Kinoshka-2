"""Библиотека скачанного: «Мои видео», «Мои фильмы», «Моя музыка».

Показывает и готовые файлы, и активные загрузки с живым прогрессом
(подписка на DownloadManager).
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import flet as ft

from core.downloader import download_manager
from core.media import MediaItem
from database.models import Collection
from UI.components.Common import EmptyState, OutlineButton, SectionTitle, StatusChip
from UI.themes.DarkTheme import COLORS, FONT_BOLD
from UI.views.BaseView import BaseView

#: Подписи статусов загрузки.
STATUS_LABELS = {
    "queued": ("В очереди", COLORS["muted"], ft.Icons.SCHEDULE_ROUNDED),
    "downloading": ("Скачивается", COLORS["warning"], ft.Icons.DOWNLOADING_ROUNDED),
    "processing": ("Обработка", COLORS["warning"], ft.Icons.SETTINGS_ROUNDED),
    "done": ("Готово", COLORS["success"], ft.Icons.CHECK_CIRCLE_ROUNDED),
    "error": ("Ошибка", COLORS["error"], ft.Icons.ERROR_ROUNDED),
    "canceled": ("Отменено", COLORS["muted"], ft.Icons.CANCEL_ROUNDED),
}


class LibraryView(BaseView):
    """Список скачанного для одного типа контента."""

    def __init__(self, session, app, media_type: str = "video", title: str = "Мои видео"):
        super().__init__(session, app)
        self.media_type = media_type
        self.title = title
        #: id записи -> элементы строки прогресса, чтобы обновлять точечно.
        self._rows: Dict[int, Dict[str, ft.Control]] = {}
        self._subscribed = False

    # ------------------------------------------------------------------ #
    def on_show(self) -> None:
        if not self._subscribed:
            download_manager.add_listener(self._on_progress)
            self._subscribed = True
        self._load()

    def on_hide(self) -> None:
        if self._subscribed:
            download_manager.remove_listener(self._on_progress)
            self._subscribed = False

    # ------------------------------------------------------------------ #
    def _load(self) -> None:
        user_id = self.session.user_id
        if not user_id:
            return

        records = download_manager.library(user_id, self.media_type)
        self._rows.clear()

        if not records:
            self.set_controls(
                [
                    self._header(0, 0),
                    EmptyState(
                        "Здесь пока пусто",
                        "Скачанные файлы появятся тут и будут доступны без интернета. "
                        "Нажмите на значок загрузки на любой карточке.",
                        icon=ft.Icons.DOWNLOAD_ROUNDED,
                        action_text="Найти что посмотреть",
                        on_action=lambda: self.app.navigate(self._source_route()),
                    ),
                ]
            )
            return

        active = [r for r in records if r.status in ("queued", "downloading", "processing")]
        finished = [r for r in records if r.status == "done"]
        failed = [r for r in records if r.status in ("error", "canceled")]

        total_size = sum(r.filesize or 0 for r in finished)
        controls: List[ft.Control] = [self._header(len(finished), total_size)]

        if active:
            controls.append(SectionTitle("Загружается сейчас",
                                         icon=ft.Icons.DOWNLOADING_ROUNDED))
            controls.extend(self._row(r) for r in active)

        if finished:
            controls.append(SectionTitle("Скачано", icon=ft.Icons.FOLDER_ROUNDED))
            controls.extend(self._row(r) for r in finished)

        if failed:
            controls.append(
                SectionTitle(
                    "Не удалось скачать",
                    action_text="Очистить",
                    on_action=lambda: self._clear_failed(failed),
                    icon=ft.Icons.ERROR_OUTLINE_ROUNDED,
                )
            )
            controls.extend(self._row(r) for r in failed)

        self.set_controls(controls)

    def _source_route(self) -> str:
        return {"video": "video", "film": "films", "music": "music"}.get(
            self.media_type, "video"
        )

    def _header(self, count: int, total_size: int) -> ft.Control:
        size_mb = total_size / 1024 / 1024
        size_text = (
            f"{size_mb / 1024:.1f} ГБ" if size_mb >= 1024 else f"{size_mb:.0f} МБ"
        )
        return ft.Row(
            controls=[
                ft.Text(self.title, size=26, color=ft.Colors.WHITE, font_family=FONT_BOLD),
                ft.Row(
                    controls=[
                        StatusChip(f"{count} файлов", COLORS["muted"],
                                   ft.Icons.VIDEO_LIBRARY_ROUNDED),
                        StatusChip(size_text, COLORS["muted"], ft.Icons.STORAGE_ROUNDED),
                        OutlineButton("Обновить", icon=ft.Icons.REFRESH_ROUNDED,
                                      on_click=lambda e: self._load()),
                    ],
                    spacing=10,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            wrap=True,
        )

    # ------------------------------------------------------------------ #
    def _row(self, record: Collection) -> ft.Control:
        """Строка одного файла/загрузки."""
        label, color, icon = STATUS_LABELS.get(
            record.status, STATUS_LABELS["queued"]
        )

        status_text = ft.Text(label, size=12, color=color)
        progress_bar = ft.ProgressBar(
            value=(record.progress or 0) / 100,
            color=COLORS["gradient1"],
            bgcolor=COLORS["surface_alt"],
            height=4,
            visible=record.status in ("queued", "downloading", "processing"),
        )

        thumb = ft.Container(
            width=112,
            height=63,
            border_radius=8,
            bgcolor=COLORS["surface_alt"],
            content=ft.Image(
                src=record.thumbnail or "",
                width=112, height=63,
                fit=ft.BoxFit.COVER,
                border_radius=8,
                error_content=ft.Icon(icon, color=COLORS["muted"], size=24),
            ),
        )

        meta_parts = [p for p in (record.author, record.quality) if p]
        if record.filesize:
            meta_parts.append(record.size_human)
        if record.status == "error" and record.error:
            meta_parts = [record.error[:90]]

        info = ft.Column(
            controls=[
                ft.Text(record.title, size=15, color=ft.Colors.WHITE, max_lines=2,
                        overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(" • ".join(meta_parts) or "—", size=12, color=COLORS["muted"],
                        max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                ft.Row([ft.Icon(icon, size=13, color=color), status_text], spacing=5),
                progress_bar,
            ],
            spacing=4,
            expand=True,
            tight=True,
        )

        actions: List[ft.Control] = []
        if record.status == "done" and record.exists_on_disk:
            actions.append(
                ft.IconButton(
                    icon=ft.Icons.PLAY_CIRCLE_FILL_ROUNDED,
                    icon_color=COLORS["gradient1"],
                    tooltip="Смотреть офлайн",
                    on_click=lambda e, r=record: self._play_local(r),
                )
            )
            actions.append(
                ft.IconButton(
                    icon=ft.Icons.FOLDER_OPEN_ROUNDED,
                    icon_color=COLORS["muted"],
                    tooltip="Показать в папке",
                    on_click=lambda e, r=record: self._reveal(r),
                )
            )
        elif record.status in ("queued", "downloading", "processing"):
            actions.append(
                ft.IconButton(
                    icon=ft.Icons.STOP_CIRCLE_ROUNDED,
                    icon_color=COLORS["warning"],
                    tooltip="Отменить загрузку",
                    on_click=lambda e, r=record: self._cancel(r.id),
                )
            )
        elif record.status in ("error", "canceled"):
            actions.append(
                ft.IconButton(
                    icon=ft.Icons.REFRESH_ROUNDED,
                    icon_color=COLORS["muted"],
                    tooltip="Скачать заново",
                    on_click=lambda e, r=record: self._retry(r),
                )
            )

        actions.append(
            ft.IconButton(
                icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                icon_color=COLORS["error"],
                tooltip="Удалить",
                on_click=lambda e, r=record: self._confirm_delete(r),
            )
        )

        row = ft.Container(
            content=ft.Row(
                controls=[thumb, info, ft.Row(actions, spacing=0)],
                spacing=14,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=12,
            border_radius=14,
            bgcolor=COLORS["surface"],
        )

        self._rows[record.id] = {
            "status": status_text,
            "progress": progress_bar,
            "container": row,
        }
        return row

    # ------------------------------------------------------------------ #
    #  Действия
    # ------------------------------------------------------------------ #
    def _play_local(self, record: Collection) -> None:
        """Открыть скачанный файл во встроенном плеере."""
        item = MediaItem(
            id=record.video_id or str(record.id),
            title=record.title,
            url=record.source_url or record.path or "",
            platform="local",
            content_type=record.type,
            author=record.author,
            thumbnail=record.thumbnail,
            duration=record.duration,
            local_path=record.path,
        )
        self.app.open_player(item)

    def _reveal(self, record: Collection) -> None:
        """Открыть папку с файлом системным файловым менеджером."""
        if not record.path:
            return
        folder = Path(record.path).parent
        try:
            self.page.launch_url(folder.as_uri())
        except Exception:
            self.app.toast(f"Файл лежит здесь: {folder}")

    def _cancel(self, collection_id: int) -> None:
        download_manager.cancel(collection_id)
        self.app.toast("Загрузка отменена")
        self._load()

    def _retry(self, record: Collection) -> None:
        """Повторить неудачную загрузку."""
        download_manager.delete(record.id, remove_file=False)
        item = MediaItem(
            id=record.video_id or "",
            title=record.title,
            url=record.source_url or "",
            platform=record.platform or "youtube",
            content_type=record.type,
            author=record.author,
            thumbnail=record.thumbnail,
            duration=record.duration,
        )
        self.app.download_item(item, audio_only=(record.type == "music"))
        self._load()

    def _confirm_delete(self, record: Collection) -> None:
        def confirm(e):
            download_manager.delete(record.id, remove_file=True)
            self.page.close(dialog)
            self.app.toast("Удалено")
            self._load()

        dialog = ft.AlertDialog(
            modal=True,
            bgcolor=COLORS["surface"],
            title=ft.Text("Удалить файл?", color=ft.Colors.WHITE),
            content=ft.Text(
                f"«{record.title}» будет удалён с диска безвозвратно.",
                color=COLORS["muted"],
            ),
            actions=[
                ft.TextButton("Отмена", on_click=lambda e: self.page.close(dialog)),
                ft.TextButton("Удалить", on_click=confirm,
                              style=ft.ButtonStyle(color=COLORS["error"])),
            ],
        )
        self.page.open(dialog)

    def _clear_failed(self, records: List[Collection]) -> None:
        for record in records:
            download_manager.delete(record.id, remove_file=False)
        self._load()

    # ------------------------------------------------------------------ #
    def _on_progress(self, collection_id: int, status: str, percent: int, message: str) -> None:
        """Живое обновление строки без перерисовки всего списка."""
        row = self._rows.get(collection_id)
        if row is None:
            # Загрузка началась, когда экран уже был открыт — обновим целиком.
            if status in ("done", "error"):
                try:
                    self._load()
                except Exception:
                    pass
            return

        label, color, _ = STATUS_LABELS.get(status, STATUS_LABELS["downloading"])
        row["status"].value = message or label
        row["status"].color = color
        row["progress"].value = percent / 100
        row["progress"].visible = status in ("queued", "downloading", "processing")

        try:
            row["container"].update()
        except Exception:
            pass

        if status == "done":
            # Появился размер файла и кнопка воспроизведения — нужна перерисовка.
            try:
                self._load()
            except Exception:
                pass
