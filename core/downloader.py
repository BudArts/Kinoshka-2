"""Менеджер загрузок.

Скачивает видео и музыку через yt-dlp в фоновых потоках, пишет прогресс в
таблицу collection и уведомляет UI через колбэки. Одновременных загрузок
не больше, чем задано в настройках (max_parallel_downloads).
"""

from __future__ import annotations

import logging
import re
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from yt_dlp import YoutubeDL

from config import QUALITY_TO_HEIGHT, download_dir_for, settings
from core.media import MediaItem
from core.vpn import vpn_manager
from database import session_scope
from database.models import Collection

log = logging.getLogger(__name__)

#: Колбэк прогресса: (collection_id, status, percent, сообщение)
ProgressCallback = Callable[[int, str, int, str], None]

_ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_filename(name: str, max_length: int = 120) -> str:
    """Имя файла, безопасное для Windows и Linux."""
    cleaned = _ILLEGAL_CHARS.sub("_", name).strip(" .")
    return (cleaned or "download")[:max_length]


class DownloadTask:
    """Одна загрузка: связка записи в БД, потока yt-dlp и флага отмены."""

    def __init__(self, collection_id: int, item: MediaItem, audio_only: bool):
        self.collection_id = collection_id
        self.item = item
        self.audio_only = audio_only
        self.cancel_event = threading.Event()
        self.future: Optional[Future] = None
        self.progress = 0
        self.status = "queued"

    def cancel(self) -> None:
        self.cancel_event.set()
        if self.future:
            # Отменится, только если ещё не начал выполняться.
            self.future.cancel()


class _Canceled(Exception):
    """Внутреннее исключение для мягкой остановки yt-dlp."""


class DownloadManager:
    """Очередь загрузок с ограничением параллелизма."""

    def __init__(self, vpn=None):
        self.vpn = vpn or vpn_manager
        max_workers = max(1, int(settings.get("max_parallel_downloads", 2)))
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="kinoshka-dl"
        )
        self._tasks: Dict[int, DownloadTask] = {}
        self._lock = threading.RLock()
        self._listeners: List[ProgressCallback] = []

    # ------------------------------------------------------------------ #
    #  Подписка UI на прогресс
    # ------------------------------------------------------------------ #
    def add_listener(self, callback: ProgressCallback) -> None:
        self._listeners.append(callback)

    def remove_listener(self, callback: ProgressCallback) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _emit(self, collection_id: int, status: str, percent: int, message: str = "") -> None:
        for callback in list(self._listeners):
            try:
                callback(collection_id, status, percent, message)
            except Exception:
                log.debug("Слушатель загрузок упал", exc_info=True)

    # ------------------------------------------------------------------ #
    #  Постановка в очередь
    # ------------------------------------------------------------------ #
    def enqueue(
        self,
        user_id: int,
        item: MediaItem,
        *,
        audio_only: bool = False,
        quality: Optional[str] = None,
    ) -> int:
        """Поставить загрузку в очередь. Возвращает id записи в collection."""
        media_type = "music" if audio_only else item.content_type
        quality = quality or settings.get("download_quality", "1080p")

        existing = self.find_downloaded(user_id, item)
        if existing is not None:
            return existing

        with session_scope() as session:
            record = Collection(
                user_id=user_id,
                type=media_type,
                title=item.title,
                author=item.author,
                thumbnail=item.thumbnail,
                source_url=item.url,
                platform=item.platform,
                video_id=item.id,
                duration=item.duration,
                quality=quality,
                status="queued",
                progress=0,
                date=datetime.now(),
                time_key=datetime.now().time(),
            )
            session.add(record)
            session.flush()
            collection_id = record.id

        task = DownloadTask(collection_id, item, audio_only)
        with self._lock:
            self._tasks[collection_id] = task
        task.future = self._pool.submit(self._run, task, quality)
        self._emit(collection_id, "queued", 0, "В очереди")
        return collection_id

    def find_downloaded(self, user_id: int, item: MediaItem) -> Optional[int]:
        """Уже скачано (и файл на месте)? Тогда повторно не качаем."""
        with session_scope() as session:
            record = (
                session.query(Collection)
                .filter(
                    Collection.user_id == user_id,
                    Collection.video_id == item.id,
                    Collection.platform == item.platform,
                    Collection.status.in_(("done", "downloading", "queued")),
                )
                .first()
            )
            if record is None:
                return None
            if record.status == "done" and not record.exists_on_disk:
                # Файл удалили руками — запись больше не актуальна.
                session.delete(record)
                return None
            return record.id

    def cancel(self, collection_id: int) -> None:
        with self._lock:
            task = self._tasks.get(collection_id)
        if task:
            task.cancel()
        self._update_record(collection_id, status="canceled")
        self._emit(collection_id, "canceled", 0, "Отменено")

    def active_count(self) -> int:
        with self._lock:
            return sum(
                1 for t in self._tasks.values() if t.status in ("queued", "downloading")
            )

    # ------------------------------------------------------------------ #
    #  Собственно загрузка
    # ------------------------------------------------------------------ #
    def _run(self, task: DownloadTask, quality: str) -> None:
        collection_id = task.collection_id
        item = task.item

        if task.cancel_event.is_set():
            return

        task.status = "downloading"
        self._update_record(collection_id, status="downloading", progress=0)
        self._emit(collection_id, "downloading", 0, "Начинаем…")

        media_type = "music" if task.audio_only else item.content_type
        target_dir = download_dir_for(media_type)
        outtmpl = str(target_dir / f"{safe_filename(item.title)} [%(id)s].%(ext)s")

        try:
            # VPN нужен только для площадок, которые без него не открываются.
            if item.platform == "youtube":
                self.vpn.ensure_connected()

            opts = self._ydl_opts(task, quality, outtmpl)
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(item.url, download=True)
                path = self._resolve_path(ydl, info, task.audio_only)

            if task.cancel_event.is_set():
                self._cleanup(path)
                self._update_record(collection_id, status="canceled")
                self._emit(collection_id, "canceled", 0, "Отменено")
                return

            filesize = Path(path).stat().st_size if path and Path(path).is_file() else None
            self._update_record(
                collection_id,
                status="done",
                progress=100,
                path=str(path) if path else None,
                filesize=filesize,
                duration=info.get("duration") if info else item.duration,
                error=None,
            )
            task.status = "done"
            self._emit(collection_id, "done", 100, "Готово")

        except _Canceled:
            self._update_record(collection_id, status="canceled")
            self._emit(collection_id, "canceled", 0, "Отменено")
        except Exception as exc:
            message = str(exc)[:300]
            log.error("Загрузка %s не удалась: %s", item.title, message)
            task.status = "error"
            self._update_record(collection_id, status="error", error=message)
            self._emit(collection_id, "error", 0, message)
        finally:
            with self._lock:
                self._tasks.pop(collection_id, None)

    def _ydl_opts(self, task: DownloadTask, quality: str, outtmpl: str) -> Dict:
        """Опции yt-dlp под видео или только-аудио."""
        opts: Dict = {
            "outtmpl": outtmpl,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "continuedl": True,
            "retries": 3,
            "fragment_retries": 3,
            "socket_timeout": settings.get("request_timeout", 20),
            "progress_hooks": [lambda d: self._progress_hook(task, d)],
            "postprocessor_hooks": [lambda d: self._postprocessor_hook(task, d)],
        }

        proxy = self.vpn.proxy_url()
        if proxy:
            opts["proxy"] = proxy

        if task.audio_only:
            audio_format = settings.get("audio_format", "mp3")
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": audio_format,
                    "preferredquality": "192",
                }
            ]
            if settings.get("embed_thumbnail", True):
                opts["writethumbnail"] = True
                opts["postprocessors"].append({"key": "EmbedThumbnail"})
                opts["postprocessors"].append({"key": "FFmpegMetadata"})
        else:
            height = QUALITY_TO_HEIGHT.get(quality)
            if height:
                opts["format"] = (
                    f"bestvideo[height<={height}]+bestaudio/"
                    f"best[height<={height}]/best"
                )
            else:
                opts["format"] = "bestvideo+bestaudio/best"
            opts["merge_output_format"] = "mp4"

        return opts

    def _progress_hook(self, task: DownloadTask, data: Dict) -> None:
        """Хук yt-dlp: считает проценты и позволяет прервать загрузку."""
        if task.cancel_event.is_set():
            raise _Canceled()

        if data.get("status") == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            downloaded = data.get("downloaded_bytes") or 0
            percent = int(downloaded * 100 / total) if total else 0
            # Дёргаем UI и БД только при реальном изменении процента.
            if percent != task.progress:
                task.progress = percent
                speed = data.get("speed") or 0
                message = f"{percent}% • {speed / 1024 / 1024:.1f} МБ/с" if speed else f"{percent}%"
                self._emit(task.collection_id, "downloading", percent, message)
                if percent % 5 == 0:
                    self._update_record(task.collection_id, progress=percent)

        elif data.get("status") == "finished":
            self._emit(task.collection_id, "processing", 99, "Обработка…")

    def _postprocessor_hook(self, task: DownloadTask, data: Dict) -> None:
        if data.get("status") == "started":
            self._emit(task.collection_id, "processing", 99, "Конвертация…")

    @staticmethod
    def _resolve_path(ydl: YoutubeDL, info: Optional[Dict], audio_only: bool) -> Optional[str]:
        """Определить итоговый путь файла после всех постпроцессоров."""
        if not info:
            return None
        # requested_downloads содержит финальные пути после конвертации.
        requested = info.get("requested_downloads") or []
        if requested:
            final = requested[0]
            return final.get("filepath") or final.get("_filename")

        path = ydl.prepare_filename(info)
        if audio_only:
            audio_format = settings.get("audio_format", "mp3")
            converted = Path(path).with_suffix(f".{audio_format}")
            if converted.is_file():
                return str(converted)
        if Path(path).is_file():
            return path
        # merge_output_format мог сменить расширение на .mp4/.mkv
        for suffix in (".mp4", ".mkv", ".webm"):
            candidate = Path(path).with_suffix(suffix)
            if candidate.is_file():
                return str(candidate)
        return path

    @staticmethod
    def _cleanup(path: Optional[str]) -> None:
        """Удалить недокачанный файл после отмены."""
        if path:
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                pass

    @staticmethod
    def _update_record(collection_id: int, **fields) -> None:
        """Обновить запись загрузки в БД."""
        try:
            with session_scope() as session:
                record = session.get(Collection, collection_id)
                if record is None:
                    return
                for key, value in fields.items():
                    setattr(record, key, value)
        except Exception:
            log.debug("Не удалось обновить запись загрузки %s", collection_id, exc_info=True)

    # ------------------------------------------------------------------ #
    #  Библиотека скачанного
    # ------------------------------------------------------------------ #
    @staticmethod
    def library(user_id: int, media_type: Optional[str] = None) -> List[Collection]:
        """Записи библиотеки пользователя, свежие сверху."""
        with session_scope() as session:
            query = session.query(Collection).filter(Collection.user_id == user_id)
            if media_type:
                if media_type == "film":
                    query = query.filter(Collection.type.in_(("film", "series")))
                else:
                    query = query.filter(Collection.type == media_type)
            records = query.order_by(Collection.date.desc()).all()
            for record in records:
                session.expunge(record)
            return records

    @staticmethod
    def delete(collection_id: int, remove_file: bool = True) -> None:
        """Удалить запись и, по желанию, сам файл с диска."""
        with session_scope() as session:
            record = session.get(Collection, collection_id)
            if record is None:
                return
            if remove_file and record.path:
                try:
                    Path(record.path).unlink(missing_ok=True)
                except OSError:
                    log.warning("Не удалось удалить файл %s", record.path)
            session.delete(record)

    def shutdown(self) -> None:
        """Остановить все загрузки при выходе из приложения."""
        with self._lock:
            for task in self._tasks.values():
                task.cancel()
        self._pool.shutdown(wait=False, cancel_futures=True)


#: Общий экземпляр на всё приложение.
download_manager = DownloadManager()
