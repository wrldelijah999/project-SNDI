from __future__ import annotations

import os
import subprocess


def _run_git(args: list[str], cwd: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )

        output = (result.stdout or result.stderr or "").strip()
        return output

    except Exception as error:
        return f"git error: {error}"


def get_git_summary(project_path: str | None = None) -> str:
    cwd = project_path or os.getcwd()

    branch = _run_git(["branch", "--show-current"], cwd) or "unknown"
    status = _run_git(["status", "--short"], cwd)
    last_commit = _run_git(["log", "-1", "--pretty=%h %s"], cwd)
    last_tag = _run_git(["describe", "--tags", "--abbrev=0"], cwd)

    lines = [
        "стан проєкту:",
        f"- шлях: {cwd}",
        f"- гілка: {branch}",
        f"- останній коміт: {last_commit or 'нема даних'}",
        f"- останній тег: {last_tag or 'нема тегів'}",
    ]

    if status:
        changed = status.splitlines()
        lines.append(f"- незакомічені зміни: {len(changed)} файл(ів)")

        for line in changed[:10]:
            lines.append(f"  {line}")

        if len(changed) > 10:
            lines.append(f"  ...і ще {len(changed) - 10}")

    else:
        lines.append("- working tree чистий")

    return "\n".join(lines)