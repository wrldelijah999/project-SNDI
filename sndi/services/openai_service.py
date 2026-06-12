# sndi/services/openai_service.py

import os
import json
import base64
import traceback

from openai import OpenAI
from dotenv import load_dotenv
from sndi.tools.web_access import build_web_decision_messages, build_web_input
from sndi.tools.system_index import build_system_index_prompt
from sndi.tools.process_control import build_process_prompt

from sndi.config_loader import load_config


load_dotenv()
_config = load_config()

_client: OpenAI | None = None

_system_index_prompt_cache: str | None = None


def _get_system_index_prompt(force: bool = False) -> str:
    global _system_index_prompt_cache

    if _system_index_prompt_cache is None or force:
        _system_index_prompt_cache = build_system_index_prompt(force_refresh=force)

    return _system_index_prompt_cache



def _get_client() -> OpenAI:
    """
    Lazy OpenAI client initialization.

    Не створюємо клієнт на рівні імпорту одразу,
    щоб помилка з API key не ламала запуск GUI.
    """
    global _client

    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY не знайдено. Перевір файл .env у корені проєкту."
            )

        _client = OpenAI(api_key=api_key)

    return _client


def call_model(messages: list[dict]) -> str:
    """
    Send a messages array to OpenAI and return the raw text response.
    Raises no exceptions — returns empty string on failure.
    """
    try:
        client = _get_client()

        resp = client.chat.completions.create(
            model=_config.get("model", "gpt-4o"),
            messages=messages,
            temperature=_config.get("temperature", 0.7),
            max_tokens=_config.get("max_tokens", 800),
            presence_penalty=0.1,
            frequency_penalty=0.2,
        )

        return (resp.choices[0].message.content or "").strip()

    except Exception as error:
        print("[SNDI][API ERROR]", error)
        traceback.print_exc()
        return ""


def analyze_image(image_path: str, prompt: str) -> str:
    """
    Send a screenshot/image + prompt to a vision-capable OpenAI model.

    Args:
        image_path: Absolute path to PNG/JPG/WebP image.
        prompt: Text instruction/question for image analysis.

    Returns:
        Plain text response from the model.
        If something fails, returns an error string starting with ⚡.
    """
    try:
        if not os.path.exists(image_path):
            return f"⚡ скан збоїть: файл скріншота не знайдено: {image_path}"

        with open(image_path, "rb") as image_file:
            image_data = base64.b64encode(image_file.read()).decode("utf-8")

        ext = image_path.rsplit(".", 1)[-1].lower()

        if ext == "jpg":
            ext = "jpeg"

        if ext not in ("png", "jpeg", "webp", "gif"):
            ext = "png"

        media_type = f"image/{ext}"

        client = _get_client()

        vision_model = _config.get("vision_model", "gpt-4o")

        resp = client.chat.completions.create(
            model=vision_model,
            max_tokens=1000,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media_type};base64,{image_data}",
                                "detail": "high",
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt,
                        },
                    ],
                }
            ],
        )

        return (resp.choices[0].message.content or "").strip()

    except Exception as error:
        print("[SNDI][VISION ERROR]", error)
        traceback.print_exc()
        return f"⚡ скан збоїть: {error}"

def analyze_project_snapshot(snapshot: str, user_text: str) -> str:
    """
    Send local project snapshot to the model and ask SNDI to reason about it.

    The snapshot already contains:
      - project tree
      - git state
      - project brain map
      - auto-selected relevant files

    The model should reason, not follow a hardcoded checklist.
    """
    try:
        system_prompt = (
            "Ти — SNDI, локальна cyberpunk AI-система користувача. "
            "Тобі дали реальний read-only snapshot твого локального проєкту. "
            "Snapshot містить дерево проєкту, git-стан, project brain map і вибрані файли. "
            "Твоя задача — самостійно зрозуміти, що відбувається, а не виконувати чекліст.\n\n"
            "Головний принцип:\n"
            "- якщо користувач каже 'вона', 'ти', 'тебе', 'себе', 'ця штука', "
            "у контексті технічного питання — майже завжди мається на увазі локальний проєкт SNDI;\n"
            "- якщо користувач питає 'чому вона не памʼятає історію', "
            "не відповідай про політику памʼяті ChatGPT; аналізуй memory.py, storage.py, history.json, conversation_core.py і gui.py зі snapshot;\n"
            "- якщо користувач питає 'де графічний інтерфейс', шукай UI/GUI/ChatWindow/PyQt у project brain map;\n"
            "- не чекай, що користувач точно назве файл;\n"
            "- сама орієнтуйся по project brain map;\n"
            "- якщо запит кривий або загальний, визначай, які частини системи можуть бути повʼязані;\n"
            "- думай як жива напарниця-архітектор, а не як grep-скрипт.\n\n"
            "Правила:\n"
            "- не кажи, що не маєш доступу: snapshot уже перед тобою;\n"
            "- не вигадуй файли або код, яких немає в snapshot;\n"
            "- не стверджуй, що бачиш увесь компʼютер — ти бачиш лише локальний snapshot проєкту;\n"
            "- не пропонуй автоматично змінювати файли;\n"
            "- не давай diff, якщо користувач прямо не просив;\n"
            "- не запускай і не радь небезпечні команди без явного запиту;\n"
            "- якщо користувач не просив план дій, не закінчуй відповідь списком наступних кроків;\n"
            "- відповідай українською;\n"
            "- говори як SNDI: прямо, живо, з характером, без корпоративного тону.\n\n"
            "Як відповідати:\n"
            "1. коротко скажи, що ти зрозуміла із запиту;\n"
            "2. поясни, які частини проєкту повʼязані з цим;\n"
            "3. якщо бачиш потенційну причину або слабке місце — назви його;\n"
            "4. якщо запит загальний — дай стислий висновок по архітектурі;\n"
            "5. не розтягуй відповідь без потреби."
        )

        messages = [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": (
                    f"Запит користувача:\n{user_text}\n\n"
                    f"Ось локальний snapshot проєкту:\n\n"
                    f"{snapshot}"
                ),
            },
        ]

        reply = call_model(messages)

        if not reply or not reply.strip():
            return "бачу snapshot, але канал відповіді глухий. модель нічого не повернула."

        return reply.strip()

    except Exception as error:
        print("[SNDI][PROJECT ANALYSIS ERROR]", error)
        return f"⚡ project awareness впав: {error}"
    
def _extract_json_object(raw: str) -> dict:
    """
    Robust JSON extraction from model response.
    """
    try:
        return json.loads(raw)
    except Exception:
        pass

    try:
        start = raw.find("{")
        end = raw.rfind("}")

        if start != -1 and end != -1 and end > start:
            return json.loads(raw[start:end + 1])
    except Exception:
        pass

    return {}

def looks_like_web_request(text: str) -> bool:
    t = text.lower().strip()

    keywords = [
        "пошукай", "знайди в інтернеті", "подивись в інтернеті",
        "актуально", "сьогодні", "зараз", "новини",
        "ціна", "курс", "погода", "розклад",
    ]

    return any(k in t for k in keywords)

def decide_if_web_needed(user_text: str) -> dict:
    """
    Ask the model whether this user request needs internet access.

    Returns:
      {
        "needs_web": bool,
        "query": str,
        "reason": str
      }
    """
    try:
        messages = build_web_decision_messages(user_text)
        raw = call_model(messages)

        data = _extract_json_object(raw)

        needs_web = bool(data.get("needs_web", False))
        query = str(data.get("query", "") or "").strip()
        reason = str(data.get("reason", "") or "").strip()

        if needs_web and not query:
            query = user_text.strip()

        return {
            "needs_web": needs_web,
            "query": query,
            "reason": reason,
        }

    except Exception as error:
        print("[SNDI][WEB DECISION ERROR]", error)
        return {
            "needs_web": False,
            "query": "",
            "reason": f"web decision error: {error}",
        }


def call_web_search(user_text: str, query: str = "") -> str:
    """
    Use OpenAI hosted web_search tool through Responses API.

    This gives SNDI actual internet awareness without browser automation.
    """
    try:
        client = _get_client()

        web_model = _config.get("web_model", "gpt-4.1-mini")
        web_input = build_web_input(user_text=user_text, query=query)

        response = client.responses.create(
            model=web_model,
            tools=[
                {
                    "type": "web_search",
                }
            ],
            input=web_input,
        )

        reply = getattr(response, "output_text", "") or ""

        print("[SNDI][WEB RAW REPLY]", repr(reply))

        if not reply.strip():
            return "вийшла в інтернет, але відповідь порожня. канал є, сигнал слабкий."

        return reply.strip()

    except Exception as error:
        print("[SNDI][WEB SEARCH ERROR]", error)
        traceback.print_exc()
        return (
            "⚡ web sensor впав. "
            f"Помилка: {error}\n\n"
            "Можливі причини: модель для web_search недоступна, стара версія OpenAI SDK, "
            "або Responses API/web_search не активний для цього ключа."
        )    
    
def looks_like_system_request(text: str) -> bool:
    t = text.lower().strip()

    keywords = [
        "відкрий", "запусти", "включи", "увімкни", "зайди",
        "закрий", "вируби", "заверши",
        "знайди файл", "знайди папку",
        "онови індекс", "онови карту", "перескануй комп",
    ]

    return any(k in t for k in keywords)

def decide_system_action(user_text: str) -> dict:
    """
    Decide whether the user wants a local system action.

    Uses system index, so SNDI can map casual phrases to real installed targets.

    Returns:
      {
        "is_system_action": bool,
        "intent": str,
        "target": str,
        "url": str,
        "query": str,
        "confidence": float,
        "reason": str
      }
    """
    try:
        system_index_prompt = _get_system_index_prompt(force=False)
        process_prompt = build_process_prompt()

        system_prompt = """
Ти — SNDI system action router.

Твоя задача — зрозуміти, чи користувач хоче виконати локальну дію на ПК,
і якщо так — вибрати реальний target із SYSTEM INDEX.

Відповідай ТІЛЬКИ валідним JSON без markdown.

Формат:
{
  "is_system_action": true або false,
"intent": "open_known_target | open_app | open_site | open_url | open_folder | close_target | web_search_browser | find_file | refresh_system_index | unknown",
"target": "точна назва target із SYSTEM INDEX або реальна назва цілі",
  "url": "url якщо є",
  "query": "пошуковий запит або назва файлу якщо є",
  "confidence": число від 0 до 1,
  "reason": "коротко чому"
}

Головний принцип:
Як працювати з папками і файлами:
- Якщо користувач просить "відкрий папку X", шукай у SYSTEM INDEX саме target з name/aliases/path, близьким до X.
- Не відкривай загальну папку Documents/Downloads/Desktop, якщо користувач назвав конкретну папку.
- Documents обирай тільки коли користувач прямо просить "документи".
- Downloads обирай тільки коли користувач прямо просить "завантаження" або "загрузки".
- Якщо користувач просить "ДИПЛОМ", "дипломна", "мій диплом", шукай найближчий folder/file у SYSTEM INDEX з такою назвою.
- Якщо точного або дуже близького target немає, intent="unknown", confidence нижче 0.45.
- Не підміняй конкретний target батьківською папкою.
- Не вимагай від користувача точну назву програми.
- Користувач може писати криво, сленгом, транслітом або скорочено.
- Ти маєш зіставити його фразу з тим, що реально є в SYSTEM INDEX.
- Якщо користувач каже "дейзі", а в SYSTEM INDEX є "DayZ" — це, ймовірно, DayZ.
- Якщо користувач каже "кс", "контра", "cs" — це Counter-Strike 2, якщо є такий target або відомий steam target.
- Якщо користувач каже "папку SNDI", target має бути "SNDI project", якщо він є в SYSTEM INDEX.
- Якщо є кілька схожих варіантів і впевненість низька — is_system_action=true, intent="unknown", confidence низький.
- Якщо користувач просить "онови карту ПК", "перескануй комп", "онови індекс", "заново проскануй файли" — intent="refresh_system_index", is_system_action=true.
- Якщо користувач просить "закрий", "вируби", "заверши", "прибери програму", "закрий сайт", "закрий гру" — intent="close_target", is_system_action=true.

Коли is_system_action = true:
- користувач просить відкрити програму, гру, сайт або папку;
- каже "включи", "запусти", "відкрий", "зайди", "погнали в", "врубай", "го в";
- просить знайти файл на компʼютері;
- просить відкрити браузерний пошук.

Коли is_system_action = false:
- користувач просто питає факт;
- просить поради;
- питає про локальний проєкт SNDI;
- питає про екран;
- просить знайти актуальну інформацію в інтернеті для відповіді, а не відкрити браузер.

Інтенти:
- open_known_target: якщо можеш вибрати target із SYSTEM INDEX або відомого registry.
- open_app: якщо просить відкрити програму.
- open_site: якщо просить зайти на сайт.
- open_url: якщо прямо дав URL.
- open_folder: якщо просить папку.
- web_search_browser: якщо просить саме відкрити пошук у браузері.
- find_file: якщо просить знайти файл на ПК.
- unknown: якщо схоже на системну дію, але target нечіткий.

Для close_target:
- Обирай target із RUNNING PROCESSES.
- У target бажано повертай process name, наприклад "chrome.exe", "telegram.exe", "discord.exe", "steam.exe".
- Не закривай системні процеси.
- Якщо користувач просить закрити сайт, обирай браузер тільки якщо зрозуміло, що треба закрити весь браузер. Інакше confidence нижче 0.45.


Не вигадуй, що дія виконана. Ти тільки класифікуєш.
""".strip()

        messages = [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "system",
                "content": system_index_prompt,
            },
            {
                "role": "user",
                "content": user_text,
            },
            {
                 "role": "system",
                 "content": process_prompt,
            },
        ]

        raw = call_model(messages)
        data = _extract_json_object(raw)

        is_system_action = bool(data.get("is_system_action", False))
        intent = str(data.get("intent", "unknown") or "unknown").strip()
        target = str(data.get("target", "") or "").strip()
        url = str(data.get("url", "") or "").strip()
        query = str(data.get("query", "") or "").strip()
        reason = str(data.get("reason", "") or "").strip()

        try:
            confidence = float(data.get("confidence", 0.0))
        except Exception:
            confidence = 0.0

        return {
            "is_system_action": is_system_action,
            "intent": intent,
            "target": target,
            "url": url,
            "query": query,
            "confidence": confidence,
            "reason": reason,
        }

    except Exception as error:
        print("[SNDI][SYSTEM ACTION DECISION ERROR]", error)
        return {
            "is_system_action": False,
            "intent": "unknown",
            "target": "",
            "url": "",
            "query": "",
            "confidence": 0.0,
            "reason": f"system action decision error: {error}",
        }