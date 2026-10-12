"""Local desktop GUI for a personal Roco Kingdom: World breeding notebook."""
from __future__ import annotations

import sqlite3
import tkinter as tk
import uuid
from contextlib import contextmanager
from tkinter import messagebox, simpledialog, ttk

from engine import CATALOG, PETS, ROOT, TRAITS, inferred_size, record_traits, search, target_chance

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
    return "待确认" if value is None else f"{value * 100:.2f}%"


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
        right = ttk.Frame(pane)
        pane.add(left, weight=3)
        pane.add(right, weight=2)
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
            widget = PetCombobox(right, var, values) if key == "pet_display" else ttk.Combobox(right, textvariable=var, values=values, state="readonly") if values else ttk.Entry(right, textvariable=var)
            widget.pack(fill="x", padx=(0, 4))
            self.fields[key] = var
        field("自定义昵称（可留空，自动用精灵名）", "name")
        field("精灵名称（可直接输入全名，或选筛选结果）", "pet_display", self.pet_choices)
        field("性别", "sex", ["公", "母"])
        field("成年精灵体重（kg，如 3.142）", "size_raw")
        field("成年精灵身高（m，可选；体型倾向需同时录入）", "height_raw")
        field("声音标签", "voice_label", ["", "普通", "婉转声", "粗嗓门"])
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
        ttk.Label(self.query_tab, text="目标特征（只显示当前账号记录中有来源的特征；体型是成年身高和体重的估计倾向，非已确认奖牌）").pack(anchor="w", pady=(14, 4))
        trait_frame = ttk.Frame(self.query_tab)
        trait_frame.pack(fill="x")
        self.target_vars = {t: tk.BooleanVar() for t in TRAITS}
        self.trait_widgets = {}
        for i, trait in enumerate(TRAITS):
            widget = ttk.Checkbutton(trait_frame, text=trait, variable=self.target_vars[trait])
            widget.grid(row=0, column=i, padx=10, sticky="w")
            self.trait_widgets[trait] = widget
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
        self.dex_list = ttk.Treeview(self.dex_tab, columns=("number", "name", "groups", "sex", "egg"), show="headings")
        for col, label, width in (("number", "编号", 75), ("name", "精灵", 170), ("groups", "蛋组", 200), ("sex", "雌雄比例", 110), ("egg", "蛋重范围", 160)):
            self.dex_list.heading(col, text=label)
            self.dex_list.column(col, width=width)
        self.dex_list.pack(fill="both", expand=True)
        self.dex_list.bind("<<TreeviewSelect>>", self.show_dex_detail)
        self.dex_detail = ttk.Label(self.dex_tab, text="", wraplength=1080, foreground="#405664")
        self.dex_detail.pack(anchor="w", pady=10)

    def _rules_ui(self):
        ttk.Label(self.rules_tab, text="概率参数", font=("Microsoft YaHei UI", 14, "bold")).pack(anchor="w")
        ttk.Label(self.rules_tab, text="填每一位拥有目标特征的亲本向子代传递该特征的概率（0–100%）。空白表示未知。两亲本机会按独立事件近似合并；不同目标特征的合并也是假设独立，不能视作游戏官方概率。", wraplength=1030).pack(anchor="w", pady=8)
        self.rule_vars = {}
        with db() as connection:
            saved = {r["key"]: r["value"] for r in connection.execute("SELECT key,value FROM settings")}
        for trait in TRAITS:
            row = ttk.Frame(self.rules_tab)
            row.pack(fill="x", pady=3)
            ttk.Label(row, text=trait, width=11).pack(side="left")
            variable = tk.StringVar(value=saved.get("rate:" + trait, ""))
            self.rule_vars[trait] = variable
            ttk.Entry(row, textvariable=variable, width=9).pack(side="left")
            ttk.Label(row, text="%", foreground="#526875").pack(side="left")
        ttk.Button(self.rules_tab, text="保存参数", command=self.save_rules).pack(anchor="w", pady=10)
        notes = (
            "已核对：一公一母且共享蛋组；子代物种随母方。未发现蛋组不参与配对。\n"
            "体型：按成年身高和体重在图鉴范围内的位置，取两者都在边缘 2% 为倾向；这不是已验证的游戏判牌公式。声音直接记录游戏可见的类别。\n"
            "其他活动、时间、地区奖牌不录入、不参与计算。\n"
            "异色/炫彩：亲本有此特征会提高子代出现机会，但网上数字相互矛盾，默认不填概率。\n"
            "数据源：洛克王国世界 WIKI 的图鉴数据镜像，2026-09-24 版本。详见 README.md 与 SOURCES.md。"
        )
        ttk.Label(self.rules_tab, text=notes, wraplength=1030, justify="left", foreground="#405664").pack(anchor="w", pady=18)

    def refresh(self):
        if not hasattr(self, "listing"):
            return
        self.listing.delete(*self.listing.get_children())
        records = read_records(self.account_id())
        for r in records:
            features = [t for t, chance in record_traits(r).items() if chance]
            size = inferred_size(r)
            if size not in ("未录体重", "普通体型倾向"):
                features.append(size)
            self.listing.insert("", "end", iid=str(r["id"]), values=(r["name"], PETS.get(r["pet_id"], {}).get("name", "?"), r["sex"], ", ".join(dict.fromkeys(features))))
        possible = {t for r in records for t, value in record_traits(r).items() if value}
        missing = []
        for trait, widget in self.trait_widgets.items():
            if trait in possible:
                widget.grid()
            else:
                widget.grid_remove()
                self.target_vars[trait].set(False)
                missing.append(trait)
        self.query_hint.configure(text=("当前没有来源：" + "、".join(missing) + "。异色/炫彩/声音请补录对应个体；体型倾向需同时录成年身高与体重。已有记录会保留。" if missing else ""))
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
        self.pet_info.configure(text=f"图鉴 {pet['number']} · 蛋组 {', '.join(pet['egg_groups']) or '未发现'} · 成年范围：{pet.get('weight') or '?'} / {pet.get('height') or '?'} · 体型：{inferred_size(specimen)}（仅估计）")

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
        columns = ("account", "name", "pet_id", "sex", "size_raw", "height_raw", "voice_label", "shiny", "colorful", "notes")
        payload = (self.account_id(), name, pet_id, values["sex"], values["size_raw"], values["height_raw"], values["voice_label"], int(self.shiny.get()), int(self.colorful.get()), values["notes"])
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
            for trait, var in self.rule_vars.items():
                value = var.get().strip()
                if value and not 0 <= float(value) <= 100:
                    raise ValueError(trait)
        except ValueError:
            messagebox.showerror("参数有误", "概率请输入 0–100 的数字，或留空。")
            return
        with db() as connection:
            for trait, var in self.rule_vars.items():
                connection.execute("INSERT OR REPLACE INTO settings(key,value) VALUES (?,?)", ("rate:" + trait, var.get().strip()))
        messagebox.showinfo("已保存", "概率参数已保存到本机。")

    def run_query(self):
        pet_id = self.resolve_pet(self.target_pet.get())
        if not pet_id:
            messagebox.showerror("选择目标", "请从目标精灵列表选择精灵。")
            return
        records = read_records(self.account_id())
        targets = [t for t, var in self.target_vars.items() if var.get()]
        if ({"大块头", "小不点"} <= set(targets)) or ({"婉转声", "粗嗓门"} <= set(targets)):
            messagebox.showerror("目标冲突", "同一只精灵不能同时选两种相反的体型或声音奖牌。")
            return
        try:
            rules = {t: (float(v.get()) / 100 if v.get().strip() else None) for t, v in self.rule_vars.items()}
            if any(v is not None and not 0 <= v <= 1 for v in rules.values()):
                raise ValueError
        except ValueError:
            messagebox.showerror("参数有误", "请先修正概率参数：0–100 的数字，或留空。")
            return
        results = search(records, pet_id, targets, self.generations.get(), rules)
        base_id = PETS[pet_id]["family_base_id"]
        lines = [f"目标：{PETS[pet_id]['name']}（孵化形态：{PETS[base_id]['name']}）  |  {self.account.get()}  |  最多 {self.generations.get()} 代", ""]
        if not records:
            lines.append("当前账号尚未录入种公种母。")
        elif not results:
            lines.append("现有记录中没有找到兼容的路线。请核对性别、蛋组及目标母系。记录仍保留。")
        else:
            lines.append("概率基于您填写的参数和独立事件假设；空白参数显示待确认。体型目标依据成年身高体重估算倾向，不代表确定奖牌。中间代需实际孵出对应性别。")
            lines.append("")
            for i, candidate in enumerate(results[:50], 1):
                joint = target_chance(candidate, targets)
                lines.append(f"{i}. {len(candidate.route)} 代  ·  目标特征条件概率 {percent(joint)}  ·  中间代性别路径 {percent(candidate.probability)}")
                lines.extend("   " + step for step in candidate.route)
                lines.append("   各特征：" + "  ".join(f"{t} {percent(candidate.traits[t])}" for t in TRAITS))
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
            egg = pet.get("egg_size") or {}
            sex = f"公 {ratio.get('male','?')} : 母 {ratio.get('female','?')}"
            weight = f"{egg.get('min','?')}–{egg.get('max','?')} {egg.get('unit','')}" if egg else "未知"
            self.dex_list.insert("", "end", iid=pet["id"], values=(pet["number"], pet["name"], ", ".join(pet["egg_groups"]) or "未发现", sex, weight))

    def show_dex_detail(self, _event=None):
        selection = self.dex_list.selection()
        if not selection:
            return
        pet = PETS[selection[0]]
        egg = pet.get("egg_size") or {}
        text = f"{pet['name']}｜图鉴 {pet['number']}｜身高 {pet.get('height') or '未知'}｜体重 {pet.get('weight') or '未知'}｜大块头蛋重阈值 {egg.get('huge_min','未知')} {egg.get('unit','')}｜小不点蛋重阈值 {egg.get('mini_max','未知')} {egg.get('unit','')}"
        self.dex_detail.configure(text=text)


if __name__ == "__main__":
    App().mainloop()
