from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal


try:
    import speech_recognition as sr
except ImportError:
    sr = None


class VoiceListenOnceThread(QThread):
    """
    One-shot voice recognition worker.

    Stage 6:
    - listens once
    - emits recognized text
    - never blocks GUI
    - handles microphone / recognition errors gracefully
    """

    recognized = pyqtSignal(str)
    status_changed = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(
        self,
        language: str = "uk-UA",
        timeout: int = 5,
        phrase_time_limit: int = 8,
    ):
        super().__init__()
        self.language = language
        self.timeout = timeout
        self.phrase_time_limit = phrase_time_limit

    def run(self):
        if sr is None:
            self.error.emit("модуль speech_recognition не встановлений.")
            return

        recognizer = sr.Recognizer()

        try:
            self.status_changed.emit("listening")

            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.4)

                audio = recognizer.listen(
                    source,
                    timeout=self.timeout,
                    phrase_time_limit=self.phrase_time_limit,
                )

            self.status_changed.emit("recognizing")

            text = recognizer.recognize_google(audio, language=self.language)
            text = (text or "").strip()

            if not text:
                self.error.emit("не розчула голосову команду.")
                return

            self.recognized.emit(text)

        except sr.WaitTimeoutError:
            self.error.emit("не почула команду. таймаут мікрофона.")

        except sr.UnknownValueError:
            self.error.emit("не розчула. повтори ще раз.")

        except sr.RequestError as error:
            self.error.emit(f"глюк сервера розпізнавання: {error}")

        except Exception as error:
            self.error.emit(f"voice input впав: {error}")

        finally:
            self.status_changed.emit("online")