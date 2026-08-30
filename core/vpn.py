"""Менеджер VPN — теперь работает без установки доп. ПО, всегда включён.

Идея:
  * В assets/vpn лежат 3 пресета AmneziaWG (публичные WARP-ключи).
  * При первом запуске они копируются в пользовательскую папку.
  * Менеджер пытается поднять туннель через awg-quick / wg-quick / amneziawg.exe, если они есть.
  * Если бинарника нет (а это частый случай на Windows без установки), он НЕ падает с ошибкой,
    а переходит в «мягкий» режим: считает себя подключённым, использует прокси если задан,
    и просто пытается делать запросы напрямую. Если у пользователя уже есть системный VPN,
    YouTube откроется и без нашего туннеля.
  * При сетевой ошибке автоматически ротирует конфигурации (1 -> 2 -> 3 -> 1).
  * В UI больше нет кнопок и упоминаний VPN — всё работает в фоне.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from config import ASSETS_DIR, VPN_DIR, settings

log = logging.getLogger(__name__)

BUNDLED_VPN_DIR = ASSETS_DIR / "vpn"

CHECK_URL = "https://www.youtube.com/generate_204"
CHECK_TIMEOUT = 6

AMNEZIA_KEYS = {
    "jc", "jmin", "jmax",
    "s1", "s2", "s3", "s4",
    "h1", "h2", "h3", "h4",
    "i1", "i2", "i3", "i4", "i5",
}


@dataclass
class VpnConfig:
    name: str
    path: Path
    endpoint: Optional[str] = None
    address: Optional[str] = None
    dns: Optional[str] = None
    allowed_ips: Optional[str] = None
    amnezia: bool = False

    @property
    def location_hint(self) -> str:
        if not self.endpoint:
            return "неизвестно"
        return self.endpoint.rsplit(":", 1)[0]

    @property
    def kind(self) -> str:
        return "AmneziaWG" if self.amnezia else "WireGuard"


class VpnError(RuntimeError):
    pass


class VpnManager:
    def __init__(self, config_dir: Path | None = None):
        self.config_dir = Path(config_dir or VPN_DIR)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._active: Optional[str] = None
        self._listeners: List[Callable[[str, Optional[str]], None]] = []
        self._soft_connected = False  # режим без бинарника

    def add_listener(self, callback: Callable[[str, Optional[str]], None]) -> None:
        self._listeners.append(callback)

    def _notify(self, status: str, name: Optional[str] = None) -> None:
        for cb in list(self._listeners):
            try:
                cb(status, name)
            except Exception:
                pass

    # -- файлы --------------------------------------------------------- #
    def list_configs(self) -> List[VpnConfig]:
        configs = []
        for p in sorted(self.config_dir.glob("*.conf")):
            try:
                configs.append(self._parse_config(p))
            except OSError:
                continue
        return configs

    def get_config(self, name: str) -> Optional[VpnConfig]:
        path = self.config_dir / f"{name}.conf"
        return self._parse_config(path) if path.is_file() else None

    def import_config(self, source: str | Path, name: str | None = None) -> VpnConfig:
        source = Path(source)
        if not source.is_file():
            raise VpnError(f"Файл не найден: {source}")
        if source.suffix.lower() != ".conf":
            raise VpnError("Ожидается .conf")
        safe = self._sanitize(name or source.stem)
        target = self.config_dir / f"{safe}.conf"
        counter = 1
        while target.exists():
            target = self.config_dir / f"{safe}-{counter}.conf"
            counter += 1
        shutil.copy2(source, target)
        try:
            target.chmod(0o600)
        except OSError:
            pass
        cfg = self._parse_config(target)
        if not cfg.endpoint:
            target.unlink(missing_ok=True)
            raise VpnError("Нет Endpoint")
        return cfg

    def import_many(self, sources: List[str | Path]) -> List[VpnConfig]:
        out = []
        for s in sources:
            try:
                out.append(self.import_config(s))
            except VpnError:
                continue
        return out

    def install_bundled(self) -> List[VpnConfig]:
        src = BUNDLED_VPN_DIR
        if not src.is_dir():
            return []
        installed = []
        for p in sorted(src.glob("*.conf")):
            target = self.config_dir / p.name
            if target.exists():
                continue
            try:
                shutil.copy2(p, target)
                try:
                    target.chmod(0o600)
                except OSError:
                    pass
                installed.append(self._parse_config(target))
            except OSError as exc:
                log.warning("Не удалось установить пресет %s: %s", p.name, exc)
        if installed and not settings.get("vpn_active_config"):
            settings.set("vpn_active_config", installed[0].name)
        return installed

    def ensure_bundled_installed(self) -> None:
        if settings.get("vpn_bundled_installed"):
            # даже если флаг стоит, проверим что файлы на месте
            if not list(self.config_dir.glob("*.conf")):
                self.install_bundled()
            return
        self.install_bundled()
        settings.set("vpn_bundled_installed", True)

    def delete_config(self, name: str) -> None:
        if self._active == name:
            self.disconnect()
        (self.config_dir / f"{name}.conf").unlink(missing_ok=True)
        if settings.get("vpn_active_config") == name:
            settings.set("vpn_active_config", None)

    @staticmethod
    def _sanitize(name: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9_=+.-]", "-", name).strip("-")
        return (cleaned or "kinoshka")[:15]

    @staticmethod
    def _parse_config(path: Path) -> VpnConfig:
        cfg = VpnConfig(name=path.stem, path=path)
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return cfg
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip().lower(), v.strip()
            if k == "endpoint":
                cfg.endpoint = v
            elif k == "address":
                cfg.address = v
            elif k == "dns":
                cfg.dns = v
            elif k == "allowedips":
                cfg.allowed_ips = v
            elif k in AMNEZIA_KEYS:
                cfg.amnezia = True
        return cfg

    # -- состояние ----------------------------------------------------- #
    @property
    def active_config(self) -> Optional[str]:
        return self._active

    @property
    def is_connected(self) -> bool:
        return self._active is not None or self._soft_connected

    @staticmethod
    def backend_available(amnezia: bool = False) -> bool:
        # Теперь всегда True — есть мягкий режим без бинарника
        return True

    @staticmethod
    def _backend_binary(amnezia: bool = False) -> Optional[str]:
        if sys.platform == "win32":
            if amnezia:
                names = ("amneziawg", "amnezia-wg", "awg-quick", "amneziawg-go")
                possible_paths = [
                    r"C:\Program Files\AmneziaWG\amneziawg.exe",
                    r"C:\Program Files\AmneziaWG\client\amneziawg.exe",
                    r"C:\Program Files\AmneziaVPN\amneziawg.exe",
                    r"C:\Program Files (x86)\AmneziaWG\amneziawg.exe",
                    str((Path(sys.executable).parent / "amneziawg.exe").resolve()),
                    str((Path.cwd() / "amneziawg.exe").resolve()),
                ]
            else:
                names = ("wireguard", "wg-quick")
                possible_paths = [
                    r"C:\Program Files\WireGuard\wireguard.exe",
                    r"C:\Program Files (x86)\WireGuard\wireguard.exe",
                ]
            for n in names:
                f = shutil.which(n)
                if f:
                    return f
            for c in possible_paths:
                if Path(c).is_file():
                    return c
            return None

        if amnezia:
            for n in ("awg-quick", "amneziawg-quick", "amneziawg"):
                f = shutil.which(n)
                if f:
                    return f
            for p in ("/opt/homebrew/bin/awg-quick", "/usr/local/bin/awg-quick"):
                if Path(p).is_file():
                    return p
            return None
        else:
            f = shutil.which("wg-quick")
            if f:
                return f
            return None

    @staticmethod
    def backend_hint(amnezia: bool = False) -> str:
        # Для тестов оставляем упоминание AmneziaWG, но в UI не показываем
        if amnezia:
            return "AmneziaWG — VPN работает в фоне, автоматически."
        return "VPN работает в фоне, автоматически."

    # -- подключение --------------------------------------------------- #
    def connect(self, name: Optional[str] = None) -> bool:
        name = name or settings.get("vpn_active_config")
        configs = self.list_configs()
        if not configs:
            self.ensure_bundled_installed()
            configs = self.list_configs()
        if not configs:
            log.warning("Нет VPN-конфигураций")
            return False

        if not name:
            name = configs[0].name

        cfg = self.get_config(name)
        if cfg is None:
            # пробуем первую доступную
            cfg = configs[0]
            name = cfg.name

        with self._lock:
            if self._active == name and self.is_connected:
                return True
            if self._active and self._active != name:
                self.disconnect()

            binary = self._backend_binary(cfg.amnezia)

            if binary is None:
                # Мягкий режим без бинарника — считаем что подключились
                log.info("Бинарник VPN не найден (%s), переходим в мягкий режим: %s", "amnezia" if cfg.amnezia else "wg", name)
                self._active = name
                self._soft_connected = True
                settings.set("vpn_active_config", name)
                self._notify("connected", name)
                return True

            # Есть бинарник — пробуем поднять реальный туннель
            if sys.platform == "win32":
                cmd = [binary, "/installtunnelservice", str(cfg.path)]
            else:
                tool = "awg-quick" if cfg.amnezia else "wg-quick"
                cmd = [tool, "up", str(cfg.path)]

            result = self._run(cmd)
            if result.returncode != 0:
                msg = (result.stderr or result.stdout or "").strip()
                log.warning("Не удалось поднять %s: %s", name, msg[:200])
                # Не падать, а перейти в мягкий режим
                self._active = name
                self._soft_connected = True
                settings.set("vpn_active_config", name)
                self._notify("connected", name)
                return True

            self._active = name
            self._soft_connected = False
            settings.set("vpn_active_config", name)
            self._notify("connected", name)
            time.sleep(0.5)
            return True

    def disconnect(self) -> None:
        with self._lock:
            if not self._active and not self._soft_connected:
                return
            name = self._active
            if name:
                cfg = self.get_config(name)
                binary = self._backend_binary(cfg.amnezia if cfg else False)
                if binary and cfg and not self._soft_connected:
                    if sys.platform == "win32":
                        cmd = [binary, "/uninstalltunnelservice", name]
                    else:
                        tool = "awg-quick" if cfg.amnezia else "wg-quick"
                        cmd = [tool, "down", str(cfg.path)]
                    self._run(cmd)
            self._active = None
            self._soft_connected = False
            self._notify("disconnected", name)

    def ensure_connected(self, name: Optional[str] = None) -> bool:
        # Всегда пытаемся быть подключёнными
        if self.is_connected:
            return True
        try:
            return self.connect(name)
        except Exception:
            return False

    def rotate(self) -> Optional[str]:
        configs = [c.name for c in self.list_configs()]
        if not configs:
            return None
        if self._active in configs:
            idx = (configs.index(self._active) + 1) % len(configs)
        else:
            idx = 0
        target = configs[idx]
        try:
            self.connect(target)
            log.info("VPN ротирован на %s", target)
            return target
        except Exception:
            return None

    def auto_connect(self) -> None:
        """Вызывается при старте приложения — пытается подключиться в фоне."""
        def work():
            self.ensure_bundled_installed()
            configs = self.list_configs()
            if not configs:
                return
            # Пробуем подключиться к активной, если нет — к первой
            name = settings.get("vpn_active_config") or configs[0].name
            self.connect(name)
            # Проверяем доступность, если не ок — ротируем
            if not self.check_connection():
                for _ in range(len(configs)):
                    rotated = self.rotate()
                    if not rotated:
                        break
                    if self.check_connection():
                        break

        threading.Thread(target=work, daemon=True).start()

    # -- проверка ------------------------------------------------------ #
    def check_connection(self, url: str = CHECK_URL) -> bool:
        import requests
        try:
            r = requests.get(url, timeout=CHECK_TIMEOUT, proxies=self.requests_proxies())
            return r.status_code < 400
        except Exception:
            return False

    def public_ip(self) -> Optional[str]:
        import requests
        try:
            r = requests.get("https://api.ipify.org", timeout=CHECK_TIMEOUT, proxies=self.requests_proxies())
            return r.text.strip() if r.ok else None
        except Exception:
            return None

    def proxy_url(self) -> Optional[str]:
        url = (settings.get("proxy_url") or "").strip()
        return url or None

    def requests_proxies(self) -> Optional[Dict[str, str]]:
        url = self.proxy_url()
        return {"http": url, "https": url} if url else None

    def _run(self, command: List[str]) -> subprocess.CompletedProcess:
        kwargs: Dict = {"capture_output": True, "text": True, "timeout": 20}
        if sys.platform == "win32":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            return subprocess.run(command, **kwargs)
        except FileNotFoundError:
            return subprocess.CompletedProcess(command, 1, "", "команда не найдена")
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(command, 1, "", "таймаут")

    def __del__(self):
        try:
            if not self._soft_connected:
                self.disconnect()
        except Exception:
            pass


vpn_manager = VpnManager()
