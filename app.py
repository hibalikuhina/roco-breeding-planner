"""Local desktop GUI for a personal Roco Kingdom: World breeding notebook."""
from __future__ import annotations

import sqlite3
import math
import tkinter as tk
import uuid
from contextlib import contextmanager
from tkinter import messagebox, simpledialog, ttk

from engine import (ATTRS, CATALOG, DEFAULT_RULES, NATURES, NATURE_BY_PAIR, PETS,
                    ROOT, RULE_INFO, TRAITS, inferred_size, nature_chance,
                    record_traits, search, target_chance)

DB_PATH = ROOT / "data" / "personal.sqlite3"
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
INSERT OR IGNORE INTO accounts(id,name) VALUES ('账号 1','账号 1');
INSERT OR IGNORE INTO accounts(id,name) VALUES ('账号 2','账号 2');
"""


@contextmanager
def db():
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
        self._style()
        self._layout()
        self.refresh()

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
        self.clear_record()
        self.refresh()

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
        self.listing = ttk.Treeview(left, columns=("name", "pet", "sex", "features"), show="headings", selectmode="browse")
        for col, label, width in (("name", "昵称", 130), ("pet", "精灵", 140), ("sex", "性别", 55), ("features", "特征", 300)):
            self.listing.heading(col, text=label)
            self.listing.column(col, width=width, stretch=True)
        self.listing.pack(fill="both", expand=True, padx=(0, 12))
        self.listing.bind("<<TreeviewSelect>>", self.select_record)
        self.fields = {}
        def field(label, key, values=None):
            ttk.Label(right, text=label).pack(anchor="w", pady=(6, 1))
            var = tk.StringVar()
            widget = PetCombobox(right, var, values) if key == "pet_display" else ttk.Combobox(right, textvariable=var, values=values, state="normal" if key == "nature_name" else "readonly") if values else ttk.Entry(right, textvariable=var)
            widget.pack(fill="x", padx=(0, 4))
            self.fields[key] = var
        field("自定义昵称（可留空，自动用精灵名）", "name")
        field("精灵名称（可直接输入全名，或选筛选结果）", "pet_display", self.pet_choices)
        field("性别", "sex", ["公", "母"])
        field("成年精灵体重（kg，如 3.142）", "size_raw")
        field("成年精灵身高（m，可选；体型倾向需同时录入）", "height_raw")
        field("声音标签", "voice_label", ["", "普通", "婉转声", "粗嗓门"])
        field("原始性格名（可输入或选择；修改后的性格不遗传）", "nature_name", ["", *NATURES])
        field("原始性格加成 +", "nature_plus", ["", *ATTRS])
        field("原始性格减益 −", "nature_minus", ["", *ATTRS])
        self._nature_syncing = False
        self.fields["nature_name"].trace_add("write", self._nature_from_name)
        self.fields["nature_plus"].trace_add("write", self._nature_from_pair)
        self.fields["nature_minus"].trace_add("write", self._nature_from_pair)
        self.pet_info = ttk.Label(right, text="", wraplength=380, foreground="#405664")
        self.pet_info.pack(anchor="w", pady=(6, 2))
        for key in ("pet_display", "size_raw", "height_raw"):
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

    def _nature_from_name(self, *_):
        if self._nature_syncing:
            return
        name = self.fields["nature_name"].get().strip()
        if name not in NATURES:
            return
        self._nature_syncing = True
        plus, minus = NATURES[name]
        self.fields["nature_plus"].set(plus)
        self.fields["nature_minus"].set(minus)
        self._nature_syncing = False

    def _nature_from_pair(self, *_):
        if self._nature_syncing:
            return
        pair = (self.fields["nature_plus"].get(), self.fields["nature_minus"].get())
        self._nature_syncing = True
        self.fields["nature_name"].set(NATURE_BY_PAIR.get(pair, ""))
        self._nature_syncing = False

    def _query_ui(self):
        top = ttk.Frame(self.query_tab)
        top.pack(fill="x")
        ttk.Label(top, text="目标精灵").grid(row=0, column=0, sticky="w")
        self.target_pet = tk.StringVar()
        PetCombobox(top, self.target_pet, self.pet_choices, width=48).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Label(top, text="最多几代").grid(row=0, column=2, padx=(16, 5))
        self.generations = tk.IntVar(value=1)
        ttk.Combobox(top, textvariable=self.generations, values=[1, 2, 3], state="readonly", width=5).grid(row=0, column=3)
        ttk.Button(top, text="查询路线", command=self.run_query).grid(row=0, column=4, padx=16)
        top.columnconfigure(1, weight=1)
        ttk.Label(self.query_tab, text="目标特征（异色/炫彩包含普通蛋的隐性概率；体型是成年数据估算）").pack(anchor="w", pady=(14, 4))
        trait_frame = ttk.Frame(self.query_tab)
        trait_frame.pack(fill="x")
        self.target_vars = {t: tk.BooleanVar() for t in TRAITS}
        self.trait_widgets = {}
        for i, trait in enumerate(TRAITS):
            widget = ttk.Checkbutton(trait_frame, text=trait, variable=self.target_vars[trait])
            widget.grid(row=0, column=i, padx=10, sticky="w")
            self.trait_widgets[trait] = widget
        nature_row = ttk.Frame(self.query_tab)
        nature_row.pack(fill="x", pady=(10, 2))
        self.nature_target = tk.StringVar()
        self.plus_target = tk.StringVar()
        self.minus_target = tk.StringVar()
        for label, var, choices, width in (("完整性格", self.nature_target, ["", *NATURES], 16),
                                           ("只看 +", self.plus_target, ["", *ATTRS], 10),
                                           ("只看 −", self.minus_target, ["", *ATTRS], 10)):
            ttk.Label(nature_row, text=label).pack(side="left", padx=(8, 3))
            ttk.Combobox(nature_row, textvariable=var, values=choices, state="readonly", width=width).pack(side="left", padx=(0, 12))
        ttk.Label(self.query_tab, text="三项可分别筛选；同时选择时需指向同一种性格。空白表示不限。", foreground="#526875").pack(anchor="w")
        self.query_hint = ttk.Label(self.query_tab, text="", foreground="#9a5b16", wraplength=1060)
        self.query_hint.pack(anchor="w", pady=8)
        self.results = tk.Text(self.query_tab, wrap="word", font=("Microsoft YaHei UI", 10), padx=14, pady=12)
        self.results.pack(fill="both", expand=True)
        self.results.configure(state="disabled")

    def _dex_ui(self):
        top = ttk.Frame(self.dex_tab)
        top.pack(fill="x", pady=(0, 8))
        ttk.Label(top, text="搜索名称 / 编号 / 蛋组").pack(side="left")
        self.dex_search = tk.StringVar()
        entry = ttk.Entry(top, textvariable=self.dex_search)
        entry.pack(side="left", fill="x", expand=True, padx=10)
        self.dex_search.trace_add("write", lambda *_: self.refresh_dex())
        self.dex_list = ttk.Treeview(self.dex_tab, columns=("number", "name", "groups", "sex", "weight"), show="headings")
        for col, label, width in (("number", "编号", 75), ("name", "精灵", 170), ("groups", "蛋组", 200), ("sex", "雌雄比例", 110), ("weight", "成年体重范围", 160)):
            self.dex_list.heading(col, text=label)
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
            "体型：双亲分别换算到各自图鉴成年体重、身高区间的位置，再平均并按区间 ±2% 浮动；两项都落在边缘 2% 才算奖牌倾向。\n"
            "体型多代概率用近似分布，声音只用奖牌类别；缺失原始数据会显示待确认。各特征联合概率按独立近似。详见 SOURCES.md。"
        )
        ttk.Label(self.rules_tab, text=notes, wraplength=1030, justify="left", foreground="#405664").pack(anchor="w", pady=5)

    def refresh(self):
        if not hasattr(self, "listing"):
            return
        self.listing.delete(*self.listing.get_children())
        records = read_records(self.account_id())
        edge = self.display_rules()["size_edge"] * 100
        for r in records:
            features = [t for t, chance in record_traits(r, edge).items() if chance]
            nature = (r.get("nature_name") or "").strip()
            if nature:
                features.append(nature)
            size = inferred_size(r, edge)
            if size not in ("未录体重", "普通体型倾向"):
                features.append(size)
            self.listing.insert("", "end", iid=str(r["id"]), values=(r["name"], PETS.get(r["pet_id"], {}).get("name", "?"), r["sex"], ", ".join(dict.fromkeys(features))))
        possible = {t for r in records for t, value in record_traits(r, edge).items() if value}
        if any(r.get("size_raw") for r in records):
            possible.update(("大块头", "小不点"))
        if any(r.get("voice_label") == "普通" for r in records):
            possible.update(("婉转声", "粗嗓门"))
        missing = []
        for trait, widget in self.trait_widgets.items():
            if trait in possible or trait in ("异色", "炫彩"):
                widget.grid()
            else:
                widget.grid_remove()
                self.target_vars[trait].set(False)
                missing.append(trait)
        self.query_hint.configure(text=("当前缺少亲本数据：" + "、".join(missing) + "。普通蛋仍可能隐性异色/炫彩；声音请填奖牌或普通，体型请录成年身高与体重。已有记录会保留。" if missing else ""))
        self.refresh_dex()

    def update_pet_preview(self):
        if not hasattr(self, "pet_info"):
            return
        pet_id = self.resolve_pet(self.fields["pet_display"].get())
        if not pet_id:
            self.pet_info.configure(text="输入图鉴中的完整精灵名，或点下拉箭头选择匹配项。")
            return
        pet = PETS[pet_id]
        specimen = {"pet_id": pet_id, "size_raw": self.fields["size_raw"].get(), "height_raw": self.fields["height_raw"].get()}
        edge = self.display_rules()["size_edge"] * 100
        self.pet_info.configure(text=f"图鉴 {pet['number']} · 蛋组 {', '.join(pet['egg_groups']) or '未发现'} · 成年体重：{pet.get('adult_weight_range') or '?'} · 成年身高：{pet.get('adult_height_range') or '?'} · 体型：{inferred_size(specimen, edge)}（仅估计）")

    def clear_record(self):
        self.selected_id = None
        for variable in self.fields.values():
            variable.set("")
        self.shiny.set(False)
        self.colorful.set(False)
        self.listing.selection_remove(self.listing.selection())

    def select_record(self, _event=None):
        selection = self.listing.selection()
        if not selection:
            return
        record_id = int(selection[0])
        with db() as connection:
            row = connection.execute("SELECT * FROM specimens WHERE id=? AND account=?", (record_id, self.account_id())).fetchone()
        if not row:
            return
        self.selected_id = record_id
        for key, variable in self.fields.items():
            variable.set(self.display_by_id.get(row["pet_id"], "") if key == "pet_display" else row[key] or "")
        self.shiny.set(bool(row["shiny"]))
        self.colorful.set(bool(row["colorful"]))

    def save_record(self):
        values = {key: var.get().strip() for key, var in self.fields.items()}
        pet_id = self.resolve_pet(values.pop("pet_display"))
        if not pet_id or values["sex"] not in ("公", "母"):
            messagebox.showerror("信息不完整", "请输入图鉴中的精灵全名（或从筛选列表选择），并选择公或母。")
            return
        name = values["name"] or PETS[pet_id]["name"]
        for key in ("size_raw", "height_raw"):
            if values[key]:
                try:
                    if float(values[key]) < 0:
                        raise ValueError
                except ValueError:
                    messagebox.showerror("体型数值有误", "体重和身高请输入非负数字。")
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
        columns = ("account", "name", "pet_id", "sex", "size_raw", "height_raw", "voice_label", "shiny", "colorful", "notes", "nature_name", "nature_plus", "nature_minus")
        payload = (self.account_id(), name, pet_id, values["sex"], values["size_raw"], values["height_raw"], values["voice_label"], int(self.shiny.get()), int(self.colorful.get()), values["notes"], values["nature_name"], values["nature_plus"], values["nature_minus"])
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
        pet_id = self.resolve_pet(self.target_pet.get())
        if not pet_id:
            messagebox.showerror("选择目标", "请从目标精灵列表选择精灵。")
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
        results = search(records, pet_id, targets, self.generations.get(), rules, nature)
        base_id = PETS[pet_id]["family_base_id"]
        lines = [f"目标：{PETS[pet_id]['name']}（孵化形态：{PETS[base_id]['name']}）  |  {self.account.get()}  |  最多 {self.generations.get()} 代", ""]
        if not records:
            lines.append("当前账号尚未录入种公种母。")
        elif not results:
            lines.append("现有记录中没有找到兼容的路线。请核对性别、蛋组及目标母系。记录仍保留。")
        else:
            lines.append("概率基于玩家资料及可修改的假设参数；体型、声音与跨特征联合概率均为估算。体型需要成年体重和身高；中间代需实际孵出对应性别。")
            lines.append("")
            for i, candidate in enumerate(results[:50], 1):
                joint = target_chance(candidate, targets, nature)
                lines.append(f"{i}. {len(candidate.route)} 代  ·  目标特征条件概率 {percent(joint)}  ·  中间代性别路径 {percent(candidate.probability)}")
                lines.extend("   " + step for step in candidate.route)
                lines.append("   各特征：" + "  ".join(f"{t} {percent(candidate.traits[t])}" for t in TRAITS))
                lines.append("   外观拆分：" + "  ".join(f"{t} 显性 {percent(candidate.visible[t])} / 隐性 {percent(candidate.hidden[t])}" for t in ("异色", "炫彩")))
                if any(nature):
                    lines.append(f"   性格目标：完整={nature[0] or '不限'}  +{nature[1] or '不限'}  −{nature[2] or '不限'}  → {percent(nature_chance(candidate, *nature))}")
                lines.append("")
            if len(results) > 50:
                lines.append(f"另有 {len(results)-50} 条路线未展示。")
        self.results.configure(state="normal")
        self.results.delete("1.0", "end")
        self.results.insert("end", "\n".join(lines))
        self.results.configure(state="disabled")

    def refresh_dex(self):
        if not hasattr(self, "dex_list"):
            return
        needle = self.dex_search.get().strip().lower()
        self.dex_list.delete(*self.dex_list.get_children())
        for pet in CATALOG["pets"]:
            hay = " ".join((pet["name"] or "", pet["number"] or "", *pet["egg_groups"])).lower()
            if needle and needle not in hay:
                continue
            ratio = pet.get("gender_ratio") or {}
            sex = f"公 {ratio.get('male','?')} : 母 {ratio.get('female','?')}"
            weight = pet.get("adult_weight_range") or "未知"
            self.dex_list.insert("", "end", iid=pet["id"], values=(pet["number"], pet["name"], ", ".join(pet["egg_groups"]) or "未发现", sex, weight))

    def show_dex_detail(self, _event=None):
        selection = self.dex_list.selection()
        if not selection:
            return
        pet = PETS[selection[0]]
        text = f"{pet['name']}｜图鉴 {pet['number']}｜成年体重范围 {pet.get('adult_weight_range') or '未知'}｜成年身高范围 {pet.get('adult_height_range') or '未知'}"
        self.dex_detail.configure(text=text)


if __name__ == "__main__":
    App().mainloop()
