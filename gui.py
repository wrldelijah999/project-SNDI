import sys, os, re, math, random
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit,
    QPushButton, QLabel, QFrame, QSizePolicy, QGraphicsDropShadowEffect, QSpacerItem
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QFont, QFontDatabase, QPixmap, QColor, QPainter, QLinearGradient, QBrush
from main import sndi
import pygame
import speech_recognition as sr
from sndi.storage import resource_path 


# ---------- helpers: fonts ----------
def load_cyberpunk_font():
    candidates = [
        "assets/fonts/Rajdhani-Regular.ttf",
        "assets/fonts/Orbitron-Regular.ttf",
        "assets/fonts/Audiowide-Regular.ttf",
        "assets/fonts/ShareTechMono-Regular.ttf",
    ]
    loaded_family = None
    for rel in candidates:
        path = resource_path(rel)  # <— ЗАМІНА
        if os.path.exists(path):
            fid = QFontDatabase.addApplicationFont(path)
            if fid != -1:
                families = QFontDatabase.applicationFontFamilies(fid)
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
        p = resource_path(rel)  # <— ЗАМІНА
        if os.path.exists(p):
            pix = QPixmap(p)
            break
    if pix.isNull():
        pix = QPixmap(target_h, target_h)
        pix.fill(Qt.GlobalColor.black)
    if target_h:
        pix = pix.scaledToHeight(target_h, Qt.TransformationMode.SmoothTransformation)
    return pix

# ---------- async ----------
class ResponseThread(QThread):
    finished = pyqtSignal(str)
    def __init__(self, user_text: str):
        super().__init__()
        self.user_text = user_text
    def run(self):
        reply = sndi(self.user_text)
        self.finished.emit(reply)

# ---------- widget: NeonBar ----------
class NeonBar(QWidget):
    """Thin neon bar with gentle flicker (no extra libs/models needed)."""
    def __init__(self, color: QColor | None = None, height: int = 8, radius: int = 4, parent=None):
        super().__init__(parent)
        self.base_color = color or QColor(0, 255, 255)
        self.radius = radius
        self.setFixedHeight(height)
        self._t = 0.0
        self._intensity = 0.75
        self._target = 0.85
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(30)  # ~33 FPS

    def _tick(self):
        # smooth breathing
        self._t += 0.03
        breath = 0.08 * math.sin(self._t)
        # sporadic flickers
        if random.random() < 0.04:
            self._target = 0.65 + random.random() * 0.35  # 0.65..1.0
        # ease toward target
        self._intensity += (self._target - self._intensity) * 0.12
        self._intensity = max(0.5, min(1.0, self._intensity + breath))
        self.update()

    def paintEvent(self, e):
        w, h = self.width(), self.height()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # gradient core brightness
        alpha_core = int(255 * self._intensity)
        alpha_edge = int(alpha_core * 0.28)
        grad = QLinearGradient(0, 0, w, 0)
        c = QColor(self.base_color)
        c1 = QColor(c.red(), c.green(), c.blue(), 0)
        c2 = QColor(c.red(), c.green(), c.blue(), alpha_edge)
        c3 = QColor(c.red(), c.green(), c.blue(), alpha_core)
        grad.setColorAt(0.00, c1)
        grad.setColorAt(0.14, c2)
        grad.setColorAt(0.50, c3)
        grad.setColorAt(0.86, c2)
        grad.setColorAt(1.00, c1)
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, w, h, self.radius, self.radius)

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

        # root layout: sidebar | conversation
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)
        self.setStyleSheet(f"background-color: {self.theme_bg}; color: {self.cyan_text};")

        # left sidebar
        self.sidebar = self._build_sidebar()
        root.addWidget(self.sidebar)

        # right column
        right_col = QVBoxLayout()
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(10)

        # animated neon bar (replaces static line)
        right_col.addWidget(NeonBar(QColor(0, 255, 240), height=8, radius=4))

        # chat area
        self.chat_area = QTextEdit(readOnly=True)
        self.chat_area.setFont(self.base_font)
        self.chat_area.setStyleSheet(f"""
            QTextEdit {{
                background-color: {self.chat_bg};
                color: {self.cyan_text};
                padding: 16px;
                border: 1px solid #142028;
                border-radius: 12px;
            }}
        """)
        right_col.addWidget(self.chat_area, 1)

        # input row
        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self.input_field = QLineEdit(placeholderText="Введи щось…")
        self.input_field.setFont(QFont(self.ui_font_family, 12))
        self.input_field.setStyleSheet(f"""
            QLineEdit {{
                background-color: #121520;
                color: {self.cyan_text};
                padding: 12px 14px;
                border: 1px solid #1b2a33;
                border-radius: 10px;
                selection-background-color: #094a52;
            }}
            QLineEdit:focus {{ border: 1px solid {self.cyan_text}; }}
        """)
        self.input_field.returnPressed.connect(self.send_message)
        input_row.addWidget(self.input_field, 1)

        self.send_button = QPushButton("▶")
        self.send_button.setToolTip("Надіслати")
        self.send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_button.setFixedSize(44, 38)
        self.send_button.setFont(QFont(self.ui_font_family, 11, QFont.Weight.Bold))
        self.send_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.cyan_text};
                color: #001316;
                border: none;
                border-radius: 8px;
                font-weight: 700;
            }}
            QPushButton:hover  {{ background-color: #00cde0; }}
            QPushButton:pressed{{ background-color: #00b6c7; }}
        """)
        self.send_button.clicked.connect(self.send_message)
        input_row.addWidget(self.send_button)

        right_col.addLayout(input_row)

        right_wrap = QFrame()
        right_wrap.setLayout(right_col)
        root.addWidget(right_wrap, 1)

        # state
        self.messages = []
        self.response_thread = None
        self.timer = QTimer()
        self.timer.timeout.connect(self._on_timer)
        self.streaming_text = None
        self.streaming_index = 0
        self.dot_phase = 0

        pygame.mixer.init()
        self.message_sound = pygame.mixer.Sound(resource_path("assets/audio/cyberpunk_message.wav"))
        self.send_sound = pygame.mixer.Sound(resource_path("assets/audio/send_sound.mp3"))

    # ---------- sidebar builder ----------
    def _build_sidebar(self) -> QFrame:
        side = QFrame()
        side.setObjectName("sidebar")
        side.setStyleSheet(
            f"#sidebar {{ background-color: #0c0e15; border: 1px solid {self.frame_line}; border-radius: 12px; }}"
        )
        side.setFixedWidth(280)
        v = QVBoxLayout(side)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(10)

        self.big_avatar = QLabel()
        self.big_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.big_avatar.setPixmap(load_avatar_pixmap(240))
        self.big_avatar.setStyleSheet("border-radius: 12px; border: 1px solid #19313a;")
        v.addWidget(self.big_avatar)

        title = QLabel("SNDI")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont(self.ui_font_family, 26, QFont.Weight.Black))
        title.setStyleSheet(f"color:{self.cyan_text}; letter-spacing:2px;")
        glow = QGraphicsDropShadowEffect(blurRadius=14, xOffset=0, yOffset=0)
        glow.setColor(QColor(0,255,255,110))
        title.setGraphicsEffect(glow)
        v.addWidget(title)

        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        status_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_dot = QLabel(); self.status_dot.setFixedSize(12, 12)
        self.status_dot.setStyleSheet("border-radius:6px; background:#29fca5;")
        self.status_label = QLabel("online")
        self.status_label.setFont(QFont(self.ui_font_family, 11, QFont.Weight.DemiBold))
        self.status_label.setStyleSheet("color:#79ffe1;")
        status_row.addWidget(self.status_dot); status_row.addWidget(self.status_label)
        status_wrap = QFrame(); status_wrap.setLayout(status_row)
        v.addWidget(status_wrap)

        v.addItem(QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
        return side

    def set_status(self, online: bool, text: str | None = None):
        if not hasattr(self, "status_label"):
            return
        t = text if text is not None else ("online" if online else "offline")
        self.status_label.setText(t)
        self.status_dot.setStyleSheet(
            f"border-radius:6px; background:{'#29fca5' if online else '#ff3b3b'};"
        )

    # ---------- rendering ----------
    def escape_html(self, text: str) -> str:
        return (text.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                    .replace('"', "&quot;")
                    .replace("'", "&#39;"))

    def render_markdown(self, text: str) -> str:
        def highlight_code(code: str, lang: str) -> str:
            esc = self.escape_html(code)
            esc = re.sub(r'(#.*?$)', r'<font color="#b3a1ff">\\1</font>', esc, flags=re.MULTILINE)
            esc = re.sub(r'(&quot;.*?&quot;|&#39;.*?&#39;)', r'<font color="#5ffbf1">\\1</font>', esc)
            if lang.lower() in ("py", "python"):
                kw = r"\\b(False|None|True|and|as|assert|async|await|break|class|continue|def|del|elif|else|except|finally|for|from|global|if|import|in|is|lambda|nonlocal|not|or|pass|raise|return|try|while|with|yield)\\b"
                esc = re.sub(kw, r'<font color="#7ee787">\\1</font>', esc)
                esc = re.sub(r'\\b(print|len|range|list|dict|set|int|float|str|bool|type|isinstance|enumerate|zip|map|filter|sum|min|max)\\b',
                             r'<font color="#5fd4ff">\\1</font>', esc)
                esc = re.sub(r'\\b(\\d+(\\.\\d+)?)\\b', r'<font color="#ff89a5">\\1</font>', esc)
            elif lang.lower() in ("json",):
                esc = re.sub(r'(\"[^\"]+\"\s*:)', r'<font color="#7ee787">\\1</font>', esc)
                esc = re.sub(r'\\b(true|false|null)\\b', r'<font color="#ff89a5">\\1</font>', esc)
                esc = re.sub(r'(\".*?\")', r'<font color="#5ffbf1">\\1</font>', esc)
            else:
                esc = re.sub(r'\\b(\\d+(\\.\\d+)?)\\b', r'<font color="#ff89a5">\\1</font>', esc)
            esc = esc.replace("&#39;", "'")
            return (f'<table width="100%" cellspacing="0" cellpadding="8" bgcolor="#0f1117"><tr><td>'
                    f'<pre>{esc}</pre>'
                    f'</td></tr></table>')

        parts, pos = [], 0
        pattern = re.compile(r"```(\\w+)?\\n(.*?)```", re.DOTALL)
        for m in pattern.finditer(text):
            normal = text[pos:m.start()]
            parts.append(f'<span style="white-space:pre-wrap;">{self.escape_html(normal)}</span>')
            lang = m.group(1) or ""
            code = m.group(2)
            parts.append(highlight_code(code, lang))
            pos = m.end()
        tail = text[pos:]
        parts.append(f'<span style=\"white-space:pre-wrap;\">{self.escape_html(tail)}</span>')
        return "".join(parts)

    def bubble_html(self, is_user: bool, name_html: str, body_html: str) -> str:
        left_bg  = self.sndi_bubble_fill
        right_bg = self.user_bubble_fill
        def cell(bfill):
            return (
                f'<table cellspacing="0" cellpadding="0" style="border:1px solid {self.frame_line};" bgcolor="{bfill}"><tr><td style="padding:10px 14px;">'
                f'<div style="font-family:{self.ui_font_family}; font-weight:700; font-size:13px; color:{self.name_red}; margin-bottom:4px;">{name_html}</div>'
                f'<div style="color:{self.cyan_text}; font-family:{self.ui_font_family}; font-size:15px; line-height:1.35;">{body_html}</div>'
                f'</td></tr></table>'
            )
        if is_user:
            return (f'<table width="100%" cellspacing="0" cellpadding="6">'
                    f'<tr><td width="24%"></td><td align="right">{cell(right_bg)}</td></tr>'
                    f'</table>')
        else:
            return (f'<table width="100%" cellspacing="0" cellpadding="6">'
                    f'<tr><td align="left">{cell(left_bg)}</td><td width="24%"></td></tr>'
                    f'</table>')

    def render_messages(self):
        html_parts = []
        for msg in self.messages:
            is_user = (msg["speaker"] == "user")
            name = "Ти" if is_user else "SNDI"
            body_html = self.render_markdown(msg["text"])
            html_parts.append(self.bubble_html(is_user, name, body_html))
        self.chat_area.setHtml("".join(html_parts))
        self.chat_area.moveCursor(self.chat_area.textCursor().MoveOperation.End)

    # ---------- events ----------
    def send_message(self):
        user_text = self.input_field.text().strip()
        if not user_text:
            return
        self.send_sound.play()
        self.messages.append({"speaker": "user", "text": user_text, "typing": False})
        self.messages.append({"speaker": "sndi", "text": "друкує…", "typing": True})
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
        self.message_sound.play()
        if not reply or not reply.strip():
            reply = "шум глушить канал. повтори."
        if not self.messages or self.messages[-1]["speaker"] != "sndi":
            self.messages.append({"speaker": "sndi", "text": "", "typing": True})
        self.streaming_text = reply
        self.streaming_index = 0
        self.timer.start(12)

    def _on_timer(self):
        if self.streaming_text is None:
            dots = "." * ((self.dot_phase % 3) + 1)
            self.dot_phase += 1
            self.messages[-1]["text"] = f"друкує{dots}"
            self.render_messages()
            return
        if self.streaming_index <= len(self.streaming_text):
            visible = self.streaming_text[:self.streaming_index]
            self.messages[-1]["text"] = visible
            self.render_messages()
            self.streaming_index += 1
        else:
            self.messages[-1]["typing"] = False
            self.timer.stop()

    def start_voice_input(self):
        recognizer = sr.Recognizer()
        with sr.Microphone() as source:
            self.messages.append({"speaker": "sndi", "text": "слухаю.", "typing": False})
            self.render_messages()
            audio = recognizer.listen(source)
        try:
            user_input = recognizer.recognize_google(audio, language="uk-UA")
            self.input_field.setText(user_input)
            self.send_message()
        except sr.UnknownValueError:
            self.messages.append({"speaker": "sndi", "text": "не розчула. повтори.", "typing": False})
            self.render_messages()
        except sr.RequestError:
            self.messages.append({"speaker": "sndi", "text": "глюк сервера розпізнавання.", "typing": False})
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
