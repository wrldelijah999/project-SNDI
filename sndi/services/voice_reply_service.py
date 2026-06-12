from __future__ import annotations

import asyncio
import re
import tempfile
import time
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal


try:
    import edge_tts
except ImportError:
    edge_tts = None

try:
    import pygame
except ImportError:
    pygame = None


def prepare_tts_text(text: str, max_chars: int = 700) -> str:
    """
    Prepare SNDI reply for short voice output.

    Rules:
    - remove fenced code blocks;
    - remove huge spacing;
    - truncate long technical replies;
    """
    text = text or ""

    text = re.sub(r"```.*?```", " фрагмент коду пропущено. ", text, flags=re.DOTALL)
    text = re.sub(r"\s+", " ", text).strip()

    if len(text) > max_chars:
        text = text[:max_chars].strip() + "…"

    return text


class VoiceReplyThread(QThread):
    """
    Optional TTS worker.

    Uses edge-tts if available.
    Uses pygame mixer for playback.
    Never blocks GUI.
    """

    status_changed = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(
        self,
        text: str,
        voice: str = "uk-UA-PolinaNeural",
        max_chars: int = 700,
    ):
        super().__init__()
        self.text = text
        self.voice = voice
        self.max_chars = max_chars

    async def _save_tts(self, text: str, output_path: Path):
        communicate = edge_tts.Communicate(text, self.voice)
        await communicate.save(str(output_path))

    def run(self):
        if edge_tts is None:
            self.error.emit("озвучка недоступна: edge-tts не встановлений.")
            return

        if pygame is None:
            self.error.emit("озвучка недоступна: pygame не встановлений.")
            return

        clean_text = prepare_tts_text(self.text, max_chars=self.max_chars)

        if not clean_text:
            return

        temp_path: Path | None = None

        try:
            self.status_changed.emit("speaking")

            with tempfile.NamedTemporaryFile(
                delete=False,
                suffix=".mp3",
                prefix="sndi_tts_",
            ) as temp_file:
                temp_path = Path(temp_file.name)

            asyncio.run(self._save_tts(clean_text, temp_path))

            if not pygame.mixer.get_init():
                pygame.mixer.init()

            pygame.mixer.music.load(str(temp_path))
            pygame.mixer.music.play()

            while pygame.mixer.music.get_busy():
                time.sleep(0.05)

        except Exception as error:
            self.error.emit(f"озвучка впала: {error}")

        finally:
            self.status_changed.emit("online")

            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except Exception:
                    pass