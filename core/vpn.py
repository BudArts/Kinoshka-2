"""Менеджер WireGuard-туннелей.

На территории России YouTube без VPN недоступен, поэтому приложение умеет
поднимать WireGuard-туннель само. Поддерживаются два способа:

  * ``wireguard`` — системный клиент (``wg-quick`` на Linux/macOS,
    ``wireguard.exe /installtunnelservice`` на Windows). Требует прав
    администратора, но даёт настоящий системный туннель.
  * ``proxy`` — запасной вариант без прав: все HTTP-запросы и yt-dlp идут
    через HTTP/SOCKS-прокси из настроек.

Конфигурации (.conf) пользователь импортирует через настройки; они копируются
в config.VPN_DIR (каталог пользовательских данных), а не в репозиторий, чтобы
приватные ключи не попадали в git.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from config import VPN_DIR, settings

#: Проверочный URL: если он открывается, значит выход в YouTube есть.
CHECK_URL = "https://www.youtube.com/generate_204"
CHECK_TIMEOUT = 8


@dataclass
class VpnConfig:
    """Разобранная WireGuard-конфигурация."""

    name: str
    path: Path
    endpoint: Optional[str] = None
    address: Optional[str] = None
    dns: Optional[str] = None
    allowed_ips: Optional[str] = None

    @property
    def location_hint(self) -> str:
        """Человекочитаемая подпись — хост эндпоинта без порта."""
        if not self.endpoint:
            return "неизвестно"
        return self.endpoint.rsplit(":", 1)[0]


class VpnError(RuntimeError):
    """Ошибка при работе с туннелем."""


class VpnManager:
    """Импорт, хранение и подъём/остановка WireGuard-конфигураций."""

    def __init__(self, config_dir: Path | None = None):
        self.config_dir = Path(config_dir or VPN_DIR)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._active: Optional[str] = None
        self._listeners: List[Callable[[str, Optional[str]], None]] = []

    # ------------------------------------------------------------------ #
    #  Наблюдатели за статусом
    # ------------------------------------------------------------------ #
    def add_listener(self, callback: Callable[[str, Optional[str]], None]) -> None:
        """callback(status, config_name), status: connected/disconnected/error."""
        self._listeners.append(callback)

    def _notify(self, status: str, name: Optional[str] = None) -> None:
        for callback in list(self._listeners):
            try:
                callback(status, name)
            except Exception:
                # Падение UI-колбэка не должно ломать сеть.
                pass

    # ------------------------------------------------------------------ #
    #  Работа с файлами конфигураций
    # ------------------------------------------------------------------ #
    def list_configs(self) -> List[VpnConfig]:
        """Все .conf в каталоге VPN, отсортированные по имени."""
        configs = []
        for path in sorted(self.config_dir.glob("*.conf")):
            try:
                configs.append(self._parse_config(path))
            except OSError:
                continue
        return configs

    def get_config(self, name: str) -> Optional[VpnConfig]:
        path = self.config_dir / f"{name}.conf"
        return self._parse_config(path) if path.is_file() else None

    def import_config(self, source: str | Path, name: str | None = None) -> VpnConfig:
        """Скопировать .conf пользователя в каталог приложения."""
        source = Path(source)
        if not source.is_file():
            raise VpnError(f"Файл не найден: {source}")
        if source.suffix.lower() != ".conf":
            raise VpnError("Ожидается файл конфигурации WireGuard (.conf)")

        safe = self._sanitize(name or source.stem)
        target = self.config_dir / f"{safe}.conf"
        counter = 1
        while target.exists():
            target = self.config_dir / f"{safe}-{counter}.conf"
            counter += 1

        shutil.copy2(source, target)
        # Приватный ключ внутри — закрываем файл от других пользователей.
        try:
            target.chmod(0o600)
        except OSError:
            pass

        config = self._parse_config(target)
        if not config.endpoint:
            target.unlink(missing_ok=True)
            raise VpnError("В конфигурации нет секции [Peer] с Endpoint — файл повреждён")
        return config

    def import_many(self, sources: List[str | Path]) -> List[VpnConfig]:
        """Импортировать пачку файлов, пропуская битые."""
        imported = []
        for source in sources:
            try:
                imported.append(self.import_config(source))
            except VpnError:
                continue
        return imported

    def delete_config(self, name: str) -> None:
        if self._active == name:
            self.disconnect()
        (self.config_dir / f"{name}.conf").unlink(missing_ok=True)
        if settings.get("vpn_active_config") == name:
            settings.set("vpn_active_config", None)

    @staticmethod
    def _sanitize(name: str) -> str:
        """Имя интерфейса WireGuard: только [A-Za-z0-9_=+.-], до 15 символов."""
        cleaned = re.sub(r"[^A-Za-z0-9_=+.-]", "-", name).strip("-")
        return (cleaned or "kinoshka")[:15]

    @staticmethod
    def _parse_config(path: Path) -> VpnConfig:
        """Достать из .conf поля, интересные для отображения."""
        config = VpnConfig(name=path.stem, path=path)
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return config

        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip().lower(), value.strip()
            if key == "endpoint":
                config.endpoint = value
            elif key == "address":
                config.address = value
            elif key == "dns":
                config.dns = value
            elif key == "allowedips":
                config.allowed_ips = value
        return config

    # ------------------------------------------------------------------ #
    #  Состояние
    # ------------------------------------------------------------------ #
    @property
    def active_config(self) -> Optional[str]:
        return self._active

    @property
    def is_connected(self) -> bool:
        return self._active is not None

    @staticmethod
    def backend_available() -> bool:
        """Установлен ли системный клиент WireGuard."""
        return VpnManager._backend_binary() is not None

    @staticmethod
    def _backend_binary() -> Optional[str]:
        if sys.platform == "win32":
            found = shutil.which("wireguard")
            if found:
                return found
            for candidate in (
                r"C:\Program Files\WireGuard\wireguard.exe",
                r"C:\Program Files (x86)\WireGuard\wireguard.exe",
            ):
                if Path(candidate).is_file():
                    return candidate
            return None
        return shutil.which("wg-quick")

    # ------------------------------------------------------------------ #
    #  Подключение / отключение
    # ------------------------------------------------------------------ #
    def connect(self, name: Optional[str] = None) -> bool:
        """Поднять туннель. Возвращает True при успехе."""
        name = name or settings.get("vpn_active_config")
        if not name:
            raise VpnError("Не выбрана конфигурация VPN")

        config = self.get_config(name)
        if config is None:
            raise VpnError(f"Конфигурация «{name}» не найдена")

        with self._lock:
            if self._active == name:
                return True
            if self._active:
                self.disconnect()

            binary = self._backend_binary()
            if binary is None:
                raise VpnError(
                    "Клиент WireGuard не найден. Установите WireGuard "
                    "или укажите прокси в настройках."
                )

            if sys.platform == "win32":
                command = [binary, "/installtunnelservice", str(config.path)]
            else:
                command = ["wg-quick", "up", str(config.path)]

            result = self._run(command)
            if result.returncode != 0:
                message = (result.stderr or result.stdout or "").strip()
                self._notify("error", name)
                raise VpnError(f"Не удалось поднять туннель: {message[:300]}")

            self._active = name
            settings.set("vpn_active_config", name)
            self._notify("connected", name)
            # Дать интерфейсу подняться перед первым запросом.
            time.sleep(1.5)
            return True

    def disconnect(self) -> None:
        """Опустить активный туннель (ошибки гасим — важен сам факт остановки)."""
        with self._lock:
            if not self._active:
                return
            name = self._active
            config = self.get_config(name)
            binary = self._backend_binary()
            if binary and config:
                if sys.platform == "win32":
                    command = [binary, "/uninstalltunnelservice", name]
                else:
                    command = ["wg-quick", "down", str(config.path)]
                self._run(command)
            self._active = None
            self._notify("disconnected", name)

    def ensure_connected(self, name: Optional[str] = None) -> bool:
        """Поднять туннель, если он нужен по настройкам и ещё не поднят.

        Вызывается перед запросами к YouTube. Возвращает True, если сеть
        готова (туннель поднят, уже был поднят, или VPN не требуется).
        """
        if not settings.get("vpn_enabled"):
            return True
        if self.is_connected:
            return True
        if not settings.get("vpn_auto_connect"):
            return False
        try:
            return self.connect(name)
        except VpnError:
            return False

    def rotate(self) -> Optional[str]:
        """Переключиться на следующую конфигурацию (если текущая не тянет)."""
        configs = [c.name for c in self.list_configs()]
        if not configs:
            return None
        if self._active in configs:
            index = (configs.index(self._active) + 1) % len(configs)
        else:
            index = 0
        target = configs[index]
        try:
            self.connect(target)
            return target
        except VpnError:
            return None

    # ------------------------------------------------------------------ #
    #  Проверка доступности
    # ------------------------------------------------------------------ #
    def check_connection(self, url: str = CHECK_URL) -> bool:
        """Реально ли открывается YouTube с текущими настройками сети."""
        import requests

        try:
            response = requests.get(
                url, timeout=CHECK_TIMEOUT, proxies=self.requests_proxies()
            )
            return response.status_code < 400
        except Exception:
            return False

    def public_ip(self) -> Optional[str]:
        """Внешний IP — чтобы показать в настройках, что туннель работает."""
        import requests

        try:
            response = requests.get(
                "https://api.ipify.org", timeout=CHECK_TIMEOUT,
                proxies=self.requests_proxies(),
            )
            return response.text.strip() if response.ok else None
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    #  Прокси
    # ------------------------------------------------------------------ #
    def proxy_url(self) -> Optional[str]:
        """Прокси из настроек (запасной путь, когда WireGuard недоступен)."""
        url = (settings.get("proxy_url") or "").strip()
        return url or None

    def requests_proxies(self) -> Optional[Dict[str, str]]:
        """Словарь proxies для библиотеки requests."""
        url = self.proxy_url()
        return {"http": url, "https": url} if url else None

    # ------------------------------------------------------------------ #
    def _run(self, command: List[str]) -> subprocess.CompletedProcess:
        """Запустить внешнюю команду без всплывающего окна консоли."""
        kwargs: Dict = {
            "capture_output": True,
            "text": True,
            "timeout": 45,
        }
        if sys.platform == "win32":  # pragma: no cover
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            return subprocess.run(command, **kwargs)
        except FileNotFoundError:
            return subprocess.CompletedProcess(command, 1, "", "команда не найдена")
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(command, 1, "", "истекло время ожидания")

    def __del__(self):  # pragma: no cover
        try:
            self.disconnect()
        except Exception:
            pass


#: Общий экземпляр на всё приложение.
vpn_manager = VpnManager()
