"""Сборка Kinoshka в .exe и установщик для Windows.

Запускать на Windows:

    python build_installer.py            # onedir-сборка + установщик
    python build_installer.py --onefile  # один .exe без установщика
    python build_installer.py --no-installer

Что нужно установить заранее:
  * Python 3.11+ и зависимости из requirements.txt
  * PyInstaller           -> pip install pyinstaller
  * Inno Setup 6 (для установщика) -> https://jrsoftware.org/isdl.php
  * ffmpeg.exe рядом с проектом или в PATH — нужен, чтобы склеивать
    видео с аудио и конвертировать музыку в mp3.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
INSTALLER_OUT = ROOT / "installer_output"

APP_NAME = "Kinoshka"
ENTRY = "main.py"


def read_version() -> str:
    """Версия берётся из config.py, чтобы не разъезжалась со сборкой."""
    sys.path.insert(0, str(ROOT))
    from config import APP_VERSION

    return APP_VERSION


VERSION = read_version()


# --------------------------------------------------------------------------- #
#  PyInstaller
# --------------------------------------------------------------------------- #
def pyinstaller_args(onefile: bool, console: bool) -> list[str]:
    """Аргументы PyInstaller.

    Ключевой момент — hidden-imports: PyInstaller не видит модули, которые
    импортируются динамически (экстракторы yt-dlp, драйверы Flet), поэтому
    их приходится указывать явно.
    """
    separator = ";" if sys.platform == "win32" else ":"

    args = [
        sys.executable, "-m", "PyInstaller",
        ENTRY,
        "--name", APP_NAME,
        "--noconfirm",
        "--clean",
        # Ресурсы приложения (шрифты, иконки).
        "--add-data", f"assets{separator}assets",
        # Динамические импорты.
        "--hidden-import", "yt_dlp",
        "--hidden-import", "yt_dlp.extractor",
        "--hidden-import", "yt_dlp.extractor.youtube",
        "--hidden-import", "yt_dlp.extractor.rutube",
        "--hidden-import", "flet",
        "--hidden-import", "flet_desktop",
        "--hidden-import", "flet_video",
        "--hidden-import", "sqlalchemy",
        "--hidden-import", "sqlalchemy.dialects.sqlite",
        "--collect-all", "flet",
        "--collect-all", "flet_desktop",
        "--collect-all", "flet_video",
        "--collect-submodules", "yt_dlp.extractor",
        # Лишнее, что PyInstaller любит утаскивать за собой.
        "--exclude-module", "tkinter",
        "--exclude-module", "matplotlib",
        "--exclude-module", "pytest",
    ]

    icon = ROOT / "assets" / "icon.ico"
    if icon.is_file():
        args += ["--icon", str(icon)]

    # ffmpeg кладём внутрь сборки, если он лежит рядом с проектом.
    ffmpeg = ROOT / "ffmpeg.exe"
    if ffmpeg.is_file():
        args += ["--add-binary", f"{ffmpeg}{separator}."]

    args.append("--onefile" if onefile else "--onedir")
    # Без консоли окно чище, но при отладке консоль полезна.
    args.append("--console" if console else "--windowed")
    return args


def build_exe(onefile: bool, console: bool) -> Path:
    """Собрать исполняемый файл."""
    print(f"==> Сборка {APP_NAME} {VERSION} ({'onefile' if onefile else 'onedir'})")

    for folder in (DIST, BUILD):
        if folder.exists():
            shutil.rmtree(folder, ignore_errors=True)

    result = subprocess.run(pyinstaller_args(onefile, console), cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit("PyInstaller завершился с ошибкой")

    exe = DIST / f"{APP_NAME}.exe" if onefile else DIST / APP_NAME / f"{APP_NAME}.exe"
    if not exe.exists() and sys.platform != "win32":
        # На Linux PyInstaller делает файл без расширения — это нормально
        # для проверки самой сборки.
        exe = exe.with_suffix("")
    print(f"==> Готово: {exe}")
    return exe


# --------------------------------------------------------------------------- #
#  Inno Setup
# --------------------------------------------------------------------------- #
ISS_TEMPLATE = r"""; Сгенерировано build_installer.py — правки перезапишутся
#define MyAppName "{app_name}"
#define MyAppVersion "{version}"
#define MyAppPublisher "Budin's industries"
#define MyAppExeName "{app_name}.exe"

[Setup]
; AppId должен быть постоянным GUID: по нему Windows понимает, что новая
; версия ставится поверх старой, а не рядом с ней. Не меняйте его.
AppId={{{{B1D0A5E2-7C4F-4A91-9E3D-6F2C8A4B1D73}}}}
AppName={{#MyAppName}}
AppVersion={{#MyAppVersion}}
AppPublisher={{#MyAppPublisher}}
DefaultDirName={{autopf}}\{{#MyAppName}}
DefaultGroupName={{#MyAppName}}
OutputDir={out_dir}
OutputBaseFilename={app_name}-Setup-{version}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Установка в Program Files требует прав администратора
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={{app}}\{{#MyAppExeName}}

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{{cm:CreateDesktopIcon}}"; \
    GroupDescription: "{{cm:AdditionalIcons}}"; Flags: unchecked

[Files]
Source: "{source_dir}\*"; DestDir: "{{app}}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{{group}}\{{#MyAppName}}"; Filename: "{{app}}\{{#MyAppExeName}}"
Name: "{{group}}\{{cm:UninstallProgram,{{#MyAppName}}}}"; Filename: "{{uninstallexe}}"
Name: "{{autodesktop}}\{{#MyAppName}}"; Filename: "{{app}}\{{#MyAppExeName}}"; \
    Tasks: desktopicon

[Run]
Filename: "{{app}}\{{#MyAppExeName}}"; \
    Description: "{{cm:LaunchProgram,{{#MyAppName}}}}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Настройки и база пользователя остаются в %APPDATA%\Kinoshka намеренно:
; при переустановке профили и история не теряются.
Type: filesandordirs; Name: "{{app}}\_internal"
"""


def find_iscc() -> str | None:
    """Найти компилятор Inno Setup."""
    found = shutil.which("iscc")
    if found:
        return found
    for candidate in (
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
    ):
        if Path(candidate).is_file():
            return candidate
    return None


def build_installer() -> None:
    """Собрать .exe-установщик из onedir-сборки."""
    source_dir = DIST / APP_NAME
    if not source_dir.is_dir():
        raise SystemExit(
            "Не найдена папка сборки. Сначала соберите приложение "
            "без флага --onefile."
        )

    INSTALLER_OUT.mkdir(parents=True, exist_ok=True)
    iss_path = ROOT / "installer.iss"
    iss_path.write_text(
        ISS_TEMPLATE.format(
            app_name=APP_NAME,
            version=VERSION,
            out_dir=str(INSTALLER_OUT),
            source_dir=str(source_dir),
        ),
        encoding="utf-8",
    )
    print(f"==> Скрипт Inno Setup: {iss_path}")

    iscc = find_iscc()
    if iscc is None:
        print(
            "\n!! Inno Setup не найден. Установите его с https://jrsoftware.org/isdl.php\n"
            f"   затем выполните:  iscc \"{iss_path}\""
        )
        return

    result = subprocess.run([iscc, str(iss_path)], cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit("Inno Setup завершился с ошибкой")

    print(f"==> Установщик готов: {INSTALLER_OUT / f'{APP_NAME}-Setup-{VERSION}.exe'}")


# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(description=f"Сборка {APP_NAME}")
    parser.add_argument("--onefile", action="store_true",
                        help="один .exe (запускается медленнее, установщик не делается)")
    parser.add_argument("--no-installer", action="store_true",
                        help="только .exe, без Inno Setup")
    parser.add_argument("--console", action="store_true",
                        help="оставить окно консоли (для отладки)")
    args = parser.parse_args()

    if sys.platform != "win32":
        print("!! Внимание: .exe собирается только на Windows. "
              "Здесь будет проверена лишь корректность конфигурации.\n")

    build_exe(onefile=args.onefile, console=args.console)

    if args.onefile:
        print("==> Режим onefile: установщик не собирается.")
        return
    if args.no_installer:
        return
    if sys.platform != "win32":
        print("==> Установщик собирается только на Windows — пропускаем.")
        return

    build_installer()


if __name__ == "__main__":
    main()
