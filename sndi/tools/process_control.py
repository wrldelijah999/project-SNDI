# sndi/tools/process_control.py
"""
SNDI V1.7 — Process Control.

Safe-ish process closing layer.

No arbitrary shell.
No raw user command execution.
Only closes processes selected by AI/system index/process list.
"""

from __future__ import annotations

import subprocess


def list_processes() -> list[dict]:
    """
    Returns running processes using Windows tasklist.
    """
    try:
        result = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            shell=False,
        )

        lines = result.stdout.splitlines()
        processes: list[dict] = []

        for line in lines:
            parts = [p.strip().strip('"') for p in line.split('","')]

            if len(parts) < 2:
                continue

            name = parts[0].strip('"')
            pid = parts[1].strip('"')

            if not name or not pid:
                continue

            processes.append(
                {
                    "name": name,
                    "pid": pid,
                }
            )

        return processes

    except Exception:
        return []


def build_process_prompt() -> str:
    processes = list_processes()

    if not processes:
        return "RUNNING PROCESSES: empty"

    lines = ["RUNNING PROCESSES:"]

    for proc in processes[:180]:
        lines.append(f"- name: {proc['name']} | pid: {proc['pid']}")

    return "\n".join(lines)


def _normalize_close_target(target: str) -> list[str]:
    """
    Convert human/app/shortcut names into possible process names.
    """
    clean = target.strip().lower()

    for suffix in [".lnk", ".url", ".exe"]:
        if clean.endswith(suffix):
            clean = clean[: -len(suffix)]

    clean = clean.replace("-", " ")
    clean = clean.replace("_", " ")
    clean = " ".join(clean.split())

    candidates = {clean}

    known = {
        "visual studio code": ["code.exe", "code"],
        "vs code": ["code.exe", "code"],
        "vscode": ["code.exe", "code"],
        "вскод": ["code.exe", "code"],
        "вс код": ["code.exe", "code"],

        "spotify": ["spotify.exe", "spotify"],
        "спотик": ["spotify.exe", "spotify"],
        "спотіфай": ["spotify.exe", "spotify"],

        "telegram": ["telegram.exe", "telegram"],
        "телега": ["telegram.exe", "telegram"],
        "телеграм": ["telegram.exe", "telegram"],

        "discord": ["discord.exe", "discord"],
        "діскорд": ["discord.exe", "discord"],
        "дискорд": ["discord.exe", "discord"],

        "chrome": ["chrome.exe", "chrome"],
        "google chrome": ["chrome.exe", "chrome"],
        "хром": ["chrome.exe", "chrome"],

        "steam": ["steam.exe", "steam"],
        "стім": ["steam.exe", "steam"],
        "стим": ["steam.exe", "steam"],
    }

    for key, values in known.items():
        if clean == key or key in clean or clean in key:
            candidates.update(values)

    return [c for c in candidates if c]


def close_process_by_name_or_pid(target: str) -> str:
    """
    Close process by exact/soft process name or PID.
    Uses /F because many desktop apps ignore soft taskkill.
    """
    clean_targets = _normalize_close_target(target)

    if not clean_targets:
        return "не бачу, що саме закривати."

    protected = {
        "explorer.exe",
        "system",
        "registry",
        "services.exe",
        "lsass.exe",
        "winlogon.exe",
        "csrss.exe",
        "smss.exe",
        "svchost.exe",
        "dwm.exe",
        "taskmgr.exe",
    }

    processes = list_processes()
    matches: list[dict] = []

    for proc in processes:
        name = proc["name"].lower()
        pid = str(proc["pid"]).lower()

        for clean in clean_targets:
            clean = clean.lower()

            if clean == pid or clean == name or clean in name:
                matches.append(proc)
                break

    # de-duplicate by pid
    unique: list[dict] = []
    seen_pids: set[str] = set()

    for proc in matches:
        pid = str(proc["pid"])
        if pid not in seen_pids:
            seen_pids.add(pid)
            unique.append(proc)

    matches = unique

    if not matches:
        return f"не знайшла запущений процес для: {target}"

    closed: list[str] = []
    failed: list[str] = []
    skipped: list[str] = []

    for proc in matches[:12]:
        name = proc["name"]
        pid = proc["pid"]

        if name.lower() in protected:
            skipped.append(f"{name} ({pid}) — protected")
            continue

        try:
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                shell=False,
            )

            if result.returncode == 0:
                closed.append(f"{name} ({pid})")
            else:
                err = (result.stderr or result.stdout or "").strip()
                failed.append(f"{name} ({pid}) — {err}")

        except Exception as error:
            failed.append(f"{name} ({pid}) — {error}")

    if closed:
        msg = "закрила:\n" + "\n".join(f"- {x}" for x in closed)

        if skipped:
            msg += "\n\nпропустила:\n" + "\n".join(f"- {x}" for x in skipped)

        if failed:
            msg += "\n\nне змогла закрити:\n" + "\n".join(f"- {x}" for x in failed)

        return msg

    msg = "нічого не закрила."

    if skipped:
        msg += "\n\nпропустила:\n" + "\n".join(f"- {x}" for x in skipped)

    if failed:
        msg += "\n\nпомилки:\n" + "\n".join(f"- {x}" for x in failed)

    return msg