# sndi/system_manager.py
# -*- coding: utf-8 -*-
import os, re, subprocess, webbrowser, json, time, getpass, difflib, string, glob, shutil, winreg
from pathlib import Path
from os import path as osp
from typing import Callable, Optional, Tuple, Dict, List
from datetime import datetime

try:
    import psutil  # optional
except ImportError:
    psutil = None

# ---------------- Security / policy ----------------
ALLOWED_DIRS = [str(Path.home() / "Desktop"),
                str(Path.home() / "Documents"),
                str(Path.home() / "Downloads")]
DANGEROUS_ACTIONS = {"shutdown", "restart", "sleep", "hibernate", "kill_process"}

# Manual aliases (disabled by default — auto-discovery is used)
USE_ALIASES = os.getenv("SNDI_USE_ALIASES", "0") == "1"

APP_ALIASES: Dict[str, str] = {
    "explorer": r"C:\Windows\explorer.exe",
    "cs2": "steam://rungameid/730",
}
FOLDER_ALIASES = {
    "downloads": str(Path.home() / "Downloads"),
    "documents": str(Path.home() / "Documents"),
    "desktop":   str(Path.home() / "Desktop"),
}
APP_SYNONYMS: Dict[str, List[str]] = {
    "explorer": ["провідник", "файли", "експлорер", "file explorer", "windows explorer"],
    "settings": ["параметри", "налаштування", "settings"],
}
SETTINGS_SECTIONS: Dict[str, List[str]] = {
    "": ["параметри", "налаштування", "settings"],
    "display": ["екран", "дисплей", "яскравість"],
    "network": ["мережа", "інтернет", "вайфай", "wi-fi", "wifi"],
    "bluetooth": ["блютуз", "bluetooth"],
    "appsfeatures": ["програми", "apps"],
    "privacy": ["конфіденційність", "privacy"],
    "windowsupdate": ["оновлення", "update", "windows update"],
    "sound": ["звук", "гучність", "саунд"],
}

START_MENU_DIRS = [
    os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs"),
    os.path.expandvars(r"%AppData%\Microsoft\Windows\Start Menu\Programs"),
]
NEGATIVE_HINTS = (" ac", "anti-cheat", "anti cheat", "uninstall", "updater",
                  "helper", "console", "maintenance", "safe mode")

# ---------------- normalizers / translit ----------------
def _clean_token(s: str) -> str:
    table = str.maketrans("", "", string.punctuation.replace("-", ""))
    return " ".join(s.translate(table).lower().split())

_UA2LAT = {
    "а":"a","б":"b","в":"v","г":"h","ґ":"g","д":"d","е":"e","є":"ie","ж":"zh","з":"z","и":"y","і":"i",
    "ї":"i","й":"i","к":"k","л":"l","м":"m","н":"n","о":"o","п":"p","р":"r","с":"s","т":"t","у":"u",
    "ф":"f","х":"kh","ц":"ts","ч":"ch","ш":"sh","щ":"shch","ь":"","ю":"iu","я":"ia",
}
def _ua_to_lat(s: str) -> str:
    s = s.lower()
    s = (s.replace("кс", "cs")
           .replace("дискорд", "discord")
           .replace("хром", "chrome")
           .replace("гугл", "google")
           .replace("провідник", "explorer"))
    return "".join(_UA2LAT.get(ch, ch) for ch in s)

def _name_variants(name: str) -> List[str]:
    n = _clean_token(name)
    v = {n, _ua_to_lat(n), n.replace("-", " "), n.replace(" ", ""), _ua_to_lat(n).replace(" ", "")}
    return [x for x in v if x]

# ---------------- Start Menu index (.lnk) ----------------
class ShortcutIndex:
    def __init__(self) -> None:
        self.map: Dict[str, str] = {}
        self._build()

    def _score(self, name: str, q: str) -> int:
        n = name.lower()
        if n == q: return 10_000
        score = 0
        if n.startswith(q): score += 500
        if q in n: score += 120
        score += len(os.path.commonprefix([n, q]))
        for bad in NEGATIVE_HINTS:
            if bad in n: score -= 350
        return score

    def _build(self) -> None:
        for root in START_MENU_DIRS:
            if not osp.isdir(root): continue
            for p in glob.glob(osp.join(root, "**", "*.lnk"), recursive=True):
                name = osp.splitext(osp.basename(p))[0]
                for var in _name_variants(name):
                    self.map[var] = p

    def find(self, query: str) -> Optional[str]:
        qs = _name_variants(query)
        for q in qs:
            if q in self.map:
                return self.map[q]
        keys = list(self.map.keys())
        for q in qs:
            best = difflib.get_close_matches(q, keys, n=3, cutoff=0.72)
            if best:
                best.sort(key=lambda k: -self._score(k, q))
                return self.map[best[0]]
        return None

_SHORTCUTS = ShortcutIndex()

# ---------------- Program Files scan (*.exe) ----------------
PROGRAM_DIRS = [
    os.environ.get("ProgramFiles", r"C:\Program Files"),
    os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
    str(Path.home() / "AppData" / "Local" / "Programs"),
]

def _scan_program_dirs(token: str) -> Optional[str]:
    tok = _clean_token(token)
    patterns = [f"*{tok}*.exe", f"{tok}.exe"]
    for root in PROGRAM_DIRS:
        if not root or not osp.isdir(root): continue
        for pat in patterns:
            try:
                hits = glob.glob(osp.join(root, "**", pat), recursive=True)
            except Exception:
                hits = []
            hits.sort(key=lambda p: (len(osp.basename(p)), len(p)))
            for h in hits:
                if osp.exists(h):
                    return h
    return None

# ---------------- Microsoft Store / UWP via PowerShell ----------------
# Get-StartApps → [{Name, AppID}, ...]
def _get_startapps_json() -> Optional[List[Dict[str, str]]]:
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Depth 2"],
            text=True, stderr=subprocess.DEVNULL
        )
        data = json.loads(out)
        if isinstance(data, dict):  # single item
            data = [data]
        if isinstance(data, list):
            return [{"Name": d.get("Name",""), "AppID": d.get("AppID","")} for d in data if isinstance(d, dict)]
    except Exception:
        return None
    return None

_STARTAPPS_CACHE = _get_startapps_json()

def _find_store_app_aumid(query: string) -> Optional[str]:  # type: ignore[name-defined]
    # (python typing trick: 'string' above is imported; keep it simple)
    if not _STARTAPPS_CACHE:
        return None
    qs = _name_variants(query)
    # exact/contains
    for q in qs:
        for it in _STARTAPPS_CACHE:
            name = _clean_token(it.get("Name",""))
            if q == name or q in name:
                return it.get("AppID")
    # fuzzy
    names = [_clean_token(it.get("Name","")) for it in _STARTAPPS_CACHE]
    for q in qs:
        best = difflib.get_close_matches(q, names, n=1, cutoff=0.72)
        if best:
            for it in _STARTAPPS_CACHE:
                if _clean_token(it.get("Name","")) == best[0]:
                    return it.get("AppID")
    return None

def _launch_store_app(aumid: str) -> bool:
    try:
        # launch via explorer shell:AppsFolder\<AUMID>
        subprocess.Popen(["explorer", f"shell:AppsFolder\\{aumid}"])
        return True
    except Exception:
        return False

# ---------------- registry / PATH resolver ----------------
def _try_app_paths_registry(app_name: str) -> Optional[str]:
    keys = [r"Software\Microsoft\Windows\CurrentVersion\App Paths",
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"]
    roots = [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]
    base = app_name.strip().lower()
    cand = [base if base.endswith(".exe") else base + ".exe", base]
    for root in roots:
        for key in keys:
            try:
                with winreg.OpenKey(root, key) as k:
                    for nm in cand:
                        try:
                            with winreg.OpenKey(k, nm) as sub:
                                val, _ = winreg.QueryValueEx(sub, None)
                                if val and osp.exists(val):
                                    return val
                        except OSError:
                            pass
            except OSError:
                continue
    return None

def _resolve_app_dynamic(name_or_path: str) -> Dict[str, Optional[str]]:
    """
    Повертає dict із першим валідним варіантом:
    {"type": "lnk|exe|store|shell|none", "target": <string or None>}
    """
    s = name_or_path.strip().strip('"')
    # 1) явний шлях
    if osp.exists(s):
        return {"type": "exe", "target": s}
    # 2) Microsoft Store (AUMID)
    aumid = _find_store_app_aumid(s)
    if aumid:
        return {"type": "store", "target": aumid}
    # 3) PATH / where
    w = shutil.which(s)
    if w:
        return {"type": "exe", "target": w}
    try:
        out = subprocess.check_output(["where", s], stderr=subprocess.DEVNULL, text=True, shell=False)
        for line in out.splitlines():
            line = line.strip()
            if line and osp.exists(line):
                return {"type": "exe", "target": line}
    except Exception:
        pass
    # 4) registry App Paths
    reg = _try_app_paths_registry(s)
    if reg:
        return {"type": "exe", "target": reg}
    # 5) Start Menu shortcut
    lnk = _SHORTCUTS.find(s)
    if lnk:
        return {"type": "lnk", "target": lnk}
    # 6) Program Files scan
    exe = _scan_program_dirs(s)
    if exe:
        return {"type": "exe", "target": exe}
    # 7) нічого не знайшли
    return {"type": "none", "target": None}

# ---------------- misc helpers ----------------
def _resolve_settings_section(name: str) -> Optional[str]:
    q = _clean_token(name)
    for sec, labels in SETTINGS_SECTIONS.items():
        for lbl in labels:
            if q == _clean_token(lbl):
                return sec
    labels, back = [], {}
    for sec, arr in SETTINGS_SECTIONS.items():
        for lbl in arr:
            l = _clean_token(lbl)
            labels.append(l); back[l] = sec
    best = difflib.get_close_matches(q, labels, n=1, cutoff=0.72)
    return back[best[0]] if best else None

def _parse_combo_list(payload: str) -> List[str]:
    tmp = re.sub(r"\s*(,|;|\+|&| та | і )\s*", " | ", payload, flags=re.IGNORECASE)
    return [p.strip() for p in tmp.split("|") if p.strip()]

def _canonical_app_key(raw: str) -> str:
    q = _clean_token(raw)
    if USE_ALIASES and q in APP_ALIASES: return q
    for canon, syns in APP_SYNONYMS.items():
        all_names = [canon] + syns
        if q in map(_clean_token, all_names):
            return canon
    return q

# ---------------- SystemManager ----------------
class SystemManager:
    def __init__(self,
                 confirm_cb: Optional[Callable[[str], bool]] = None,
                 log_cb: Optional[Callable[[str], None]] = None):
        self.confirm_cb = confirm_cb
        self.log_cb = log_cb

    def _log(self, msg: str):
        if self.log_cb: self.log_cb(msg)

    def _with_user(self, s: str) -> str:
        return s.replace("{USER}", getpass.getuser())

    def _expand_user_alias(self, path_or_alias: str) -> str:
        alias = path_or_alias.lower()
        if alias in FOLDER_ALIASES:
            return FOLDER_ALIASES[alias]
        return os.path.expandvars(os.path.expanduser(path_or_alias))

    def _in_allowed_dir(self, target: str) -> bool:
        p = Path(target).resolve()
        return any(str(p).startswith(d) for d in ALLOWED_DIRS)

    def _should_force(self, text: str) -> bool:
        t = text.lower()
        return any(kw in t for kw in ["без підтвердження", "без підтв", "force", "примусово"])

    # ---- system actions ----
    def lock_screen(self) -> str:
        subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"])
        return "🔒 Заблокувала екран."

    def shutdown(self, force: bool = False) -> str:
        if not force and self.confirm_cb and not self.confirm_cb("Вимкнути ПК зараз?"):
            return "❎ Скасувала."
        subprocess.Popen(["shutdown", "/s", "/t", "0"])
        return "🛑 Вимикаю комп’ютер…"

    def restart(self, force: bool = False) -> str:
        if not force and self.confirm_cb and not self.confirm_cb("Перезавантажити ПК зараз?"):
            return "❎ Скасувала."
        subprocess.Popen(["shutdown", "/r", "/t", "0"])
        return "🔁 Перезавантажую…"

    def sleep(self, force: bool = False) -> str:
        if not force and self.confirm_cb and not self.confirm_cb("Перевести ПК в сон?"):
            return "❎ Скасувала."
        subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], shell=True)
        return "😴 Засинаємо…"

    # ---- Windows Settings ----
    def open_settings(self, section: Optional[str] = None) -> str:
        uri = "ms-settings:" + (section if section else "")
        try:
            os.startfile(uri)  # type: ignore[attr-defined]
            return "⚙️ Відкрила Параметри." if not section else f"⚙️ Відкрила Параметри → {section}."
        except Exception:
            return "⚠️ Не вдалося відкрити Параметри."

    # ---- Explorer ----
    def open_explorer(self, target: Optional[str] = None) -> str:
        try:
            if not target or not target.strip():
                subprocess.Popen(["explorer", "::"])
            else:
                path = self._expand_user_alias(target.strip().strip('"'))
                subprocess.Popen(["explorer", path])
            return "🗂 Відкрила Провідник."
        except Exception as e:
            self._log(f"Explorer error: {e}")
            return "⚠️ Не вдалося відкрити Провідник."

    # ---- apps ----
    def open_app(self, alias_or_path: str, args: Optional[List[str]] = None) -> str:
        args = args or []
        key = _canonical_app_key(alias_or_path)
        # спец-випадок: провідник
        if _clean_token(key) in {"провідник", "explorer", "експлорер"}:
            return self.open_explorer("")

        candidate = APP_ALIASES.get(key, alias_or_path) if USE_ALIASES else key
        candidate = self._with_user(candidate)

        resolved = _resolve_app_dynamic(candidate)
        rtype, target = resolved.get("type"), resolved.get("target")

        if rtype == "store" and target:
            ok = _launch_store_app(target)
            return "🚀 Запускаю застосунок…" if ok else "⚠️ Не вдалося запустити застосунок із Microsoft Store."

        if rtype == "lnk" and target:
            try:
                os.startfile(target)  # type: ignore[attr-defined]
                return f"🚀 Запускаю {key}…"
            except Exception as e:
                self._log(f".lnk error: {e}")

        if rtype == "exe" and target and osp.exists(target):
            try:
                subprocess.Popen([target] + args)
                return f"🚀 Запускаю {key}…"
            except Exception as e:
                return f"⚠️ Не вдалося запустити {key}: {e}"

        # останні спроби через Shell — тільки якщо є слово, інакше повертаємо помилку
        if candidate and candidate.strip():
            try:
                os.startfile(candidate)  # може спрацювати для деяких URI
                return f"🚀 Запускаю {key}…"
            except Exception:
                pass
            try:
                subprocess.Popen(["cmd", "/c", "start", "", candidate] + args, shell=False)
                return f"🚀 Запускаю {key}…"
            except Exception:
                pass

        return f"❓ Не знайшла застосунок «{alias_or_path}»."

    def kill_process(self, name_or_pid: str, force: bool = False) -> str:
        if not force and self.confirm_cb and not self.confirm_cb(f"Завершити процес {name_or_pid}?"):
            return "❎ Скасувала."
        if name_or_pid.isdigit():
            subprocess.run(["taskkill", "/PID", name_or_pid, "/F"], capture_output=True)
            return f"⛔ Завершила процес PID {name_or_pid}."
        subprocess.run(["taskkill", "/IM", name_or_pid, "/F"], capture_output=True)
        return f"⛔ Завершила процес {name_or_pid}."

    # ---- files/folders ----
    def open_folder(self, alias_or_path: str) -> str:
        target = self._expand_user_alias(alias_or_path)
        if not Path(target).exists():
            return f"⚠️ Тека не існує: {target}"
        os.startfile(target)  # type: ignore[attr-defined]
        return "📂 Відкрила теку."

    def create_folder(self, alias_or_path: str) -> str:
        target = self._expand_user_alias(alias_or_path)
        if not self._in_allowed_dir(target):
            return "⛔ Створення поза дозволеними директоріями заборонено."
        Path(target).mkdir(parents=True, exist_ok=True)
        return "📁 Теку створено."

    def delete_file(self, path: str) -> str:
        target = self._expand_user_alias(path)
        if not self._in_allowed_dir(target):
            return "⛔ Видалення поза дозволеними директоріями заборонено."
        p = Path(target)
        if not p.exists() or not p.is_file():
            return "⚠️ Файл не знайдено."
        p.unlink()
        return "🗑️ Видалила файл."

    # ---- URL ----
    def open_url(self, url: str) -> str:
        if not re.match(r"^https?://", url):
            url = "https://" + url
        webbrowser.open(url)
        return "🌐 Відкрила сайт."

    # ---- time / stats ----
    def system_time(self) -> str:
        now = datetime.now()
        lines = [f"⏰ Час: {now:%H:%M:%S}", f"📅 Дата: {now:%Y-%m-%d}"]
        if psutil:
            try:
                boot = datetime.fromtimestamp(psutil.boot_time())
                uptime = now - boot
                d, h = uptime.days, uptime.seconds // 3600
                m = (uptime.seconds % 3600) // 60
                lines.append(f"🟢 Аптайм: {d}д {h}г {m}хв")
            except Exception:
                pass
        return "\n".join(lines)

    def system_info(self) -> str:
        if not psutil:
            return "ℹ️ Встанови psutil для системної статистики: pip install psutil"
        cpu = psutil.cpu_percent(interval=0.6)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage(str(Path.home().drive or "C:\\"))
        battery = None
        try:
            battery = psutil.sensors_battery()
        except Exception:
            pass
        lines = [f"🧠 CPU: {cpu:.0f}%",
                 f"🧵 RAM: {mem.percent:.0f}% ({round(mem.used/1e9,1)} / {round(mem.total/1e9,1)} GB)",
                 f"💾 Disk: {disk.percent:.0f}% ({round(disk.used/1e9,1)} / {round(disk.total/1e9,1)} GB)"]
        if battery:
            lines.append(f"🔋 Battery: {battery.percent}% {'(charging)' if battery.power_plugged else ''}")
        return "\n".join(lines)

    # ---- dispatcher ----
    def dispatch(self, text: str) -> Tuple[bool, str]:
        t = text.strip()
        tl = t.lower()
        force = self._should_force(tl)

        # system
        if any(k in tl for k in ["заблокуй екран", "заблокуй пк", "lock screen"]):
            return True, self.lock_screen()
        if any(k in tl for k in ["вимкни пк", "вимкни комп", "shutdown", "вимкни комп'ютер", "вимкни компьютер"]):
            return True, self.shutdown(force=force)
        if any(k in tl for k in ["перезавантаж", "restart", "ребут", "перезавантаж комп", "перезавантаж комп'ютер"]):
            return True, self.restart(force=force)
        if any(k in tl for k in ["усипи", "сон", "sleep"]):
            return True, self.sleep(force=force)

        # time/date
        if any(k in tl for k in ["який час", "котра година", "time", "дата", "сьогодні"]):
            return True, self.system_time()

        # Explorer standalone
        m = re.search(r"(провідник|explorer)(.*)", tl)
        if m and not re.search(r"(відкрий|запусти)", tl):
            arg = (m.group(2) or "").strip()
            return True, self.open_explorer(arg)

        # Settings standalone
        m = re.search(r"(параметри|налаштування)(.*)", tl)
        if m and not re.search(r"(відкрий|запусти)", tl):
            sec = _resolve_settings_section(m.group(2).strip()) if m.group(2) else ""
            return True, self.open_settings(sec or "")

        # open app/settings/explorer (combo)
        m = re.search(r"(відкрий|запусти)\s+(.+)", tl)
        if m:
            payload = m.group(2).strip()
            items = _parse_combo_list(payload)
            msgs: List[str] = []
            for it in items:
                if _clean_token(it) in {"провідник", "explorer", "експлорер"}:
                    msgs.append(self.open_explorer(""))
                    continue
                sec = _resolve_settings_section(it)
                if sec is not None:
                    msgs.append(self.open_settings(sec))
                else:
                    msgs.append(self.open_app(it))
            return True, "\n".join(msgs)

        # folders
        m = re.search(r"(відкрий теку|відкрий папку)\s+(.+)", tl)
        if m:
            items = _parse_combo_list(m.group(2).strip())
            msgs = [self.open_folder(item) for item in items]
            return True, "\n".join(msgs)

        m = re.search(r"(створи теку|створи папку)\s+(.+)", tl)
        if m:
            items = _parse_combo_list(m.group(2).strip())
            msgs = [self.create_folder(item) for item in items]
            return True, "\n".join(msgs)

        m = re.search(r"(видали файл)\s+(.+)", tl)
        if m:
            items = _parse_combo_list(m.group(2).strip().strip('"'))
            msgs = [self.delete_file(item) for item in items]
            return True, "\n".join(msgs)

        # URL
        m = re.search(r"(відкрий сайт|відкрий url|open url|open site)\s+(.+)", tl)
        if m:
            return True, self.open_url(m.group(2).strip())

        # system info
        if any(k in tl for k in ["стан системи", "системна інформація", "system info", "cpu", "ram"]):
            return True, self.system_info()

        return False, ""
