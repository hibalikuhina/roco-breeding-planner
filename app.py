"""Local desktop GUI for a personal Roco Kingdom: World breeding notebook."""
from __future__ import annotations

import sqlite3
import math
import json
import re
import sys
import tkinter as tk
import uuid
from contextlib import contextmanager
from functools import lru_cache
from tkinter import messagebox, simpledialog, ttk

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

from engine import (ATTRS, CATALOG, DEFAULT_RULES, NATURES, NATURE_BY_PAIR, PETS,
                    ROOT, RULE_INFO, TRAITS, display_identity, final_route_key,
                    group_breeding_records, inferred_size, nature_chance, record_traits,
                    retained_zero_route, search, target_chance)

USER_DATA = ROOT / "user_data"
DB_PATH = USER_DATA / "personal.sqlite3"
SCHEMA = """
CREATE TABLE IF NOT EXISTS specimens (
 id INTEGER PRIMARY KEY, account TEXT NOT NULL, name TEXT NOT NULL, pet_id TEXT NOT NULL,
 sex TEXT NOT NULL, size_raw TEXT, size_label TEXT, voice_raw TEXT, voice_label TEXT,
 medals TEXT, shiny INTEGER NOT NULL DEFAULT 0, colorful INTEGER NOT NULL DEFAULT 0,
 notes TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_specimens_account ON specimens(account);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS accounts (id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE);
INSERT OR IGNORE INTO accounts(id,name) VALUES ('账号 1','账号1');
"""


@contextmanager
def db():
    USER_DATA.mkdir(exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        connection.executescript(SCHEMA)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(specimens)")}
        if "height_raw" not in columns:
            connection.execute("ALTER TABLE specimens ADD COLUMN height_raw TEXT")
        for column in ("nature_name", "nature_plus", "nature_minus"):
            if column not in columns:
                connection.execute(f"ALTER TABLE specimens ADD COLUMN {column} TEXT")
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def read_records(account: str) -> list[dict]:
    with db() as connection:
        return [dict(r) for r in connection.execute(
            "SELECT * FROM specimens WHERE account=? ORDER BY id DESC", (account,))]


def percent(value: float | None) -> str:
    if value is None:
        return "待确认"
    if 0 < value * 100 < 0.01:
        return "<0.01%"
    return f"{value * 100:.2f}%"


@lru_cache(maxsize=None)
def dex_text_key(value: str):
    """Use Windows Chinese pinyin collation for names and other text."""
    value = value.casefold()
    if sys.platform != "win32":
        return value
    mapper = ctypes.windll.kernel32.LCMapStringEx
    mapper.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.LPCWSTR,
                       ctypes.c_int, ctypes.c_void_p, ctypes.c_int,
                       ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
    mapper.restype = ctypes.c_int
    size = mapper("zh-CN", 0x400, value, -1, None, 0, None, None, None)
    if not size:
        raise OSError("Cannot create Chinese text sort key")
    buffer = ctypes.create_string_buffer(size)
    if not mapper("zh-CN", 0x400, value, -1, buffer, size, None, None, None):
        raise OSError("Cannot create Chinese text sort key")
    return buffer.raw


def dex_number_key(pet):
    number = pet.get("number") or ""
    return (int(number) if number.isdigit() else float("inf"), number)


def dex_primary_value(pet, column):
    if column == "number":
        return dex_number_key(pet)
    if column == "name":
        return dex_text_key(pet["name"])
    if column == "groups":
        return dex_text_key("、".join(pet["egg_groups"]) or "未发现")
    if column == "sex":
        ratio = pet.get("gender_ratio")
        if not ratio:
            return None
        total = ratio.get("male", 0) + ratio.get("female", 0)
        return ratio.get("male", 0) / total if total else None
    if column == "weight":
        match = re.match(r"\s*(\d+(?:\.\d+)?)\s*~\s*(\d+(?:\.\d+)?)", pet.get("adult_weight_range") or "")
        return (float(match[1]), float(match[2])) if match else None
    raise ValueError(f"Unknown Pokédex sort column: {column}")


def group_final_routes(candidates):
    """Merge sex variants and catalog forms of the same pet."""
    grouped = {}
    def remember_forms(candidate, forms):
        if candidate.mother is not None and candidate.father is not None:
            remember_forms(candidate.mother, forms)
            remember_forms(candidate.father, forms)
        elif candidate.record_id is None:
            identity = display_identity(candidate.pet_id)
            forms.setdefault(identity, {})[candidate.pet_id] = PETS[candidate.pet_id]["name"]
    for candidate in candidates:
        key = final_route_key(candidate)
        group = grouped.setdefault(key, {"variants": {}, "candidates": [],
                                         "mothers": [], "fathers": [], "children": [], "forms": {}})
        group["variants"].setdefault(candidate.sex, candidate)
        group["candidates"].append(candidate)
        remember_forms(candidate, group["forms"])
        for label, names in ((candidate.mother.label, group["mothers"]),
                             (candidate.father.label, group["fathers"]),
                             (PETS[candidate.pet_id]["name"], group["children"])):
            if label not in names:
                names.append(label)
    return list(grouped.values())


def child_label(group):
    variants = group["variants"]
    candidate = next(iter(variants.values()))
    sexes = "公/母" if set(variants) == {"公", "母"} else next(iter(variants))
    return f"{display_pet_name(candidate.pet_id)}（{sexes}）"


DISPLAY_NAMES = {}
for _pet in CATALOG["pets"]:
    DISPLAY_NAMES.setdefault(display_identity(_pet["id"]), _pet["name"].split("（")[0])


def display_pet_name(pet_id):
    return DISPLAY_NAMES[display_identity(pet_id)]


def result_number_key(group):
    return tuple(min(int(PETS[pet_id]["number"]) for pet_id in ids) for ids in (
        [step.father.pet_id for c in group["candidates"] for step in first_generation_steps(c)],
        [step.mother.pet_id for c in group["candidates"] for step in first_generation_steps(c)],
        [c.pet_id for c in group["candidates"]]))


def parent_summary(candidate):
    if candidate.record_id is None:
        prefix = "[未录入] " if not candidate.route else "[需先孵出] "
        return f"{prefix}{display_pet_name(candidate.pet_id)}（{candidate.sex}）"
    return f"[已录入] {display_pet_name(candidate.pet_id)}（{candidate.sex}）"


def record_features(record, edge_percent):
    features = [(trait + "奖牌" if trait in ("大块头", "小不点") else trait)
                for trait, chance in record_traits(record, edge_percent).items() if chance]
    nature = (record.get("nature_name") or "").strip()
    if nature:
        features.append(nature)
    size = inferred_size(record, edge_percent)
    if size not in ("未录体重", "普通体型", "大块头", "小不点"):
        features.append(size)
    return ", ".join(dict.fromkeys(features))


def record_matches_filters(record, edge_percent, size_medal="全部", voice_medal="全部",
                           shiny_only=False, colorful_only=False):
    traits = record_traits(record, edge_percent)
    for medal in (size_medal, voice_medal):
        if medal != "全部" and traits.get(medal) != 1.0:
            return False
    for checked, key in ((shiny_only, "shiny"), (colorful_only, "colorful")):
        if checked and not record.get(key):
            return False
    return True


def first_generation_steps(candidate):
    if candidate.mother is None or candidate.father is None:
        return []
    if not candidate.mother.route and not candidate.father.route:
        return [candidate]
    return first_generation_steps(candidate.mother) + first_generation_steps(candidate.father)


def first_generation_summary(candidate, role):
    return " / ".join(dict.fromkeys(parent_summary(getattr(step, role))
                                  for step in first_generation_steps(candidate)))


def detail_parent_label(candidate):
    return ("[需先孵出] " if candidate.record_id is None and candidate.route else "") + candidate.label


class PetCombobox(ttk.Combobox):
    def __init__(self, parent, variable, choices, **kwargs):
        super().__init__(parent, textvariable=variable, values=choices, **kwargs)
        self.all_choices = choices
        self.bind("<KeyRelease>", self._filter)
        self.configure(postcommand=self._filter)

    def _filter(self, _event=None):
        needle = self.get().strip().casefold()
        self.configure(values=[x for x in self.all_choices if needle in x.casefold()][:60] if needle else self.all_choices)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("洛克王国：世界 · 生蛋查询")
        self.geometry("1180x790")
        self.minsize(970, 650)
        self.configure(bg="#edf3f5")
        self.accounts = {}
        self._load_accounts()
        self.account = tk.StringVar(value=self.accounts.get("账号 1", next(iter(self.accounts.values()))))
        self.pet_display = {f"{p['name']} · {p['number'] or '---'}": p["id"] for p in CATALOG["pets"]}
        self.pet_choices = sorted(self.pet_display)
        self.display_by_id = {v: k for k, v in self.pet_display.items()}
        self.name_to_id = {p["name"]: p["id"] for p in CATALOG["pets"]}
        self.selected_id = None
        self._query_loading = True
        self._query_after = None
        self._query_account_id = None
        self._style()
        self._layout()
        self.refresh()
        self._restore_query_options()
        self._query_loading = False
        self._watch_query_options()
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _load_accounts(self):
        with db() as connection:
            self.accounts = {r["id"]: r["name"] for r in connection.execute("SELECT id,name FROM accounts ORDER BY rowid")}

    def account_id(self):
        return next((key for key, value in self.accounts.items() if value == self.account.get()), None)

    def resolve_pet(self, text):
        text = text.strip()
        if text in self.pet_display:
            return self.pet_display[text]
        if text in self.name_to_id:
            return self.name_to_id[text]
        matches = [p["id"] for p in CATALOG["pets"] if p["number"] == text]
        return matches[0] if len(matches) == 1 else None

    def _account_changed(self, *_):
        if not hasattr(self, "target_pet"):
            return
        self._flush_query_options()
        self._query_loading = True
        self.clear_record()
        self.refresh()
        self._restore_query_options()
        self._query_loading = False

    def add_account(self):
        name = simpledialog.askstring("添加账号", "新账号名称：", parent=self)
        if not name or not name.strip():
            return
        name = name.strip()
        if name in self.accounts.values():
            messagebox.showerror("名称重复", "已有同名账号。")
            return
        with db() as connection:
            connection.execute("INSERT INTO accounts(id,name) VALUES (?,?)", (uuid.uuid4().hex, name))
        self._load_accounts()
        self.account_picker.configure(values=list(self.accounts.values()))
        self.account.set(name)

    def rename_account(self):
        old_id = self.account_id()
        if not old_id:
            return
        name = simpledialog.askstring("重命名账号", "账号新名称：", initialvalue=self.account.get(), parent=self)
        if not name or not name.strip():
            return
        name = name.strip()
        if name in self.accounts.values() and name != self.account.get():
            messagebox.showerror("名称重复", "已有同名账号。")
            return
        with db() as connection:
            connection.execute("UPDATE accounts SET name=? WHERE id=?", (name, old_id))
        self._load_accounts()
        self.account_picker.configure(values=list(self.accounts.values()))
        self.account.set(name)

    def _style(self):
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("TNotebook.Tab", padding=(18, 8), font=("Microsoft YaHei UI", 10))
        style.configure("Treeview", rowheight=28, font=("Microsoft YaHei UI", 9))
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 9, "bold"))
        style.configure("TButton", padding=6)

    def _layout(self):
        top = ttk.Frame(self, padding=12)
        top.pack(fill="x")
        ttk.Label(top, text="生蛋查询", font=("Microsoft YaHei UI", 19, "bold")).pack(side="left", padx=(4, 20))
        ttk.Label(top, text="当前数据：").pack(side="left")
        self.account_picker = ttk.Combobox(top, textvariable=self.account, values=list(self.accounts.values()), state="readonly", width=16)
        self.account_picker.pack(side="left")
        ttk.Button(top, text="新增", command=self.add_account).pack(side="left", padx=(6, 2))
        ttk.Button(top, text="重命名", command=self.rename_account).pack(side="left", padx=2)
        self.account.trace_add("write", self._account_changed)
        ttk.Label(top, text="离线图鉴 625 条  ·  记录只存本机", foreground="#526875").pack(side="right", padx=8)
        book = ttk.Notebook(self)
        book.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.records_tab = ttk.Frame(book, padding=12)
        self.query_tab = ttk.Frame(book, padding=12)
        self.dex_tab = ttk.Frame(book, padding=12)
        self.rules_tab = ttk.Frame(book, padding=12)
        book.add(self.records_tab, text="种公种母")
        book.add(self.query_tab, text="生蛋路线")
        book.add(self.dex_tab, text="离线图鉴")
        book.add(self.rules_tab, text="概率参数与来源")
        self._records_ui()
        self._query_ui()
        self._dex_ui()
        self._rules_ui()

    def _records_ui(self):
        frame = self.records_tab
        pane = ttk.PanedWindow(frame, orient="horizontal")
        pane.pack(fill="both", expand=True)
        left = ttk.Frame(pane)
        right_shell = ttk.Frame(pane)
        canvas = tk.Canvas(right_shell, highlightthickness=0)
        scrollbar = ttk.Scrollbar(right_shell, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        right = ttk.Frame(canvas)
        form_window = canvas.create_window((0, 0), window=right, anchor="nw")
        right.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(form_window, width=e.width))
        pane.add(left, weight=3)
        pane.add(right_shell, weight=2)
        filters = ttk.Frame(left)
        filters.pack(fill="x", padx=(0, 12), pady=(0, 8))
        self.record_size_medal_filter = tk.StringVar(value="全部")
        self.record_voice_medal_filter = tk.StringVar(value="全部")
        self.record_shiny_filter = tk.BooleanVar(value=False)
        self.record_colorful_filter = tk.BooleanVar(value=False)
        for label, variable, choices, width in (
            ("体型奖牌", self.record_size_medal_filter, ("全部", "大块头", "小不点"), 8),
            ("声音奖牌", self.record_voice_medal_filter, ("全部", "婉转声", "粗嗓门"), 8),
        ):
            ttk.Label(filters, text=label).pack(side="left", padx=(0, 4))
            ttk.Combobox(filters, textvariable=variable, values=choices,
                         state="readonly", width=width).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(filters, text="仅异色", variable=self.record_shiny_filter).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(filters, text="仅炫彩", variable=self.record_colorful_filter).pack(side="left")
        self.record_columns = (("name", "昵称", 130), ("pet", "精灵", 140),
                               ("sex", "性别", 55), ("features", "特征", 300))
        self.record_sort_column = None
        self.record_sort_desc = False
        self.listing = ttk.Treeview(left, columns=("name", "pet", "sex", "features"), show="headings", selectmode="browse")
        for col, label, width in self.record_columns:
            self.listing.heading(col, text=label, command=lambda selected=col: self.sort_records_by(selected))
            self.listing.column(col, width=width, stretch=True)
        self.listing.pack(fill="both", expand=True, padx=(0, 12))
        self.listing.bind("<<TreeviewSelect>>", self.select_record)
        for variable in (self.record_size_medal_filter, self.record_voice_medal_filter,
                         self.record_shiny_filter, self.record_colorful_filter):
            variable.trace_add("write", lambda *_: self.refresh_records())
        ttk.Label(right, text="当前组的原始记录（属性相同的记录合并显示）").pack(anchor="w", pady=(0, 2))
        self.record_variant = tk.StringVar()
        self.record_variant_picker = ttk.Combobox(right, textvariable=self.record_variant,
                                                  state="readonly")
        self.record_variant_picker.pack(fill="x", padx=(0, 4))
        self.record_variant_picker.bind("<<ComboboxSelected>>", self.select_record_variant)
        self.fields = {}
        self.field_widgets = {}
        def field(label, key, values=None):
            ttk.Label(right, text=label).pack(anchor="w", pady=(6, 1))
            var = tk.StringVar()
            widget = PetCombobox(right, var, values) if key == "pet_display" else ttk.Combobox(right, textvariable=var, values=values, state="normal" if key == "nature_name" else "readonly") if values else ttk.Entry(right, textvariable=var)
            widget.pack(fill="x", padx=(0, 4))
            self.fields[key] = var
            self.field_widgets[key] = widget
        field("自定义昵称（可留空，自动用精灵名）", "name")
        field("精灵名称（可直接输入全名，或选筛选结果）", "pet_display", self.pet_choices)
        field("性别", "sex", ["公", "母"])
        field("成年精灵体重（kg，如 3.142）", "size_raw")
        field("声音标签", "voice_label", ["", "普通", "婉转声", "粗嗓门"])
        field("原始性格名（可输入或选择；修改后的性格不遗传）", "nature_name", ["", *NATURES])
        field("原始性格加成 +", "nature_plus", ["", *ATTRS])
        field("原始性格减益 −", "nature_minus", ["", *ATTRS])
        self._nature_syncing = False
        self.record_nature_widgets = {key: self.field_widgets[key] for key in ("nature_name", "nature_plus", "nature_minus")}
        self.fields["nature_name"].trace_add("write", lambda *_: self._sync_nature("name", self.fields, self.record_nature_widgets))
        self.fields["nature_plus"].trace_add("write", lambda *_: self._sync_nature("plus", self.fields, self.record_nature_widgets))
        self.fields["nature_minus"].trace_add("write", lambda *_: self._sync_nature("minus", self.fields, self.record_nature_widgets))
        self.pet_info = ttk.Label(right, text="", wraplength=380, foreground="#405664")
        self.pet_info.pack(anchor="w", pady=(6, 2))
        for key in ("pet_display", "size_raw"):
            self.fields[key].trace_add("write", lambda *_: self.update_pet_preview())
        checks = ttk.Frame(right)
        checks.pack(fill="x", pady=8)
        self.shiny = tk.BooleanVar()
        self.colorful = tk.BooleanVar()
        ttk.Checkbutton(checks, text="异色", variable=self.shiny).pack(side="left", padx=(0, 18))
        ttk.Checkbutton(checks, text="炫彩", variable=self.colorful).pack(side="left")
        field("备注", "notes")
        buttons = ttk.Frame(right)
        buttons.pack(fill="x", pady=10)
        ttk.Button(buttons, text="新建", command=self.clear_record).pack(side="left", padx=3)
        ttk.Button(buttons, text="保存", command=self.save_record).pack(side="left", padx=3)
        ttk.Button(buttons, text="删除", command=self.delete_record).pack(side="left", padx=3)

    def _sync_nature(self, changed, variables, widgets):
        if self._nature_syncing:
            return
        self._nature_syncing = True
        try:
            name, plus, minus = (variables[key].get().strip() for key in ("nature_name", "nature_plus", "nature_minus"))
            if changed == "name" and (name in NATURES or not name):
                plus, minus = NATURES[name] if name else ("", "")
                variables["nature_plus"].set(plus)
                variables["nature_minus"].set(minus)
            elif changed != "name":
                name = NATURE_BY_PAIR.get((plus, minus), "")
                variables["nature_name"].set(name)
            one_selected = sum(bool(x) for x in (name, plus, minus)) == 1
            widgets["nature_name"].configure(values=["", *(n for n, pair in NATURES.items()
                if not one_selected or (not plus or pair[0] == plus) and (not minus or pair[1] == minus))])
            widgets["nature_plus"].configure(values=["", *(a for a in ATTRS if a != minus)])
            widgets["nature_minus"].configure(values=["", *(a for a in ATTRS if a != plus)])
        finally:
            self._nature_syncing = False

    def _query_ui(self):
        top = ttk.Frame(self.query_tab)
        top.pack(fill="x")
        ttk.Label(top, text="目标精灵（可选）").grid(row=0, column=0, sticky="w")
        self.target_pet = tk.StringVar()
        PetCombobox(top, self.target_pet, self.pet_choices, width=48).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Label(top, text="最多几代").grid(row=0, column=2, padx=(16, 5))
        self.generations = tk.IntVar(value=1)
        ttk.Combobox(top, textvariable=self.generations, values=[1, 2, 3], state="readonly", width=5).grid(row=0, column=3)
        ttk.Button(top, text="查询路线", command=self.run_query).grid(row=0, column=4, padx=16)
        ttk.Button(top, text="清空选项", command=self.clear_query_options).grid(row=0, column=5)
        top.columnconfigure(1, weight=1)
        parents = ttk.Frame(self.query_tab)
        parents.pack(fill="x", pady=(8, 0))
        self.mother_target = tk.StringVar()
        self.father_target = tk.StringVar()
        self.parent_choices = {}
        ttk.Label(parents, text="指定母本（可选）").pack(side="left")
        self.mother_picker = ttk.Combobox(parents, textvariable=self.mother_target, state="readonly", width=34)
        self.mother_picker.pack(side="left", padx=(8, 20))
        ttk.Label(parents, text="指定父本（可选）").pack(side="left")
        self.father_picker = ttk.Combobox(parents, textvariable=self.father_target, state="readonly", width=34)
        self.father_picker.pack(side="left", padx=8)
        ttk.Label(self.query_tab, text="目标精灵、母本、父本至少填一项；指定亲本用于首代繁育，首代子代可在后续代作为公本或母本。", foreground="#526875").pack(anchor="w", pady=(5, 0))
        self.allow_unrecorded = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.query_tab, text="允许未录入亲本（从图鉴补足兼容的父本或母本）",
                        variable=self.allow_unrecorded).pack(anchor="w", pady=(7, 0))
        ttk.Label(self.query_tab, text="未录入亲本按成年体重区间中值、普通声音、无异色炫彩计算；原始性格未知。结果会标明需要取得的亲本。",
                  foreground="#526875").pack(anchor="w")
        ttk.Label(self.query_tab, text="目标特征（异色/炫彩包含普通蛋的隐性概率；体型是成年数据估算）").pack(anchor="w", pady=(14, 4))
        trait_frame = ttk.Frame(self.query_tab)
        trait_frame.pack(fill="x")
        self.target_vars = {t: tk.BooleanVar() for t in TRAITS}
        for i, trait in enumerate(TRAITS):
            widget = ttk.Checkbutton(trait_frame, text=trait, variable=self.target_vars[trait])
            widget.grid(row=0, column=i, padx=10, sticky="w")
        nature_row = ttk.Frame(self.query_tab)
        nature_row.pack(fill="x", pady=(10, 2))
        self.nature_target = tk.StringVar()
        self.plus_target = tk.StringVar()
        self.minus_target = tk.StringVar()
        self.query_nature_widgets = {}
        for label, key, var, choices, width in (("完整性格", "nature_name", self.nature_target, ["", *NATURES], 16),
                                           ("只看 +", "nature_plus", self.plus_target, ["", *ATTRS], 10),
                                           ("只看 −", "nature_minus", self.minus_target, ["", *ATTRS], 10)):
            ttk.Label(nature_row, text=label).pack(side="left", padx=(8, 3))
            widget = ttk.Combobox(nature_row, textvariable=var, values=choices, state="readonly", width=width)
            widget.pack(side="left", padx=(0, 12))
            self.query_nature_widgets[key] = widget
        query_nature = {"nature_name": self.nature_target, "nature_plus": self.plus_target, "nature_minus": self.minus_target}
        for key, changed in (("nature_name", "name"), ("nature_plus", "plus"), ("nature_minus", "minus")):
            query_nature[key].trace_add("write", lambda *_, c=changed: self._sync_nature(c, query_nature, self.query_nature_widgets))
        ttk.Label(self.query_tab, text="性格任选一项；选一项会筛选其他选项，选两项会自动补齐第三项。空白表示不限。", foreground="#526875").pack(anchor="w")
        self.query_hint = ttk.Label(self.query_tab, text="", foreground="#9a5b16", wraplength=1060)
        self.query_hint.pack(anchor="w", pady=8)
        self.query_status = ttk.Label(self.query_tab, text="", foreground="#405664", wraplength=1060)
        self.query_status.pack(anchor="w", pady=(0, 6))
        result_frame = ttk.Frame(self.query_tab)
        result_frame.pack(fill="both", expand=True)
        columns = ("generations", "father", "mother", "child", "virtuals", "note")
        self.results = ttk.Treeview(result_frame, columns=columns, show="headings", selectmode="browse")
        for key, label, width in (("generations", "代数", 55), ("father", "首代父本", 205),
                                  ("mother", "首代母本", 225), ("child", "最终子代", 160),
                                  ("virtuals", "未录入亲本", 90), ("note", "说明", 230)):
            self.results.heading(key, text=label)
            self.results.column(key, width=width, minwidth=50, stretch=key in ("father", "mother", "note"))
        scrollbar = ttk.Scrollbar(result_frame, orient="vertical", command=self.results.yview)
        self.results.configure(yscrollcommand=scrollbar.set)
        self.results.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.results.bind("<Double-1>", self.show_result_detail)
        self.result_groups = []
        self.result_targets = []
        self.result_nature = ("", "", "")

    def _query_variables(self):
        return (self.target_pet, self.mother_target, self.father_target, self.generations,
                self.allow_unrecorded, self.nature_target, self.plus_target, self.minus_target,
                *self.target_vars.values())

    def _watch_query_options(self):
        for variable in self._query_variables():
            variable.trace_add("write", self._query_changed)

    def _query_changed(self, *_):
        if self._query_loading:
            return
        self._update_query_hint()
        if self._query_after is not None:
            self.after_cancel(self._query_after)
        self._query_after = self.after(350, self._flush_query_options)

    def _query_snapshot(self):
        return {
            "target_pet_id": self.resolve_pet(self.target_pet.get()),
            "mother_id": self.parent_choices.get(self.mother_target.get()),
            "father_id": self.parent_choices.get(self.father_target.get()),
            "generations": self.generations.get(),
            "allow_unrecorded": self.allow_unrecorded.get(),
            "traits": [trait for trait, variable in self.target_vars.items() if variable.get()],
            "nature": [self.nature_target.get(), self.plus_target.get(), self.minus_target.get()],
        }

    def _flush_query_options(self):
        if self._query_after is None:
            return
        self.after_cancel(self._query_after)
        self._query_after = None
        if self._query_loading or not self._query_account_id:
            return
        with db() as connection:
            connection.execute("INSERT OR REPLACE INTO settings(key,value) VALUES (?,?)",
                               ("query:" + self._query_account_id,
                                json.dumps(self._query_snapshot(), ensure_ascii=False)))

    def _restore_query_options(self):
        self._query_account_id = self.account_id()
        with db() as connection:
            row = connection.execute("SELECT value FROM settings WHERE key=?",
                                     ("query:" + self._query_account_id,)).fetchone()
        try:
            options = json.loads(row["value"]) if row else {}
            if not isinstance(options, dict):
                options = {}
        except (ValueError, TypeError):
            options = {}
        pet_id = options.get("target_pet_id")
        self.target_pet.set(self.display_by_id.get(pet_id, ""))
        for variable, record_id in ((self.mother_target, options.get("mother_id")),
                                    (self.father_target, options.get("father_id"))):
            record_id = self.record_representative.get(record_id, record_id)
            variable.set(next((label for label, value in self.parent_choices.items()
                               if value == record_id), ""))
        generations = options.get("generations", 1)
        self.generations.set(generations if generations in (1, 2, 3) else 1)
        self.allow_unrecorded.set(bool(options.get("allow_unrecorded", False)))
        traits = options.get("traits", [])
        for trait, variable in self.target_vars.items():
            variable.set(trait in traits)
        nature = options.get("nature", ["", "", ""])
        if not isinstance(nature, list) or len(nature) != 3:
            nature = ["", "", ""]
        self._nature_syncing = True
        for variable, value in zip((self.nature_target, self.plus_target, self.minus_target), nature):
            variable.set(value if isinstance(value, str) else "")
        self._nature_syncing = False
        query_nature = {"nature_name": self.nature_target, "nature_plus": self.plus_target,
                        "nature_minus": self.minus_target}
        self._sync_nature("name" if self.nature_target.get() else "plus",
                          query_nature, self.query_nature_widgets)
        self._update_query_hint()
        self._set_results("")

    def _update_query_hint(self):
        if self.allow_unrecorded.get():
            hint = "已允许未录入亲本；路线中的 [未录入] 精灵需自行取得，概率按默认值估算。"
        else:
            hint = "仅使用当前账号已录入的亲本。目标特征始终可选；没有可行路线时会在结果中说明。"
        self.query_hint.configure(text=hint)

    def _set_results(self, value):
        self.results.delete(*self.results.get_children())
        self.result_groups = []
        self.query_status.configure(text=value)

    def show_result_detail(self, _event=None):
        selection = self.results.selection()
        if not selection:
            return
        group = self.result_groups[int(selection[0])]
        variants = group["variants"]
        candidate = next(iter(variants.values()))
        window = tk.Toplevel(self)
        window.title("生蛋路线详情")
        window.geometry("900x600")
        body = tk.Text(window, wrap="word", font=("Microsoft YaHei UI", 10), padx=16, pady=14)
        scrollbar = ttk.Scrollbar(window, orient="vertical", command=body.yview)
        body.configure(yscrollcommand=scrollbar.set)
        body.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        lengths = sorted({len(variant.route) for variant in group["candidates"]})
        lines = [f"最终子代：{child_label(group)}  |  繁育轮数：{'、'.join(map(str, lengths))}",
                 "同一最终配对的不同取得方式已合并；下方分别列出路线。", ""]
        if len(group["mothers"]) > 1:
            lines.append("可用母本记录/形态：" + "、".join(group["mothers"]))
        if len(group["fathers"]) > 1:
            lines.append("可用父本记录/形态：" + "、".join(group["fathers"]))
        if len(group["children"]) > 1:
            lines.append("子代形态：" + "、".join(group["children"]))
        for forms in group["forms"].values():
            if len(forms) > 1 and len(group["mothers"]) <= 1 and len(group["fathers"]) <= 1:
                lines.append("路线中可替换的形态：" + "、".join(forms.values()))
        lines.append("")
        lines.append("各亲本记录、形态及子代性别：")
        for variant in group["candidates"]:
            lines.append(f"父本 {detail_parent_label(variant.father)}  ×  母本 {detail_parent_label(variant.mother)}  →  {variant.label}："
                         f"目标特征条件概率 {percent(target_chance(variant, self.result_targets, self.result_nature))}"
                         f"  |  性别路径 {percent(variant.probability)}")
        lines.append("")
        if retained_zero_route(candidate, self.result_targets, self.result_nature):
            if candidate.conditional_medal_parents:
                lines.append("模型估算为 0%；此路线以先孵出带目标奖牌的中间亲本为前提，因此保留供规划参考。")
            else:
                lines.append("模型估算为 0%；至少一方按录入体重与体型奖牌边缘参数判为目标奖牌，因此保留此路线。")
            lines.append("")
        seen_routes = set()
        for variant in group["candidates"]:
            if variant.route in seen_routes:
                continue
            seen_routes.add(variant.route)
            lines.append(f"路线 {len(seen_routes)}：繁育 {len(variant.route)} 轮；未录入亲本 {len(variant.virtual_keys)} 种")
            steps = []
            def collect(current):
                if current.mother is None or current.father is None:
                    return
                collect(current.mother)
                collect(current.father)
                steps.append(current)
            collect(variant)
            for index, step in enumerate(steps, 1):
                offspring = child_label(group) if step is variant else step.label
                lines.append(f"第 {index} 轮：母本 {detail_parent_label(step.mother)}  ×  父本 {detail_parent_label(step.father)}  →  {offspring}")
                lines.append("    特征估算：" + "  ".join(f"{t} {percent(step.traits[t])}" for t in TRAITS))
                if step.conditional_medal_parents:
                    lines.append("    前提：" + "；".join(step.conditional_medal_parents))
            lines.append("")
        if any(self.result_nature):
            lines.append("性格目标：" + "/".join(x or "不限" for x in self.result_nature)
                         + " → " + percent(nature_chance(candidate, *self.result_nature)))
        lines.append("未录入亲本按体重中值、普通声音、无异色炫彩、未知性格估算；需取得并核实。")
        body.insert("1.0", "\n".join(lines))
        body.configure(state="disabled")

    def clear_query_options(self):
        if self._query_after is not None:
            self.after_cancel(self._query_after)
            self._query_after = None
        self._query_loading = True
        self.target_pet.set("")
        self.mother_target.set("")
        self.father_target.set("")
        self.generations.set(1)
        self.allow_unrecorded.set(False)
        for variable in self.target_vars.values():
            variable.set(False)
        self.nature_target.set("")
        self.plus_target.set("")
        self.minus_target.set("")
        self._query_loading = False
        self._update_query_hint()
        self._set_results("")
        with db() as connection:
            connection.execute("DELETE FROM settings WHERE key=?", ("query:" + self.account_id(),))

    def _close(self):
        self._flush_query_options()
        self.destroy()

    def _dex_ui(self):
        top = ttk.Frame(self.dex_tab)
        top.pack(fill="x", pady=(0, 8))
        ttk.Label(top, text="搜索名称 / 编号 / 蛋组").pack(side="left")
        self.dex_search = tk.StringVar()
        entry = ttk.Entry(top, textvariable=self.dex_search)
        entry.pack(side="left", fill="x", expand=True, padx=10)
        self.dex_search.trace_add("write", lambda *_: self.refresh_dex())
        filters = ttk.Frame(self.dex_tab)
        filters.pack(fill="x", pady=(0, 8))
        ttk.Label(filters, text="归属赛季").pack(side="left")
        self.dex_season = tk.StringVar(value="全部")
        seasons = sorted({pet["season"] for pet in CATALOG["pets"] if pet.get("season")},
                         key=lambda season: int(season[1:]))
        ttk.Combobox(filters, textvariable=self.dex_season,
                     values=("全部", *seasons, "无赛季"), state="readonly", width=10).pack(side="left", padx=(8, 20))
        self.dex_shiny = tk.BooleanVar(value=False)
        ttk.Checkbutton(filters, text="仅显示有异色", variable=self.dex_shiny).pack(side="left")
        self.dex_season.trace_add("write", lambda *_: self.refresh_dex())
        self.dex_shiny.trace_add("write", lambda *_: self.refresh_dex())
        self.dex_columns = (("number", "编号", 75), ("name", "精灵", 170),
                            ("groups", "蛋组", 200), ("sex", "雌雄比例", 110),
                            ("weight", "成年体重范围", 160))
        self.dex_sort_column = "number"
        self.dex_sort_desc = False
        self.dex_list = ttk.Treeview(self.dex_tab, columns=tuple(col for col, _, _ in self.dex_columns), show="headings")
        for col, label, width in self.dex_columns:
            self.dex_list.heading(col, text=label, command=lambda selected=col: self.sort_dex_by(selected))
            self.dex_list.column(col, width=width)
        self.dex_list.pack(fill="both", expand=True)
        self.dex_list.bind("<<TreeviewSelect>>", self.show_dex_detail)
        self.dex_detail = ttk.Label(self.dex_tab, text="", wraplength=1080, foreground="#405664")
        self.dex_detail.pack(anchor="w", pady=10)

    def _rules_ui(self):
        ttk.Label(self.rules_tab, text="概率参数（百分数，可修改）", font=("Microsoft YaHei UI", 14, "bold")).pack(anchor="w")
        ttk.Label(self.rules_tab, text="显性外观按双亲各一次机会估算；隐性外观只作用于未出显性蛋的情况。性格随机部分 = 100% − 随父 − 随母。体型与声音是规划估算，非游戏保证。", wraplength=1030).pack(anchor="w", pady=8)
        self.rule_vars = {}
        with db() as connection:
            saved = {r["key"]: r["value"] for r in connection.execute("SELECT key,value FROM settings")}
        for key, label, source in RULE_INFO:
            row = ttk.Frame(self.rules_tab)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=label, width=26).pack(side="left")
            legacy = {"shiny_parent": "异色", "color_parent": "炫彩"}.get(key)
            initial = saved.get("rule:" + key, saved.get("rate:" + legacy, "") if legacy and saved.get("rate:" + legacy, "") else str(DEFAULT_RULES[key]))
            variable = tk.StringVar(value=initial)
            self.rule_vars[key] = variable
            ttk.Entry(row, textvariable=variable, width=9).pack(side="left")
            ttk.Label(row, text="%", foreground="#526875").pack(side="left", padx=(2, 15))
            ttk.Label(row, text=source, foreground="#526875").pack(side="left")
        buttons = ttk.Frame(self.rules_tab)
        buttons.pack(anchor="w", pady=10)
        ttk.Button(buttons, text="保存参数", command=self.save_rules).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="恢复全部默认值", command=self.restore_rules).pack(side="left")
        notes = (
            "声音奖牌模型：同侧×同侧常保留同侧；单侧×无牌只有小概率；相反两侧默认无牌；无牌×无牌也留极小概率。\n"
            "体重奖牌：按录入体重在图鉴成年体重区间的位置判定，落在边缘 2% 算对应奖牌；子代按双亲均值与区间 ±2% 浮动估算。\n"
            "体型多代概率用近似分布，声音只用奖牌类别；缺失原始数据会显示待确认。各特征联合概率按独立近似。详见 SOURCES.md。"
        )
        ttk.Label(self.rules_tab, text=notes, wraplength=1030, justify="left", foreground="#405664").pack(anchor="w", pady=5)

    def refresh(self):
        if not hasattr(self, "listing"):
            return
        self.refresh_records()
        self._update_query_hint()
        self.refresh_dex()

    def sort_records_by(self, column):
        if self.record_sort_column == column:
            self.record_sort_desc = not self.record_sort_desc
        else:
            self.record_sort_column = column
            self.record_sort_desc = False
        self.refresh_records()

    def refresh_records(self):
        selected_id = self.selected_id
        selected_iid = str(self.record_representative.get(selected_id, selected_id)) if selected_id is not None and hasattr(self, "record_representative") else None
        self.listing.delete(*self.listing.get_children())
        records = read_records(self.account_id())
        groups = group_breeding_records(records)
        self.record_groups = {group[0]["id"]: group for group in groups}
        self.record_representative = {record["id"]: group[0]["id"]
                                      for group in groups for record in group}
        representatives = [group[0] for group in groups]
        self.parent_choices = {
            f"#{r['id']} · {r['name']}（{PETS.get(r['pet_id'], {}).get('name', '?')}）"
            + (f" ×{len(self.record_groups[r['id']])}" if len(self.record_groups[r['id']]) > 1 else ""): r["id"]
            for r in representatives}
        record_sexes = {r["id"]: r["sex"] for r in representatives}
        for picker, variable, sex in ((self.mother_picker, self.mother_target, "母"),
                                      (self.father_picker, self.father_target, "公")):
            choices = ["", *(label for label, record_id in self.parent_choices.items()
                             if record_sexes[record_id] == sex)]
            picker.configure(values=choices)
            if variable.get() not in choices:
                variable.set("")
        edge = self.display_rules()["size_edge"] * 100
        visible = []
        for r in representatives:
            if not record_matches_filters(r, edge, self.record_size_medal_filter.get(),
                                          self.record_voice_medal_filter.get(),
                                          self.record_shiny_filter.get(), self.record_colorful_filter.get()):
                continue
            count = len(self.record_groups[r["id"]])
            name = r["name"] + (f" ×{count}" if count > 1 else "")
            visible.append((r, (name, PETS.get(r["pet_id"], {}).get("name", "?"),
                                r["sex"], record_features(r, edge))))
        if self.record_sort_column is not None:
            index = next(i for i, (column, _, _) in enumerate(self.record_columns)
                         if column == self.record_sort_column)
            visible.sort(key=lambda item: (dex_text_key(item[1][index]), item[0]["id"]),
                         reverse=self.record_sort_desc)
        for column, label, _ in self.record_columns:
            arrow = (" ↓" if self.record_sort_desc else " ↑") if column == self.record_sort_column else ""
            self.listing.heading(column, text=label + arrow)
        for r, values in visible:
            self.listing.insert("", "end", iid=str(r["id"]), values=values)
        if selected_iid is not None:
            if self.listing.exists(selected_iid):
                self.listing.selection_set(selected_iid)
                self.after_idle(lambda record_id=selected_id: self._restore_record_variant(record_id))
            else:
                self.clear_record()

    def _restore_record_variant(self, record_id):
        selection = self.listing.selection()
        if not selection or not any(r["id"] == record_id for r in self.record_groups.get(int(selection[0]), [])):
            return
        self.select_record()
        label = next((label for label, value in self.record_variant_choices.items()
                      if value == record_id), None)
        if label is not None:
            self.record_variant.set(label)
            self._load_record(record_id)

    def update_pet_preview(self):
        if not hasattr(self, "pet_info"):
            return
        pet_id = self.resolve_pet(self.fields["pet_display"].get())
        if not pet_id:
            self.pet_info.configure(text="输入图鉴中的完整精灵名，或点下拉箭头选择匹配项。")
            return
        pet = PETS[pet_id]
        specimen = {"pet_id": pet_id, "size_raw": self.fields["size_raw"].get()}
        edge = self.display_rules()["size_edge"] * 100
        self.pet_info.configure(text=f"图鉴 {pet['number']} · 蛋组 {', '.join(pet['egg_groups']) or '未发现'} · 成年体重：{pet.get('adult_weight_range') or '?'} · 体重奖牌：{inferred_size(specimen, edge)}（按当前边缘参数判定）")

    def clear_record(self):
        self.selected_id = None
        self.record_variant.set("")
        self.record_variant_picker.configure(values=[])
        self._nature_syncing = True
        for variable in self.fields.values():
            variable.set("")
        self._nature_syncing = False
        self._sync_nature("name", self.fields, self.record_nature_widgets)
        self.shiny.set(False)
        self.colorful.set(False)
        self.listing.selection_remove(self.listing.selection())

    def select_record(self, _event=None):
        selection = self.listing.selection()
        if not selection:
            return
        representative_id = int(selection[0])
        matching = self.record_groups.get(representative_id, [])
        self.record_variant_choices = {f"#{record['id']} · {record['name']}": record["id"]
                                       for record in matching}
        self.record_variant_picker.configure(values=list(self.record_variant_choices))
        if self.record_variant_choices:
            self.record_variant.set(next(iter(self.record_variant_choices)))
            self._load_record(self.record_variant_choices[self.record_variant.get()])

    def select_record_variant(self, _event=None):
        record_id = self.record_variant_choices.get(self.record_variant.get())
        if record_id is not None:
            self._load_record(record_id)

    def _load_record(self, record_id):
        with db() as connection:
            row = connection.execute("SELECT * FROM specimens WHERE id=? AND account=?", (record_id, self.account_id())).fetchone()
        if not row:
            return
        self.selected_id = record_id
        self._nature_syncing = True
        for key, variable in self.fields.items():
            if key == "pet_display":
                value = self.display_by_id.get(row["pet_id"], "")
            else:
                value = row[key] or ""
            variable.set(value)
        self._nature_syncing = False
        self._sync_nature("name" if self.fields["nature_name"].get() else "plus", self.fields, self.record_nature_widgets)
        self.shiny.set(bool(row["shiny"]))
        self.colorful.set(bool(row["colorful"]))

    def save_record(self):
        values = {key: var.get().strip() for key, var in self.fields.items()}
        pet_id = self.resolve_pet(values.pop("pet_display"))
        if not pet_id or values["sex"] not in ("公", "母"):
            messagebox.showerror("信息不完整", "请输入图鉴中的精灵全名（或从筛选列表选择），并选择公或母。")
            return
        name = values["name"] or PETS[pet_id]["name"]
        for key in ("size_raw",):
            if values[key]:
                try:
                    if float(values[key]) < 0:
                        raise ValueError
                except ValueError:
                    messagebox.showerror("体重数值有误", "体重请输入非负数字。")
                    return
        nature_name = values["nature_name"]
        pair = (values["nature_plus"], values["nature_minus"])
        if nature_name and nature_name not in NATURES:
            messagebox.showerror("性格有误", "请输入列表中的完整原始性格名，或选择加成和减益属性。")
            return
        if any(pair) and pair not in NATURE_BY_PAIR:
            messagebox.showerror("性格有误", "原始性格的加成和减益需各选一项，且不能相同。")
            return
        if nature_name and pair in NATURE_BY_PAIR and NATURES[nature_name] != pair:
            messagebox.showerror("性格冲突", "性格名与加成、减益属性不一致。")
            return
        if nature_name:
            values["nature_plus"], values["nature_minus"] = NATURES[nature_name]
        elif pair in NATURE_BY_PAIR:
            values["nature_name"] = NATURE_BY_PAIR[pair]
        columns = ("account", "name", "pet_id", "sex", "size_raw", "voice_label", "shiny", "colorful", "notes", "nature_name", "nature_plus", "nature_minus")
        payload = (self.account_id(), name, pet_id, values["sex"], values["size_raw"], values["voice_label"], int(self.shiny.get()), int(self.colorful.get()), values["notes"], values["nature_name"], values["nature_plus"], values["nature_minus"])
        with db() as connection:
            if self.selected_id:
                connection.execute("UPDATE specimens SET " + ",".join(f"{c}=?" for c in columns) + " WHERE id=? AND account=?", payload + (self.selected_id, self.account_id()))
            else:
                connection.execute("INSERT INTO specimens (" + ",".join(columns) + ") VALUES (" + ",".join("?" for _ in columns) + ")", payload)
        self.clear_record()
        self.refresh()

    def delete_record(self):
        if not self.selected_id:
            return
        if not messagebox.askyesno("删除记录", "确认删除这只精灵的记录？"):
            return
        with db() as connection:
            connection.execute("DELETE FROM specimens WHERE id=? AND account=?", (self.selected_id, self.account_id()))
        self.clear_record()
        self.refresh()

    def save_rules(self):
        try:
            rules = self.current_rules()
        except ValueError:
            messagebox.showerror("参数有误", "所有参数须为 0–100；性格父母合计≤100，声音相反/无牌每侧≤50，体型奖牌边缘≤50。")
            return
        with db() as connection:
            for key in DEFAULT_RULES:
                connection.execute("INSERT OR REPLACE INTO settings(key,value) VALUES (?,?)", ("rule:" + key, str(rules[key] * 100)))
        messagebox.showinfo("已保存", "概率参数已保存到本机。")

    def current_rules(self) -> dict[str, float]:
        if not hasattr(self, "rule_vars") or not self.rule_vars:
            return {key: value / 100 for key, value in DEFAULT_RULES.items()}
        rules = {}
        for key, var in self.rule_vars.items():
            value = float(var.get().strip())
            if not math.isfinite(value) or not 0 <= value <= 100:
                raise ValueError(key)
            rules[key] = value / 100
        if (rules["nature_male"] + rules["nature_female"] > 1 + 1e-12
                or rules["voice_opposite"] > .5 or rules["voice_neither"] > .5
                or rules["size_edge"] > .5):
            raise ValueError("combination")
        return rules

    def display_rules(self) -> dict[str, float]:
        try:
            return self.current_rules()
        except ValueError:
            return {key: value / 100 for key, value in DEFAULT_RULES.items()}

    def restore_rules(self):
        for key, value in DEFAULT_RULES.items():
            self.rule_vars[key].set(str(value))
        with db() as connection:
            connection.execute("DELETE FROM settings WHERE key LIKE 'rule:%'")
            connection.execute("DELETE FROM settings WHERE key LIKE 'rate:%'")
        self.refresh()
        messagebox.showinfo("已恢复默认", "全部参数已恢复默认，并保存到本机。")

    def run_query(self):
        self._flush_query_options()
        target_text = self.target_pet.get().strip()
        pet_id = self.resolve_pet(target_text) if target_text else None
        mother_id = self.parent_choices.get(self.mother_target.get())
        father_id = self.parent_choices.get(self.father_target.get())
        if target_text and not pet_id:
            messagebox.showerror("目标精灵有误", "请从目标精灵列表选择精灵，或留空。")
            return
        if not any((pet_id, mother_id, father_id)):
            messagebox.showerror("查询条件不足", "目标精灵、母本、父本至少填写一项。")
            return
        records = read_records(self.account_id())
        targets = [t for t, var in self.target_vars.items() if var.get()]
        nature = (self.nature_target.get(), self.plus_target.get(), self.minus_target.get())
        if nature[0] and ((nature[1] and NATURES[nature[0]][0] != nature[1]) or (nature[2] and NATURES[nature[0]][1] != nature[2])):
            messagebox.showerror("性格目标冲突", "完整性格与所选加成或减益属性不一致。")
            return
        if nature[1] and nature[1] == nature[2]:
            messagebox.showerror("性格目标冲突", "同一属性不能既是加成又是减益。")
            return
        if ({"大块头", "小不点"} <= set(targets)) or ({"婉转声", "粗嗓门"} <= set(targets)):
            messagebox.showerror("目标冲突", "同一只精灵不能同时选两种相反的体型或声音奖牌。")
            return
        try:
            rules = self.current_rules()
        except ValueError:
            messagebox.showerror("参数有误", "请先修正概率参数。")
            return
        results = search(records, pet_id, targets, self.generations.get(), rules, nature,
                         mother_id=mother_id, father_id=father_id,
                         allow_unrecorded=self.allow_unrecorded.get())
        target_label = (f"{PETS[pet_id]['name']}（孵化形态：{PETS[PETS[pet_id]['family_base_id']]['name']}；含同编号形态）"
                        if pet_id else "不限")
        heading = f"目标精灵：{target_label}  |  {self.account.get()}  |  最多 {self.generations.get()} 代"
        self._set_results("")
        self.result_targets = targets
        self.result_nature = nature
        if not records and not self.allow_unrecorded.get():
            self.query_status.configure(text=heading + "。当前账号尚未录入亲本；可开启“允许未录入亲本”。")
        elif not results:
            self.query_status.configure(text=heading + "。没有找到满足目标的兼容路线；可调整亲本、目标或代数。")
        else:
            self.result_groups = sorted(group_final_routes(results), key=result_number_key)
            cap_hint = "；已达到 200 组显示上限，可能还有其他路线" if len(self.result_groups) >= 200 else ""
            self.query_status.configure(text=heading + f"。显示 {len(self.result_groups)} 组最终配对{cap_hint}；列表显示代表路线的首代父母和最终子代，双击查看各条完整路线及概率。")
            for index, group in enumerate(self.result_groups):
                candidate = next(iter(group["variants"].values()))
                route_count = len({variant.route for variant in group["candidates"]})
                if candidate.conditional_medal_parents:
                    note = "须先孵出带牌亲本；详见概率"
                elif route_count > 1:
                    note = "多条完整路线；双击查看"
                elif retained_zero_route(candidate, targets, nature):
                    note = "单亲有目标奖牌；详见概率"
                else:
                    note = "双击查看步骤"
                father = first_generation_summary(candidate, "father")
                mother = first_generation_summary(candidate, "mother")
                generations = sorted({len(variant.route) for variant in group["candidates"]})
                virtual_counts = sorted({len(variant.virtual_keys) for variant in group["candidates"]})
                self.results.insert("", "end", iid=str(index), values=(
                    "/".join(map(str, generations)), father, mother, child_label(group),
                    "/".join(map(str, virtual_counts)), note))

    def sort_dex_by(self, column):
        if self.dex_sort_column == column:
            self.dex_sort_desc = not self.dex_sort_desc
        else:
            self.dex_sort_column = column
            self.dex_sort_desc = False
        self.refresh_dex()

    def refresh_dex(self):
        if not hasattr(self, "dex_list"):
            return
        needle = self.dex_search.get().strip().lower()
        season_filter = self.dex_season.get()
        shiny_only = self.dex_shiny.get()
        pets = []
        for pet in CATALOG["pets"]:
            if season_filter != "全部" and pet.get("season") != (None if season_filter == "无赛季" else season_filter):
                continue
            if shiny_only and not pet.get("has_shiny"):
                continue
            hay = " ".join((pet["name"] or "", pet["number"] or "", *pet["egg_groups"])).lower()
            if not needle or needle in hay:
                pets.append(pet)
        pets.sort(key=lambda pet: (dex_number_key(pet), dex_text_key(pet["name"]), pet["id"]))
        known = [pet for pet in pets if dex_primary_value(pet, self.dex_sort_column) is not None]
        unknown = [pet for pet in pets if dex_primary_value(pet, self.dex_sort_column) is None]
        known.sort(key=lambda pet: dex_primary_value(pet, self.dex_sort_column), reverse=self.dex_sort_desc)
        for col, label, _ in self.dex_columns:
            arrow = (" ↓" if self.dex_sort_desc else " ↑") if col == self.dex_sort_column else ""
            self.dex_list.heading(col, text=label + arrow)
        self.dex_list.delete(*self.dex_list.get_children())
        self.dex_detail.configure(text="")
        for pet in known + unknown:
            ratio = pet.get("gender_ratio") or {}
            sex = f"公 {ratio.get('male','?')} : 母 {ratio.get('female','?')}"
            weight = pet.get("adult_weight_range") or "未知"
            self.dex_list.insert("", "end", iid=pet["id"], values=(
                pet["number"], pet["name"], ", ".join(pet["egg_groups"]) or "未发现",
                sex, weight))

    def show_dex_detail(self, _event=None):
        selection = self.dex_list.selection()
        if not selection:
            return
        pet = PETS[selection[0]]
        text = (f"{pet['name']}｜图鉴 {pet['number']}｜归属赛季 {pet.get('season') or '无'}"
                f"｜异色 {'有' if pet.get('has_shiny') else '无'}"
                f"｜成年体重范围 {pet.get('adult_weight_range') or '未知'}"
                f"｜成年身高范围 {pet.get('adult_height_range') or '未知'}")
        self.dex_detail.configure(text=text)


if __name__ == "__main__":
    App().mainloop()
