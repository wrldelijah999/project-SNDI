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
    QTextEdit,
    QLineEdit,
    QPushButton,
    QLabel,
    QFrame,
    QSizePolicy,
    QGraphicsDropShadowEffect,
    QSpacerItem,
    QMessageBox,
)

from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import (
    QFont,
    QFontDatabase,
    QPixmap,
    QColor,
    QPainter,
    QLinearGradient,
    QBrush,
    QTextCursor,
)

from sndi.core.conversation_core import ask
from sndi.storage import resource_path
from sndi.system_manager import SystemManager

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
        self.streaming_text: str | None = None
        self.streaming_index = 0
        self.dot_phase = 0

        self.timer = QTimer()
        self.timer.timeout.connect(self._on_timer)

        # SystemManager only at GUI level
        self.system_mgr = SystemManager(
            confirm_cb=self.confirm_dialog,
            log_cb=self.append_system_log,
        )

        self._build_ui()

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

        self.chat_area = QTextEdit(readOnly=True)
        self.chat_area.setFont(self.base_font)
        self.chat_area.setStyleSheet(
            f"""
            QTextEdit {{
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

    def render_markdown(self, text: str) -> str:
        """
        Lightweight markdown/code renderer for QTextEdit HTML.

        Supports:
        - plain multiline text
        - fenced code blocks ```python ... ```
        - simple syntax highlighting for Python and JSON
        """

        def highlight_code(code: str, lang: str) -> str:
            escaped = self.escape_html(code)
            lang = (lang or "").lower().strip()

            # comments
            escaped = re.sub(
                r"(#.*?$)",
                r'<font color="#b3a1ff">\1</font>',
                escaped,
                flags=re.MULTILINE,
            )

            # strings
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
            normal_text = text[position : match.start()]

            if normal_text:
                parts.append(
                    '<span style="white-space: pre-wrap;">'
                    f"{self.escape_html(normal_text)}"
                    "</span>"
                )

            lang = match.group(1) or ""
            code = match.group(2)
            parts.append(highlight_code(code, lang))

            position = match.end()

        tail = text[position:]

        if tail:
            parts.append(
                '<span style="white-space: pre-wrap;">'
                f"{self.escape_html(tail)}"
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

    # ---------- events ----------
    def send_message(self):
        user_text = self.input_field.text().strip()

        if not user_text:
            return

        self.sound_manager.play_send()

        self.messages.append(
            {
                "speaker": "user",
                "text": user_text,
                "typing": False,
            }
        )

        handled, response = self.system_mgr.dispatch(user_text)

        if handled:
            self.messages.append(
                {
                    "speaker": "sndi",
                    "text": response,
                    "typing": False,
                }
            )
            self.render_messages()
            self.input_field.clear()
            return

        self.messages.append(
            {
                "speaker": "sndi",
                "text": "друкує…",
                "typing": True,
            }
        )

        self.dot_phase = 0
        self.streaming_text = None
        self.streaming_index = 0

        self.timer.start(450)
        self.render_messages()
        self.input_field.clear()

        self.response_thread = ResponseThread(user_text)
        self.response_thread.finished.connect(self.receive_reply)
        self.response_thread.start()

    def receive_reply(self, reply: str):
        self.sound_manager.play_message()

        if not reply or not reply.strip():
            reply = "шум глушить канал. повтори."

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


# ---------- app ----------
def main():
    app = QApplication(sys.argv)

    _ = load_cyberpunk_font()

    window = ChatWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()