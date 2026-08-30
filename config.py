"""Конфигурация приложения Kinoshka.

Здесь собраны:
  * пути к пользовательским данным (БД, загрузки, VPN-конфиги, кэш);
  * класс Settings — постоянное хранилище пользовательских настроек в JSON;
  * значения по умолчанию.

Все пользовательские данные лежат вне каталога с программой (в %APPDATA%\\Kinoshka
на Windows или ~/.local/share/kinoshka на Linux/macOS), чтобы установленное
через .exe приложение могло писать их без прав администратора.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path
from typing import Any, Dict

APP_NAME = "Kinoshka"
APP_VERSION = "0.2.0"
APP_PUBLISHER = "Budin's industries"


# --------------------------------------------------------------------------- #
#  Пути
# --------------------------------------------------------------------------- #
def _user_data_dir() -> Path:
    """Каталог пользовательских данных, зависящий от ОС."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    base = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    return Path(base) / APP_NAME.lower()


def app_root() -> Path:
    """Каталог, из которого запущена программа (работает и внутри PyInstaller)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


#: Корень пользовательских данных. Может быть переопределён переменной
#: окружения KINOSHKA_DATA_DIR (удобно для тестов и портативного режима).
DATA_DIR = Path(os.environ.get("KINOSHKA_DATA_DIR") or _user_data_dir())

DB_PATH = DATA_DIR / "kinoshka.db"
SETTINGS_PATH = DATA_DIR / "settings.json"
VPN_DIR = DATA_DIR / "vpn"
CACHE_DIR = DATA_DIR / "cache"
THUMBS_DIR = CACHE_DIR / "thumbnails"
LOG_DIR = DATA_DIR / "logs"

DOWNLOADS_DIR = DATA_DIR / "downloads"
VIDEO_DIR = DOWNLOADS_DIR / "video"
FILMS_DIR = DOWNLOADS_DIR / "films"
MUSIC_DIR = DOWNLOADS_DIR / "music"

ASSETS_DIR = app_root() / "assets"


def ensure_dirs() -> None:
    """Создать все нужные каталоги (идемпотентно)."""
    for path in (
        DATA_DIR,
        VPN_DIR,
        CACHE_DIR,
        THUMBS_DIR,
        LOG_DIR,
        DOWNLOADS_DIR,
        VIDEO_DIR,
        FILMS_DIR,
        MUSIC_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------- #
#  Настройки
# --------------------------------------------------------------------------- #
# Встроенный ключ GigaChat — по просьбе пользователя вшит в программу,
# чтобы не приходилось вводить его вручную. Если ключ протухнет,
# его можно переопределить в настройках (поле остаётся доступным через
# файл settings.json, но в UI не показывается).
BUNDLED_GIGACHAT_CREDENTIALS = (
    "YzNhMGVlNzYtYmNiNC00MTUyLWJkMjAtZGRlMjhkMzJkNzY5OjAyMWUwNjBhLTdkZTktNDY3Ni04NDEyLWZjZTlkYjM1NDI4OA=="
)

DEFAULT_SETTINGS: Dict[str, Any] = {
    # --- общие ---
    "theme": "dark",
    "language": "ru",
    "last_user_id": None,
    "start_page": "Главная",
    # --- воспроизведение ---
    "preferred_quality": "720p",       # 360p / 480p / 720p / 1080p / best
    "autoplay": True,
    "default_volume": 80,              # 0..100
    "save_history": True,
    # --- загрузки ---
    "download_dir": str(DOWNLOADS_DIR),
    "max_parallel_downloads": 2,
    "download_quality": "1080p",
    "audio_format": "mp3",             # mp3 / m4a / opus
    "embed_thumbnail": True,
    # --- сеть / VPN ---
    "vpn_enabled": False,
    "vpn_bundled_installed": False,  # развёрнуты ли вшитые пресеты
    "vpn_active_config": None,         # имя конфигурации в VPN_DIR
    "vpn_auto_connect": True,          # поднимать туннель перед запросами к YouTube
    "vpn_only_for": ["youtube"],       # для каких источников нужен VPN
    "proxy_url": "",                   # запасной вариант: http:// или socks5://
    "request_timeout": 20,
    # --- ИИ-поиск ---
    "ai_enabled": True,                # включён по умолчанию — ключ вшит
    "ai_provider": "gigachat",          # gigachat / openai
    # GigaChat (Сбер): ключ Basic из личного кабинета — вшит по умолчанию
    "gigachat_credentials": BUNDLED_GIGACHAT_CREDENTIALS,
    "gigachat_scope": "GIGACHAT_API_PERS",
    "gigachat_model": "GigaChat",
    # Сертификаты GigaChat подписаны Минцифры и обычно отсутствуют
    # в системном хранилище, поэтому по умолчанию проверку TLS не делаем.
    "gigachat_verify_ssl": False,
    # OpenAI-совместимый сервис (запасной)
    "ai_base_url": "https://api.openai.com/v1",
    "ai_api_key": "",
    "ai_model": "gpt-4o-mini",
    # --- метаданные фильмов ---
    "kinopoisk_api_key": "",           # бесплатный ключ с kinopoisk.dev
    # --- рекомендации ---
    "recommendations_count": 24,
    "interest_decay_days": 30,
}


class Settings:
    """Потокобезопасное JSON-хранилище настроек с доступом как у словаря."""

    def __init__(self, path: Path | None = None):
        self._path = Path(path) if path else SETTINGS_PATH
        self._lock = threading.RLock()
        self._data: Dict[str, Any] = dict(DEFAULT_SETTINGS)
        self.load()

    # -- чтение/запись файла ------------------------------------------------ #
    def load(self) -> "Settings":
        with self._lock:
            if self._path.exists():
                try:
                    raw = json.loads(self._path.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        # неизвестные ключи игнорируем, отсутствующие берём из умолчаний
                        self._data = {**DEFAULT_SETTINGS, **raw}
                except (json.JSONDecodeError, OSError):
                    # битый файл настроек не должен ронять приложение
                    self._data = dict(DEFAULT_SETTINGS)
            return self

    def save(self) -> None:
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            tmp.replace(self._path)

    # -- доступ ------------------------------------------------------------- #
    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, DEFAULT_SETTINGS.get(key, default))

    def set(self, key: str, value: Any, *, autosave: bool = True) -> None:
        with self._lock:
            self._data[key] = value
            if autosave:
                self.save()

    def update(self, values: Dict[str, Any], *, autosave: bool = True) -> None:
        with self._lock:
            self._data.update(values)
            if autosave:
                self.save()

    def reset(self) -> None:
        with self._lock:
            self._data = dict(DEFAULT_SETTINGS)
            self.save()

    def as_dict(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._data)

    def __getitem__(self, key: str) -> Any:
        return self.get(key)

    def __setitem__(self, key: str, value: Any) -> None:
        self.set(key, value)

    def __contains__(self, key: str) -> bool:
        with self._lock:
            return key in self._data


#: Глобальный экземпляр настроек, используемый по всему приложению.
settings = Settings()


# --------------------------------------------------------------------------- #
#  Вспомогательное
# --------------------------------------------------------------------------- #
QUALITY_TO_HEIGHT = {
    "360p": 360,
    "480p": 480,
    "720p": 720,
    "1080p": 1080,
    "1440p": 1440,
    "2160p": 2160,
    "best": None,
}


def download_dir_for(media_type: str) -> Path:
    """Каталог загрузок под конкретный тип контента."""
    base = Path(settings.get("download_dir", str(DOWNLOADS_DIR)))
    mapping = {
        "video": base / "video",
        "film": base / "films",
        "series": base / "films",
        "music": base / "music",
    }
    target = mapping.get(media_type, base / "other")
    target.mkdir(parents=True, exist_ok=True)
    return target
