import sys, os, re
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QTextEdit, QLineEdit, QPushButton
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QFontDatabase
from main import sndi
import pygame
import speech_recognition as sr


# ---------- helpers: fonts ----------
def load_cyberpunk_font():
    """
    Спроба підвантажити кастомні TTF, якщо вони є в assets/fonts/.
    Рекомендую Orbitron/Audiowide/ShareTechMono — просто поклади .ttf файли туди.
    """
    candidates = [
        "assets/fonts/Orbitron-Regular.ttf",
        "assets/fonts/Audiowide-Regular.ttf",
        "assets/fonts/ShareTechMono-Regular.ttf",
    ]
    loaded_family = None
    for path in candidates:
        if os.path.exists(path):
            fid = QFontDatabase.addApplicationFont(path)
            if fid != -1:
                families = QFontDatabase.applicationFontFamilies(fid)
                if families:
                    loaded_family = families[0]
                    break
    # Фолбек стек: на Win зазвичай є Bahnschrift/Segoe UI
    return loaded_family or "Bahnschrift"

# ---------- async ----------
class ResponseThread(QThread):
    finished = pyqtSignal(str)

    def __init__(self, user_text: str):
        super().__init__()
        self.user_text = user_text

    def run(self):
        reply = sndi.ask(self.user_text)
        self.finished.emit(reply)

# ---------- main UI ----------
class ChatWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SNDI — Night City Chat")
        self.setMinimumSize(900, 640)

        self.theme_bg = "#0b0b0f"
        self.chat_bg = "#121218"
        self.user_bubble_fill = "#042e2a"   # темний бірюзовий фон
        self.sndi_bubble_fill = "#1f0f33"   # темний фіолетовий фон
        self.user_accent = "#00e5c3"        # бірюзовий контур/текст
        self.sndi_accent = "#a64dff"        # фіолетовий контур/текст
        self.text_on_dark = "#e8f8ff"

        # Fonts
        self.ui_font_family = load_cyberpunk_font()
        self.mono_font_family = "Consolas"  # для коду (фолбек)
        self.base_font = QFont(self.ui_font_family, 11)

        self.setStyleSheet(f"background-color: {self.theme_bg}; color: {self.text_on_dark};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Chat Area
        self.chat_area = QTextEdit(readOnly=True)
        self.chat_area.setFont(self.base_font)
        self.chat_area.setStyleSheet(f"""
            QTextEdit {{
                background-color: {self.chat_bg};
                color: {self.text_on_dark};
                padding: 16px;
                border: 1px solid #1e1e28;
                border-radius: 12px;
            }}
        """)
        layout.addWidget(self.chat_area)

        # Input
        self.input_field = QLineEdit(placeholderText="Введи щось…")
        self.input_field.setFont(QFont(self.ui_font_family, 12))
        self.input_field.setStyleSheet("""
            QLineEdit {
                background-color: #1a1b22;
                color: #e8f8ff;
                padding: 12px 14px;
                border: 1px solid #2a2b36;
                border-radius: 10px;
            }
            QLineEdit:focus { border: 1px solid #00e5c3; }
        """)
        layout.addWidget(self.input_field)

        # Send
        self.send_button = QPushButton("▶")
        self.send_button.setFont(QFont(self.ui_font_family, 13, QFont.Weight.Bold))
        self.send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_button.setStyleSheet("""
            QPushButton {
                background-color: #00e5c3;
                color: #0b0b0f;
                padding: 10px 18px;
                border: none;
                border-radius: 10px;
            }
            QPushButton:hover { background-color: #00c9ac; }
        """)
        self.send_button.clicked.connect(self.send_message)
        layout.addWidget(self.send_button)
        self.input_field.returnPressed.connect(self.send_message)

        # State
        self.messages = []  # {"speaker": "user"|"sndi", "text": str, "typing": bool}
        self.response_thread = None

        # Typing animation
        self.timer = QTimer()
        self.timer.timeout.connect(self._on_timer)
        self.streaming_text = None
        self.streaming_index = 0
        self.dot_phase = 0



        # звук
        pygame.mixer.init()
        self.message_sound = pygame.mixer.Sound("assets/cyberpunk_message.wav")


    # ---------- rendering ----------
    def escape_html(self, text: str) -> str:
        return (text.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                    .replace('"', "&quot;")
                    .replace("'", "&#39;"))

    def render_markdown(self, text: str) -> str:
        """
        Підтримка блоків ```lang ... ``` з підсвічуванням для Python/JSON.
        Замість <span style=...> — <font color=...> (Qt RichText це краще рендерить).
        """
        def highlight_code(code: str, lang: str) -> str:
            esc = self.escape_html(code)

            # Коментарі — світло-фіолетові
            esc = re.sub(r'(#.*?$)', r'<font color="#b3a1ff">\1</font>', esc, flags=re.MULTILINE)
            # Рядки — бірюзові (з урахуванням ескейпу лапок)
            esc = re.sub(r'(&quot;.*?&quot;|&#39;.*?&#39;)', r'<font color="#5ffbf1">\1</font>', esc)

            if lang.lower() in ("py", "python"):
                keywords = r"\b(False|None|True|and|as|assert|async|await|break|class|continue|def|del|elif|else|except|finally|for|from|global|if|import|in|is|lambda|nonlocal|not|or|pass|raise|return|try|while|with|yield)\b"
                esc = re.sub(keywords, r'<font color="#7ee787">\1</font>', esc)
                esc = re.sub(r'\b(print|len|range|list|dict|set|int|float|str|bool|type|isinstance|enumerate|zip|map|filter|sum|min|max)\b',
                             r'<font color="#5fd4ff">\1</font>', esc)
                esc = re.sub(r'\b(\d+(\.\d+)?)\b', r'<font color="#ff89a5">\1</font>', esc)
            elif lang.lower() in ("json",):
                esc = re.sub(r'(\"[^\"]+\"\s*:)', r'<font color="#7ee787">\1</font>', esc)
                esc = re.sub(r'\b(true|false|null)\b', r'<font color="#ff89a5">\1</font>', esc)
                esc = re.sub(r'(\".*?\")', r'<font color="#5ffbf1">\1</font>', esc)
            else:
                esc = re.sub(r'\b(\d+(\.\d+)?)\b', r'<font color="#ff89a5">\1</font>', esc)

            # повертаємо нормальні апострофи в коді
            esc = esc.replace("&#39;", "'")

            # контейнер із фоном (таблиця стабільно рендериться в Qt)
            return (f'<table width="100%" cellspacing="0" cellpadding="8" bgcolor="#0f1117"><tr><td>'
                    f'<pre>{esc}</pre>'
                    f'</td></tr></table>')

        # Розбір на текст і код-блоки
        parts, pos = [], 0
        pattern = re.compile(r"```(\w+)?\n(.*?)```", re.DOTALL)
        for m in pattern.finditer(text):
            normal = text[pos:m.start()]
            parts.append(f'<span style="white-space:pre-wrap;">{self.escape_html(normal)}</span>')
            lang = m.group(1) or ""
            code = m.group(2)
            parts.append(highlight_code(code, lang))
            pos = m.end()
        tail = text[pos:]
        parts.append(f'<span style="white-space:pre-wrap;">{self.escape_html(tail)}</span>')
        return "".join(parts)

    def bubble_html(self, is_user: bool, name_html: str, body_html: str) -> str:
        """
        Один ряд чату як таблиця 2×1 (Qt RichText гарантовано вирівнює).
        Ти — праворуч, SNDI — ліворуч.
        """
        left_bg = self.sndi_bubble_fill
        right_bg = self.user_bubble_fill
        left_border = self.sndi_accent
        right_border = self.user_accent

        def cell(bfill, bcolor):
            return (
                f'<table cellspacing="0" cellpadding="0" style="border:1px solid {bcolor};" bgcolor="{bfill}"><tr><td style="padding:10px 14px;">'
                f'<div style="font-family:{self.ui_font_family}; font-weight:600; font-size:12px; color:{bcolor}; margin-bottom:4px;">{name_html}</div>'
                f'<div style="color:{self.text_on_dark}; font-family:{self.ui_font_family}; font-size:14px; line-height:1.35;">{body_html}</div>'
                f'</td></tr></table>'
            )

        if is_user:
            # порожня ліва — контент праворуч
            row = (
                f'<table width="100%" cellspacing="0" cellpadding="6">'
                f'<tr>'
                f'  <td width="24%"></td>'
                f'  <td align="right">{cell(right_bg, right_border)}</td>'
                f'</tr>'
                f'</table>'
            )
        else:
            # контент ліворуч — порожня права
            row = (
                f'<table width="100%" cellspacing="0" cellpadding="6">'
                f'<tr>'
                f'  <td align="left">{cell(left_bg, left_border)}</td>'
                f'  <td width="24%"></td>'
                f'</tr>'
                f'</table>'
            )
        return row

    def render_messages(self):
        html_parts = []
        for msg in self.messages:
            is_user = (msg["speaker"] == "user")
            name = "🟣 Ти" if is_user else "🔵 SNDI"
            body_html = self.render_markdown(msg["text"])
            html_parts.append(self.bubble_html(is_user, name, body_html))

        self.chat_area.setHtml("".join(html_parts))
        self.chat_area.moveCursor(self.chat_area.textCursor().MoveOperation.End)

    # ---------- events ----------
    def send_message(self):
        user_text = self.input_field.text().strip()
        if not user_text:
            return

        # push user's message (праворуч)
        self.messages.append({"speaker": "user", "text": user_text, "typing": False})

        # push SNDI placeholder (ліворуч)
        self.messages.append({"speaker": "sndi", "text": "Друкує…", "typing": True})
        self.dot_phase = 0
        self.streaming_text = None
        self.streaming_index = 0
        self.timer.start(450)  # animate "Друкує…"

        self.render_messages()
        self.input_field.clear()

        # async get reply
        self.response_thread = ResponseThread(user_text)
        self.response_thread.finished.connect(self.receive_reply)
        self.response_thread.start()

    def receive_reply(self, reply: str):
        # Start typewriter on the last SNDI message
        self.message_sound.play()  

        if not self.messages or self.messages[-1]["speaker"] != "sndi":
            self.messages.append({"speaker": "sndi", "text": "", "typing": True})

        self.streaming_text = reply
        self.streaming_index = 0
        self.timer.start(12)

    def _on_timer(self):
        if self.streaming_text is None:
            # animate "Друкує..."
            dots = "." * ((self.dot_phase % 3) + 1)
            self.dot_phase += 1
            self.messages[-1]["text"] = f"Друкує{dots}"
            self.render_messages()
            return

        # typewriter
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
            self.append_message("SNDI", "Слухаю тебе... 🎧")
            audio = recognizer.listen(source)

        try:
            user_input = recognizer.recognize_google(audio, language="uk-UA")  # або "en-US"
            self.input_field.setText(user_input)
            self.send_message()  # автоматично відправляє
        except sr.UnknownValueError:
            self.append_message("SNDI", "Не розчула, скажи ще раз.")
        except sr.RequestError:
            self.append_message("SNDI", "Помилка сервера розпізнавання.")

# ---------- app ----------
def main():
    app = QApplication(sys.argv)
    window = ChatWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
