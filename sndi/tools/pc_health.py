from __future__ import annotations

from pathlib import Path
import shutil
import time


try:
    import psutil
except ImportError:
    psutil = None


def _format_bytes(value: int | float) -> str:
    value = float(value)

    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024:
            return f"{value:.1f} {unit}"

        value /= 1024

    return f"{value:.1f} PB"


def get_pc_health_report() -> str:
    if psutil is None:
        return (
            "pc health модуль не активний.\n"
            "треба встановити залежність:\n"
            "python -m pip install psutil"
        )

    cpu_percent = psutil.cpu_percent(interval=0.6)
    ram = psutil.virtual_memory()

    disk_root = Path.home().anchor or "/"
    disk = shutil.disk_usage(disk_root)

    boot_time = psutil.boot_time()
    uptime_seconds = int(time.time() - boot_time)
    uptime_hours = uptime_seconds // 3600
    uptime_minutes = (uptime_seconds % 3600) // 60

    processes = []

    for proc in psutil.process_iter(["pid", "name", "memory_percent"]):
        try:
            info = proc.info

            processes.append(
                {
                    "pid": info.get("pid"),
                    "name": info.get("name") or "unknown",
                    "memory_percent": float(info.get("memory_percent") or 0.0),
                }
            )

        except Exception:
            continue

    top_processes = sorted(
        processes,
        key=lambda item: item["memory_percent"],
        reverse=True,
    )[:7]

    lines = [
        "стан пк:",
        f"- CPU: {cpu_percent:.1f}%",
        (
            f"- RAM: {ram.percent:.1f}% "
            f"({_format_bytes(ram.used)} / {_format_bytes(ram.total)})"
        ),
        (
            f"- диск {disk_root}: "
            f"{(disk.used / disk.total * 100):.1f}% "
            f"({_format_bytes(disk.used)} / {_format_bytes(disk.total)})"
        ),
        f"- uptime: {uptime_hours} год {uptime_minutes} хв",
        "",
        "найважчі процеси по RAM:",
    ]

    if not top_processes:
        lines.append("- не вдалося прочитати список процесів")
    else:
        for proc in top_processes:
            lines.append(
                f"- {proc['name']} "
                f"(PID {proc['pid']}): "
                f"{proc['memory_percent']:.1f}% RAM"
            )

    return "\n".join(lines)