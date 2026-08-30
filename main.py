"""Точка входа Kinoshka.

По умолчанию запускается как настольное приложение (именно так его собирает
установщик). Флаг --web поднимает тот же интерфейс в браузере — удобно для
отладки.

    python main.py           # окно приложения
    python main.py --web     # http://localhost:5173
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import flet as ft

from app import App
from config import APP_NAME, APP_VERSION, LOG_DIR, ensure_dirs


def setup_logging(verbose: bool = False) -> None:
    """Логи в файл и в консоль — без них диагностировать сбои у пользователя нечем."""
    ensure_dirs()
    level = logging.DEBUG if verbose else logging.INFO
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    try:
        handlers.append(logging.FileHandler(LOG_DIR / "kinoshka.log", encoding="utf-8"))
    except OSError:
        pass

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )
    # Глушим болтливые библиотеки, чтобы не спамить в консоль пользователя
    for name in ("urllib3", "yt_dlp", "flet", "flet_controls", "flet_transport", "flet_desktop"):
        logging.getLogger(name).setLevel(logging.WARNING if not verbose else logging.DEBUG)
    # Но наши логи оставляем
    logging.getLogger("app").setLevel(level)
    logging.getLogger("core").setLevel(level)


def main(page: ft.Page) -> None:
    App(page)


def run() -> None:
    parser = argparse.ArgumentParser(description=f"{APP_NAME} {APP_VERSION}")
    parser.add_argument("--web", action="store_true", help="открыть в браузере")
    parser.add_argument("--port", type=int, default=5173, help="порт для веб-режима")
    parser.add_argument("--host", default="0.0.0.0", help="адрес для веб-режима")
    parser.add_argument("-v", "--verbose", action="store_true", help="подробные логи")
    args = parser.parse_args()

    setup_logging(args.verbose)

    assets_dir = str(Path(__file__).resolve().parent / "assets")

    if args.web:
        ft.run(
            main,
            assets_dir=assets_dir,
            view=ft.AppView.WEB_BROWSER,
            host=args.host,
            port=args.port,
        )
    else:
        ft.run(main, assets_dir=assets_dir)


if __name__ == "__main__":
    run()
