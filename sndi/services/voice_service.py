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

class VoiceWakeLoopThread(QThread):
    """
    Wake word voice loop.

    Flow:
    - listens in short chunks;
    - tries to detect wake word;
    - after wake word, listens for one command phrase;
    - emits recognized command to GUI;
    - continues listening until stopped.
    """

    command_recognized = pyqtSignal(str)
    wake_detected = pyqtSignal(str)
    status_changed = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(
        self,
        wake_words: tuple[str, ...] | None = None,
        language: str = "uk-UA",
        listen_timeout: int = 4,
        wake_phrase_time_limit: int = 4,
        command_phrase_time_limit: int = 8,
    ):
        super().__init__()

        self.wake_words = wake_words or (
            "сенді",
            "сенді",
            "сенди",
            "sndi",
            "sandy",
        )
        self.language = language
        self.listen_timeout = listen_timeout
        self.wake_phrase_time_limit = wake_phrase_time_limit
        self.command_phrase_time_limit = command_phrase_time_limit
        self._running = True

    def request_stop(self):
        self._running = False

    def _contains_wake_word(self, text: str) -> bool:
        normalized = (text or "").strip().lower()
        return any(wake_word in normalized for wake_word in self.wake_words)

    def run(self):
        if sr is None:
            self.error.emit("модуль speech_recognition не встановлений.")
            self.status_changed.emit("voice off")
            return

        recognizer = sr.Recognizer()

        try:
            with sr.Microphone() as source:
                self.status_changed.emit("listening")
                recognizer.adjust_for_ambient_noise(source, duration=0.5)

                while self._running:
                    try:
                        self.status_changed.emit("listening")

                        wake_audio = recognizer.listen(
                            source,
                            timeout=self.listen_timeout,
                            phrase_time_limit=self.wake_phrase_time_limit,
                        )

                        if not self._running:
                            break

                        wake_text = recognizer.recognize_google(
                            wake_audio,
                            language=self.language,
                        )
                        wake_text = (wake_text or "").strip()

                        if not self._contains_wake_word(wake_text):
                            continue

                        self.wake_detected.emit(wake_text)
                        self.status_changed.emit("wake detected")

                        command_audio = recognizer.listen(
                            source,
                            timeout=self.listen_timeout,
                            phrase_time_limit=self.command_phrase_time_limit,
                        )

                        if not self._running:
                            break

                        self.status_changed.emit("recognizing")

                        command_text = recognizer.recognize_google(
                            command_audio,
                            language=self.language,
                        )
                        command_text = (command_text or "").strip()

                        if command_text:
                            self.command_recognized.emit(command_text)

                    except sr.WaitTimeoutError:
                        continue

                    except sr.UnknownValueError:
                        continue

                    except sr.RequestError as error:
                        self.error.emit(f"глюк сервера розпізнавання: {error}")
                        break

                    except Exception as error:
                        self.error.emit(f"wake loop впав: {error}")
                        break

        except Exception as error:
            self.error.emit(f"мікрофон недоступний: {error}")

        finally:
            self.status_changed.emit("voice off")