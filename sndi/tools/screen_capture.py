# sndi/tools/screen_capture.py
"""
Screenshot capture for SNDI screen analysis.

Responsibilities:
  - Capture the full desktop to a temp PNG file.
  - Return the file path.
  - Clean up temp file when done.

No OpenAI calls. No GUI business logic. No system actions.
Uses PyQt6 QScreen (already a project dependency — zero new deps).
"""

import os
import tempfile
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt


def capture_screen() -> str:
    """
    Capture the primary screen and save it to a temp PNG.

    Returns:
        Absolute path to the saved PNG file.

    Raises:
        RuntimeError: if no QApplication exists or screen grab fails.
    """
    app = QApplication.instance()
    if app is None:
        raise RuntimeError(
            "capture_screen() must be called after QApplication is created."
        )

    screen = app.primaryScreen()
    if screen is None:
        raise RuntimeError("No primary screen detected.")

    # WinId 0 → grab the full virtual desktop (all monitors combined).
    # On single-monitor setups this is identical to grabWindow(screen).
    pixmap = screen.grabWindow(0)

    if pixmap.isNull():
        raise RuntimeError("Screen grab returned a null pixmap.")

    # Write to a named temp file that survives until we explicitly delete it.
    fd, path = tempfile.mkstemp(suffix=".png", prefix="sndi_scan_")
    os.close(fd)  # close the OS file descriptor; Qt will open by path

    saved = pixmap.save(path, "PNG")
    if not saved:
        os.unlink(path)
        raise RuntimeError(f"Failed to save screenshot to {path}")

    return path


def cleanup_screenshot(path: str) -> None:
    """
    Delete a screenshot file after it has been sent to the API.
    Call this from the thread that created the file, after the API call returns.
    """
    try:
        if path and os.path.exists(path):
            os.unlink(path)
    except OSError:
        pass  # non-fatal — temp files will be cleaned up by OS on reboot