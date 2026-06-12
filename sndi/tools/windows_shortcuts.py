from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys
import tempfile

from sndi.core.app_paths import (
    get_project_root,
    get_executable_path,
    is_frozen,
)


APP_NAME = "SNDI"
SHORTCUT_NAME = "SNDI.lnk"


def get_desktop_dir() -> Path:
    """
    User Desktop directory.
    """
    user_profile = os.environ.get("USERPROFILE")

    if user_profile:
        desktop = Path(user_profile) / "Desktop"

        if desktop.exists():
            return desktop

    return Path.home() / "Desktop"


def get_start_menu_dir() -> Path:
    """
    User-level Start Menu Programs directory.
    No admin rights required.
    """
    appdata = os.environ.get("APPDATA")

    if not appdata:
        return Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs"

    return (
        Path(appdata)
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
    )


def get_desktop_shortcut_path() -> Path:
    return get_desktop_dir() / SHORTCUT_NAME


def get_start_menu_shortcut_path() -> Path:
    return get_start_menu_dir() / SHORTCUT_NAME


def get_built_exe_path() -> Path:
    """
    Dev mode expected build output:
    C:\\SNDI project\\dist\\SNDI\\SNDI.exe
    """
    return get_project_root() / "dist" / "SNDI" / "SNDI.exe"


def _get_pythonw_path() -> Path:
    """
    Prefer pythonw.exe for dev shortcut fallback to avoid console window.
    """
    current = Path(sys.executable).resolve()
    pythonw = current.with_name("pythonw.exe")

    if pythonw.exists():
        return pythonw

    return current


def get_shortcut_launch_parts() -> tuple[str, str, str]:
    """
    Return target, arguments, working_dir.

    Priority:
    1. If running frozen: current SNDI.exe.
    2. If dist/SNDI/SNDI.exe exists: built exe.
    3. Fallback dev mode: pythonw.exe run.py.
    """
    if is_frozen():
        exe = get_executable_path()
        return str(exe), "", str(exe.parent)

    built_exe = get_built_exe_path()

    if built_exe.exists():
        return str(built_exe), "", str(built_exe.parent)

    project_root = get_project_root()
    run_py = project_root / "run.py"
    pythonw = _get_pythonw_path()

    return str(pythonw), f'"{run_py}"', str(project_root)


def _get_icon_path() -> str:
    """
    Use exe icon if available. If no built exe, leave icon empty.
    """
    target, _arguments, _working_dir = get_shortcut_launch_parts()
    target_path = Path(target)

    if target_path.exists() and target_path.suffix.lower() == ".exe":
        return str(target_path)

    return ""


def _escape_powershell_single_quoted(value: str) -> str:
    return value.replace("'", "''")


def _create_lnk_shortcut(shortcut_path: Path) -> str:
    """
    Create a real Windows .lnk shortcut via PowerShell COM.
    No pywin32 dependency required.
    """
    shortcut_path.parent.mkdir(parents=True, exist_ok=True)

    target, arguments, working_dir = get_shortcut_launch_parts()
    icon_path = _get_icon_path()

    ps_script = f"""
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut('{_escape_powershell_single_quoted(str(shortcut_path))}')
$Shortcut.TargetPath = '{_escape_powershell_single_quoted(target)}'
$Shortcut.Arguments = '{_escape_powershell_single_quoted(arguments)}'
$Shortcut.WorkingDirectory = '{_escape_powershell_single_quoted(working_dir)}'
$Shortcut.Description = 'SNDI — local Windows AI companion'
"""

    if icon_path:
        ps_script += f"$Shortcut.IconLocation = '{_escape_powershell_single_quoted(icon_path)}'\n"

    ps_script += "$Shortcut.Save()\n"

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".ps1",
        delete=False,
        encoding="utf-8-sig",
    ) as temp_script:
        temp_script.write(ps_script)
        script_path = Path(temp_script.name)

    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )

        if result.returncode != 0:
            return (
                "не змогла створити ярлик: "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )

        return f"ярлик створено: {shortcut_path}"

    except Exception as error:
        return f"не змогла створити ярлик: {error}"

    finally:
        try:
            script_path.unlink(missing_ok=True)
        except Exception:
            pass


def create_desktop_shortcut() -> str:
    return _create_lnk_shortcut(get_desktop_shortcut_path())


def create_start_menu_shortcut() -> str:
    return _create_lnk_shortcut(get_start_menu_shortcut_path())


def remove_desktop_shortcut() -> str:
    shortcut = get_desktop_shortcut_path()

    if not shortcut.exists():
        return "ярлика на робочому столі немає."

    try:
        shortcut.unlink()
        return "ярлик на робочому столі видалено."
    except Exception as error:
        return f"не змогла видалити ярлик на робочому столі: {error}"


def remove_start_menu_shortcut() -> str:
    shortcut = get_start_menu_shortcut_path()

    if not shortcut.exists():
        return "ярлика в Start Menu немає."

    try:
        shortcut.unlink()
        return "ярлик у Start Menu видалено."
    except Exception as error:
        return f"не змогла видалити ярлик у Start Menu: {error}"


def create_all_shortcuts() -> str:
    desktop_result = create_desktop_shortcut()
    start_menu_result = create_start_menu_shortcut()

    return f"{desktop_result}\n{start_menu_result}"


def remove_all_shortcuts() -> str:
    desktop_result = remove_desktop_shortcut()
    start_menu_result = remove_start_menu_shortcut()

    return f"{desktop_result}\n{start_menu_result}"


def get_shortcut_status() -> str:
    target, arguments, working_dir = get_shortcut_launch_parts()

    desktop_shortcut = get_desktop_shortcut_path()
    start_menu_shortcut = get_start_menu_shortcut_path()

    return (
        "SNDI shortcut status:\n"
        f"- mode: {'frozen_exe' if is_frozen() else 'dev'}\n"
        f"- target: {target}\n"
        f"- arguments: {arguments or '(none)'}\n"
        f"- working dir: {working_dir}\n"
        f"- desktop shortcut: {'exists' if desktop_shortcut.exists() else 'missing'} — {desktop_shortcut}\n"
        f"- start menu shortcut: {'exists' if start_menu_shortcut.exists() else 'missing'} — {start_menu_shortcut}"
    )