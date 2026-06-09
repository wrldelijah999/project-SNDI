# sndi/tools/project_context.py
"""
SNDI V1.5 — Local Project Awareness / Project Brain Map.

This module is READ-ONLY.

Responsibilities:
  - Detect local SNDI project root.
  - Build compact project tree.
  - Build a project brain map:
      file -> imports/classes/functions/role hints
  - Select potentially relevant files based on user request + file signatures.
  - Read selected files safely.
  - Collect git context.
  - Build one snapshot for the model.

No file modification.
No auto-fix.
No commit/push.
No dangerous commands.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


DEFAULT_PROJECT_ROOT = r"C:\SNDI project"

MAX_TREE_ITEMS = 260
MAX_INDEXED_FILES = 180
MAX_FILE_CHARS = 8500
MAX_SELECTED_FILES = 8
MAX_TOTAL_SNAPSHOT_CHARS = 65000

IGNORED_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".idea",
    ".vscode",
    "build",
    "dist",
    "venv",
    ".venv",
    "env",
    "node_modules",
}

IGNORED_FILE_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".zip",
    ".7z",
    ".rar",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".ico",
    ".wav",
    ".mp3",
    ".mp4",
    ".mov",
    ".pdf",
}

TEXT_FILE_SUFFIXES = {
    ".py",
    ".yaml",
    ".yml",
    ".json",
    ".txt",
    ".md",
    ".toml",
    ".ini",
    ".cfg",
    ".gitignore",
}

ALWAYS_INCLUDE_FILES = [
    ".gitignore",
    "config.yaml",
    "requirements.txt",
    "run.py",
    "main.py",
    "gui.py",
    "sndi/core/conversation_core.py",
    "sndi/core/memory.py",
    "sndi/core/intents.py",
    "sndi/services/openai_service.py",
    "sndi/storage.py",
    "sndi/tools/project_context.py",
]


@dataclass
class FileSignature:
    rel_path: str
    suffix: str
    size: int
    imports: list[str]
    classes: list[str]
    functions: list[str]
    role_hints: list[str]

    def compact(self) -> str:
        imports = ", ".join(self.imports[:12]) if self.imports else "-"
        classes = ", ".join(self.classes[:12]) if self.classes else "-"
        functions = ", ".join(self.functions[:18]) if self.functions else "-"
        roles = ", ".join(self.role_hints[:10]) if self.role_hints else "-"

        return (
            f"{self.rel_path}\n"
            f"  size: {self.size} bytes\n"
            f"  imports: {imports}\n"
            f"  classes: {classes}\n"
            f"  functions: {functions}\n"
            f"  role_hints: {roles}"
        )


def get_project_root() -> Path:
    """
    Return local project root.

    Priority:
      1. SNDI_PROJECT_ROOT env variable
      2. DEFAULT_PROJECT_ROOT
      3. current working directory
    """
    env_root = os.getenv("SNDI_PROJECT_ROOT")

    if env_root and Path(env_root).exists():
        return Path(env_root).resolve()

    default = Path(DEFAULT_PROJECT_ROOT)

    if default.exists():
        return default.resolve()

    return Path.cwd().resolve()


def _run_command(command: list[str], cwd: Path, timeout: int = 8) -> str:
    """
    Run a safe read-only command.
    Never pass raw user input here.
    """
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
        )

        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()

        if stdout and stderr:
            return stdout + "\n[stderr]\n" + stderr

        return stdout or stderr or ""

    except FileNotFoundError:
        return f"command not found: {command[0]}"

    except subprocess.TimeoutExpired:
        return f"command timeout: {' '.join(command)}"

    except Exception as error:
        return f"command error: {error}"


def _should_skip_dir(dirname: str) -> bool:
    return dirname in IGNORED_DIRS


def _should_skip_file(path: Path) -> bool:
    name = path.name.lower()

    if name == ".env" or name.endswith(".env"):
        return True

    if path.suffix.lower() in IGNORED_FILE_SUFFIXES:
        return True

    return False


def _is_text_candidate(path: Path) -> bool:
    if _should_skip_file(path):
        return False

    if path.name == ".gitignore":
        return True

    if path.suffix.lower() in TEXT_FILE_SUFFIXES:
        return True

    return False


def _iter_project_files(root: Path, max_files: int = MAX_INDEXED_FILES) -> list[Path]:
    files: list[Path] = []

    for current_root, dirs, filenames in os.walk(root):
        current = Path(current_root)

        dirs[:] = sorted(
            [d for d in dirs if not _should_skip_dir(d)],
            key=str.lower,
        )

        try:
            rel_dir = current.relative_to(root)
        except ValueError:
            continue

        depth = 0 if rel_dir == Path(".") else len(rel_dir.parts)

        if depth > 6:
            dirs[:] = []
            continue

        for filename in sorted(filenames, key=str.lower):
            path = current / filename

            if not _is_text_candidate(path):
                continue

            files.append(path)

            if len(files) >= max_files:
                return files

    return files


def get_git_snapshot(root: Path) -> str:
    """
    Collect read-only git context.
    """
    if not (root / ".git").exists():
        return "git: not a git repository"

    parts = []

    parts.append("## git branch")
    parts.append(_run_command(["git", "branch", "--show-current"], root))

    parts.append("\n## git status --short --branch")
    parts.append(_run_command(["git", "status", "--short", "--branch"], root))

    parts.append("\n## git log --oneline -8")
    parts.append(_run_command(["git", "log", "--oneline", "-8"], root))

    parts.append("\n## git diff --stat")
    parts.append(_run_command(["git", "diff", "--stat"], root))

    parts.append("\n## git diff --cached --stat")
    parts.append(_run_command(["git", "diff", "--cached", "--stat"], root))

    return "\n".join(parts).strip()


def get_project_tree(root: Path, max_items: int = MAX_TREE_ITEMS) -> str:
    """
    Return compact project tree.
    """
    lines = []
    count = 0

    for current_root, dirs, files in os.walk(root):
        current = Path(current_root)

        dirs[:] = sorted(
            [d for d in dirs if not _should_skip_dir(d)],
            key=str.lower,
        )

        rel_dir = current.relative_to(root)
        depth = 0 if rel_dir == Path(".") else len(rel_dir.parts)

        if depth > 5:
            dirs[:] = []
            continue

        for filename in sorted(files, key=str.lower):
            path = current / filename

            if _should_skip_file(path):
                continue

            rel = path.relative_to(root)
            indent = "  " * depth
            lines.append(f"{indent}- {rel.as_posix()}")
            count += 1

            if count >= max_items:
                lines.append(f"... truncated after {max_items} files")
                return "\n".join(lines)

    return "\n".join(lines) if lines else "(empty tree)"


def read_text_file_safe(root: Path, rel_path: str, max_chars: int = MAX_FILE_CHARS) -> str:
    """
    Read project text file safely.
    Prevents path traversal outside project.
    """
    try:
        path = (root / rel_path).resolve()

        if root not in path.parents and path != root:
            return f"[blocked path outside project: {rel_path}]"

        if not path.exists():
            return f"[missing file: {rel_path}]"

        if not path.is_file():
            return f"[not a file: {rel_path}]"

        if not _is_text_candidate(path):
            return f"[skipped unsafe/heavy file: {rel_path}]"

        text = path.read_text(encoding="utf-8", errors="replace")

        if len(text) > max_chars:
            return text[:max_chars] + f"\n\n... truncated after {max_chars} chars"

        return text

    except Exception as error:
        return f"[read error {rel_path}: {error}]"


def _extract_python_signature(path: Path, root: Path) -> FileSignature:
    rel_path = path.relative_to(root).as_posix()
    size = path.stat().st_size

    imports: list[str] = []
    classes: list[str] = []
    functions: list[str] = []

    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)

            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module:
                    imports.append(module)

            elif isinstance(node, ast.ClassDef):
                classes.append(node.name)

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(node.name)

    except Exception:
        pass

    role_hints = _infer_role_hints(rel_path, imports, classes, functions)

    return FileSignature(
        rel_path=rel_path,
        suffix=path.suffix.lower(),
        size=size,
        imports=sorted(set(imports)),
        classes=classes,
        functions=functions,
        role_hints=role_hints,
    )


def _extract_generic_signature(path: Path, root: Path) -> FileSignature:
    rel_path = path.relative_to(root).as_posix()
    size = path.stat().st_size
    role_hints = _infer_role_hints(rel_path, [], [], [])

    return FileSignature(
        rel_path=rel_path,
        suffix=path.suffix.lower() or path.name,
        size=size,
        imports=[],
        classes=[],
        functions=[],
        role_hints=role_hints,
    )


def _infer_role_hints(
    rel_path: str,
    imports: list[str],
    classes: list[str],
    functions: list[str],
) -> list[str]:
    """
    Soft role inference.

    This is not final reasoning.
    It only gives the model a map of likely responsibilities.
    """
    text = " ".join(
        [
            rel_path.lower(),
            " ".join(imports).lower(),
            " ".join(classes).lower(),
            " ".join(functions).lower(),
        ]
    )

    hints: list[str] = []

    role_patterns = [
        ("gui/ui/chat window", ["gui", "pyqt", "qwidget", "chatwindow", "render", "input_field"]),
        ("openai/api/model calls", ["openai", "call_model", "analyze_image", "analyze_project"]),
        ("memory/history/profile", ["memory", "history", "profile", "append_history", "load_history"]),
        ("storage/appdata/json persistence", ["storage", "appdata", "save_json", "load_json"]),
        ("intent detection/routing", ["intent", "is_", "patterns", "regex"]),
        ("screen capture/vision", ["screen", "capture", "screenshot", "grabwindow", "analyze_image"]),
        ("local project awareness", ["project_context", "project_snapshot", "project", "git_snapshot"]),
        ("system commands/safety", ["system_manager", "shutdown", "restart", "kill", "confirm"]),
        ("configuration/prompts", ["config", "yaml", "system_prompt", "developer_prompt"]),
        ("entrypoint/startup", ["run.py", "main.py", "if __name__"]),
        ("sanitizing/cleanup", ["sanitize", "clean", "filter"]),
        ("requirements/dependencies", ["requirements"]),
        ("git ignore/repository hygiene", [".gitignore"]),
    ]

    for hint, needles in role_patterns:
        if any(needle in text for needle in needles):
            hints.append(hint)

    return hints


def build_project_brain_map(root: Path) -> tuple[list[FileSignature], str]:
    """
    Build signatures for project files.
    """
    signatures: list[FileSignature] = []

    for path in _iter_project_files(root):
        try:
            if path.suffix.lower() == ".py":
                sig = _extract_python_signature(path, root)
            else:
                sig = _extract_generic_signature(path, root)

            signatures.append(sig)

        except Exception:
            continue

    lines = []

    for sig in signatures:
        lines.append(sig.compact())

    return signatures, "\n\n".join(lines) if lines else "(no project signatures)"


def _normalize_query_tokens(user_request: str) -> set[str]:
    text = user_request.lower()

    tokens = re.findall(r"[a-zа-яіїєґ0-9_\.]{3,}", text, flags=re.IGNORECASE)

    # легкі синоніми, щоб не вимагати точних назв файлів
    semantic_expansions = {
        "пам": ["memory", "history", "profile", "storage"],
        "істор": ["memory", "history", "append_history", "load_history"],
        "екран": ["screen", "capture", "screenshot", "vision", "image"],
        "скан": ["screen", "capture", "screenshot", "vision", "image"],
        "модель": ["openai", "call_model", "api", "services"],
        "опенаі": ["openai", "api", "model"],
        "openai": ["openai", "api", "model"],
        "чат": ["conversation", "chat", "gui", "messages"],
        "відповід": ["conversation", "call_model", "openai"],
        "інтерфейс": ["gui", "pyqt", "chatwindow"],
        "вікно": ["gui", "pyqt", "chatwindow"],
        "конфіг": ["config", "yaml", "prompt"],
        "промпт": ["config", "prompt", "system_prompt", "developer_prompt"],
        "гіт": ["git", ".gitignore", "repository"],
        "git": ["git", ".gitignore", "repository"],
        "залеж": ["requirements", "dependencies"],
        "команд": ["system_manager", "commands", "safety"],
        "система": ["system_manager", "storage", "appdata"],
    }

    expanded = set(tokens)

    for token in list(tokens):
        for key, values in semantic_expansions.items():
            if key in token:
                expanded.update(values)

    return expanded


def select_relevant_files(
    signatures: list[FileSignature],
    user_request: str,
    max_files: int = MAX_SELECTED_FILES,
) -> list[str]:
    """
    Select files likely relevant to the user request.

    This is not a hard command router.
    It only chooses extra context for the model.
    The model still reasons over the brain map.
    """
    query_tokens = _normalize_query_tokens(user_request)

    scored: list[tuple[int, str]] = []

    for sig in signatures:
        searchable = " ".join(
            [
                sig.rel_path.lower(),
                " ".join(sig.imports).lower(),
                " ".join(sig.classes).lower(),
                " ".join(sig.functions).lower(),
                " ".join(sig.role_hints).lower(),
            ]
        )

        score = 0

        for token in query_tokens:
            if token and token in searchable:
                score += 2

        # мʼякий бонус для ключових файлів архітектури
        if sig.rel_path in ALWAYS_INCLUDE_FILES:
            score += 1

        if score > 0:
            scored.append((score, sig.rel_path))

    scored.sort(key=lambda item: (-item[0], item[1]))

    selected: list[str] = []

    for _, rel_path in scored:
        if rel_path not in selected:
            selected.append(rel_path)

        if len(selected) >= max_files:
            break

    # якщо запит загальний — даємо базовий набір ядра
    if not selected:
        for rel_path in ALWAYS_INCLUDE_FILES:
            if rel_path not in selected:
                selected.append(rel_path)

            if len(selected) >= max_files:
                break

    return selected


def build_selected_files_snapshot(root: Path, selected_files: list[str]) -> str:
    blocks = []

    for rel_path in selected_files:
        content = read_text_file_safe(root, rel_path)

        if content.startswith("[missing file:"):
            continue

        blocks.append(
            f"\n\n--- SELECTED FILE: {rel_path} ---\n"
            f"{content}"
        )

    return "".join(blocks).strip() if blocks else "(no selected files read)"


def build_project_snapshot(user_request: str = "") -> str:
    """
    Build one local project snapshot for model reasoning.

    The snapshot contains:
      - tree
      - git state
      - project brain map
      - selected file contents

    This is the main function used by GUI ProjectThread.
    """
    root = get_project_root()

    signatures, brain_map = build_project_brain_map(root)
    selected_files = select_relevant_files(signatures, user_request)
    selected_snapshot = build_selected_files_snapshot(root, selected_files)

    sections = [
        "# SNDI LOCAL PROJECT SNAPSHOT",
        "",
        f"project_root: {root}",
        f"user_request: {user_request.strip() or '(none)'}",
        "",
        "# PROJECT TREE",
        get_project_tree(root),
        "",
        "# GIT SNAPSHOT",
        get_git_snapshot(root),
        "",
        "# PROJECT BRAIN MAP",
        brain_map,
        "",
        "# AUTO-SELECTED FILES FOR THIS REQUEST",
        "\n".join(f"- {path}" for path in selected_files),
        "",
        "# SELECTED FILE CONTENTS",
        selected_snapshot,
    ]

    snapshot = "\n".join(sections)

    if len(snapshot) > MAX_TOTAL_SNAPSHOT_CHARS:
        snapshot = (
            snapshot[:MAX_TOTAL_SNAPSHOT_CHARS]
            + f"\n\n... PROJECT SNAPSHOT TRUNCATED AFTER {MAX_TOTAL_SNAPSHOT_CHARS} CHARS"
        )

    return snapshot