#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
glossary_xlsx_import.py — 译者姐姐的 6 份新 xlsx 译名表：
  解析(多 sheet/多格式) -> 冲突报告 -> 并入 dict/mistborn.json

用法:
  .venv/bin/python scripts/glossary_xlsx_import.py --stage parse   # -> state/glossary_xlsx_import/records.json
  .venv/bin/python scripts/glossary_xlsx_import.py --stage report  # -> conflicts.md / conflicts.json
  .venv/bin/python scripts/glossary_xlsx_import.py --stage merge   # 备份后并入（幂等），冲突不覆盖
  .venv/bin/python scripts/glossary_xlsx_import.py --stage all

原则:
  - 现有 dict/mistborn.json 优先（书证/用户口径），冲突只报告不覆盖。
  - 新表之间冲突按 FILES 优先级择一，其余记入报告 + 备注。
  - 有英文无中文的行 -> pending（需书证采证），不入主表。
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import shutil
import warnings
from collections import OrderedDict
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

import openpyxl

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "dict" / "raw"
OUTDIR = ROOT / "state" / "glossary_xlsx_import"
GLOSSARY = ROOT / "dict" / "mistborn.json"
KEEP_EN = ROOT / "dict" / "keep_en.json"

# 来源优先级（新表互相冲突时择优先级高者）
FILES = [
    "迷雾之子译名表.xlsx",
    "无界秘典译名表.xlsx",
    "飓光志译名表.xlsx",
    "伊岚翠译名表.xlsx",
    "破战者译名表.xlsx",
    "三界宙翻译勘误表.xlsx",
]
PRIORITY = {f: i for i, f in enumerate(FILES)}

# (文件, sheet) -> 解析方式; opts: pairs=取值列对, label=行标签
SHEET_CFG = {
    ("三界宙翻译勘误表.xlsx", "最后帝国"): {"kind": "errata"},
    ("三界宙翻译勘误表.xlsx", "王者之路"): {"kind": "errata"},
    ("伊岚翠译名表.xlsx", "伊岚翠"): {"kind": "std"},
    ("伊岚翠译名表.xlsx", "艾欧符文表"): {"kind": "runes"},
    ("伊岚翠译名表.xlsx", "皇帝魂"): {"kind": "skip"},
    ("破战者译名表.xlsx", "破战者"): {"kind": "std"},
    ("破战者译名表.xlsx", "译者提供的译名表"): {"kind": "concat1"},
    ("迷雾之子译名表.xlsx", "迷雾之子"): {"kind": "std"},
    ("迷雾之子译名表.xlsx", "金属技艺"): {"kind": "metals"},
    ("飓光志译名表.xlsx", "总表"): {"kind": "std"},
    ("飓光志译名表.xlsx", "章节标题"): {"kind": "skip"},
    ("飓光志译名表.xlsx", "章节题词"): {"kind": "skip"},
    ("飓光志译名表.xlsx", "生造语"): {"kind": "conlang"},
    ("飓光志译名表.xlsx", "诅咒语"): {"kind": "curses"},
    ("飓光志译名表.xlsx", "光辉骑士团"): {"kind": "rowzip", "label": "光辉骑士团"},
    ("飓光志译名表.xlsx", "令使"): {
        "kind": "heralds",
        "pairs": [(2, 3), (4, 5), (6, 7), (8, 9), (12, 13), (14, 15)],
    },
    ("飓光志译名表.xlsx", "灵体"): {"kind": "std"},
    ("飓光志译名表.xlsx", "歌者"): {"kind": "std"},
    ("飓光志译名表.xlsx", "融族"): {"kind": "fused"},
    ("飓光志译名表.xlsx", "灭者"): {"kind": "paircols", "pairs": [(0, 1), (2, 3), (4, 5)]},
    ("飓光志译名表.xlsx", "三界宙术语"): {"kind": "std"},
    ("飓光志译名表.xlsx", "三界宙魔法体系"): {"kind": "paircols", "pairs": [(0, 1), (2, 3), (4, 5)]},
    ("飓光志译名表.xlsx", "三界宙天体"): {"kind": "std"},
    ("飓光志译名表.xlsx", "裂影界"): {"kind": "std"},
    ("飓光志译名表.xlsx", "调试用"): {"kind": "pair2"},
    ("飓光志译名表.xlsx", "Sheet17"): {"kind": "skip"},
}
WILDCARD_CFG = {"kind": "std"}  # 无界秘典译名表.xlsx 各 sheet 未列出时

# 疑似台版用词（用于给冲突打标，供人工裁定参考）
TAIWAN_MARKERS = [
    "斯卡德利亚", "依兰黛尔", "伊兰黛尔", "和谐之主", "寰宇", "史坦敦",
    "独盟", "奥迪厄姆", "金属艺术", "拉剎克", "霍伊得",
]

CJK = re.compile(r"[㐀-䶿一-鿿]")
LATIN3 = re.compile(r"[A-Za-z]{3,}")
SEP = re.compile(r"[．․‧•∙⋅]")
PAREN_END = re.compile(r"\s*[（(]([^）)]*)[）)]\s*$")


def has_cjk(s: str) -> bool:
    return bool(CJK.search(s or ""))


def cell(v) -> str:
    return "" if v is None else str(v).strip()


def concat_split(s: str):
    """'Basic Metals 基础金属' -> ('Basic Metals', '基础金属')；纯中文标签/中英夹杂返回 None。"""
    m = CJK.search(s or "")
    if not m:
        return None
    en, zh = s[: m.start()].strip(), s[m.start():].strip()
    if not en or not zh:
        return None
    if LATIN3.search(zh):  # zh 段仍夹英文 -> 不是对译
        return None
    return en, zh


def strip_numbering(s: str) -> str:
    for p in (r"^\d+-\d+\s+(?=[A-Za-z])", r"^\d+\.\d+\s+(?=[A-Za-z])", r"^\d+\s*[-–—]\s+(?=[A-Za-z])"):
        s2 = re.sub(p, "", s)
        if s2 != s:
            return s2
    return s


def canon_key(s: str) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip())
    return strip_numbering(s)


def strip_paren(s: str) -> str:
    return re.sub(r"\s*[（(][^）)]*[）)]\s*$", "", s or "").strip()


def en_ok(en: str) -> bool:
    """key 至少含一个字母，且非 XX 占位符。"""
    return bool(en) and bool(re.search(r"[A-Za-z]", en)) and not re.fullmatch(r"[Xx]{1,5}", en)


def zh_full(s: str) -> str:
    return re.sub(r"\s+", "", SEP.sub("·", (s or "").strip()))


def zh_core(s: str) -> str:
    s = PAREN_END.sub("", (s or "").strip())
    s = SEP.sub("·", s)
    return re.sub(r"[\s·]", "", s)


def zh_equal(a: str, b: str) -> bool:
    if not a or not b:
        return False
    return zh_full(a) == zh_full(b) or zh_core(a) == zh_core(b)


def split_zh(zh: str):
    """-> (primary, extras[], paren)：多行/斜杠为别译，' - '/—— 后为释义、行尾括号剥离。"""
    raw_lines = [l.strip() for l in (zh or "").split("\n") if l.strip()]
    if not raw_lines:
        return "", [], ""
    terms: list[str] = []
    gloss: list[str] = []
    for l in raw_lines:
        segs = [x.strip() for x in re.split(r"\s*——\s*|\s+[-–—]\s+", l) if x.strip()]
        if segs:
            terms.append(segs[0])
            gloss += segs[1:]
    parts: list[str] = []
    for t in terms:
        parts += [x.strip() for x in t.split("/") if x.strip()]
    if not parts:
        return "", [], ""
    primary, extras = parts[0], parts[1:]
    paren = ""
    m = PAREN_END.search(primary)
    if m:
        paren = m.group(1).strip()
        primary = primary[: m.start()].strip()
    if gloss:
        paren = (paren + "；" if paren else "") + " ".join(gloss)
    return primary, extras, paren


@dataclass
class Record:
    file: str
    sheet: str
    row: int
    en: str
    zh: str = ""
    kind: str = "term"  # term|derived|metal|curse|rune|...
    note: str = ""
    first: str = ""
    extras: list = field(default_factory=list)
    paren: str = ""

    @property
    def src(self) -> str:
        return f"raw/{self.file}#{self.sheet}"


# ---------------------------------------------------------------- 解析（按 sheet 格式分派）

HDR_MAP = {
    "原名": "en", "原名（区分大小写）": "en", "原名(区分大小写)": "en",
    "标准译名": "zh", "译名": "zh",
    "首次出现": "first", "衍生用法": "derived",
    "注释": "note", "备注": "note",
}


def load_rows(ws) -> list[tuple[int, list]]:
    out = []
    for i, r in enumerate(ws.iter_rows(values_only=True), start=1):
        vals = list(r)
        if any(cell(c) for c in vals):
            out.append((i, vals))
    return out


def _get(r, i):
    return cell(r[i]) if i is not None and i < len(r) else ""


def add_pending(pend, file, sheet, row, en, note="", first=""):
    en = canon_key(en)
    if en_ok(en) and not has_cjk(en):
        pend.append({"file": file, "sheet": sheet, "row": row, "en": en,
                     "note": note, "first": first})


def add_pair(recs, file, sheet, row, en0, zh0, kind="term", note="", first="", label=""):
    """统一入口：拆 zh（别译/括号）、规范 en key；en 无效或 zh 空则不入。"""
    en = canon_key(en0)
    if not en or has_cjk(en) or not en_ok(en):
        return False
    primary, extras, paren = split_zh(zh0)
    if not primary:
        return False
    recs.append(Record(file, sheet, row, en, primary, kind, note, first, extras, paren))
    if label:
        recs[-1].note = (recs[-1].note + "；" if recs[-1].note else "") + label
    return True


def extract_derived(text, file, sheet, row, parent_en, recs):
    """衍生用法列 -> 'Arguois caverns阿谷瓦山洞' 形式的额外对译。"""
    for line in re.split(r"[\n;；]", text or ""):
        line = line.strip()
        if not line or not has_cjk(line):
            continue
        sp = concat_split(line)
        if not sp:
            continue
        en, zh = sp
        if canon_key(en).casefold() == canon_key(parent_en).casefold():
            continue
        add_pair(recs, file, sheet, row, en, zh, kind="derived")


def h_std(cfg, file, sheet, rows, res):
    """标准表头: 原名/标准译名/[首次出现]/衍生用法/注释/备注 ..."""
    recs, pend, notes = res["records"], res["pending"], res["notes"]
    header = rows[0][1]
    idx: dict[str, list[int]] = {}
    for i, c in enumerate(header):
        k = HDR_MAP.get(cell(c))
        if k:
            idx.setdefault(k, []).append(i)
    if "en" not in idx:  # 无表头（防御）
        return h_pair2(cfg, file, sheet, rows, res)
    en_i, zh_i = idx["en"][0], idx.get("zh", [1])[0]
    note_i = idx.get("note", [])
    first_i = idx.get("first", [None])[0] if "first" in idx else None
    der_i = idx.get("derived", [None])[0] if "derived" in idx else None
    for rn, r in rows[1:]:
        en0, zh0 = _get(r, en_i), _get(r, zh_i)
        if not en0:
            continue
        note = "；".join(x for x in (_get(r, i) for i in note_i) if x)
        first = _get(r, first_i) if first_i is not None else ""
        derived = _get(r, der_i) if der_i is not None else ""
        if has_cjk(en0):
            if zh0:
                notes.append({"kind": "malformed", "file": file, "sheet": sheet, "row": rn, "text": en0})
                continue
            sp = concat_split(en0)
            if not sp:
                notes.append({"kind": "label_skip", "file": file, "sheet": sheet, "row": rn, "text": en0})
                continue
            en0, zh0 = sp
        if len(note) > 400:
            note = note[:400] + "…"
        if not add_pair(recs, file, sheet, rn, en0, zh0, note=note, first=first):
            add_pending(pend, file, sheet, rn, en0, note, first)
        if derived:
            extract_derived(derived, file, sheet, rn, en0, recs)


def h_pair2(cfg, file, sheet, rows, res):
    """无表头两列: col0=en, col1=zh（调试用 等）。"""
    recs, pend = res["records"], res["pending"]
    for rn, r in rows:
        en0, zh0 = _get(r, 0), _get(r, 1)
        if not en0:
            continue
        if has_cjk(en0) and not zh0:
            sp = concat_split(en0)
            if not sp:
                continue
            en0, zh0 = sp
        if not add_pair(recs, file, sheet, rn, en0, zh0):
            add_pending(pend, file, sheet, rn, en0)


def h_concat1(cfg, file, sheet, rows, res):
    """单列拼接: 'Vasher瓦西尔'。"""
    recs, pend = res["records"], res["pending"]
    for rn, r in rows:
        s = _get(r, 0)
        if not s:
            continue
        sp = concat_split(s)
        if not sp:
            add_pending(pend, file, sheet, rn, s)
            continue
        add_pair(recs, file, sheet, rn, sp[0], sp[1])


def _pair_lines(en0: str, zh0: str):
    """多行单元格按行配对；行数不等则首行做对译、其余进 extras。"""
    en_lines = [l.strip() for l in (en0 or "").split("\n") if l.strip()]
    zh_lines = [l.strip() for l in (zh0 or "").split("\n") if l.strip()]
    if not en_lines or not zh_lines:
        return []
    if len(en_lines) == len(zh_lines) and len(en_lines) > 1:
        return list(zip(en_lines, zh_lines))
    return [(en_lines[0], "\n".join(zh_lines))]


def h_metals(cfg, file, sheet, rows, res):
    """金属技艺矩阵: (金属,中文) (别称) (镕金术师) (藏金术师)。备注列改译 -> notes。"""
    recs, notes = res["records"], res["notes"]
    for rn, r in rows[1:]:
        memo = _get(r, 13)
        if memo:
            notes.append({"kind": "metals_memo", "file": file, "sheet": sheet, "row": rn, "text": memo})
        for a, b in ((0, 1), (3, 4), (5, 6), (8, 9)):
            en0, zh0 = _get(r, a), _get(r, b)
            if not en0:
                continue
            if not zh0:
                sp = concat_split(en0)
                if not sp:
                    continue
                en0, zh0 = sp
            for e, z in _pair_lines(en0, zh0):
                add_pair(recs, file, sheet, rn, e, z, kind="metal")


def _en_slash_split(en: str) -> list[str]:
    parts = [p.strip() for p in en.split("/") if p.strip()]
    if len(parts) > 1 and all(re.match(r"^[A-Z][A-Za-z'’.\- ]{2,}$", p) for p in parts):
        return parts
    return [en]


def _do_pairs(pairs, file, sheet, rows, res, label=""):
    recs, pend = res["records"], res["pending"]
    for rn, r in rows:
        for a, b in pairs:
            en0, zh0 = _get(r, a), _get(r, b)
            if not en0:
                continue
            if not zh0:
                sp = concat_split(en0)
                if not sp:
                    continue
                en0, zh0 = sp
            if has_cjk(en0):
                continue
            for e, z in _pair_lines(en0, zh0):
                for e2 in _en_slash_split(e):
                    if not add_pair(recs, file, sheet, rn, e2, z, note=label):
                        add_pending(pend, file, sheet, rn, e2, label)


def h_paircols(cfg, file, sheet, rows, res):
    hdr = rows[0][1]
    start = 1 if cell(hdr[0]) in ("原名", "体系") else 0
    _do_pairs(cfg["pairs"], file, sheet, rows[start:], res)


def h_heralds(cfg, file, sheet, rows, res):
    # col0/1 = 数/词缀（无中文义）、col10/11 = 头衔/司掌（非直译对），均不取
    _do_pairs(cfg["pairs"], file, sheet, rows[1:], res, label="令使")


def h_fused(cfg, file, sheet, rows, res):
    recs, pend = res["records"], res["pending"]
    for rn, r in rows[1:]:
        en0, zh0 = _get(r, 0), _get(r, 1)
        if not en0 or has_cjk(en0):
            continue
        note_bits = [x for x in (f"大意 {_get(r, 2)} {_get(r, 3)}".strip(), _get(r, 4)) if x]
        note = "；".join(note_bits)
        if not add_pair(recs, file, sheet, rn, en0, zh0, kind="term", note=note):
            add_pending(pend, file, sheet, rn, en0, note)


def h_rowzip(cfg, file, sheet, rows, res):
    """整行配对（光辉骑士团）：英 row i + 中 row i+1，同列 ASCII/CJK 配对。"""
    recs = res["records"]
    label = cfg.get("label", sheet)
    i = 0
    while i < len(rows):
        rn, r = rows[i]
        if i + 1 < len(rows):
            rn2, r2 = rows[i + 1]
            pairs = []
            for j in range(max(len(r), len(r2))):
                a, b = _get(r, j), _get(r2, j)
                if a and b and not has_cjk(a) and has_cjk(b) and re.search(r"[A-Za-z]", a):
                    pairs.append((a, b))
            if pairs:
                row_label = _get(r, 0)
                note = f"{label}·{row_label}" if has_cjk(row_label) else label
                for a, b in pairs:
                    for a2 in _en_slash_split(a):
                        add_pair(recs, file, sheet, rn, a2, b, kind="term", note=note)
                i += 2
                continue
        i += 1


def h_curses(cfg, file, sheet, rows, res):
    recs, pend = res["records"], res["pending"]
    for rn, r in rows[1:]:
        en0, zh0 = _get(r, 1), _get(r, 2)
        if not en0:
            continue
        note = "；".join(x for x in (_get(r, 3), _get(r, 4), _get(r, 5)) if x)
        if not add_pair(recs, file, sheet, rn, en0, zh0, kind="curse", note=note[:400]):
            add_pending(pend, file, sheet, rn, en0, note[:400])


def h_conlang(cfg, file, sheet, rows, res):
    recs, pend = res["records"], res["pending"]
    for rn, r in rows[1:]:
        en0, translit, gist = _get(r, 0), _get(r, 1), _get(r, 2)
        if not en0:
            continue
        zh0 = translit or gist
        if has_cjk(en0) and not zh0:
            sp = concat_split(en0)
            if not sp:
                continue
            en0, zh0 = sp
        note_bits = []
        if gist and gist != zh0:
            note_bits.append(f"大意 {gist}")
        first = _get(r, 3)
        if first:
            note_bits.append(f"首现 {first}")
        tail = _get(r, 5)
        if tail:
            note_bits.append(tail)
        note = "；".join(note_bits)[:400]
        if not add_pair(recs, file, sheet, rn, en0, zh0, kind="conlang", note=note):
            add_pending(pend, file, sheet, rn, en0, note)


def h_runes(cfg, file, sheet, rows, res):
    recs, pend = res["records"], res["pending"]
    for rn, r in rows[1:]:
        reading, translit = _get(r, 0), _get(r, 1)
        if not reading:
            continue
        meaning, usage, trans = _get(r, 2), _get(r, 3), _get(r, 4)
        en = reading.capitalize() if reading.isupper() else reading
        note_bits = [x for x in (f"含义 {meaning}" if meaning else "",
                                 f"用例 {usage}→{trans}" if usage and trans else "") if x]
        note = "；".join(note_bits)
        if not add_pair(recs, file, sheet, rn, en, translit, kind="rune", note=note):
            add_pending(pend, file, sheet, rn, en, note)
        # 用例对译: 'Aanden, Taan' × '安登、泰安'
        if usage and trans:
            ens = [x.strip() for x in usage.split(",") if x.strip()]
            zhs = [x.strip() for x in trans.split("、") if x.strip()]
            if len(ens) == len(zhs) and all(not has_cjk(e) for e in ens):
                for e, z in zip(ens, zhs):
                    add_pair(recs, file, sheet, rn, e, z, kind="derived", note="符文用例")


def h_errata(cfg, file, sheet, rows, res):
    for rn, r in rows[1:]:
        res["errata"].append({
            "file": file, "sheet": sheet, "row": rn,
            "no": _get(r, 0), "where": _get(r, 1),
            "orig": _get(r, 2), "fix": _get(r, 3), "memo": _get(r, 4),
        })


HANDLERS = {
    "std": h_std, "pair2": h_pair2, "concat1": h_concat1, "metals": h_metals,
    "paircols": h_paircols, "heralds": h_heralds, "fused": h_fused,
    "rowzip": h_rowzip, "curses": h_curses, "conlang": h_conlang,
    "runes": h_runes, "errata": h_errata,
}


# ---------------------------------------------------------------- parse

def stage_parse() -> dict:
    res = {"records": [], "pending": [], "notes": [], "errata": [], "sheet_stats": []}
    for f in FILES:
        wb = openpyxl.load_workbook(RAW / f, data_only=True)
        for ws in wb.worksheets:
            cfg = SHEET_CFG.get((f, ws.title)) or (WILDCARD_CFG if f.startswith("无界秘典") else None)
            rows = load_rows(ws)
            if cfg is None:
                res["notes"].append({"kind": "unknown_sheet", "file": f, "sheet": ws.title})
                continue
            before = len(res["records"])
            if cfg["kind"] == "skip":
                res["sheet_stats"].append({"file": f, "sheet": ws.title, "kind": "skip",
                                           "rows": len(rows), "records": 0})
                continue
            HANDLERS[cfg["kind"]](cfg, f, ws.title, rows, res)
            res["sheet_stats"].append({"file": f, "sheet": ws.title, "kind": cfg["kind"],
                                       "rows": len(rows), "records": len(res["records"]) - before})
        wb.close()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    payload = {"parsed_at": datetime.now().isoformat(timespec="seconds"),
               "sheet_stats": res["sheet_stats"],
               "records": [asdict(r) for r in res["records"]],
               "pending": res["pending"], "notes": res["notes"], "errata": res["errata"]}
    (OUTDIR / "records.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return payload


# ---------------------------------------------------------------- analyze

def match_existing(key: str, existing: dict, fold: dict):
    if key in existing:
        return key, "exact"
    if key.casefold() in fold:
        return fold[key.casefold()], "case"
    base = strip_paren(key)
    if base != key:
        if base in existing:
            return base, "base"
        if base.casefold() in fold:
            return fold[base.casefold()], "base"
    return None, None


def analyze(payload: dict, glossary: dict) -> dict:
    terms = glossary["terms"]
    fold = {k.casefold(): k for k in terms}
    recs = [Record(**r) for r in payload["records"]]
    out = {"same": [], "fill": [], "conflict_existing": [], "variant_existing": [],
           "new": [], "conflict_new": [], "pending_true": [], "pending_covered": []}
    new_pool = []
    for rec in recs:
        mkey, mtype = match_existing(rec.en, terms, fold)
        if mtype in ("exact", "case"):
            ex = terms[mkey]
            exzh = (ex or {}).get("zh") if isinstance(ex, dict) else ex
            if not exzh:
                out["fill"].append({"key": mkey, "rec": asdict(rec)})
            elif zh_equal(exzh, rec.zh):
                out["same"].append({"key": mkey, "rec": asdict(rec)})
            else:
                out["conflict_existing"].append({
                    "key": mkey, "existing_zh": exzh, "existing_note": (ex.get("note") or "")[:160],
                    "existing_src": ex.get("src") or "", "match": mtype, "rec": asdict(rec)})
        elif mtype == "base":
            out["variant_existing"].append({"key": rec.en, "base": mkey, "rec": asdict(rec)})
        else:
            new_pool.append(rec)
    # 冲突去重（同 key 同译名对只报一次，保留首个来源）
    seen, uniq = set(), []
    for c in out["conflict_existing"]:
        k = (c["key"], zh_full(c["existing_zh"]), zh_full(c["rec"]["zh"]))
        if k in seen:
            continue
        seen.add(k)
        uniq.append(c)
    out["conflict_existing"] = uniq
    # 新表之间：按 (优先级, 首字母大写, 行号) 分组择一
    groups: "OrderedDict[str, list]" = OrderedDict()
    for rec in sorted(new_pool, key=lambda r: (PRIORITY[r.file], 0 if r.en[:1].isupper() else 1, r.row)):
        groups.setdefault(rec.en.casefold(), []).append(rec)
    for _, grp in groups.items():
        chosen, others, srcs = grp[0], [], [chosen_src for chosen_src in [grp[0].src]]
        for r in grp[1:]:
            if zh_equal(chosen.zh, r.zh):
                if r.src not in srcs:
                    srcs.append(r.src)
            else:
                others.append(r)
        entry = asdict(chosen)
        entry["all_srcs"] = srcs
        out["new"].append(entry)
        if others:
            out["conflict_new"].append({"key": chosen.en, "chosen": entry,
                                        "others": [asdict(o) for o in others]})
    # pending 复核：新表/现表已有译名则不算 pending
    new_keys = {r.en.casefold() for r in recs}
    for p in payload["pending"]:
        en = p.get("en") or ""
        if en.casefold() in new_keys:
            out["pending_covered"].append({**p, "why": "其他新表/列已给译名"})
            continue
        mkey, mtype = match_existing(en, terms, fold)
        if mtype in ("exact", "case") and (terms[mkey] or {}).get("zh"):
            out["pending_covered"].append({**p, "why": f"现表已有 {terms[mkey]['zh']}"})
            continue
        out["pending_true"].append(p)
    return out


# ---------------------------------------------------------------- report

def _tw_tag(zh: str) -> str:
    return " ⚠台版" if any(m in (zh or "") for m in TAIWAN_MARKERS) else ""


def _md_conflict_existing(a, md):
    md.append(f"\n### A. 新表 vs 现有表（{len(a)} 条，现有表保留，未覆盖）\n")
    if not a:
        md.append("（无）")
        return
    md.append("| 英文 | 现表 | 新表 | 新表来源 | 备注 |")
    md.append("|---|---|---|---|---|")
    for c in sorted(a, key=lambda x: (x["rec"]["file"], x["rec"]["sheet"], x["rec"]["row"])):
        r = c["rec"]
        note = (c["existing_note"] or r.get("note") or "").replace("|", "｜").replace("\n", " ")[:60]
        md.append(f"| {c['key']} | {c['existing_zh']}{_tw_tag(c['existing_zh'])} "
                  f"| {r['zh']}{_tw_tag(r['zh'])} | {r['file']}#{r['sheet']}(行{r['row']}) | {note} |")


def _md_conflict_new(a, md):
    md.append(f"\n### B. 新表互相冲突（{len(a)} 条，按优先级择一，其余记入备注）\n")
    if not a:
        md.append("（无）")
        return
    md.append("| 英文 | 拟采用 | 其他译名（来源） |")
    md.append("|---|---|---|")
    for c in a:
        ch = c["chosen"]
        oth = "；".join(f"{o['zh']}（{o['file']}#{o['sheet']}(行{o['row']}){_tw_tag(o['zh'])}）"
                        for o in c["others"])
        md.append(f"| {c['key']} | {ch['zh']}（{ch['file']}#{ch['sheet']}） | {oth} |")


def _md_errata(payload, md):
    rows = payload["errata"]
    md.append(f"\n## 4. 三界宙翻译勘误表（句子级，未并入译名表）\n")
    md.append(f"共 {len(rows)} 条，原译/改译为整句，需人工判断是否影响词条。\n")
    done = [r for r in rows if r["fix"] and r["fix"] != r["orig"]]
    empty = [r for r in rows if not r["fix"]]
    same = [r for r in rows if r["fix"] and r["fix"] == r["orig"]]
    if done:
        md.append("### 4.1 已给改译（改动片段 + 备注中的英文线索）\n")
        md.append("| sheet | # | 位置 | 改动（原→改） | 备注 |")
        md.append("|---|---|---|---|---|")
        for r in done:
            sm = difflib.SequenceMatcher(None, r["orig"], r["fix"])
            segs = []
            for tag, i1, i2, j1, j2 in sm.get_opcodes():
                if tag == "equal":
                    continue
                a, b = r["orig"][i1:i2], r["fix"][j1:j2]
                if tag == "insert":
                    ctx = r["orig"][max(0, i1 - 8):i1 + 8]
                    segs.append(f"插「{b}」于「{ctx}」")
                elif tag == "delete":
                    segs.append(f"删「{a}」")
                else:
                    segs.append(f"{a}→{b}")
            seg = "；".join(segs) if segs else "（改动过大，见原表）"
            md.append(f"| {r['sheet']} | {r['no']} | {r['where']} | {seg} | {r['memo']} |")
    if empty:
        md.append(f"\n### 4.2 改译列为空（{len(empty)} 条，待定）\n")
        for r in empty:
            md.append(f"- [{r['sheet']} #{r['no']} {r['where']}] 原译：{r['orig'][:60]}"
                      f"{'…' if len(r['orig']) > 60 else ''} ｜备注：{r['memo']}")
    if same:
        md.append(f"\n### 4.3 原译=改译（{len(same)} 条，无净改动）\n")
        for r in same:
            md.append(f"- [{r['sheet']} #{r['no']} {r['where']}] 备注：{r['memo']}")


def _hdr(cols):
    return ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]


def stage_report(payload: dict, glossary: dict, a: dict) -> str:
    md = ["# 译名表扩充：6 份新 Excel 解析与冲突报告",
          f"\n生成时间：{datetime.now().isoformat(timespec='seconds')}",
          "\n> 「处理方法」列留空待人工填写；**填写后勿再重跑 --stage report**（会覆盖）。", ""]
    n_rec = len(payload["records"])
    new_count = a.get("new_count") or len(a.get("new") or [])
    if not new_count:  # 合并后复用旧分析时，用 merge_report 的 added 数
        mr = OUTDIR / "merge_report.json"
        if mr.exists():
            new_count = len(json.loads(mr.read_text(encoding="utf-8")).get("added") or [])
    md.append("## 0. 总览\n")
    md.append(f"- 解析 {len(FILES)} 文件 / {len(payload['sheet_stats'])} sheet，"
              f"提取 **{n_rec} 条**对译记录（term/derived/...），表中无译名的行 {len(payload['pending'])} 条")
    md.append(f"- 与现表比对：一致确认 **{len(a['same'])}**、补空 **{len(a['fill'])}**、"
              f"**冲突 {len(a['conflict_existing'])}**（现有表保留）、括号消歧重名 {len(a['variant_existing'])}")
    md.append(f"- 新增并入 **{new_count}** 条；新表互相冲突 {len(a['conflict_new'])}（已按优先级择一）")
    md.append(f"- 真 pending（需书证补译）**{len(a['pending_true'])}** 条；"
              f"复核后不成立 {len(a['pending_covered'])} 条")
    md.append("\n来源优先级（新表冲突择一用）：" + " > ".join(FILES))

    # A 冲突 vs 现表
    ac = a["conflict_existing"]
    md.append(f"\n## 1. 冲突 A：新表 vs 现有表（{len(ac)} 条，现有表保留，未覆盖）\n")
    md += _hdr(["英文", "现表", "新表", "新表来源", "备注", "处理方法"])
    for c in sorted(ac, key=lambda x: (x["rec"]["file"], x["rec"]["sheet"], x["rec"]["row"])):
        r = c["rec"]
        note = (c["existing_note"] or r.get("note") or "").replace("|", "｜").replace("\n", " ")[:60]
        md.append(f"| {c['key']} | {c['existing_zh']}{_tw_tag(c['existing_zh'])} "
                  f"| {r['zh']}{_tw_tag(r['zh'])} | {r['file']}#{r['sheet']}(行{r['row']}) | {note} | |")

    # B 新表互斥
    bn = a["conflict_new"]
    md.append(f"\n## 2. 冲突 B：新表互相冲突（{len(bn)} 条，已按优先级择一并把异译记入 note）\n")
    md += _hdr(["英文", "拟采用", "其他译名（来源）", "处理方法"])
    for c in bn:
        ch = c["chosen"]
        oth = "；".join(f"{o['zh']}（{o['file']}#{o['sheet']}(行{o['row']}){_tw_tag(o['zh'])}）"
                        for o in c["others"])
        md.append(f"| {c['key']} | {ch['zh']}（{ch['file']}#{ch['sheet']}） | {oth} | |")

    # C 消歧重名
    vr = a["variant_existing"]
    md.append(f"\n## 3. 冲突 C：消歧/括号词条与现表基础词条重名（{len(vr)} 条，未新增 key）\n")
    md += _hdr(["新表词条", "现表基础词条", "新表给的译义（来源）", "处理方法"])
    for v in vr:
        r = v["rec"]
        md.append(f"| {v['key']} | {v['base']} "
                  f"| {r['zh']}（{r['file']}#{r['sheet']} 行{r['row']}） | |")

    # D 拆名新增
    sp_path = OUTDIR / "split_names.json"
    if sp_path.exists():
        sp = json.loads(sp_path.read_text(encoding="utf-8"))
        applied, sp_conf = sp.get("applied", []), sp.get("conflicts", [])
        md.append(f"\n## 4. 拆名专项：全名拆出的裸名条目（{len(applied)} 条已并入，"
                  f"冲突 {len(sp_conf)} 条未并入）\n")
        if applied:
            md += _hdr(["裸名", "中文", "来自全名", "来源", "处理方法"])
            for x in applied:
                md.append(f"| {x['key']} | {x['zh']} | {x['from']} | {x['src']} | |")
        if sp_conf:
            md.append(f"\n拆名冲突（{len(sp_conf)}，裸名已有不同译名，未并入）：")
            md += _hdr(["裸名", "已用", "候选", "来自全名", "处理方法"])
            for x in sp_conf:
                md.append(f"| {x['key']} | {x['existing_zh']} | {x['candidate_zh']} "
                          f"| {x['from']} | |")

    # 勘误表
    rows = payload["errata"]
    md.append(f"\n## 5. 三界宙翻译勘误表（句子级，未并入译名表，共 {len(rows)} 条）\n")
    done = [r for r in rows if r["fix"] and r["fix"] != r["orig"]]
    empty = [r for r in rows if not r["fix"]]
    same = [r for r in rows if r["fix"] and r["fix"] == r["orig"]]
    if done:
        md.append(f"### 5.1 已给改译（{len(done)} 条，改动片段 + 备注英文线索）\n")
        md += _hdr(["sheet", "#", "位置", "改动（原→改）", "备注", "处理方法"])
        for r in done:
            sm = difflib.SequenceMatcher(None, r["orig"], r["fix"])
            segs = []
            for tag, i1, i2, j1, j2 in sm.get_opcodes():
                if tag == "equal":
                    continue
                a_, b_ = r["orig"][i1:i2], r["fix"][j1:j2]
                if tag == "insert":
                    segs.append(f"插「{b_}」于「{r['orig'][max(0, i1 - 8):i1 + 8]}」")
                elif tag == "delete":
                    segs.append(f"删「{a_}」")
                else:
                    segs.append(f"{a_}→{b_}")
            seg = "；".join(segs) if segs else "（改动过大，见原表）"
            memo = (r["memo"] or "").replace("|", "｜").replace("\n", " ")
            md.append(f"| {r['sheet']} | {r['no']} | {r['where']} | {seg} | {memo[:80]} | |")
    if empty:
        md.append(f"\n### 5.2 改译列为空（{len(empty)} 条，待定）\n")
        md += _hdr(["sheet", "#", "位置", "原译", "备注", "处理方法"])
        for r in empty:
            md.append(f"| {r['sheet']} | {r['no']} | {r['where']} | {r['orig'][:50]} "
                      f"| {(r['memo'] or '').replace(chr(10), ' ')[:60]} | |")
    if same:
        md.append(f"\n### 5.3 原译=改译（{len(same)} 条，无净改动）\n")
        md += _hdr(["sheet", "#", "位置", "备注", "处理方法"])
        for r in same:
            md.append(f"| {r['sheet']} | {r['no']} | {r['where']} "
                      f"| {(r['memo'] or '').replace(chr(10), ' ')[:80]} | |")

    # pending 明细
    md.append(f"\n## 6. pending：表中有英文名但无译名（{len(a['pending_true'])} 条，需书证补译）\n")
    groups: dict[str, list] = {}
    for x in a["pending_true"]:
        groups.setdefault(f"{x['file']}#{x['sheet']}", []).append(x)
    md.append("| 来源 sheet | 条数 |")
    md.append("|---|---|")
    for k in sorted(groups, key=lambda k: -len(groups[k])):
        md.append(f"| {k} | {len(groups[k])} |")
    for k in sorted(groups, key=lambda k: -len(groups[k])):
        md.append(f"\n### {k}（{len(groups[k])} 条）\n")
        md += _hdr(["英文", "表内注释/首现", "处理方法"])
        for x in groups[k]:
            note = (x.get("note") or "").replace("|", "｜").replace("\n", " ")[:70]
            md.append(f"| {x['en']} | {note} | |")
    cov = a["pending_covered"]
    md.append(f"\n复核不成立 {len(cov)} 条（现表/其他新表已有译名，明细 pending_covered 见 pending.json）。")

    # 金属技艺备注
    memo = [n for n in payload["notes"] if n["kind"] == "metals_memo"]
    if memo:
        md.append(f"\n## 7. 金属技艺表备注列的「改译」提示（{len(memo)} 条，与列值可能不一致）\n")
        md += _hdr(["行", "备注", "处理方法"])
        for m in memo:
            md.append(f"| {m['row']} | {m['text']} | |")

    # 解析统计
    md.append("\n## 8. sheet 解析统计（留档，无需处理）\n")
    md += _hdr(["文件", "sheet", "方式", "行数", "提取"])
    for st in payload["sheet_stats"]:
        md.append(f"| {st['file']} | {st['sheet']} | {st['kind']} | {st['rows']} | {st['records']} |")
    warn = [n for n in payload["notes"] if n["kind"] != "metals_memo"]
    if warn:
        md.append(f"\n跳过/异常 {len(warn)} 行（label_skip/malformed/unknown_sheet，见 notes.json）。")

    OUTDIR.mkdir(parents=True, exist_ok=True)
    text = "\n".join(md) + "\n"
    (OUTDIR / "conflicts.md").write_text(text, encoding="utf-8")
    (OUTDIR / "conflicts.json").write_text(
        json.dumps({**{k: v for k, v in a.items() if k != "new"},
                    "new_count": new_count}, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUTDIR / "pending.json").write_text(
        json.dumps({"true": a["pending_true"], "covered": a["pending_covered"]},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    return text


# ---------------------------------------------------------------- merge

def _build_entry(rec: dict) -> dict:
    note_bits = []
    if rec.get("first"):
        note_bits.append(f"首现 {rec['first']}")
    if rec.get("note"):
        note_bits.append(rec["note"])
    if rec.get("extras"):
        note_bits.append("另译：" + "/".join(rec["extras"]))
    if rec.get("paren"):
        note_bits.append(f"（{rec['paren']}）")
    entry = {"zh": rec["zh"]}
    note = "；".join(note_bits)[:600]
    if note:
        entry["note"] = note
    entry["src"] = "；".join(rec.get("all_srcs") or [rec["src"]])
    return entry


def stage_merge(glossary: dict, a: dict, keep_en: dict) -> dict:
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    for bak in (GLOSSARY, KEEP_EN):
        shutil.copy2(bak, bak.with_name(bak.name + f".bak.xlsximport-{ts}"))
    terms = glossary["terms"]
    added, filled = [], []
    for rec in a["new"]:
        key = rec["en"]
        if key not in terms:
            terms[key] = _build_entry(rec)
            added.append(key)
    for f in a["fill"]:
        key, rec = f["key"], f["rec"]
        entry = terms.get(key) if isinstance(terms.get(key), dict) else {"zh": terms.get(key)}
        entry["zh"] = rec["zh"]
        entry.setdefault("src", rec["src"])
        terms[key] = entry
        filled.append(key)
    glossary["terms"] = terms
    m = glossary["meta"]
    m["entry_count"] = len(terms)
    m["updated"] = datetime.now().strftime("%Y-%m-%d")
    m["source"] = m.get("source", "") + " + 2026-10-19 译者表6份(xlsx: 三界宙翻译勘误表/伊岚翠/无界秘典/破战者/迷雾之子/飓光志)"
    m.setdefault("notes", []).append(
        f"2026-10-19 译者译名表 6 份并入（scripts/glossary_xlsx_import.py）：新增 {len(added)}、"
        f"补空 {len(filled)}、一致确认 {len(a['same'])}、与现表冲突 {len(a['conflict_existing'])}"
        f"（未覆盖，见 state/glossary_xlsx_import/conflicts.md）、新表互斥 {len(a['conflict_new'])}（已按优先级择一记入 note）；"
        f"覆盖扩展至三界宙其他书系（飓光志/伊岚翠/破战者/无界秘典），"
        f"pending {len(a['pending_true'])} 条待书证。")
    GLOSSARY.write_text(json.dumps(glossary, ensure_ascii=False, indent=2), encoding="utf-8")
    # keep_en 清理：已入译名表的词条按其 meta.note 约定移除（精确/大小写匹配）
    new_keys = {k.casefold(): k for k in added}
    kept = [t for t in keep_en.get("terms", []) if t.casefold() not in new_keys]
    pruned = sorted(set(keep_en.get("terms", [])) - set(kept))
    if pruned:
        keep_en["terms"] = kept
        KEEP_EN.write_text(json.dumps(keep_en, ensure_ascii=False, indent=2), encoding="utf-8")
    report = {"added": added, "filled": filled, "pruned_keep_en": pruned,
              "counts": {"terms": len(terms), "same": len(a["same"]),
                         "conflict_existing": len(a["conflict_existing"]),
                         "conflict_new": len(a["conflict_new"]),
                         "pending": len(a["pending_true"])}}
    (OUTDIR / "merge_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                              encoding="utf-8")
    return report


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["parse", "report", "merge", "all"], default="all")
    ap.add_argument("--reuse-analysis", action="store_true",
                    help="直接复用已保存的 conflicts.json 分析结果重新生成报告（合并后用）")
    args = ap.parse_args()
    glossary = json.loads(GLOSSARY.read_text(encoding="utf-8"))
    keep_en = json.loads(KEEP_EN.read_text(encoding="utf-8"))
    payload = None
    if args.stage in ("parse", "all"):
        payload = stage_parse()
        print(f"[parse] records={len(payload['records'])} pending={len(payload['pending'])} "
              f"errata={len(payload['errata'])} notes={len(payload['notes'])}")
    else:
        payload = json.loads((OUTDIR / "records.json").read_text(encoding="utf-8"))
    if args.reuse_analysis:
        a = json.loads((OUTDIR / "conflicts.json").read_text(encoding="utf-8"))
    else:
        a = analyze(payload, glossary)
    print(f"[analyze] same={len(a['same'])} fill={len(a['fill'])} "
          f"conflict_vs_existing={len(a['conflict_existing'])} variant={len(a['variant_existing'])} "
          f"new={a.get('new_count') or len(a.get('new') or [])} conflict_new={len(a['conflict_new'])} "
          f"pending_true={len(a['pending_true'])} pending_covered={len(a['pending_covered'])}")
    if args.stage in ("report", "all"):
        stage_report(payload, glossary, a)
        print(f"[report] -> {OUTDIR / 'conflicts.md'}")
    if args.stage in ("merge", "all"):
        rep = stage_merge(glossary, a, keep_en)
        print(f"[merge] added={len(rep['added'])} filled={len(rep['filled'])} "
              f"terms={rep['counts']['terms']} pruned_keep_en={rep['pruned_keep_en']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
