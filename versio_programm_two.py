import customtkinter as ctk
from tkinter import filedialog
import os
import sys
import shutil
import sqlite3
from datetime import datetime


def resource_path(relative_path: str) -> str:
    """Возвращает путь к ресурсу (работает и в .py, и в .exe PyInstaller)."""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(_app_dir(), relative_path)


def _app_dir() -> str:
    """Папка приложения: рядом со скриптом (.py) или рядом с .exe (PyInstaller)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_data_dir() -> str:
    """Выбирает папку для хранения данных (не %APPDATA%)."""
    candidates = [
        os.path.join(_app_dir(), "data"),
        os.path.join(os.path.expanduser("~"), "Documents", "Твой личный блокнот"),
    ]

    for folder in candidates:
        try:
            os.makedirs(folder, exist_ok=True)
            test_file = os.path.join(folder, ".write_test")
            with open(test_file, "w", encoding="utf-8"):
                pass
            os.remove(test_file)
            return folder
        except Exception:
            continue

    return _app_dir()


def data_path(filename: str) -> str:
    return os.path.join(get_data_dir(), filename)

# ---------------- НАСТРОЙКИ ----------------
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# ---------------- ОКНО ----------------
app = ctk.CTk()
app.title("Твой личный блокнот")
app.geometry("1100x800")
app.resizable(False, False)

# ---------------- ШРИФТЫ / НАСТРОЙКИ ----------------
emoji_font = ("Arial Unicode MS", 16)
title_font = ("Segoe UI", 24)

settings = {
    "theme": "dark",
    "font_family": "Segoe UI",
    "notes_font_size": 14,
    "editor_font_size": 14,
    "always_on_top": False,
    "show_save_status": True,
}


def _focused_text_like_widget():
    """Возвращает виджет с фокусом, если это поле ввода (Entry/Text)."""
    try:
        w = app.focus_get()
    except Exception:
        return None

    if w is None:
        return None

    try:
        cls = w.winfo_class()
    except Exception:
        return None

    # Tk классы для ввода
    if cls in ("Text", "Entry"):
        return w
    return None


def _event_generate_on_focused(sequence: str):
    w = _focused_text_like_widget()
    if not w:
        return
    try:
        w.event_generate(sequence)
    except Exception:
        pass


def _select_all_on_focused():
    w = _focused_text_like_widget()
    if not w:
        return
    try:
        if w.winfo_class() == "Text":
            w.tag_add("sel", "1.0", "end-1c")
            w.mark_set("insert", "1.0")
            w.see("insert")
        elif w.winfo_class() == "Entry":
            w.selection_range(0, "end")
            w.icursor(0)
    except Exception:
        pass


def _undo_on_focused():
    w = _focused_text_like_widget()
    if not w:
        return
    try:
        if w.winfo_class() == "Text":
            w.edit_undo()
    except Exception:
        pass


def _redo_on_focused():
    w = _focused_text_like_widget()
    if not w:
        return
    try:
        if w.winfo_class() == "Text":
            w.edit_redo()
    except Exception:
        pass


def _bind_edit_hotkeys_to_app():
    """Глобальные горячие клавиши для копирования/вставки/вырезания и т.п."""
    # Не используем bind_all, чтобы избежать дублирования событий
    pass


def get_notes_font():
    return (settings["font_family"], settings["notes_font_size"])


def get_editor_font():
    return ("Consolas", settings["editor_font_size"])

# ---------------- ОСНОВНОЙ КОНТЕЙНЕР ----------------
content_frame = ctk.CTkFrame(app)
content_frame.grid(row=2, column=0, columnspan=4, sticky="nsew", padx=20, pady=(0, 20))

app.grid_columnconfigure((0, 1, 2, 3), weight=1)
app.grid_rowconfigure(2, weight=1)

content_frame.grid_rowconfigure(0, weight=1)
content_frame.grid_columnconfigure(0, weight=1)

# ---------------- TOOLBAR ДЛЯ БЛОКНОТА ----------------
toolbar = ctk.CTkFrame(app)
toolbar.grid(row=1, column=0, columnspan=4, sticky="ew", padx=20, pady=(0, 10))

# Переменные для работы с вкладками
tab_counter = 1
current_tabs = {}  # Словарь для хранения данных вкладок
tab_order = []

# Данные заметок (вкладки внутри "Заметок")
notes_search_text = ""
notes_tabs_order: list[str] = []
notes_by_tab: dict[str, list[dict]] = {}
notes_frames: dict[str, ctk.CTkScrollableFrame] = {}

# ---------------- SQLITE (ПАМЯТЬ БЛОКНОТА) ----------------
DB_PATH = data_path("notebook.sqlite3")

# Если переносим приложение/первый запуск в новой папке — подхватим существующую БД
if not os.path.exists(DB_PATH):
    src_db = resource_path("notebook.sqlite3")
    if os.path.exists(src_db):
        try:
            shutil.copy2(src_db, DB_PATH)
        except Exception:
            pass


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tabs (
                position INTEGER NOT NULL,
                name TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                filepath TEXT
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                position INTEGER NOT NULL,
                tab_name TEXT NOT NULL,
                text TEXT NOT NULL,
                done INTEGER NOT NULL,
                pinned INTEGER NOT NULL,
                date TEXT NOT NULL,
                color TEXT NOT NULL,
                time_start TEXT,
                time_end TEXT
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS note_tabs (
                position INTEGER NOT NULL,
                name TEXT PRIMARY KEY
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )

        # Миграция: если база уже была создана без новых колонок
        existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(notes)").fetchall()}
        if "tab_name" not in existing_cols:
            conn.execute("ALTER TABLE notes ADD COLUMN tab_name TEXT")
            conn.execute("UPDATE notes SET tab_name='Заметки' WHERE tab_name IS NULL")
        if "time_start" not in existing_cols:
            conn.execute("ALTER TABLE notes ADD COLUMN time_start TEXT")
        if "time_end" not in existing_cols:
            conn.execute("ALTER TABLE notes ADD COLUMN time_end TEXT")


def save_all_to_db():
    """Сохраняет ВСЕ вкладки в SQLite (имя, текст, filepath)."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM tabs")
        for position, tab_name in enumerate(tab_order):
            tab_data = current_tabs.get(tab_name)
            if not tab_data:
                continue
            content = tab_data["textbox"].get("1.0", "end-1c")
            filepath = tab_data.get("filepath")
            conn.execute(
                "INSERT INTO tabs(position, name, content, filepath) VALUES(?, ?, ?, ?)",
                (position, tab_name, content, filepath),
            )


def load_from_db():
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT position, name, content, filepath FROM tabs ORDER BY position ASC"
        ).fetchall()
    return rows


def save_notes_to_db():
    """Сохраняет все вкладки заметок и заметки в SQLite."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM notes")
        conn.execute("DELETE FROM note_tabs")

        for pos, tab_name in enumerate(notes_tabs_order):
            conn.execute("INSERT INTO note_tabs(position, name) VALUES(?, ?)", (pos, tab_name))

        for tab_name in notes_tabs_order:
            tab_notes = notes_by_tab.get(tab_name, [])
            for position, note in enumerate(tab_notes):
                conn.execute(
                    "INSERT INTO notes(position, tab_name, text, done, pinned, date, color, time_start, time_end) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        position,
                        tab_name,
                        note.get("text", ""),
                        1 if note.get("done") else 0,
                        1 if note.get("pinned") else 0,
                        note.get("date", ""),
                        note.get("color", ""),
                        note.get("time_start") or "",
                        note.get("time_end") or "",
                    ),
                )


def load_notes_from_db():
    with sqlite3.connect(DB_PATH) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(notes)").fetchall()}
        has_tab = "tab_name" in cols
        has_time = "time_start" in cols and "time_end" in cols

        tab_rows = conn.execute(
            "SELECT position, name FROM note_tabs ORDER BY position ASC"
        ).fetchall()

        if has_tab and has_time:
            note_rows = conn.execute(
                "SELECT position, tab_name, text, done, pinned, date, color, time_start, time_end FROM notes ORDER BY tab_name ASC, position ASC"
            ).fetchall()
        elif has_tab:
            note_rows = conn.execute(
                "SELECT position, tab_name, text, done, pinned, date, color, '' as time_start, '' as time_end FROM notes ORDER BY tab_name ASC, position ASC"
            ).fetchall()
        else:
            note_rows = conn.execute(
                "SELECT position, 'Заметки' as tab_name, text, done, pinned, date, color, '' as time_start, '' as time_end FROM notes ORDER BY position ASC"
            ).fetchall()

    return tab_rows, note_rows


def save_settings_to_db():
    """Сохраняет настройки приложения в SQLite."""
    with sqlite3.connect(DB_PATH) as conn:
        for key, value in settings.items():
            conn.execute(
                "INSERT INTO app_settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value)),
            )


def load_settings_from_db():
    """Загружает настройки приложения из SQLite (если есть)."""
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT key, value FROM app_settings").fetchall()

    for key, value in rows:
        if key not in settings:
            continue
        if key in ("notes_font_size", "editor_font_size"):
            try:
                settings[key] = int(value)
            except Exception:
                pass
        elif key in ("always_on_top", "show_save_status"):
            settings[key] = str(value).lower() in ("1", "true", "yes", "on")
        else:
            settings[key] = value


# ---------------- СТАТУС СОХРАНЕНИЯ (В TOOLBAR) ----------------

_status_after_ids: list[str] = []


def show_status(message: str = "✓ Сохранено", ms: int = 1600):
    """Показывает краткий статус справа и затем скрывает."""
    global _status_after_ids

    if not settings.get("show_save_status", True):
        return

    # Отменяем предыдущие таймеры, чтобы сообщения не наслаивались
    for after_id in _status_after_ids:
        try:
            app.after_cancel(after_id)
        except Exception:
            pass
    _status_after_ids = []

    status_label.configure(text=message)

    # Простая "красивая" анимация исчезновения через точки
    steps = [message, f"{message}.", f"{message}..", f"{message}...", ""]
    step_ms = max(200, ms // max(1, (len(steps) - 1)))
    for i, text in enumerate(steps):
        after_id = app.after(i * step_ms, lambda t=text: status_label.configure(text=t))
        _status_after_ids.append(after_id)

# ---------------- ФУНКЦИЯ ПЕРЕКЛЮЧЕНИЯ ----------------
def show_frame(frame):
    toolbar.grid_remove()  # Скрываем toolbar по умолчанию
    for f in (frame_blocknot, frame_notes, frame_dev, frame_settings):
        f.grid_forget()
    frame.grid(sticky="nsew")
    
    # Показываем toolbar только для блокнота
    if frame == frame_blocknot:
        toolbar.grid(row=1, column=0, columnspan=4, sticky="ew", padx=20, pady=(0, 20))

# ---------------- ЭКРАНЫ ----------------
frame_blocknot = ctk.CTkFrame(content_frame)
frame_notes = ctk.CTkFrame(content_frame)
frame_dev = ctk.CTkFrame(content_frame)
frame_settings = ctk.CTkFrame(content_frame)

# ---------- Экран 1: Блокнот ----------
# TabView для вкладок
tabs = ctk.CTkTabview(frame_blocknot)
tabs.pack(fill="both", expand=True, padx=5, pady=5)

frame_blocknot.tabs = tabs

# Сделать "шапку" вкладок выше/крупнее
if hasattr(tabs, "_segmented_button"):
    try:
        tabs._segmented_button.configure(height=42, font=("Segoe UI", 16))
    except Exception:
        pass

# ---------- Экран 2: Заметки ----------
# ---------- Экран 3: В разработке ----------
# ---------- Экран 4: Настройки ----------

# Большая надпись по центру для экрана "В разработке"
ctk.CTkLabel(
    frame_dev,
    text="🚧 В РАЗРАБОТКЕ 🚧",
    font=("Segoe UI", 48),
    text_color="#aaaaaa",
).place(relx=0.5, rely=0.5, anchor="center")


# =====================
# ЭКРАН "ЗАМЕТКИ"
# =====================

ctk.CTkLabel(frame_notes, text="📌 Мои заметки", font=title_font).pack(pady=10)

search_entry = ctk.CTkEntry(frame_notes, placeholder_text="🔍 Поиск по заметкам")
search_entry.pack(fill="x", padx=20, pady=(0, 10))

input_frame = ctk.CTkFrame(frame_notes)
input_frame.pack(fill="x", padx=20)

note_entry = ctk.CTkTextbox(input_frame, height=80, font=get_notes_font())
note_entry.pack(fill="x", padx=10, pady=(10, 5))

# Включим undo/redo для Ctrl+Z / Ctrl+Y (если доступно во внутреннем Text)
try:
    note_entry._textbox.configure(undo=True, autoseparators=True, maxundo=-1)
except Exception:
    pass

# Дата + время (начало/конец)
datetime_frame = ctk.CTkFrame(input_frame)
datetime_frame.pack(fill="x", padx=10, pady=(0, 10))

date_entry = ctk.CTkEntry(datetime_frame, placeholder_text="📅 Дата (ДД.ММ.ГГГГ)")
date_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
date_entry.insert(0, datetime.now().strftime("%d.%m.%Y"))

time_start_entry = ctk.CTkEntry(datetime_frame, placeholder_text="⏱ Начало (ЧЧ:ММ)")
time_start_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

time_end_entry = ctk.CTkEntry(datetime_frame, placeholder_text="⏱ Конец (ЧЧ:ММ)")
time_end_entry.pack(side="left", fill="x", expand=True)

colors = {
    "Серый": "#2b2b2b",
    "Синий": "#1f4fff",
    "Оранжевый": "#ff8c1a",
    "Жёлтый": "#f5c542",
    "Фиолетовый": "#7a3db8",
}

color_var = ctk.StringVar(value="Серый")

ctk.CTkOptionMenu(
    input_frame,
    values=list(colors.keys()),
    variable=color_var,
).pack(anchor="w", padx=10, pady=(0, 10))

notes_controls = ctk.CTkFrame(frame_notes)
notes_controls.pack(fill="x", padx=20, pady=(0, 10))


def add_note():
    text = note_entry.get("1.0", "end-1c").strip()
    if not text:
        return
    
    # Ограничение до 20 символов
    if len(text) > 20:
        show_status("❌ Максимум 20 символов!", 2000)
        return

    date_str = (date_entry.get() or "").strip() or datetime.now().strftime("%d.%m.%Y")
    time_start = (time_start_entry.get() or "").strip()
    time_end = (time_end_entry.get() or "").strip()

    tab_name = get_current_notes_tab()
    notes_by_tab.setdefault(tab_name, [])
    notes_by_tab[tab_name].append(
        {
            "text": text,
            "done": False,
            "pinned": False,
            "date": date_str,
            "color": colors[color_var.get()],
            "time_start": time_start,
            "time_end": time_end,
        }
    )

    note_entry.delete("1.0", "end")
    time_start_entry.delete(0, "end")
    time_end_entry.delete(0, "end")
    save_notes_to_db()
    redraw_notes()
    show_status("✓ Заметка сохранена")


def move_tabview_tabs_to_bottom(tabview: ctk.CTkTabview):
    """Пытается перенести кнопки вкладок вниз (если внутренности доступны)."""
    try:
        if hasattr(tabview, "_segmented_button") and hasattr(tabview, "_tab_frame"):
            tabview.grid_rowconfigure(0, weight=1)
            tabview.grid_rowconfigure(1, weight=0)
            tabview._tab_frame.grid_forget()
            tabview._segmented_button.grid_forget()
            tabview._tab_frame.grid(row=0, column=0, sticky="nsew")
            tabview._segmented_button.grid(row=1, column=0, sticky="ew", pady=(8, 0))
    except Exception:
        pass


def get_current_notes_tab() -> str:
    return notes_tabview.get()


def ensure_notes_tab(name: str, switch_to: bool = True):
    if name in notes_by_tab:
        if switch_to:
            notes_tabview.set(name)
        return

    notes_tabview.add(name)
    tab_frame = notes_tabview.tab(name)
    scroll = ctk.CTkScrollableFrame(tab_frame)
    scroll.pack(fill="both", expand=True, padx=0, pady=0)

    notes_by_tab[name] = []
    notes_frames[name] = scroll
    notes_tabs_order.append(name)
    if switch_to:
        notes_tabview.set(name)


def new_notes_tab():
    dialog = ctk.CTkInputDialog(title="Новая вкладка", text="Название вкладки заметок:")
    name = (dialog.get_input() or "").strip()
    if not name:
        name = f"Заметки {len(notes_tabs_order) + 1}"

    if name in notes_by_tab:
        base = name
        suffix = 2
        while f"{base} ({suffix})" in notes_by_tab:
            suffix += 1
        name = f"{base} ({suffix})"

    ensure_notes_tab(name, switch_to=True)
    save_notes_to_db()
    redraw_notes()


ctk.CTkButton(
    notes_controls,
    text="✨ Новая вкладка",
    height=40,
    font=emoji_font,
    command=new_notes_tab,
).pack(side="left")


def delete_current_notes_tab():
    tab_name = get_current_notes_tab()

    # Нельзя удалить последнюю вкладку — тогда просто очищаем
    if len(notes_tabs_order) <= 1:
        notes_by_tab[tab_name] = []
        save_notes_to_db()
        redraw_notes()
        show_status("✓ Вкладка очищена")
        return

    # Выбираем вкладку, на которую переключимся после удаления
    try:
        idx = notes_tabs_order.index(tab_name)
    except ValueError:
        idx = 0

    next_tab = None
    if idx > 0:
        next_tab = notes_tabs_order[idx - 1]
    elif idx + 1 < len(notes_tabs_order):
        next_tab = notes_tabs_order[idx + 1]

    # Удаляем данные и UI
    if tab_name in notes_by_tab:
        del notes_by_tab[tab_name]
    if tab_name in notes_frames:
        del notes_frames[tab_name]
    if tab_name in notes_tabs_order:
        notes_tabs_order.remove(tab_name)

    try:
        notes_tabview.delete(tab_name)
    except Exception:
        pass

    if not notes_tabs_order:
        ensure_notes_tab("Заметки", switch_to=True)
    else:
        notes_tabview.set(next_tab or notes_tabs_order[0])

    save_notes_to_db()
    redraw_notes()
    show_status("✓ Вкладка удалена")


ctk.CTkButton(
    notes_controls,
    text="🗑 Удалить вкладку",
    height=40,
    font=emoji_font,
    command=delete_current_notes_tab,
).pack(side="left", padx=10)

ctk.CTkButton(
    notes_controls,
    text="💾 Сохранить заметку",
    height=40,
    font=emoji_font,
    command=add_note,
).pack(side="left", padx=10)


notes_tabview = ctk.CTkTabview(frame_notes)
notes_tabview.pack(fill="both", expand=True, padx=20, pady=(0, 20))
move_tabview_tabs_to_bottom(notes_tabview)


def on_notes_tab_changed(_value=None):
    redraw_notes()


notes_tabview.configure(command=on_notes_tab_changed)


def redraw_notes():
    tab_name = get_current_notes_tab()
    frame = notes_frames.get(tab_name)
    if not frame:
        return

    for widget in frame.winfo_children():
        widget.destroy()

    tab_notes = notes_by_tab.get(tab_name, [])
    sorted_notes = sorted(tab_notes, key=lambda n: not n.get("pinned", False))

    number = 1
    for note in sorted_notes:
        if notes_search_text and notes_search_text not in note.get("text", "").lower():
            continue
        create_note_widget(number, note)
        number += 1


def update_search(event=None):
    global notes_search_text
    notes_search_text = search_entry.get().lower()
    redraw_notes()


search_entry.bind("<KeyRelease>", update_search)


def create_note_widget(number, note):
    tab_name = get_current_notes_tab()
    parent = notes_frames.get(tab_name)
    if not parent:
        return

    frame = ctk.CTkFrame(parent, fg_color=note.get("color", "#2b2b2b"))
    frame.pack(fill="x", pady=5)

    date_str = note.get("date", "")
    time_start = (note.get("time_start") or "").strip()
    time_end = (note.get("time_end") or "").strip()

    time_part = ""
    if time_start or time_end:
        if time_start and time_end:
            time_part = f" {time_start}-{time_end}"
        elif time_start:
            time_part = f" {time_start}"
        else:
            time_part = f" {time_end}"

    meta = f"{date_str}{time_part}".strip()
    if meta:
        text = f"{number}. {note.get('text', '')}  ({meta})"
    else:
        text = f"{number}. {note.get('text', '')}"
    label = ctk.CTkLabel(frame, text=text, font=get_notes_font(), anchor="w")
    label.pack(side="left", padx=10, fill="x", expand=True)

    # Если закреплено — оранжевый текст, если выполнено — зелёный, иначе обычный цвет
    default_label_text_color = ctk.ThemeManager.theme.get("CTkLabel", {}).get("text_color")
    if note.get("pinned"):
        label.configure(text_color="#ff8c1a")
    elif note.get("done"):
        label.configure(text_color="#00ff7f")
    else:
        if default_label_text_color is not None:
            label.configure(text_color=default_label_text_color)

    def toggle_done():
        note["done"] = not note.get("done", False)
        save_notes_to_db()
        redraw_notes()

    def toggle_pin():
        note["pinned"] = not note.get("pinned", False)
        save_notes_to_db()
        redraw_notes()

    def move_up():
        idx = notes_by_tab[tab_name].index(note)
        if idx > 0:
            notes_by_tab[tab_name][idx], notes_by_tab[tab_name][idx - 1] = (
                notes_by_tab[tab_name][idx - 1],
                notes_by_tab[tab_name][idx],
            )
            save_notes_to_db()
            redraw_notes()

    def move_down():
        idx = notes_by_tab[tab_name].index(note)
        if idx < len(notes_by_tab[tab_name]) - 1:
            notes_by_tab[tab_name][idx], notes_by_tab[tab_name][idx + 1] = (
                notes_by_tab[tab_name][idx + 1],
                notes_by_tab[tab_name][idx],
            )
            save_notes_to_db()
            redraw_notes()

    def delete_note():
        notes_by_tab[tab_name].remove(note)
        save_notes_to_db()
        redraw_notes()

    for txt, cmd in [
        ("⬆️", move_up),
        ("⬇️", move_down),
        ("📌", toggle_pin),
        ("✔️", toggle_done),
        ("🗑", delete_note),
    ]:
        ctk.CTkButton(frame, text=txt, width=40, height=32, command=cmd).pack(side="right", padx=3)


# ----------------ФУНКЦИИ БЛОКНОТА ----------------


def create_tab(tab_name: str, text: str = "", filepath: str | None = None, switch_to: bool = True):
    """Создаёт вкладку в UI и регистрирует её в current_tabs/tab_order."""
    if tab_name in current_tabs:
        base_name = tab_name
        suffix = 2
        while f"{base_name} ({suffix})" in current_tabs:
            suffix += 1
        tab_name = f"{base_name} ({suffix})"

    frame_blocknot.tabs.add(tab_name)
    tab_frame = frame_blocknot.tabs.tab(tab_name)

    textbox = ctk.CTkTextbox(tab_frame, font=get_editor_font())
    textbox.pack(fill="both", expand=True, padx=10, pady=10)

    # Включим undo/redo для Ctrl+Z / Ctrl+Y (если доступно во внутреннем Text)
    try:
        textbox._textbox.configure(undo=True, autoseparators=True, maxundo=-1)
    except Exception:
        pass

    if text:
        textbox.insert("1.0", text)

    current_tabs[tab_name] = {"textbox": textbox, "filepath": filepath}
    tab_order.append(tab_name)
    if switch_to:
        frame_blocknot.tabs.set(tab_name)
    return tab_name

def new_tab():
    global tab_counter

    # Спрашиваем имя для новой вкладки
    dialog = ctk.CTkInputDialog(title="Новая вкладка", text="Название вкладки:")
    user_title = dialog.get_input()
    user_title = (user_title or "").strip()

    # Если пользователь отменил/ничего не ввёл — даём стандартное имя
    if not user_title:
        tab_name = f"Документ {tab_counter}"
        tab_counter += 1
    else:
        tab_name = user_title

    # Гарантируем уникальность имени вкладки
    if tab_name in current_tabs:
        base_name = tab_name
        suffix = 2
        while f"{base_name} ({suffix})" in current_tabs:
            suffix += 1
        tab_name = f"{base_name} ({suffix})"

    create_tab(tab_name, text="", filepath=None, switch_to=True)

def get_current_textbox():
    tab_name = frame_blocknot.tabs.get()
    if tab_name in current_tabs:
        return current_tabs[tab_name]["textbox"], tab_name
    return None, None

def save_file():
    # "Сохранить" сохраняет ВСЁ в SQLite
    save_all_to_db()
    save_notes_to_db()
    show_status("✓ Сохранено")

def save_file_as():
    textbox, tab_name = get_current_textbox()
    if textbox is None:
        return
    
    path = filedialog.asksaveasfilename(
        defaultextension=".txt",
        filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
    )
    
    if not path:
        return
    
    current_tabs[tab_name]["filepath"] = path
    with open(path, "w", encoding="utf-8") as file:
        file.write(textbox.get("1.0", "end-1c"))

    # Дополнительно фиксируем состояние в SQLite
    save_all_to_db()
    save_notes_to_db()
    show_status("✓ Сохранено")

def clear_textbox():
    textbox, tab_name = get_current_textbox()
    if textbox:
        textbox.delete("1.0", "end")

def close_tab():
    tab_name = frame_blocknot.tabs.get()
    if tab_name in current_tabs:
        if tab_name in tab_order:
            tab_order.remove(tab_name)
        del current_tabs[tab_name]
        frame_blocknot.tabs.delete(tab_name)
        if not current_tabs:
            create_tab("Документ 1", text="", filepath=None, switch_to=True)


def on_app_close():
    save_all_to_db()
    save_notes_to_db()
    save_settings_to_db()
    app.destroy()


def apply_settings():
    """Применяет настройки к уже созданным элементам UI."""
    try:
        ctk.set_appearance_mode(settings["theme"])
    except Exception:
        pass

    try:
        app.attributes("-topmost", bool(settings.get("always_on_top", False)))
    except Exception:
        pass

    try:
        note_entry.configure(font=get_notes_font())
    except Exception:
        pass

    for tab_data in current_tabs.values():
        try:
            tab_data["textbox"].configure(font=get_editor_font())
        except Exception:
            pass

    redraw_notes()

# ---------- КНОПКИ TOOLBAR ДЛЯ БЛОКНОТА ----------

ctk.CTkButton(
    toolbar,
    text="✨ Новая вкладка",
    font=emoji_font,
    command=new_tab
).pack(side="left", padx=5)

ctk.CTkButton(
    toolbar,
    text="💾 Сохранить",
    font=emoji_font,
    command=save_file
).pack(side="left", padx=5)

ctk.CTkButton(
    toolbar,
    text="💿 Сохранить как",
    font=emoji_font,
    command=save_file_as
).pack(side="left", padx=5)

ctk.CTkButton(
    toolbar,
    text="🗑️ Очистить",
    font=emoji_font,
    command=clear_textbox
).pack(side="left", padx=5)

ctk.CTkButton(
    toolbar,
    text="❌ Закрыть вкладку",
    font=emoji_font,
    command=close_tab
).pack(side="left", padx=5)

status_label = ctk.CTkLabel(
    toolbar,
    text="",
    font=("Segoe UI", 16)
)
status_label.pack(side="right", padx=10)


# =====================
# ЭКРАН "НАСТРОЙКИ"
# =====================

ctk.CTkLabel(frame_settings, text="⚙️ Настройки", font=title_font).pack(pady=20)

settings_controls = ctk.CTkFrame(frame_settings)
settings_controls.pack(pady=(0, 20))


def save_settings_clicked():
    save_settings_to_db()
    show_status("✓ Настройки сохранены")


ctk.CTkButton(
    settings_controls,
    text="💾 Сохранить настройки",
    height=45,
    font=emoji_font,
    command=save_settings_clicked,
).pack()


def change_theme(value: str):
    settings["theme"] = value
    apply_settings()


theme_var = ctk.StringVar(value=settings["theme"])
ctk.CTkLabel(frame_settings, text="Тема", font=get_notes_font()).pack(pady=(0, 5))
ctk.CTkOptionMenu(
    frame_settings,
    values=["dark", "light"],
    command=change_theme,
    variable=theme_var,
    height=40,
    font=emoji_font,
).pack(pady=(0, 15))


def change_font_family(value: str):
    settings["font_family"] = value
    apply_settings()


font_var = ctk.StringVar(value=settings["font_family"])
ctk.CTkLabel(frame_settings, text="Шрифт", font=get_notes_font()).pack(pady=(0, 5))
ctk.CTkOptionMenu(
    frame_settings,
    values=["Segoe UI", "Arial", "Consolas", "Times New Roman"],
    command=change_font_family,
    variable=font_var,
    height=40,
    font=emoji_font,
).pack(pady=(0, 15))


def change_notes_font_size(value: str):
    settings["notes_font_size"] = int(value)
    apply_settings()


notes_size_var = ctk.StringVar(value=str(settings["notes_font_size"]))
ctk.CTkLabel(frame_settings, text="Размер текста (заметки)", font=get_notes_font()).pack(pady=(0, 5))
ctk.CTkOptionMenu(
    frame_settings,
    values=["12", "14", "16", "18", "20"],
    command=change_notes_font_size,
    variable=notes_size_var,
    height=40,
    font=emoji_font,
).pack(pady=(0, 15))


def change_editor_font_size(value: str):
    settings["editor_font_size"] = int(value)
    apply_settings()


editor_size_var = ctk.StringVar(value=str(settings["editor_font_size"]))
ctk.CTkLabel(frame_settings, text="Размер текста (блокнот)", font=get_notes_font()).pack(pady=(0, 5))
ctk.CTkOptionMenu(
    frame_settings,
    values=["12", "14", "16", "18", "20"],
    command=change_editor_font_size,
    variable=editor_size_var,
    height=40,
    font=emoji_font,
).pack(pady=(0, 15))


def toggle_on_top():
    settings["always_on_top"] = bool(on_top_var.get())
    apply_settings()


def toggle_save_status():
    settings["show_save_status"] = bool(save_status_var.get())


on_top_var = ctk.BooleanVar(value=settings.get("always_on_top", False))
save_status_var = ctk.BooleanVar(value=settings.get("show_save_status", True))

ctk.CTkCheckBox(
    frame_settings,
    text="Окно поверх всех",
    variable=on_top_var,
    command=toggle_on_top,
).pack(pady=(10, 0))

ctk.CTkCheckBox(
    frame_settings,
    text="Показывать статус сохранения",
    variable=save_status_var,
    command=toggle_save_status,
).pack(pady=(10, 0))

# ---------------- КНОПКИ МЕНЮ ----------------
ctk.CTkButton(
    app,
    text="  Блокнот  📝",
    width=250,
    height=40,
    font=emoji_font,
    command=lambda: show_frame(frame_blocknot)
).grid(row=0, column=0, padx=20, pady=20)

ctk.CTkButton(
    app,
    text="  Заметки  📌",
    width=250,
    height=40,
    font=emoji_font,
    command=lambda: show_frame(frame_notes)
).grid(row=0, column=1, padx=10, pady=20)

ctk.CTkButton(
    app,
    text="  В разработке..  🔨",
    width=250,
    height=40,
    font=emoji_font,
    command=lambda: show_frame(frame_dev)
).grid(row=0, column=2, padx=10, pady=20)

ctk.CTkButton(
    app,
    text="  Настройки  ⚙️",
    width=250,
    height=40,
    font=emoji_font,
    command=lambda: show_frame(frame_settings)
).grid(row=0, column=3, padx=10, pady=20)

# Скрыть toolbar изначально
toolbar.grid_remove()

# Инициализация SQLite и восстановление вкладок
init_db()
load_settings_from_db()

# Горячие клавиши редактирования (Ctrl+C/V/X/A/Z/Y)
_bind_edit_hotkeys_to_app()

saved_tabs = load_from_db()
if saved_tabs:
    for _position, name, content, filepath in saved_tabs:
        create_tab(name, text=content or "", filepath=filepath, switch_to=False)
    frame_blocknot.tabs.set(tab_order[0])
else:
    create_tab("Документ 1", text="", filepath=None, switch_to=True)
    tab_counter = 2

# Восстановление заметок
notes_tabs_order.clear()
notes_by_tab.clear()
notes_frames.clear()

tab_rows, note_rows = load_notes_from_db()

if tab_rows:
    for _pos, name in tab_rows:
        ensure_notes_tab(name, switch_to=False)
else:
    ensure_notes_tab("Заметки", switch_to=False)

for _position, tab_name, text, done, pinned, date, color, time_start, time_end in note_rows:
    notes_by_tab.setdefault(tab_name, [])
    notes_by_tab[tab_name].append(
        {
            "text": text,
            "done": bool(done),
            "pinned": bool(pinned),
            "date": date,
            "color": color,
            "time_start": time_start or "",
            "time_end": time_end or "",
        }
    )

# Убедимся, что вкладки существуют в UI и в порядке
for tab_name in list(notes_by_tab.keys()):
    if tab_name not in notes_tabs_order:
        ensure_notes_tab(tab_name, switch_to=False)

notes_tabview.set(notes_tabs_order[0])
redraw_notes()

apply_settings()

# Обновим значения контролов настроек после загрузки
try:
    theme_var.set(settings["theme"])
    font_var.set(settings["font_family"])
    notes_size_var.set(str(settings["notes_font_size"]))
    editor_size_var.set(str(settings["editor_font_size"]))
    on_top_var.set(bool(settings.get("always_on_top", False)))
    save_status_var.set(bool(settings.get("show_save_status", True)))
except Exception:
    pass

# Автосохранение при закрытии окна
app.protocol("WM_DELETE_WINDOW", on_app_close)

# ---------------- ПОКАЗ ПЕРВОГО ЭКРАНА ----------------
show_frame(frame_blocknot)

# ---------------- ЗАПУСК ----------------
app.mainloop()
 