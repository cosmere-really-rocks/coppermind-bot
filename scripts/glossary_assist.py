#!/usr/bin/env python3
"""
glossary_assist.py —— 译名表（glossary）补全的自助定位工具（把 glossary_alignment.md 的
人工 6 步流程脚本化；未来可复用于自动翻译 {{quote}}）。

对「缺失专名」，自动：
  1. 解析词条（去括号消歧 → 基础名，如 Chip (constable)→Chip）
  2. 定位出处：从页面 wikitext 取 {{book ref|书码|章}}；map/file ref 标为非正文（Finding D/E）
  3. 英书定位：在 dict/epub_out/<en书>/ 该章里找到词条并显示上下文
  4. 中英同章：按对齐规则映射到 <zh书> 同章，给出中文对照区，供人工/LLM 采证官方中译
  5. 交叉核对：支持 --page 传入词条页，多书/多章重复出现时逐处对齐
输入以书证（本地中英电子书）为准，绝不提交/传播电子书内容。

用法：
  .venv/bin/python scripts/glossary_assist.py --term "Sea of Yomend"           # 纯词条（全书搜）
  .venv/bin/python scripts/glossary_assist.py --page "Seran Range"             # 取页面 book ref
  .venv/bin/python scripts/glossary_assist.py --term "X" --book mb6 --chapter 4  # 指定书章
  .venv/bin/python scripts/glossary_assist.py --page "Elendel Basin" --json     # 结构化输出
选项：
  --term   要查的英文专名（直接给定）
  --page   英文站快照标题；自动解析其 {{book ref}} 与基础名
  --book   强制书码（mb1..mb6/aol/sos/bom 等）；--chapter 章号（配合 --term）
  --all-hits  若英书该章无命中，自动跨全书搜（人物全名场景，Finding A）
  --ctx    上下文窗口字符数（默认 220）
  --json   输出机器可读 JSON（供后续自动补录/quote 翻译）
依赖：仅 stdlib。
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SNAP = ROOT / "en_snapshot"
EPUB_OUT = ROOT / "dict" / "epub_out"

REF_RE = re.compile(r"\{\{\s*book\s+ref\s*\|([^|}]+)\|([^|}]+)", re.I)
MAPREF_RE = re.compile(r"\{\{\s*map\s+ref\s*\|", re.I)
FILEREF_RE = re.compile(r"\{\{\s*file\s+ref\s*\|", re.I)

# 书码 -> (EN 目录, ZH 目录) ；zh 为 None 表示该书暂无官方中译（The Lost Metal）
BOOKS = {
    "mb1": ("the_final_empire", "zh_最后帝国"), "mbe1": ("the_final_empire", "zh_最后帝国"),
    "mb2": ("the_well_of_ascension", "zh_升华之井"), "mbe2": ("the_well_of_ascension", "zh_升华之井"),
    "mb3": ("the_hero_of_ages", "zh_永世英雄"), "mbe3": ("the_hero_of_ages", "zh_永世英雄"),
    "mb4": ("the_alloy_of_law", "zh_执法镕金"), "aol": ("the_alloy_of_law", "zh_执法镕金"),
    "mbe4": ("the_alloy_of_law", "zh_执法镕金"),
    "mb5": ("shadows_of_self", "zh_旧影森森"), "sos": ("shadows_of_self", "zh_旧影森森"),
    "mbe5": ("shadows_of_self", "zh_旧影森森"),
    "mb6": ("the_bands_of_mourning", "zh_悲悼护腕"), "bom": ("the_bands_of_mourning", "zh_悲悼护腕"),
    "mb7": ("the_lost_metal", None), "tlm": ("the_lost_metal", None), "mbe6": ("the_lost_metal", None),
    "sh": ("secret_history", None), "eltania": ("secret_history", None),
    # —— 2026-10-19 新增：飓光志1-3（中译已就绪）、伊岚翠、皇帝魂；sa4/5/dawnshard 暂无中译 ——
    "sa1": ("the_way_of_kings", "zh_王者之路"), "twok": ("the_way_of_kings", "zh_王者之路"),
    "sa2": ("words_of_radiance", "zh_光辉真言"), "wor": ("words_of_radiance", "zh_光辉真言"),
    "sa3": ("oathbringer", "zh_渡誓"), "ob": ("oathbringer", "zh_渡誓"),
    "elantris": ("elantris", "zh_伊岚翠"),
    "tes": ("the_emperors_soul", "zh_皇帝魂"),
    # —— 2026-10-20 破战者中文书就绪 ——
    "wb": ("warbreaker", "zh_破战者"), "warbreaker": ("warbreaker", "zh_破战者"),
    "sa4": ("rhythm_of_war", None), "sa5": ("wind_and_truth", None),
    "sa3.5": ("dawnshard", None),
}
# 中英按「文件序号」对齐的英书（glossary_alignment §0.1；aol 按章节号对齐，不在此列）
INDEX_ALIGN_EN = {"the_way_of_kings", "words_of_radiance", "oathbringer", "elantris",
                  "the_emperors_soul", "warbreaker", "the_final_empire", "the_well_of_ascension",
                  "the_hero_of_ages", "shadows_of_self", "the_bands_of_mourning"}
AOL_BROADSHEET = re.compile(r"9781429994897")  # aol 英文里报章插页文件名标记（跳过）


def base_name(term: str) -> str:
    """去括号消歧 -> 基础名；如 Chip (constable)->Chip、Red (Scadrial)->Red。"""
    return re.sub(r"\s*\([^)]*\)\s*$", "", term).strip()


def strip_html(raw: str) -> str:
    t = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    t = re.sub(r"(?i)<(p|/p|div|/div|h[1-6]|/h[1-6]|br|li|/li|tr|/tr|blockquote|/blockquote)[^>]*>", "\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    lines = [re.sub(r"[ \t\u00a0]+", " ", ln).strip() for ln in t.split("\n")]
    return "\n".join(l for l in lines if l)


def chapter_file(book_dir: str, chapter: int):
    """按章号找章节文件（跳过 aol 报章插页）。chapter==999 匹配 epilogue，0 匹配 prologue。"""
    d = EPUB_OUT / book_dir
    if not d.is_dir():
        return None
    for f in d.glob("*.html"):
        if AOL_BROADSHEET.search(f.name):
            continue
        if chapter == 999 and re.search(r"(?i)epilogue|尾声|终章", f.name):
            return f
        if chapter == 0 and re.search(r"(?i)prologue|序章|序幕|引子", f.name):
            return f
        m = re.search(r"chapter[_\s]*(\d+)", f.name, re.I)
        if m and int(m.group(1)) == chapter:
            return f
        m = re.match(r"\d{3}_(\d{1,3})(?:_|$)", f.name)  # 飓光志体例 002_1_章节名
        if m and int(m.group(1)) == chapter:
            return f
        m = re.match(r"(\d{3})_", f.name)                 # 序号前缀（伊岚翠中译 061_第六十一章）
        if m and int(m.group(1)) == chapter:
            return f
    return None


def load_chapter_text(book_dir: str, chapter: int):
    f = chapter_file(book_dir, chapter)
    if not f:
        return None, None
    raw = f.read_text(encoding="utf-8", errors="replace")
    return strip_html(raw), f.name


def find_in(text: str, term: str):
    """返回 term 在 text 中的命中位置列表（大小写不敏感，词边界）。"""
    hits = []
    pat = re.compile(r"(?<![A-Za-z])" + re.escape(term) + r"(?![A-Za-z])", re.I)
    for m in pat.finditer(text):
        hits.append(m.start())
    return hits


def context(text: str, i: int, term: str, window: int) -> str:
    lo = max(0, i - window)
    hi = min(len(text), i + len(term) + window)
    seg = text[lo:hi]
    # 高亮词条
    seg = re.sub(r"(?<![A-Za-z])" + re.escape(term) + r"(?![A-Za-z])",
                 lambda m: "【" + m.group(0) + "】", seg, flags=re.I)
    seg = seg.replace("\n", " ⏎ ")
    return ("…" if lo > 0 else "") + seg + ("…" if hi < len(text) else "")


_SNAP_INDEX = None


def snap_dir(page: str) -> Path:
    """页面快照目录：默认 SNAP/<page>；含 '/' 的标题在 en_index 里映射为下划线目录。"""
    global _SNAP_INDEX
    d = SNAP / page
    if (d / "wikitext.txt").exists():
        return d
    if _SNAP_INDEX is None:
        try:
            _SNAP_INDEX = json.loads((ROOT / "state" / "en_index.json").read_text(encoding="utf-8"))
        except Exception:
            _SNAP_INDEX = {}
    ent = _SNAP_INDEX.get(page) or {}
    snap = ent.get("snapshot")
    if snap:
        d2 = ROOT / snap
        if (d2 / "wikitext.txt").exists():
            return d2
    return d


def page_book_refs(page: str):
    """从快照 wikitext 解析 book ref（书码, 章）；返回 list[(code, ch)]。"""
    wt = snap_dir(page) / "wikitext.txt"
    if not wt.exists():
        return []
    txt = wt.read_text(encoding="utf-8", errors="replace")
    refs = []
    for code, ch in REF_RE.findall(txt):
        refs.append((code.strip().lower(), ch.strip()))
    return refs


def kind_of_page(page: str):
    """页面标题类型：人物/地理/其他（用于提示词）。"""
    wt = snap_dir(page) / "wikitext.txt"
    txt = ""
    if wt.exists():
        txt = wt.read_text(encoding="utf-8", errors="replace").lower()
    for k in ("infobox character", "infobox geography", "infobox location",
              "infobox settlement", "infobox nation"):
        if k in txt:
            return k.replace("infobox ", "")
    return "?"


def main():
    ap = argparse.ArgumentParser(description="译名表补全的中英章节对齐定位工具")
    ap.add_argument("--term", default=None, help="要查的英文专名（直接给定）")
    ap.add_argument("--page", default=None, help="英文站快照标题；自动解析其 book ref 与基础名")
    ap.add_argument("--book", default=None, help="强制书码（如 mb6/bom/aol）")
    ap.add_argument("--chapter", type=int, default=None, help="强制章号")
    ap.add_argument("--all-hits", action="store_true", help="跨全书搜（人物全名场景）")
    ap.add_argument("--ctx", type=int, default=220, help="上下文窗口字符数")
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    args = ap.parse_args()

    if not args.term and not args.page:
        raise SystemExit("需 --term 或 --page 之一。")

    # 1) 解析词条与基础名
    term = args.term
    page = args.page
    if page and not term:
        term = base_name(page)
    base = base_name(term)
    kind = kind_of_page(page) if page else "?"

    report = {"term": term, "base": base, "page": page, "kind": kind,
              "book_refs": [], "chapters": []}

    # 2) 出处：优先 --book/--chapter，否则页面 book ref；无则全书搜
    forced = args.book and args.chapter
    if forced:
        pairs = [(args.book.lower(), str(args.chapter))]
    elif page:
        pairs = page_book_refs(page)
        report["book_refs"] = [{"code": c, "chapter": ch} for c, ch in pairs]
    else:
        pairs = []

    # 只保留已映射且有 EN 书的书码；去重（同书同章只查一次）
    known_pairs = [(c, ch) for c, ch in pairs if c in BOOKS]
    unique_pairs = list(dict.fromkeys(known_pairs))

    searched = []
    en_hits_total = 0

    def emit_hit(code, ch, label=None):
        """对 (书, 章) 做 EN+ZH 对照并记入 searched（无命中返回 False）。"""
        nonlocal en_hits_total
        en_dir, zh_dir = BOOKS[code]
        chnum = {"prologue": 0, "epilogue": 999}.get(label, int(ch) if str(ch).isdigit() else 0)
        text, fname = load_chapter_text(en_dir, chnum)
        if text is None:
            searched.append({"book": code, "chapter": ch, "label": label,
                             "error": f"英书{en_dir}无该章"})
            return False
        hits = find_in(text, base)
        rec = {"book": code, "chapter": ch, "label": label, "en_file": fname,
               "en_dir": en_dir, "term_hits": len(hits)}
        if not hits:
            return False
        en_hits_total += len(hits)
        rec["en_contexts"] = [context(text, i, base, args.ctx) for i in hits[:3]]
        add_zh_region(rec, text, hits, zh_dir, chnum, args, en_dir, fname)
        searched.append(rec)
        return True

    # —— 纯词条模式（无页面 ref、未强制指定书章）：跨各书全书搜 ——
    if not known_pairs and args.term and not forced:
        report["mode"] = "full-book-scan"
        for code in ("mb6", "mb5", "mb4", "mb3", "mb2", "mb1"):
            en_dir, zh_dir = BOOKS[code]
            found = find_whole_book(base, en_dir, zh_dir, args)
            if found and found["total"]:
                searched.append({"book": code, "chapter": "scan", "en_dir": en_dir,
                                 "whole_book": found})
                en_hits_total += found["total"]
    else:
        # —— 先按 ref 逐章直查（快路径）——
        any_hit = {code: False for code, _ in unique_pairs}
        if forced:
            emit_hit(args.book.lower(), str(args.chapter))
        else:
            for code, ch in unique_pairs:
                if emit_hit(code, ch):
                    any_hit[code] = True
        # —— 快路径无命中的书：全书搜找真正首现章（Finding A / 地图词，需 --all-hits）——
        if args.all_hits:
            books_to_scan = {code for code, _ in unique_pairs if not any_hit.get(code)}
            for code in books_to_scan:
                en_dir, zh_dir = BOOKS[code]
                found = find_whole_book(base, en_dir, zh_dir, args)
                if found and found["total"]:
                    searched.append({"book": code, "chapter": "scan", "en_dir": en_dir,
                                     "whole_book": found})
                    en_hits_total += found["total"]

    report["chapters"] = searched
    report["en_hits_total"] = en_hits_total
    report["note"] = (
        f"基础名={base!r}（若上表 zh_region 命中可辨，即可据此采证官方中译补入 dict/mistborn.json）。"
        "请人工在中文对照区里按上下文挑官方译名，勿直接引用行内自动推断。")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    # ------ 人类可读输出 ------
    print(f"词条: {term}  基础名: {base}  类型: {kind}")
    print(f"页面 ref: {report.get('book_refs') or '—'}  命中合计: {en_hits_total}")
    for rec in searched:
        loc = rec.get('en_file') or rec.get('en_dir') or "扫描"
        print(f"\n── {rec['book']} ch{rec['chapter']}  [{loc}] 命中 {rec.get('term_hits', 0)}")
        if "error" in rec:
            print("  ⚠", rec["error"])
            continue
        for c in rec.get("en_contexts", []):
            print("  EN>", c)
        wb = rec.get("whole_book")
        if wb:
            print(f"  全书扫描（{rec['book']}，共命中 {wb.get('total', 0)}）:")
            for h in wb.get("hits", [])[:3]:
                print(f"    ch{h['chapter']} ({h['file']}): {h['context']}")
                if h.get("zh_region"):
                    print(f"      ZH{h.get('zh_file','')} 该处为英文上下文；中文对照区见下")
                    print(f"      ZH> {h['zh_region']}")
        zh_region = rec.get("zh_region")
        if zh_region:
            print(f"  ZH{rec.get('zh_file', '')}> {zh_region}")
            print("  ⓘ 请在以上中文对照区内人工采证官方译名。")
    print("\n说明：工具负责“自动定位中英同章/上下文”，官方中译仍以中文电子书原文为准，由人/LLM 采证后写入 dict/mistborn.json。")


def add_zh_region(rec, text, hits, zh_dir, ch, args, en_dir=None, en_file=None):
    """给 rec 补上中文同章对照区（按 EN 命中位置比例映射）。

    en_dir/en_file 给定时：INDEX_ALIGN_EN 类英书按「文件序号」配对中书同序号文件
    （glossary_alignment §0.1；aol 不在 INDEX_ALIGN_EN，仍按章节号）。
    """
    zh_text, zh_fname = None, None
    if zh_dir and en_dir in INDEX_ALIGN_EN and en_file:
        m = re.match(r"(\d{3})_", en_file)
        if m:
            pref = m.group(1)
            zhs = sorted((EPUB_OUT / zh_dir).glob(f"{pref}_*.html"))
            if zhs:
                zh_fname = zhs[0].name
                zh_text = strip_html(zhs[0].read_text(encoding="utf-8", errors="replace"))
    if zh_text is None and zh_dir:
        zh_text, zh_fname = load_chapter_text(zh_dir, ch)
    if not zh_text:
        rec["zh_file"] = None
        rec["zh_note"] = "无中文版或该章缺失"
        return rec
    ratio = min(1.0, hits[0] / max(1, len(text)))
    zpos = int(ratio * max(1, len(zh_text)))
    lo = max(0, zpos - args.ctx // 2)
    hi = min(len(zh_text), zpos + args.ctx // 2)
    rec["zh_file"] = zh_fname
    rec["zh_region"] = ("…" if lo > 0 else "") + \
        zh_text[lo:hi].replace("\n", " ⏎ ") + ("…" if hi < len(zh_text) else "")
    rec["zh_note"] = "有官方中译，请在下方中文对照区按义项采证官方译名"
    return rec


def find_whole_book(term, en_dir, zh_dir, args):
    """跨全书搜 term；返回命中章节列表（每处含 EN 上下文 + 对应 ZH 对照区）。"""
    hits = []
    d = EPUB_OUT / en_dir
    total = 0
    def keyf(p):
        m = re.search(r"(\d+)", p.name)
        return int(m.group(1)) if m else 0
    for f in sorted(d.glob("*.html"), key=keyf):
        if AOL_BROADSHEET.search(f.name):
            continue
        # 章节序号取文件名前导数字（chapterN / prologue / epilogue 都含数字前缀）
        mnum = re.search(r"(\d+)", f.name)
        cap = {"prologue": 0, "epilogue": 999}
        label = "epilogue" if "epilogue" in f.name.lower() else (
            "prologue" if re.match(r"0*1?_?prologue", f.name[:20].lower()) else None)
        if label is None and not re.search(r"chapter\d+", f.name, re.I) \
                and not (en_dir in INDEX_ALIGN_EN and re.match(r"\d{3}_", f.name)):
            continue
        text = strip_html(f.read_text(encoding="utf-8", errors="replace"))
        found = find_in(text, term)
        if found:
            total += len(found)
            chnum = cap.get(label, int(mnum.group(1)) if mnum else 0)
            item = {"book": en_dir, "chapter": chnum, "label": label, "file": f.name,
                    "context": context(text, found[0], term, args.ctx)}
            add_zh_region(item, text, found, zh_dir, chnum, args, en_dir, f.name)
            hits.append(item)
    return {"total": total, "hits": hits}


def locate(term: str, book=None, chapter=None, ctx: int = 220, all_hits: bool = False) -> dict:
    """translate.py 可导入的定位 API：按 (书码, 章) 找指定英文短语在英书上下文与中书对照区。

    返回 dict（供 quote/称呼采证）：
      {found: bool, book, chapter, en_file, en_contexts: [...], zh_region: str|None, zh_note}
    - book 为书码（如 mb6/bom）；chapter 为章号（数字/字符串）。
    - 未给 book/chapter 时跨全书搜（all_hits）。
    """
    import argparse as _ap
    _args = _ap.Namespace(ctx=ctx)
    if book and chapter not in (None, ""):
        if book.lower() not in BOOKS:
            return {"found": False, "book": book, "error": f"未知书码 {book}"}
        code = book.lower()
        en_dir, zh_dir = BOOKS[code]
        chnum = {"prologue": 0, "epilogue": 999}.get(str(chapter).lower(), int(chapter) if str(chapter).isdigit() else 0)
        text, fname = load_chapter_text(en_dir, chnum)
        if text is None:
            return {"found": False, "book": code, "chapter": chapter, "error": f"英书{en_dir}无该章"}
        hits = find_in(text, term)
        if not hits:
            return {"found": False, "book": code, "chapter": chapter, "en_file": fname, "term_hits": 0}
        rec = {"found": True, "book": code, "chapter": chapter, "en_file": fname,
               "en_contexts": [context(text, i, term, ctx) for i in hits[:3]]}
        add_zh_region(rec, text, hits, zh_dir, chnum, _args, en_dir, fname)
        rec["term_hits"] = len(hits)
        return rec
    # 无具体书章 → 跨书扫
    for code in ("mb6", "mb5", "mb4", "mb3", "mb2", "mb1"):
        if code not in BOOKS:
            continue
        en_dir, zh_dir = BOOKS[code]
        fw = find_whole_book(term, en_dir, zh_dir, _args)
        if fw and fw["total"]:
            h = fw["hits"][0]
            return {"found": True, "book": code, "chapter": h["chapter"], "label": h.get("label"),
                    "en_file": h["file"], "en_contexts": [h["context"]], "zh_region": h.get("zh_region"),
                    "zh_note": h.get("zh_note"), "term_hits": fw["total"]}
    return {"found": False, "book": None, "chapter": None}


if __name__ == "__main__":
    main()
