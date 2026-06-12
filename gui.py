# gui.py
import sys
import os
import re
import math
import random

from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextBrowser,
    QLineEdit,
    QPushButton,
    QLabel,
    QFrame,
    QSizePolicy,
    QGraphicsDropShadowEffect,
    QSpacerItem,
    QMessageBox,
    QSystemTrayIcon,
    QMenu
)

from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QUrl
from PyQt6.QtGui import (
    QFont,
    QFontDatabase,
    QPixmap,
    QColor,
    QPainter,
    QLinearGradient,
    QBrush,
    QTextCursor,
    QDesktopServices,
    QIcon,
    QAction
)

from sndi.core.conversation_core import ask
from sndi.storage import resource_path
from sndi.system_manager import SystemManager
from sndi.tools.screen_capture import capture_screen, cleanup_screenshot
from sndi.core.memory import append_history
from sndi.core.intents import is_screen_scan_intent, is_project_awareness_intent
from sndi.tools.system_control import run_system_control_from_text
from sndi.tools.project_context import build_project_snapshot
from sndi.core.action_router import decide_action, execute_action
from sndi.core.app_settings import load_app_settings, save_app_settings, set_app_setting
from sndi.tools.clipboard_tools import get_clipboard_text
from sndi.services.voice_reply_service import VoiceReplyThread
from sndi.services.voice_service import VoiceListenOnceThread, VoiceWakeLoopThread
from sndi.tools.autostart import (
    enable_autostart,
    disable_autostart,
    get_autostart_status,
    is_autostart_enabled,
)
from sndi.services.openai_service import (
    analyze_image,
    analyze_project_snapshot,
    decide_if_web_needed,
    call_web_search,
    decide_system_action,
    looks_like_system_request
)
from sndi.core.action_log import append_action_log
from sndi.core.confirmation import (
    ConfirmationManager,
    PendingAction,
    format_no_pending_action_message,
    format_pending_action_cancelled_message,
    format_pending_action_expired_message,
    format_pending_action_message,
    is_cancel_text,
    is_confirmation_text,
)


try:
    import pygame
except ImportError:
    pygame = None

try:
    import speech_recognition as sr
except ImportError:
    sr = None


# ---------- helpers: fonts ----------
def load_cyberpunk_font() -> str:
    candidates = [
        "assets/fonts/Rajdhani-Regular.ttf",
        "assets/fonts/Orbitron-Regular.ttf",
        "assets/fonts/Audiowide-Regular.ttf",
        "assets/fonts/ShareTechMono-Regular.ttf",
    ]

    loaded_family = None

    for rel in candidates:
        path = resource_path(rel)

        if os.path.exists(path):
            font_id = QFontDatabase.addApplicationFont(path)

            if font_id != -1:
                families = QFontDatabase.applicationFontFamilies(font_id)

                if families:
                    loaded_family = families[0]
                    break

    return loaded_family or "Bahnschrift"


# ---------- helpers: images ----------
AVATAR_PATH_CANDIDATES = [
    "assets/images/sndi_avatar.png",
    "assets/images/sndi.png",
    "assets/pictures/sndi_avatar.png",
]


def load_avatar_pixmap(target_h: int = 240) -> QPixmap:
    pix = QPixmap()

    for rel in AVATAR_PATH_CANDIDATES:
        path = resource_path(rel)

        if os.path.exists(path):
            pix = QPixmap(path)
            break

    if pix.isNull():
        pix = QPixmap(target_h, target_h)
        pix.fill(Qt.GlobalColor.black)

    if target_h:
        pix = pix.scaledToHeight(
            target_h,
            Qt.TransformationMode.SmoothTransformation,
        )

    return pix


# ---------- helpers: audio ----------
class SoundManager:
    def __init__(self):
        self.enabled = False
        self.message_sound = None
        self.send_sound = None

        if pygame is None:
            return

        try:
            pygame.mixer.init()
            self.enabled = True
        except Exception as error:
            print("[SNDI][AUDIO INIT ERROR]", error)
            self.enabled = False
            return

        self.message_sound = self._load_sound("assets/audio/cyberpunk_message.wav")
        self.send_sound = self._load_sound("assets/audio/send_sound.mp3")

    def _load_sound(self, rel_path: str):
        if not self.enabled:
            return None

        path = resource_path(rel_path)

        if not os.path.exists(path):
            print(f"[SNDI][AUDIO] File not found: {path}")
            return None

        try:
            return pygame.mixer.Sound(path)
        except Exception as error:
            print(f"[SNDI][AUDIO LOAD ERROR] {rel_path}: {error}")
            return None

    def play_send(self):
        self._safe_play(self.send_sound)

    def play_message(self):
        self._safe_play(self.message_sound)

    def _safe_play(self, sound):
        if not self.enabled or sound is None:
            return

        try:
            sound.play()
        except Exception as error:
            print("[SNDI][AUDIO PLAY ERROR]", error)


# ---------- async ----------
class ResponseThread(QThread):
    finished = pyqtSignal(str)

    def __init__(self, user_text: str):
        super().__init__()
        self.user_text = user_text

    def run(self):
        try:
            reply = ask(self.user_text)
        except Exception as error:
            print("[SNDI][THREAD ERROR]", error)
            reply = "система дала збій. перевір консоль."
        self.finished.emit(reply)

# ---------- async: screen scan ----------
_VISION_SYSTEM_PROMPT = (
    "Ти — SNDI, cyberpunk AI companion користувача. "
    "Ти дивишся на скріншот його екрана. "
    "Поясни, що відкрито, що може бути важливим, що може бути проблемою, "
    "і дай 1-2 конкретні наступні кроки. "
    "Відповідай українською. Говори коротко, точно, як напарниця, "
    "а не як сухий корпоративний асистент. "
    "Не вигадуй того, чого не видно на екрані."
)


class ScanThread(QThread):
    finished = pyqtSignal(str)

    def __init__(self, screenshot_path: str, user_text: str):
        super().__init__()
        self.screenshot_path = screenshot_path
        self.user_text = user_text

    def run(self):
        try:
            prompt = (
                f"{_VISION_SYSTEM_PROMPT}\n\n"
                f"Запит користувача: {self.user_text}"
            )

            reply = analyze_image(self.screenshot_path, prompt)

            if not reply or not reply.strip():
                reply = "глухий канал. нічого не бачу."

        except Exception as error:
            print("[SNDI][SCAN THREAD ERROR]", error)
            reply = f"⚡ скан впав: {error}"

        finally:
            cleanup_screenshot(self.screenshot_path)

        self.finished.emit(reply)

# ---------- async: local project awareness ----------
class ProjectThread(QThread):
    finished = pyqtSignal(str)

    def __init__(self, user_text: str):
        super().__init__()
        self.user_text = user_text

    def run(self):
        try:
            snapshot = build_project_snapshot(self.user_text)
            reply = analyze_project_snapshot(snapshot, self.user_text)

            if not reply or not reply.strip():
                reply = "бачу проєкт, але думка не зібралась. модель повернула порожню відповідь."

        except Exception as error:
            print("[SNDI][PROJECT THREAD ERROR]", error)
            reply = f"⚡ project awareness впав: {error}"

        self.finished.emit(reply)

# ---------- async: internet awareness ----------
class WebThread(QThread):
    finished = pyqtSignal(str)

    def __init__(self, user_text: str):
        super().__init__()
        self.user_text = user_text

    def run(self):
        try:
            decision = decide_if_web_needed(self.user_text)

            if not decision.get("needs_web", False):
                self.finished.emit("__NO_WEB_NEEDED__")
                return

            query = decision.get("query", "") or self.user_text
            reply = call_web_search(self.user_text, query)

            if not reply or not reply.strip():
                reply = "вийшла в інтернет, але нічого нормального не витягнула."

        except Exception as error:
            print("[SNDI][WEB THREAD ERROR]", error)
            reply = f"⚡ web awareness впав: {error}"

        self.finished.emit(reply)

# ---------- async: system control ----------
class SystemActionThread(QThread):
    finished = pyqtSignal(str)

    def __init__(self, user_text: str):
        super().__init__()
        self.user_text = user_text

    def run(self):
        try:
            if looks_like_system_request(self.user_text):
                action = decide_system_action(self.user_text)
            else:
                action = {
                    "is_system_action": False,
                    "intent": "unknown",
                    "target": "",
                    "url": "",
                    "query": "",
                    "confidence": 0.0,
                    "reason": "skipped system AI check: message does not look like a system request",
                }

            if not action.get("is_system_action", False):
                self.finished.emit("__NO_SYSTEM_ACTION__")
                return

            confidence = float(action.get("confidence", 0.0) or 0.0)

            if confidence < 0.45:
                self.finished.emit("__NO_SYSTEM_ACTION__")
                return

            reply = run_system_control_from_text(self.user_text, action)

            if not reply or not reply.strip():
                reply = "системна дія ніби виконалась, але відповідь порожня."

        except Exception as error:
            print("[SNDI][SYSTEM ACTION THREAD ERROR]", error)
            reply = f"⚡ system control впав: {error}"

        self.finished.emit(reply)




# ---------- widget: NeonBar ----------
class NeonBar(QWidget):
    """
    Thin neon bar with gentle flicker.
    """

    def __init__(
        self,
        color: QColor | None = None,
        height: int = 8,
        radius: int = 4,
        parent=None,
    ):
        super().__init__(parent)

        self.base_color = color or QColor(0, 255, 255)
        self.radius = radius
        self.setFixedHeight(height)

        self._t = 0.0
        self._intensity = 0.75
        self._target = 0.85

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(30)

    def _tick(self):
        self._t += 0.03
        breath = 0.08 * math.sin(self._t)

        if random.random() < 0.04:
            self._target = 0.65 + random.random() * 0.35

        self._intensity += (self._target - self._intensity) * 0.12
        self._intensity = max(0.5, min(1.0, self._intensity + breath))

        self.update()

    def paintEvent(self, event):
        width = self.width()
        height = self.height()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        alpha_core = int(255 * self._intensity)
        alpha_edge = int(alpha_core * 0.28)

        gradient = QLinearGradient(0, 0, width, 0)
        color = QColor(self.base_color)

        transparent = QColor(color.red(), color.green(), color.blue(), 0)
        edge = QColor(color.red(), color.green(), color.blue(), alpha_edge)
        core = QColor(color.red(), color.green(), color.blue(), alpha_core)

        gradient.setColorAt(0.00, transparent)
        gradient.setColorAt(0.14, edge)
        gradient.setColorAt(0.50, core)
        gradient.setColorAt(0.86, edge)
        gradient.setColorAt(1.00, transparent)

        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, width, height, self.radius, self.radius)


# ---------- main UI ----------
class ChatWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("SNDI — Night City Chat")
        self.setMinimumSize(1080, 720)

        # palette
        self.theme_bg = "#0a0a0f"
        self.sidebar_bg = "#0c0e15"
        self.chat_bg = "#0b0c12"
        self.user_bubble_fill = "#0e1c1f"
        self.sndi_bubble_fill = "#120c1a"
        self.cyan_text = "#00f0ff"
        self.name_red = "#ff2b2b"
        self.frame_line = "#133a40"

        # fonts
        self.ui_font_family = load_cyberpunk_font()
        self.base_font = QFont(self.ui_font_family, 11)

        # sound
        self.sound_manager = SoundManager()

        # state
        self.messages: list[dict] = []
        self.response_thread: ResponseThread | None = None
        self.scan_thread: ScanThread | None = None
        self.project_thread: ProjectThread | None = None
        self.web_thread: WebThread | None = None
        self.system_action_thread: SystemActionThread | None = None
        self.voice_once_thread: VoiceListenOnceThread | None = None
        self.voice_wake_thread: VoiceWakeLoopThread | None = None
        self.voice_reply_thread: VoiceReplyThread | None = None
        self.streaming_text: str | None = None
        self.streaming_index = 0
        self.dot_phase = 0
        # local app settings for v1.10 voice/tray/autostart
        self.app_settings = load_app_settings()
        # v1.11 confirmation layer for safe mutation actions
        self.confirmation_manager = ConfirmationManager()

        # tray state
        self.force_quit = False
        self._tray_notice_shown = False
        self.tray_icon: QSystemTrayIcon | None = None
        self.tray_menu: QMenu | None = None
        self.tray_status_action: QAction | None = None
        self.tray_start_voice_action: QAction | None = None
        self.tray_listen_once_action: QAction | None = None
        self.tray_stop_voice_action: QAction | None = None
        self.tray_autostart_action: QAction | None = None

        self.timer = QTimer()
        self.timer.timeout.connect(self._on_timer)

        # SystemManager only at GUI level
        self.system_mgr = SystemManager(
            confirm_cb=self.confirm_dialog,
            log_cb=self.append_system_log,
        )

        self._build_ui()
        self._setup_tray()

    # ---------- UI builder ----------
    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        self.setStyleSheet(
            f"""
            QWidget {{
                background-color: {self.theme_bg};
                color: {self.cyan_text};
            }}
            """
        )

        self.sidebar = self._build_sidebar()
        root.addWidget(self.sidebar)

        right_col = QVBoxLayout()
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(10)

        right_col.addWidget(
            NeonBar(
                QColor(0, 255, 240),
                height=8,
                radius=4,
            )
        )

        self.chat_area = QTextBrowser()
        self.chat_area.setReadOnly(True)
        self.chat_area.setFont(self.base_font)
        self.chat_area.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )
        self.chat_area.setOpenExternalLinks(True)

        self.chat_area.setStyleSheet(
            f"""
            QTextBrowser {{
                background-color: {self.chat_bg};
                color: {self.cyan_text};
                padding: 16px;
                border: 1px solid #142028;
                border-radius: 12px;
            }}
            """
        )
        right_col.addWidget(self.chat_area, 1)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Введи щось…")
        self.input_field.setFont(QFont(self.ui_font_family, 12))
        self.input_field.setStyleSheet(
            f"""
            QLineEdit {{
                background-color: #121520;
                color: {self.cyan_text};
                padding: 12px 14px;
                border: 1px solid #1b2a33;
                border-radius: 10px;
                selection-background-color: #094a52;
            }}
            QLineEdit:focus {{
                border: 1px solid {self.cyan_text};
            }}
            """
        )
        self.input_field.returnPressed.connect(self.send_message)
        input_row.addWidget(self.input_field, 1)

        self.send_button = QPushButton("▶")
        self.send_button.setToolTip("Надіслати")
        self.send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_button.setFixedSize(44, 38)
        self.send_button.setFont(
            QFont(
                self.ui_font_family,
                11,
                QFont.Weight.Bold,
            )
        )
        self.send_button.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {self.cyan_text};
                color: #001316;
                border: none;
                border-radius: 8px;
                font-weight: 700;
            }}
            QPushButton:hover {{
                background-color: #00cde0;
            }}
            QPushButton:pressed {{
                background-color: #00b6c7;
            }}
            """
        )
        self.send_button.clicked.connect(self.send_message)
        input_row.addWidget(self.send_button)

        right_col.addLayout(input_row)

        right_wrap = QFrame()
        right_wrap.setLayout(right_col)

        root.addWidget(right_wrap, 1)

    # ---------- sidebar builder ----------
    def _build_sidebar(self) -> QFrame:
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(280)
        side.setStyleSheet(
            f"""
            #sidebar {{
                background-color: {self.sidebar_bg};
                border: 1px solid {self.frame_line};
                border-radius: 12px;
            }}
            """
        )

        layout = QVBoxLayout(side)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.big_avatar = QLabel()
        self.big_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.big_avatar.setPixmap(load_avatar_pixmap(240))
        self.big_avatar.setStyleSheet(
            """
            border-radius: 12px;
            border: 1px solid #19313a;
            """
        )
        layout.addWidget(self.big_avatar)

        title = QLabel("SNDI")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont(self.ui_font_family, 26, QFont.Weight.Black))
        title.setStyleSheet(
            f"""
            color: {self.cyan_text};
            letter-spacing: 2px;
            """
        )

        glow = QGraphicsDropShadowEffect()
        glow.setBlurRadius(14)
        glow.setXOffset(0)
        glow.setYOffset(0)
        glow.setColor(QColor(0, 255, 255, 110))
        title.setGraphicsEffect(glow)

        layout.addWidget(title)

        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        status_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.status_dot = QLabel()
        self.status_dot.setFixedSize(12, 12)
        self.status_dot.setStyleSheet(
            """
            border-radius: 6px;
            background: #29fca5;
            """
        )
        if self.tray_status_action is not None:
            self.tray_status_action.setText(f"Status: {status_text}")

        self.status_label = QLabel("online")
        self.status_label.setFont(
            QFont(
                self.ui_font_family,
                11,
                QFont.Weight.DemiBold,
            )
        )
        self.status_label.setStyleSheet("color: #79ffe1;")

        status_row.addWidget(self.status_dot)
        status_row.addWidget(self.status_label)

        status_wrap = QFrame()
        status_wrap.setLayout(status_row)
        layout.addWidget(status_wrap)

        layout.addItem(
            QSpacerItem(
                0,
                0,
                QSizePolicy.Policy.Minimum,
                QSizePolicy.Policy.Expanding,
            )
        )

        return side

    def set_status(self, online: bool, text: str | None = None):
        if not hasattr(self, "status_label"):
            return

        status_text = text if text is not None else ("online" if online else "offline")
        color = "#29fca5" if online else "#ff3b3b"

        self.status_label.setText(status_text)
        self.status_dot.setStyleSheet(
            f"""
            border-radius: 6px;
            background: {color};
            """
        )

    # ---------- system tray ----------
    def _setup_tray(self):
        """
        Create Windows system tray presence for SNDI.

        Stage 4:
        - show/hide/quit works
        - voice/autostart menu items are placeholders for later stages
        """
        if not self.app_settings.get("tray_enabled", True):
            print("[SNDI][TRAY] disabled in app settings")
            return

        if not QSystemTrayIcon.isSystemTrayAvailable():
            print("[SNDI][TRAY] system tray is not available")
            return

        try:
            self.tray_icon = QSystemTrayIcon(self)
            self.tray_icon.setToolTip("SNDI — online")

            icon = QIcon(load_avatar_pixmap(64))

            if icon.isNull():
                icon = self.windowIcon()

            self.tray_icon.setIcon(icon)
            self.setWindowIcon(icon)

            self.tray_menu = QMenu(self)

            show_action = QAction("Show SNDI", self)
            show_action.triggered.connect(self._show_from_tray)

            hide_action = QAction("Hide to tray", self)
            hide_action.triggered.connect(self._hide_to_tray)

            self.tray_listen_once_action = QAction("Listen once", self)
            self.tray_listen_once_action.triggered.connect(self._start_manual_voice_command)

            self.tray_start_voice_action = QAction("Start wake listening", self)
            self.tray_start_voice_action.triggered.connect(self._start_voice_mode)

            self.tray_stop_voice_action = QAction("Stop wake listening", self)
            self.tray_stop_voice_action.triggered.connect(self._stop_voice_mode)

            self.tray_autostart_action = QAction("Toggle autostart", self)
            self.tray_autostart_action.triggered.connect(self._toggle_autostart_from_tray)

            self.tray_status_action = QAction("Status: online", self)
            self.tray_status_action.setEnabled(False)

            quit_action = QAction("Quit", self)
            quit_action.triggered.connect(self._quit_from_tray)

            self.tray_menu.addAction(show_action)
            self.tray_menu.addAction(hide_action)
            self.tray_menu.addSeparator()
            self.tray_menu.addAction(self.tray_listen_once_action)
            self.tray_menu.addAction(self.tray_start_voice_action)
            self.tray_menu.addAction(self.tray_stop_voice_action)
            self.tray_menu.addSeparator()
            self.tray_menu.addAction(self.tray_autostart_action)
            self.tray_menu.addSeparator()
            self.tray_menu.addAction(self.tray_status_action)
            self.tray_menu.addSeparator()
            self.tray_menu.addAction(quit_action)

            self.tray_icon.setContextMenu(self.tray_menu)
            self.tray_icon.activated.connect(self._on_tray_activated)
            self.tray_icon.show()
            self._refresh_tray_autostart_label()
            self._refresh_tray_voice_labels()

            print("[SNDI][TRAY] enabled")

        except Exception as error:
            print("[SNDI][TRAY ERROR]", error)
            self.tray_icon = None
            self.tray_menu = None

    def _on_tray_activated(self, reason):
        """
        Left click / double click on tray icon restores the window.
        """
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._show_from_tray()

    def _show_from_tray(self):
        self.show()
        self.raise_()
        self.activateWindow()
        self.set_status(True, "online")

    def _hide_to_tray(self):
        self.hide()

        if self.tray_icon is not None and not self._tray_notice_shown:
            self.tray_icon.showMessage(
                "SNDI",
                "я в треї. клацни по іконці, щоб повернути вікно.",
                QSystemTrayIcon.MessageIcon.Information,
                2500,
            )
            self._tray_notice_shown = True

    def _quit_from_tray(self):
        self.force_quit = True
        self._shutdown_runtime_threads()

        if self.tray_icon is not None:
            self.tray_icon.hide()

        app = QApplication.instance()

        if app is not None:
            app.quit()

    def _shutdown_runtime_threads(self):
        """
        Stop runtime background loops before real app exit.
        """
        try:
            if self.voice_wake_thread is not None and self.voice_wake_thread.isRunning():
                self.voice_wake_thread.request_stop()
                self.voice_wake_thread.wait(1500)

            self.voice_wake_thread = None

            set_app_setting("voice_enabled", False)
            self.app_settings = load_app_settings()
            self._refresh_tray_voice_labels()

        except Exception as error:
            print("[SNDI][SHUTDOWN THREADS ERROR]", error)

    def _refresh_tray_autostart_label(self):
        if self.tray_autostart_action is None:
            return

        try:
            if is_autostart_enabled():
                self.tray_autostart_action.setText("Disable autostart")
            else:
                self.tray_autostart_action.setText("Enable autostart")

        except Exception as error:
            print("[SNDI][TRAY AUTOSTART STATUS ERROR]", error)
            self.tray_autostart_action.setText("Autostart unavailable")
        
    def _refresh_tray_voice_labels(self):
        voice_enabled = bool(self.app_settings.get("voice_enabled", False))

        if self.tray_listen_once_action is not None:
            self.tray_listen_once_action.setEnabled(not voice_enabled)

        if self.tray_start_voice_action is not None:
            self.tray_start_voice_action.setEnabled(not voice_enabled)

        if self.tray_stop_voice_action is not None:
            self.tray_stop_voice_action.setEnabled(voice_enabled)

    def _toggle_autostart_from_tray(self):
        try:
            if is_autostart_enabled():
                reply = disable_autostart()
                set_app_setting("autostart_enabled", False)
            else:
                reply = enable_autostart()
                set_app_setting("autostart_enabled", True)

            self.app_settings = load_app_settings()
            self._refresh_tray_autostart_label()

            if self.tray_icon is not None:
                self.tray_icon.showMessage(
                    "SNDI",
                    reply,
                    QSystemTrayIcon.MessageIcon.Information,
                    2500,
                )

            self.messages.append(
                {
                    "speaker": "sndi",
                    "text": reply,
                    "typing": False,
                }
            )
            self.render_messages()

        except Exception as error:
            error_text = f"не змогла перемкнути автозапуск: {error}"
            print("[SNDI][AUTOSTART TOGGLE ERROR]", error)

            self.messages.append(
                {
                    "speaker": "sndi",
                    "text": error_text,
                    "typing": False,
                }
            )
            self.render_messages()

    # ---------- voice input ----------
    def _start_voice_mode(self):
        """
        Stage 7: wake word loop.
        SNDI listens for wake word, then listens for the next command.
        """
        if self.voice_wake_thread is not None and self.voice_wake_thread.isRunning():
            self.messages.append(
                {
                    "speaker": "sndi",
                    "text": "я вже слухаю wake word.",
                    "typing": False,
                }
            )
            self.render_messages()
            return

        wake_word = str(self.app_settings.get("voice_wake_word", "сенді") or "сенді")

        wake_words = (
            wake_word,
            "сенді",
            "сенді",
            "сенди",
            "sndi",
            "sandy",
        )

        self.set_status(True, "listening")

        set_app_setting("voice_enabled", True)
        self.app_settings = load_app_settings()
                # voice loop is runtime state; do not trust stale value after app restart
        if self.app_settings.get("voice_enabled", False):
            set_app_setting("voice_enabled", False)
            self.app_settings = load_app_settings()
            self._refresh_tray_voice_labels()

        self.messages.append(
            {
                "speaker": "sndi",
                "text": f"голосовий режим увімкнено. скажи «{wake_word}», потім команду.",
                "typing": False,
            }
        )
        self.render_messages()

        self.voice_wake_thread = VoiceWakeLoopThread(
            wake_words=wake_words,
            language="uk-UA",
        )
        self.voice_wake_thread.status_changed.connect(self._on_voice_status_changed)
        self.voice_wake_thread.wake_detected.connect(self._on_voice_wake_detected)
        self.voice_wake_thread.command_recognized.connect(self._on_voice_command_recognized)
        self.voice_wake_thread.error.connect(self._on_voice_error)
        self.voice_wake_thread.finished.connect(self._on_voice_wake_finished)
        self.voice_wake_thread.start()

    def _stop_voice_mode(self):
        """
        Stop wake word loop.
        """
        set_app_setting("voice_enabled", False)
        self.app_settings = load_app_settings()
        self._refresh_tray_voice_labels()

        if self.voice_wake_thread is not None and self.voice_wake_thread.isRunning():
            self.voice_wake_thread.request_stop()
            self.voice_wake_thread.wait(1500)

        self.voice_wake_thread = None
        self.set_status(True, "voice off")

        self.messages.append(
            {
                "speaker": "sndi",
                "text": "голосовий режим вимкнено.",
                "typing": False,
            }
        )
        self.render_messages()

    def _toggle_voice_mode(self):
        voice_enabled = bool(self.app_settings.get("voice_enabled", False))

        if voice_enabled:
            self._stop_voice_mode()
        else:
            self._start_voice_mode()

    def _on_voice_wake_detected(self, wake_text: str):
        wake_text = (wake_text or "").strip()

        print("[SNDI][WAKE DETECTED]", wake_text)

        self.set_status(True, "wake detected")

        self.messages.append(
            {
                "speaker": "sndi",
                "text": f"я тут. почула wake word: {wake_text}",
                "typing": False,
            }
        )
        self.render_messages()

    def _on_voice_wake_finished(self):
        self.set_status(True, "voice off")
        set_app_setting("voice_enabled", False)
        self.app_settings = load_app_settings()
        self._refresh_tray_voice_labels()

    def _start_manual_voice_command(self):
        """
        Stage 6: one-shot voice command.
        Recognized text goes into the same ActionRouter pipeline.
        """
        if self.voice_once_thread is not None and self.voice_once_thread.isRunning():
            self.messages.append(
                {
                    "speaker": "sndi",
                    "text": "я вже слухаю команду.",
                    "typing": False,
                }
            )
            self.render_messages()
            return

        self.set_status(True, "listening")

        self.messages.append(
            {
                "speaker": "sndi",
                "text": "слухаю одну команду…",
                "typing": False,
            }
        )
        self.render_messages()

        self.voice_once_thread = VoiceListenOnceThread(language="uk-UA")
        self.voice_once_thread.status_changed.connect(self._on_voice_status_changed)
        self.voice_once_thread.recognized.connect(self._on_voice_command_recognized)
        self.voice_once_thread.error.connect(self._on_voice_error)
        self.voice_once_thread.finished.connect(self._on_voice_once_finished)
        self.voice_once_thread.start()

    def _on_voice_status_changed(self, status: str):
        status = (status or "online").strip()

        if status == "listening":
            self.set_status(True, "listening")
        elif status == "recognizing":
            self.set_status(True, "recognizing")
        else:
            self.set_status(True, "online")

    def _on_voice_command_recognized(self, text: str):
        text = (text or "").strip()

        if not text:
            self._on_voice_error("не розчула голосову команду.")
            return

        print("[SNDI][VOICE RECOGNIZED]", text)

        self.messages.append(
            {
                "speaker": "sndi",
                "text": f"почула: {text}",
                "typing": False,
            }
        )
        self.render_messages()

        self.submit_user_text(text, source="voice")

    def _on_voice_error(self, message: str):
        message = (message or "voice input дав збій.").strip()
        print("[SNDI][VOICE ERROR]", message)

        self.set_status(True, "online")

        self.messages.append(
            {
                "speaker": "sndi",
                "text": message,
                "typing": False,
            }
        )
        self.render_messages()

    def _on_voice_once_finished(self):
        self.set_status(True, "online")


    # ---------- dialogs & logs for SystemManager ----------
    def confirm_dialog(self, prompt: str) -> bool:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Підтвердження дії")
        box.setText(prompt)
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        return box.exec() == QMessageBox.StandardButton.Yes

    def append_system_log(self, msg: str):
        self.messages.append(
            {
                "speaker": "sndi",
                "text": f"🛠 {msg}",
                "typing": False,
            }
        )
        self.render_messages()

    # ---------- rendering ----------
    def escape_html(self, text: str) -> str:
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
        )
    
    def linkify_text(self, text: str) -> str:
        """
        Escape plain text and convert URLs into clickable links.
        Supports:
        - https://example.com
        - http://example.com
        - www.example.com
        """
        escaped = self.escape_html(text)

        url_pattern = r"((?:https?://|www\.)[^\s<]+)"

        def repl(match):
            visible_url = match.group(1)

            trailing = ""
            while visible_url and visible_url[-1] in ".,!?;:)":
                trailing = visible_url[-1] + trailing
                visible_url = visible_url[:-1]

            href = visible_url

            if href.startswith("www."):
                href = "https://" + href

            return (
                f'<a href="{href}" '
                f'style="color:#00f0ff; text-decoration:underline;">'
                f"{visible_url}</a>{trailing}"
            )

        return re.sub(url_pattern, repl, escaped)

    def render_markdown(self, text: str) -> str:
        """
        Lightweight markdown/code renderer for QTextBrowser HTML.

        Supports:
        - plain multiline text with clickable URLs
        - fenced code blocks ```python ... ```
        - simple syntax highlighting for Python and JSON
        """

        def highlight_code(code: str, lang: str) -> str:
            escaped = self.escape_html(code)
            lang = (lang or "").lower().strip()

            escaped = re.sub(
                r"(#.*?$)",
                r'<font color="#b3a1ff">\1</font>',
                escaped,
                flags=re.MULTILINE,
            )

            escaped = re.sub(
                r"(&quot;.*?&quot;|&#39;.*?&#39;)",
                r'<font color="#5ffbf1">\1</font>',
                escaped,
            )

            if lang in ("py", "python"):
                keywords = (
                    r"\b(False|None|True|and|as|assert|async|await|break|class|"
                    r"continue|def|del|elif|else|except|finally|for|from|global|"
                    r"if|import|in|is|lambda|nonlocal|not|or|pass|raise|return|"
                    r"try|while|with|yield)\b"
                )

                escaped = re.sub(
                    keywords,
                    r'<font color="#7ee787">\1</font>',
                    escaped,
                )

                builtins = (
                    r"\b(print|len|range|list|dict|set|int|float|str|bool|type|"
                    r"isinstance|enumerate|zip|map|filter|sum|min|max)\b"
                )

                escaped = re.sub(
                    builtins,
                    r'<font color="#5fd4ff">\1</font>',
                    escaped,
                )

                escaped = re.sub(
                    r"\b(\d+(\.\d+)?)\b",
                    r'<font color="#ff89a5">\1</font>',
                    escaped,
                )

            elif lang == "json":
                escaped = re.sub(
                    r"(&quot;[^&]+?&quot;\s*:)",
                    r'<font color="#7ee787">\1</font>',
                    escaped,
                )

                escaped = re.sub(
                    r"\b(true|false|null)\b",
                    r'<font color="#ff89a5">\1</font>',
                    escaped,
                )

            else:
                escaped = re.sub(
                    r"\b(\d+(\.\d+)?)\b",
                    r'<font color="#ff89a5">\1</font>',
                    escaped,
                )

            return (
                '<table width="100%" cellspacing="0" cellpadding="8" '
                'bgcolor="#0f1117">'
                "<tr>"
                "<td>"
                '<pre style="'
                "white-space: pre-wrap; "
                "font-family: Consolas, 'Courier New', monospace; "
                "font-size: 13px; "
                "line-height: 1.35; "
                'margin: 0;">'
                f"{escaped}"
                "</pre>"
                "</td>"
                "</tr>"
                "</table>"
            )

        parts = []
        position = 0
        pattern = re.compile(r"```(\w+)?\n(.*?)```", re.DOTALL)

        for match in pattern.finditer(text):
            normal_text = text[position:match.start()]

            if normal_text:
                safe_text = self.linkify_text(normal_text)
                parts.append(
                    '<span style="white-space: pre-wrap;">'
                    f"{safe_text}"
                    "</span>"
                )

            lang = match.group(1) or ""
            code = match.group(2)
            parts.append(highlight_code(code, lang))

            position = match.end()

        tail = text[position:]

        if tail:
            safe_tail = self.linkify_text(tail)
            parts.append(
                '<span style="white-space: pre-wrap;">'
                f"{safe_tail}"
                "</span>"
            )

        return "".join(parts)

    def bubble_html(self, is_user: bool, name_html: str, body_html: str) -> str:
        left_bg = self.sndi_bubble_fill
        right_bg = self.user_bubble_fill

        def cell(background_fill: str) -> str:
            return (
                '<table cellspacing="0" cellpadding="0" '
                f'style="border:1px solid {self.frame_line};" '
                f'bgcolor="{background_fill}">'
                "<tr>"
                '<td style="padding:10px 14px;">'
                f'<div style="'
                f"font-family:{self.ui_font_family}; "
                "font-weight:700; "
                "font-size:13px; "
                f"color:{self.name_red}; "
                'margin-bottom:4px;">'
                f"{name_html}"
                "</div>"
                f'<div style="'
                f"color:{self.cyan_text}; "
                f"font-family:{self.ui_font_family}; "
                "font-size:15px; "
                'line-height:1.35;">'
                f"{body_html}"
                "</div>"
                "</td>"
                "</tr>"
                "</table>"
            )

        if is_user:
            return (
                '<table width="100%" cellspacing="0" cellpadding="6">'
                "<tr>"
                '<td width="24%"></td>'
                f'<td align="right">{cell(right_bg)}</td>'
                "</tr>"
                "</table>"
            )

        return (
            '<table width="100%" cellspacing="0" cellpadding="6">'
            "<tr>"
            f'<td align="left">{cell(left_bg)}</td>'
            '<td width="24%"></td>'
            "</tr>"
            "</table>"
        )

    def render_messages(self):
        html_parts = []

        for msg in self.messages:
            is_user = msg["speaker"] == "user"
            name = "Ти" if is_user else "SNDI"
            body_html = self.render_markdown(msg["text"])
            html_parts.append(
                self.bubble_html(
                    is_user=is_user,
                    name_html=name,
                    body_html=body_html,
                )
            )

        self.chat_area.setHtml("".join(html_parts))
        self.chat_area.moveCursor(QTextCursor.MoveOperation.End)

    def _append_sndi_message(self, text: str):
        self.messages.append(
            {
                "speaker": "sndi",
                "text": text,
                "typing": False,
            }
        )
        self.render_messages()

    def _handle_confirmation_intent(self, user_text: str) -> bool:
        """
        Handle confirm/cancel only when there is a pending action.

        Returns True when the user_text was consumed by confirmation flow.
        """
        if not self.confirmation_manager.has_any_pending_action():
            return False

        if not is_confirmation_text(user_text) and not is_cancel_text(user_text):
            return False

        expired_action = self.confirmation_manager.pop_expired_pending_action()

        if expired_action is not None:
            append_action_log(
                action=expired_action.action,
                status="cancelled",
                target=expired_action.target,
                user_text=user_text,
                preview=expired_action.preview,
                error="pending action expired",
                metadata={"pending_id": expired_action.id},
            )
            self._append_sndi_message(format_pending_action_expired_message())
            return True

        if is_cancel_text(user_text):
            pending_action = self.confirmation_manager.cancel_pending_action()

            append_action_log(
                action=pending_action.action if pending_action else "unknown_pending_action",
                status="cancelled",
                target=pending_action.target if pending_action else None,
                user_text=user_text,
                preview=pending_action.preview if pending_action else {},
                metadata={
                    "pending_id": pending_action.id if pending_action else None,
                    "reason": "user_cancelled",
                },
            )

            self._append_sndi_message(
                format_pending_action_cancelled_message(pending_action)
            )
            return True

        if is_confirmation_text(user_text):
            pending_action = self.confirmation_manager.confirm_pending_action()

            if pending_action is None:
                append_action_log(
                    action="confirm_pending_action",
                    status="failed",
                    target=None,
                    user_text=user_text,
                    error="no active pending action",
                )
                self._append_sndi_message(format_no_pending_action_message())
                return True

            append_action_log(
                action=pending_action.action,
                status="confirmed",
                target=pending_action.target,
                user_text=user_text,
                preview=pending_action.preview,
                metadata={"pending_id": pending_action.id},
            )

            reply = self._execute_confirmed_pending_action(pending_action)
            self._append_sndi_message(reply)
            return True

        return False

    def _create_pending_action_from_preview(
        self,
        preview,
        params: dict | None = None,
        user_text: str = "",
    ):
        """
        Create pending action from FileOpPreview-like object.

        Stage 10:
        - creates pending action;
        - writes requested event to action log;
        - shows confirmation message;
        - does not execute anything yet.
        """
        pending_action = self.confirmation_manager.create_pending_action(
            action=preview.action,
            target=preview.target,
            params=params or {},
            preview=preview.preview,
            risk_level=preview.risk_level,
            user_text=user_text,
        )

        append_action_log(
            action=pending_action.action,
            status="requested",
            target=pending_action.target,
            user_text=user_text,
            preview=pending_action.preview,
            metadata={"pending_id": pending_action.id},
        )

        self._append_sndi_message(format_pending_action_message(pending_action))
        return pending_action

    def _execute_confirmed_pending_action(self, pending_action: PendingAction) -> str:
        """
        Stage 10 placeholder.

        Real mutation execution will be connected in Stage 12.
        For now this confirms safely and changes nothing.
        """
        append_action_log(
            action=pending_action.action,
            status="failed",
            target=pending_action.target,
            user_text=pending_action.user_text,
            preview=pending_action.preview,
            error="executor_not_connected_yet_stage_10",
            metadata={"pending_id": pending_action.id},
        )

        return (
            "підтвердження прийнято, але executor ще не підключений.\n"
            "На цьому stage нічого не змінено. Реальне виконання буде на Stage 12."
        )

    # ---------- events ----------
    def send_message(self):
        user_text = self.input_field.text().strip()
        self.submit_user_text(user_text, source="keyboard")

    def submit_user_text(self, user_text: str, source: str = "keyboard"):
        """
        Unified user input pipeline for SNDI.

        source:
        - keyboard: text came from input field
        - voice: text came from voice recognition
        - system: text came from internal trigger/future tools
        """
        user_text = (user_text or "").strip()

        if not user_text:
            return

        if source == "keyboard":
            self.input_field.clear()

        self.sound_manager.play_send()

        display_text = user_text

        if source == "voice":
            display_text = f"🎙 {user_text}"

        self.messages.append(
            {
                "speaker": "user",
                "text": display_text,
                "typing": False,
            }
        )
        self.render_messages()

        plan = decide_action(user_text)
        print("[SNDI][ACTION ROUTER]", plan)

        if plan.action == "screen_scan":
            self._start_scan(user_text)
            return

        if plan.action == "system_action":
            self._start_system_or_web_or_normal(user_text)
            return

        if plan.action == "web_search":
            self._start_web_or_normal(user_text)
            return

        if plan.action == "project_awareness":
            self._start_project_awareness(user_text)
            return
        
        if plan.action == "voice_once":
            self._start_manual_voice_command()
            return
        
        if plan.action == "voice_start":
            self._start_voice_mode()
            return

        if plan.action == "voice_stop":
            self._stop_voice_mode()
            return

        if plan.action == "voice_toggle":
            self._toggle_voice_mode()
            return
        
        if plan.action == "tray_hide":
            reply = "ховаюсь у трей."
            self.messages.append(
                {
                    "speaker": "sndi",
                    "text": reply,
                    "typing": False,
                }
            )
            self.render_messages()

            if self._handle_confirmation_intent(user_text):
                return
            
            self._hide_to_tray()
            return

        if plan.action == "tray_show":
            self._show_from_tray()
            reply = "я тут."
            self.messages.append(
                {
                    "speaker": "sndi",
                    "text": reply,
                    "typing": False,
                }
            )
            self.render_messages()
            return
        
        if plan.action == "voice_reply_enable":
            set_app_setting("voice_reply_enabled", True)
            self.app_settings = load_app_settings()

            reply = "озвучку відповідей увімкнено."
            self.messages.append(
                {
                    "speaker": "sndi",
                    "text": reply,
                    "typing": False,
                }
            )
            self.render_messages()
            self._maybe_speak_reply(reply)
            return

        if plan.action == "voice_reply_disable":
            set_app_setting("voice_reply_enabled", False)
            self.app_settings = load_app_settings()

            reply = "озвучку відповідей вимкнено."
            self.messages.append(
                {
                    "speaker": "sndi",
                    "text": reply,
                    "typing": False,
                }
            )
            self.render_messages()
            return

        if plan.action == "voice_reply_status":
            enabled = bool(self.app_settings.get("voice_reply_enabled", False))
            reply = "озвучка відповідей увімкнена." if enabled else "озвучка відповідей вимкнена."

            self.messages.append(
                {
                    "speaker": "sndi",
                    "text": reply,
                    "typing": False,
                }
            )
            self.render_messages()

            if enabled:
                self._maybe_speak_reply(reply)

            return
    
        if plan.action == "autostart_enable":
            reply = enable_autostart()
            set_app_setting("autostart_enabled", True)
            self.app_settings = load_app_settings()
            self._refresh_tray_autostart_label()

            self.messages.append(
                {
                    "speaker": "sndi",
                    "text": reply,
                    "typing": False,
                }
            )
            self.render_messages()
            return

        if plan.action == "autostart_disable":
            reply = disable_autostart()
            set_app_setting("autostart_enabled", False)
            self.app_settings = load_app_settings()
            self._refresh_tray_autostart_label()

            self.messages.append(
                {
                    "speaker": "sndi",
                    "text": reply,
                    "typing": False,
                }
            )
            self.render_messages()
            return

        if plan.action == "autostart_status":
            reply = get_autostart_status()
            set_app_setting("autostart_enabled", is_autostart_enabled())
            self.app_settings = load_app_settings()
            self._refresh_tray_autostart_label()

            self.messages.append(
                {
                    "speaker": "sndi",
                    "text": reply,
                    "typing": False,
                }
            )
            self.render_messages()
            return

        if plan.action == "clipboard_explain":
            clipboard_text = get_clipboard_text()

            if not clipboard_text:
                self.messages.append(
                    {
                        "speaker": "sndi",
                        "text": "буфер обміну порожній або там немає тексту.",
                        "typing": False,
                    }
                )
                self.render_messages()
                return

            enriched_prompt = (
                "Режим: clipboard_explain\n"
                "Користувач просить пояснити текст із буфера обміну.\n\n"
                f"Запит користувача:\n{user_text}\n\n"
                f"Буфер обміну:\n{clipboard_text}\n\n"
                "Відповідай українською, коротко і практично. "
                "Поясни суть, важливі деталі і що з цим робити далі."
            )

            self._start_normal_response(enriched_prompt)
            return

        if plan.action == "error_explain":
            clipboard_text = get_clipboard_text()

            error_markers = (
                "traceback",
                "error",
                "exception",
                "nameerror",
                "typeerror",
                "attributeerror",
                "importerror",
                "modulenotfounderror",
                "syntaxerror",
                "badrequesterror",
                "filenotfounderror",
            )

            user_has_error_text = any(
                marker in user_text.lower()
                for marker in error_markers
            )

            source_text = user_text if user_has_error_text else clipboard_text

            if not source_text.strip():
                self.messages.append(
                    {
                        "speaker": "sndi",
                        "text": "не бачу тексту помилки. скопіюй traceback або встав його в повідомлення.",
                        "typing": False,
                    }
                )
                self.render_messages()
                return

            enriched_prompt = (
                "Режим: error_explain\n"
                "Користувач просить пояснити технічну помилку.\n\n"
                f"Запит користувача:\n{user_text}\n\n"
                f"Текст помилки або traceback:\n{source_text}\n\n"
                "Відповідай українською. "
                "Поясни коротко:\n"
                "1. що це за помилка;\n"
                "2. найімовірніша причина;\n"
                "3. де саме шукати проблему;\n"
                "4. що зробити для фіксу.\n"
                "Не роздувай відповідь. Дай практичні кроки."
            )

            self._start_normal_response(enriched_prompt)
            return

        if plan.action == "code_review":
            clipboard_text = get_clipboard_text()

            code_markers = (
                "def ",
                "class ",
                "import ",
                "from ",
                "return ",
                "if ",
                "for ",
                "while ",
                "try:",
                "except",
                "{",
                "}",
                "function ",
                "const ",
                "let ",
                "var ",
            )

            user_has_code = any(
                marker in user_text
                for marker in code_markers
            )

            source_code = user_text if user_has_code else clipboard_text

            if not source_code.strip():
                self.messages.append(
                    {
                        "speaker": "sndi",
                        "text": "не бачу коду. скопіюй код у буфер або встав його в повідомлення.",
                        "typing": False,
                    }
                )
                self.render_messages()
                return

            enriched_prompt = (
                "Режим: code_review\n"
                "Користувач просить перевірити код.\n\n"
                f"Запит користувача:\n{user_text}\n\n"
                f"Код для ревʼю:\n{source_code}\n\n"
                "Відповідай українською. "
                "Зроби практичне ревʼю коду:\n"
                "1. коротко що робить код;\n"
                "2. потенційні баги;\n"
                "3. слабкі місця або ризики;\n"
                "4. що покращити;\n"
                "5. якщо є явний фікс — покажи маленький фрагмент, не переписуй усе без потреби.\n"
                "Не роздувай відповідь. Дай конкретику."
            )

            self._start_normal_response(enriched_prompt)
            return

        reply = execute_action(plan, user_text)

        if reply:
            self.messages.append(
                {
                    "speaker": "sndi",
                    "text": reply,
                    "typing": False,
                }
            )
            self.render_messages()
            return

        self._start_normal_response(user_text)

    # ---------- screen scan ----------
    def _start_scan(self, user_text: str):
        """
        Hide SNDI window before screenshot so the chat does not cover the screen.
        Then capture screen and restore the window.
        """
        self.set_status(True, "scanning")

        self.messages.append(
            {
                "speaker": "sndi",
                "text": "зникаю з екрана на секунду…",
                "typing": True,
            }
        )

        self.dot_phase = 0
        self.streaming_text = None
        self.streaming_index = 0

        self.timer.start(450)
        self.render_messages()

        self.hide()

        QTimer.singleShot(350, lambda: self._capture_after_hide(user_text))

    def _capture_after_hide(self, user_text: str):
        try:
            screenshot_path = capture_screen()
        except Exception as error:
            print("[SNDI][SCREEN CAPTURE ERROR]", error)

            self.show()
            self.raise_()
            self.activateWindow()
            self.set_status(True, "online")

            if self.messages and self.messages[-1]["speaker"] == "sndi":
                self.messages[-1]["text"] = f"⚡ не змогла зробити скрін: {error}"
                self.messages[-1]["typing"] = False
            else:
                self.messages.append(
                    {
                        "speaker": "sndi",
                        "text": f"⚡ не змогла зробити скрін: {error}",
                        "typing": False,
                    }
                )

            self.render_messages()
            return

        self.show()
        self.raise_()
        self.activateWindow()

        if self.messages and self.messages[-1]["speaker"] == "sndi":
            self.messages[-1]["text"] = "сканую екран…"
            self.messages[-1]["typing"] = True
        else:
            self.messages.append(
                {
                    "speaker": "sndi",
                    "text": "сканую екран…",
                    "typing": True,
                }
            )

        self.dot_phase = 0
        self.streaming_text = None
        self.streaming_index = 0

        self.timer.start(450)
        self.render_messages()

        self.scan_thread = ScanThread(screenshot_path, user_text)
        self.scan_thread.finished.connect(self._receive_scan_reply)
        self.scan_thread.start()



    def _receive_scan_reply(self, reply: str):
        self.sound_manager.play_message()
        self.set_status(True, "online")

        if not reply or not reply.strip():
            reply = "глухий канал. нічого не бачу."

        self._maybe_speak_reply(reply)

        if not self.messages or self.messages[-1]["speaker"] != "sndi":
            self.messages.append(
                {
                    "speaker": "sndi",
                    "text": "",
                    "typing": True,
                }
            )

        self.streaming_text = reply
        self.streaming_index = 0
        self.timer.start(12)


    def receive_reply(self, reply: str):
        self.sound_manager.play_message()

        if not reply or not reply.strip():
            reply = "шум глушить канал. повтори."

        self._maybe_speak_reply(reply)

        if not self.messages or self.messages[-1]["speaker"] != "sndi":
            self.messages.append(
                {
                    "speaker": "sndi",
                    "text": "",
                    "typing": True,
                }
            )

        self.streaming_text = reply
        self.streaming_index = 0
        self.timer.start(12)

    # ---------- local project awareness ----------
    def _start_project_awareness(self, user_text: str):
        """
        Build local project snapshot and let SNDI reason about it.
        Read-only. No file modifications.
        """
        self.set_status(True, "scanning")

        self.messages.append(
            {
                "speaker": "sndi",
                "text": "підключаюсь до локального проєкту…",
                "typing": True,
            }
        )

        self.dot_phase = 0
        self.streaming_text = None
        self.streaming_index = 0

        self.timer.start(450)
        self.render_messages()

        self.project_thread = ProjectThread(user_text)
        self.project_thread.finished.connect(
            lambda reply: self._receive_project_awareness_reply(user_text, reply)
        )
        self.project_thread.start()

    # ---------- normal response ----------
    def _start_normal_response(self, user_text: str):
        self.set_status(True, "thinking")

        self.messages.append(
            {
                "speaker": "sndi",
                "text": "",
                "typing": True,
            }
        )

        self.dot_phase = 0
        self.streaming_text = None
        self.streaming_index = 0

        self.timer.start(450)
        self.render_messages()

        self.response_thread = ResponseThread(user_text)
        self.response_thread.finished.connect(self.receive_reply)
        self.response_thread.start()

        # ---------- system control ----------
    def _start_system_or_web_or_normal(self, user_text: str):
        """
        First let SNDI decide whether this is a local system action.
        If not — continue to web-or-normal flow.
        """
        self.set_status(True, "thinking")

        self.messages.append(
            {
                "speaker": "sndi",
                "text": "зчитую системний намір…",
                "typing": True,
            }
        )

        self.dot_phase = 0
        self.streaming_text = None
        self.streaming_index = 0

        self.timer.start(450)
        self.render_messages()

        self.system_action_thread = SystemActionThread(user_text)
        self.system_action_thread.finished.connect(
            lambda reply: self._receive_system_or_continue_reply(user_text, reply)
        )
        self.system_action_thread.start()

    def _receive_system_or_continue_reply(self, user_text: str, reply: str):
        if reply == "__NO_SYSTEM_ACTION__":
            if self.messages and self.messages[-1]["speaker"] == "sndi":
                self.messages.pop()

            self._start_web_or_normal(user_text)
            return

        self.sound_manager.play_message()
        self.set_status(True, "online")

        if not reply or not reply.strip():
            reply = "системна дія не дала відповіді."

        self._maybe_speak_reply(reply)

        try:
            append_history(user_text, reply)
        except Exception as error:
            print("[SNDI][SYSTEM ACTION HISTORY ERROR]", error)

        if not self.messages or self.messages[-1]["speaker"] != "sndi":
            self.messages.append(
                {
                    "speaker": "sndi",
                    "text": "",
                    "typing": True,
                }
            )

        self.streaming_text = reply
        self.streaming_index = 0
        self.timer.start(12)

        
    # ---------- internet awareness ----------
    def _start_web_or_normal(self, user_text: str):
        """
        Let SNDI decide whether this request needs internet.
        If yes — use web_search.
        If no — continue normal chat flow.
        """
        self.set_status(True, "thinking")

        self.messages.append(
            {
                "speaker": "sndi",
                "text": "оцінюю, чи треба виходити в мережу…",
                "typing": True,
            }
        )

        self.dot_phase = 0
        self.streaming_text = None
        self.streaming_index = 0

        self.timer.start(450)
        self.render_messages()

        self.web_thread = WebThread(user_text)
        self.web_thread.finished.connect(
            lambda reply: self._receive_web_or_normal_reply(user_text, reply)
        )
        self.web_thread.start()

    def _receive_web_or_normal_reply(self, user_text: str, reply: str):
        if reply == "__NO_WEB_NEEDED__":
            if self.messages and self.messages[-1]["speaker"] == "sndi":
                self.messages.pop()

            if is_project_awareness_intent(user_text):
                self._start_project_awareness(user_text)
            else:
                self._start_normal_response(user_text)

            return

        self.sound_manager.play_message()
        self.set_status(True, "online")

        if not reply or not reply.strip():
            reply = "web sensor мовчить. інтернет ніби є, але відповідь не зібралась."

        self._maybe_speak_reply(reply)

        try:
            append_history(user_text, reply)
        except Exception as error:
            print("[SNDI][WEB HISTORY ERROR]", error)

        if not self.messages or self.messages[-1]["speaker"] != "sndi":
            self.messages.append(
                {
                    "speaker": "sndi",
                    "text": "",
                    "typing": True,
                }
            )

        self.streaming_text = reply
        self.streaming_index = 0
        self.timer.start(12)

    def _receive_project_awareness_reply(self, user_text: str, reply: str):
        self.sound_manager.play_message()
        self.set_status(True, "online")

        if not reply or not reply.strip():
            reply = "я бачу проєкт, але відповідь не зібралась. щось глухне на каналі."

        self._maybe_speak_reply(reply)

        try:
            append_history(user_text, reply)
        except Exception as error:
            print("[SNDI][PROJECT HISTORY ERROR]", error)

        if not self.messages or self.messages[-1]["speaker"] != "sndi":
            self.messages.append(
                {
                    "speaker": "sndi",
                    "text": "",
                    "typing": True,
                }
            )

        self.streaming_text = reply
        self.streaming_index = 0
        self.timer.start(12)

    def _on_timer(self):
        if not self.messages:
            return

        if self.streaming_text is None:
            dots = "." * ((self.dot_phase % 3) + 1)
            self.dot_phase += 1

            self.messages[-1]["text"] = f"друкує{dots}"
            self.render_messages()
            return

        if self.streaming_index <= len(self.streaming_text):
            visible = self.streaming_text[: self.streaming_index]
            self.messages[-1]["text"] = visible
            self.render_messages()
            self.streaming_index += 1
            return

        self.messages[-1]["typing"] = False
        self.timer.stop()

    def closeEvent(self, event):
        """
        If minimize_to_tray is enabled, closing the window hides it to tray.
        Real exit is available from tray menu: Quit.
        """
        minimize_to_tray = self.app_settings.get("minimize_to_tray", True)

        if (
            not self.force_quit
            and minimize_to_tray
            and self.tray_icon is not None
            and self.tray_icon.isVisible()
        ):
            event.ignore()
            self._hide_to_tray()
            return
        
        self._shutdown_runtime_threads()
        event.accept()

    def start_voice_input(self):
        """
        Старий voice-input режим. Залишаємо як fallback.
        Повноцінний Voice Companion будемо робити пізніше окремим модулем.
        """
        if sr is None:
            self.messages.append(
                {
                    "speaker": "sndi",
                    "text": "модуль speech_recognition не встановлений.",
                    "typing": False,
                }
            )
            self.render_messages()
            return

        recognizer = sr.Recognizer()

        try:
            with sr.Microphone() as source:
                self.messages.append(
                    {
                        "speaker": "sndi",
                        "text": "слухаю.",
                        "typing": False,
                    }
                )
                self.render_messages()
                audio = recognizer.listen(source)

            user_input = recognizer.recognize_google(audio, language="uk-UA")
            self.input_field.setText(user_input)
            self.send_message()

        except sr.UnknownValueError:
            self.messages.append(
                {
                    "speaker": "sndi",
                    "text": "не розчула. повтори.",
                    "typing": False,
                }
            )
            self.render_messages()

        except sr.RequestError:
            self.messages.append(
                {
                    "speaker": "sndi",
                    "text": "глюк сервера розпізнавання.",
                    "typing": False,
                }
            )
            self.render_messages()

        except Exception as error:
            print("[SNDI][VOICE ERROR]", error)
            self.messages.append(
                {
                    "speaker": "sndi",
                    "text": "голосовий модуль дав збій.",
                    "typing": False,
                }
            )
            self.render_messages()

    def _maybe_speak_reply(self, reply: str):
        """
        Speak SNDI reply only if voice_reply_enabled is true.
        This is optional and must never break chat.
        """
        if not self.app_settings.get("voice_reply_enabled", False):
            return

        if not reply or not reply.strip():
            return

        if self.voice_reply_thread is not None and self.voice_reply_thread.isRunning():
            print("[SNDI][TTS] skipped: previous voice reply still playing")
            return

        self.voice_reply_thread = VoiceReplyThread(reply)
        self.voice_reply_thread.status_changed.connect(self._on_voice_status_changed)
        self.voice_reply_thread.error.connect(self._on_voice_reply_error)
        self.voice_reply_thread.start()

    def _on_voice_reply_error(self, message: str):
        message = (message or "озвучка дала збій.").strip()
        print("[SNDI][TTS ERROR]", message)

        self.set_status(True, "online")

        self.messages.append(
            {
                "speaker": "sndi",
                "text": message,
                "typing": False,
            }
        )
        self.render_messages()

# ---------- app ----------
def main():
    app = QApplication(sys.argv)

    _ = load_cyberpunk_font()

    window = ChatWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()