#!/usr/bin/env python3
"""
split_epub.py —— 新一批电子书的分章重构（飓光志 / 伊岚翠 / 破战者 / 皇帝魂，本地、不提交）

背景：dict/epub_out/ 下迷雾之子系列由 extract_books.py（一文件一章）与
reconstruct_epub.py（spine 锚点重构）处理。后一批书形态各异（TOC 可靠程度、
章节标题是否为图片、一个文件内含多章锚点……），本脚本统一用「TOC 驱动」处理，
产物与迷雾之子完全同构：dict/epub_out/<book>/NNN_<chapter>.html

模式：
  toc       以 epub 的 TOC（toc.ncx / epub3 nav）为章节边界：
              - 白名单识别「真章节」标签（第X章 / Chapter N / 1: TITLE / I-N /
                序章·序幕·引子·尾声·后记 / Prologue / Epilogue …）；
              - 前言/版权/目录/鸣谢/分部页(Part·第X部分·插曲)/尾注/秘典 等
                不进白名单 → 不开新章；首章之前的一律丢弃，末章之后的做截断，
                中间的（分部页、地图、彩插）并入相邻章节（与 reconstruct 的 pending 同语义）；
              - 章节锚点落在文件内部时（如 渡誓 的 part0008 内含 1..32 章）按字节切分。
  each_file 一文件一章（无可用 TOC 的短篇合集 / 单文件短篇）。

用法：
  .venv/bin/python scripts/split_epub.py                 # 全部
  .venv/bin/python scripts/split_epub.py --book zh_渡誓   # 只跑一本
  .venv/bin/python scripts/split_epub.py --list           # 列书单
  .venv/bin/python scripts/split_epub.py --dry-run        # 只打印分章方案，不落盘
"""
import argparse
import html as html_mod
import os
import posixpath
import re
import shutil
import sys
import zipfile
from urllib.parse import unquote
from xml.etree import ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import reconstruct_epub as R  # 复用 read_container / read_opf / clean_fragment / text_of

OUT_DIR = os.path.join(ROOT, "dict", "epub_out")

# ---------------------------------------------------------------------------
# 书单：源 epub（相对项目根）-> 输出子目录 / 语言 / 可选覆盖项
#   mode        : toc（默认）| each_file
#   keep_extra  : 追加到白名单的正则（默认白名单之上）
#   drop_extra  : 优先于白名单的排除正则
#   strip       : 清理阶段剔除的正则（如 Warbreaker 的 Annotations 链接行）
#   split       : 纠正漏切的章——正文里还留着章标题（如 <p>第五十八章</p>），
#                 toc/打包没切成独立章节时，按 label 找到该章，再在 'at' 标记处
#                 切成两章，第二章标题取 'into'
# ---------------------------------------------------------------------------
BOOKS = [
    # ---- Elantris ----
    {"src": "dict/epub/elantris/[Elantris 01] - Elantris (epub).epub",
     "out": "elantris", "lang": "en"},
    {"src": "dict/epub/elantris/[Elantris ss] - The Hope of Elantris.epub",
     "out": "the_hope_of_elantris", "lang": "en", "mode": "each_file"},
    {"src": "dict/epub/elantris/伊岚翠 ([美]布兰登·桑德森 [[美]布兰登·桑德森]) (z-library.sk, 1lib.sk, z-lib.sk).epub",
     "out": "zh_伊岚翠", "lang": "zh"},
    # ---- The Emperor's Soul ----
    {"src": "dict/epub/The Emperor's Soul/Brandon Sanderson - The Emperor's Soul.epub",
     "out": "the_emperors_soul", "lang": "en",
     "keep_extra": [r"^day\s+[a-z]"]},          # Day Two / Day Three …（本书章节名）
    {"src": "dict/epub/The Emperor's Soul/【简体版】皇帝魂.epub",
     "out": "zh_皇帝魂", "lang": "zh",
     # 同一 epub 后半附赠《保卫至福净土》《长子》《第十一种金属》《军团》，只取皇帝魂本体
     "slice": [0, 21],
     "keep_extra": [r"^第[一二三四五六七八九十百零]+天"]},  # 第二天 …（同上中译）
    # ---- Warbreaker ----
    {"src": "dict/epub/Warbreaker/Warbreaker (Retail).epub",
     "out": "warbreaker", "lang": "en",
     # 注解版：每章开头有指向 Annotations_* 的链接行，正文注解在书末独立文件（会被截断丢弃）
     "strip": [r'(?is)<p[^>]*class="[^"]*annotations[^"]*"[^>]*>.*?</p>']},
    {"src": "dict/epub/Warbreaker/破战者.epub",
     "out": "zh_破战者", "lang": "zh",
     # 打包 epub 把“第五十八章”标题漏并进第五十七章文件（toc.ncx 也缺条目），
     # 而英文版是 58 章 → 在正文里的 <p>第五十八章</p> 处切开，凑齐 60/60 对齐
     "split": [{"label": "第五十七章", "at": "第五十八章", "into": "第五十八章"}]},
    # ---- The Stormlight Archive ----
    {"src": "dict/epub/stormlight/The Way of Kings - Brandon Sanderson.epub",
     "out": "the_way_of_kings", "lang": "en"},
    {"src": "dict/epub/stormlight/Words of Radiance (Stormlight Archive, The) - Sanderson, Brandon.epub",
     "out": "words_of_radiance", "lang": "en"},
    {"src": "dict/epub/stormlight/Oathbringer.epub",
     "out": "oathbringer", "lang": "en"},
    {"src": "dict/epub/stormlight/Rhythm of War (Brandon Sanderson) (z-library.sk, 1lib.sk, z-lib.sk).epub",
     "out": "rhythm_of_war", "lang": "en"},
    {"src": "dict/epub/stormlight/The Stormlight Archive, Book 5 - Wind and Truth (Brandon Sanderson) (z-library.sk, 1lib.sk, z-lib.sk).epub",
     "out": "wind_and_truth", "lang": "en"},
    {"src": "dict/epub/stormlight/Dawnshard.epub",
     "out": "dawnshard", "lang": "en",
     "keep_extra": [r"^\d+$"]},                 # 章节标签就是裸数字 1..19
    {"src": "dict/epub/stormlight/Elsecaller & King Lopen the First of Aleth - Brandon Sanderson.epub",
     "out": "elsecaller_and_king_lopen", "lang": "en", "mode": "each_file"},
    {"src": "dict/epub/stormlight/【重庆社版】飓光志1：王者之路 .epub",
     "out": "zh_王者之路", "lang": "zh"},
    {"src": "dict/epub/stormlight/【重庆社版】飓光志2：光辉真言.epub",
     "out": "zh_光辉真言", "lang": "zh"},
    # 渡誓只有 azw3，已用 mobi 包转成 epub 落在同目录（dict/epub/ 本地不提交）
    {"src": "dict/epub/stormlight/【重庆社版】飓光志3：渡誓 (azw3转epub).epub",
     "out": "zh_渡誓", "lang": "zh"},
]

# 「真章节」标签白名单（大小写不敏感；未命中 → 不开新章）
DEFAULT_KEEP = [
    r"^(prologue|epilogue|postscript|afterword|prelude|postlude)\b",
    r"^chapter\s+[a-z0-9]",                 # Chapter One / CHAPTER 1 / Chapter 12
    r"^\d+\s*[.:]\s*\S",                    # 1: STORMBLESSED / 1. Calluses
    r"^\d+\s+\S",                           # 1 飓风恩护者
    r"^\d+[.\-]\d+",                        # 1-1: ISHIKK / 1.1 以什克
    r"^i-\d+",                              # I-1. Puuli / I-1　普利
    r"^interlude\s*\d+$",                   # Wind and Truth 的 Interlude 1..18（另书为 I-N）
    r"^第[一二三四五六七八九十百零]+章",       # 第一章
    r"^(序章|序幕|引子|楔子|尾声|终章|终曲|后记)(\s|[:：]|$)",
]

# 书名页/目录/鸣谢…即便命中白名单也要排除（保险；多数本来就不命中）
DEFAULT_DROP = [
    r"^(table of )?contents?$",
    r"^copyright",
    r"^(dedication|acknowledg(e|)ments?|preface|endpaper|cover|title page)$",
]

TINY_TEXT = 30          # 片段正文短于此视为分隔页/图片页，剔除（若另有正文片段）
MAX_TITLE_LEN = 60      # 文件名标题部分截断


def read_toc(zf, opf_path):
    """返回 [(label, href_with_optional_#anchor), ...]，合并 epub3 nav 与 toc.ncx。"""
    base = posixpath.dirname(opf_path)
    root = ET.fromstring(zf.read(opf_path))
    items = [(it.get("href"), it.get("media-type"), it.get("properties"))
             for it in root.iter() if it.tag.endswith("item")]
    entries = []
    for href, mt, props in items:                       # epub3 nav
        if not (props and "nav" in props.split()):
            continue
        p = posixpath.normpath(posixpath.join(base, unquote(href or "")))
        try:
            nav = zf.read(p).decode("utf-8", "replace")
        except KeyError:
            continue
        for m in re.finditer(r'(?is)<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', nav):
            label = html_mod.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip()
            if label:
                entries.append((label, m.group(1)))
    for href, mt, props in items:                       # ncx
        if not (mt and "dtbncx" in mt):
            continue
        p = posixpath.normpath(posixpath.join(base, unquote(href or "")))
        try:
            data = zf.read(p)
        except KeyError:
            continue
        x = ET.fromstring(data)
        for np in x.iter():
            if not np.tag.endswith("navPoint"):
                continue
            label, src = None, ""
            for c in np.iter():
                if c.tag.endswith("text") and label is None:
                    label = (c.text or "").strip()
                if c.tag.endswith("content"):
                    src = c.get("src") or ""
            if label:
                entries.append((label, src))
    return entries


class Book:
    """封装一个 epub：spine、TOC 解析、body 缓存、锚点定位。"""

    def __init__(self, path, warnings, spine_slice=None):
        self.path = path
        self.warnings = warnings
        self.zf = zipfile.ZipFile(path)
        self.opf = R.read_container(self.zf)
        self.opf_dir = posixpath.dirname(self.opf)
        self.title, spine = R.read_opf(self.zf, self.opf)
        # 合订 epub 只取本书的 spine 区间（如【简体版】皇帝魂 后半附赠短篇不属本书）
        self.spine = spine[spine_slice[0]:spine_slice[1]] if spine_slice else spine
        self._body = {}
        self._strips = []

    def apply_strips(self, pats):
        self._strips = pats or []

    def body(self, pos):
        """body 内部 HTML（已套用 strip 规则），按 spine 位置缓存。"""
        if pos in self._body:
            return self._body[pos]
        raw = self.zf.read(self.spine[pos]).decode("utf-8", "replace")
        for pat in self._strips:
            raw = re.sub(pat, "", raw)
        m = re.search(r"(?is)<body[^>]*>(.*)</body>", raw)
        frag = m.group(1) if m else raw
        self._body[pos] = frag
        return frag

    def offset(self, pos, anchor):
        """锚点所在标签起始位置（body 内字节偏移）；找不到返回 None。"""
        if not anchor:
            return 0
        frag = self.body(pos)
        for pat in (f'id="{anchor}"', f"id='{anchor}'",
                    f'name="{anchor}"', f"name='{anchor}'"):
            i = frag.find(pat)
            if i >= 0:
                # 回退到标签开头（<），避免把 <div ... id="x"> 从中间切开
                return frag.rfind("<", 0, i)
        return None

    def resolve_entries(self):
        """TOC 条目 -> [{label,pos,anchor,off,toc}]；目标不在 spine 的丢弃。"""
        spine_index = {p: i for i, p in enumerate(self.spine)}
        out, seen, missed = [], set(), set()
        for toc_idx, (label, href) in enumerate(read_toc(self.zf, self.opf)):
            if not href:
                continue
            target, _, anchor = href.partition("#")
            full = posixpath.normpath(posixpath.join(self.opf_dir, unquote(target)))
            pos = spine_index.get(full)
            if pos is None:
                continue
            if not full.lower().endswith((".html", ".xhtml", ".htm")):
                continue
            if anchor.startswith("pg_"):          # Oathbringer 的分页书签
                continue
            label = html_mod.unescape(label).strip()
            if not label:
                continue
            off = self.offset(pos, anchor)
            if off is None:
                # 常见于 EPUB3 手写导航（锚点只是渲染用 id）——按文件头切分即可
                if anchor not in missed:
                    missed.add(anchor)
                    self.warnings.append(
                        f"锚点未找到: {label!r} -> {os.path.basename(full)}#{anchor}（按文件头切分）")
                off = 0
            if (label, pos, anchor) in seen:       # nav 与 ncx 重复条目
                continue
            seen.add((label, pos, anchor))
            out.append({"label": label, "pos": pos, "anchor": anchor,
                        "off": off, "toc": toc_idx})
        return out


def is_keep(label, keep_pats, drop_pats):
    for pat in drop_pats:
        if re.search(pat, label, re.I):
            return False
    for pat in keep_pats:
        if re.search(pat, label, re.I):
            return True
    return False


def numbering_stripped(label):
    """去掉编号前缀，留下标题本体（用于判断正文里是否已有标题）。"""
    s = label.strip()
    s = re.sub(r"^(chapter|prologue|epilogue|postscript|prelude|postlude|afterword)\s*[:.]?\s*",
               "", s, flags=re.I)
    s = re.sub(r"^i-\d+\.\s*", "", s, flags=re.I)
    s = re.sub(r"^interlude\s+\d+\s*", "", s, flags=re.I)
    s = re.sub(r"^\d+(\.\d+|-)?\d*\s*[:.]?\s*", "", s)
    s = re.sub(r"^第[一二三四五六七八九十百零]+章\s*", "", s)
    s = re.sub(r"^(序章|序幕|引子|楔子|尾声|终章|终曲|后记)\s*[:：]?\s*", "", s)
    return s.strip(" ：:")


def has_title(label, text, window=400):
    """正文开头（首 window 字符内）是否已出现该章标题——只看开头，避免正文偶合误判。"""
    head = text[:window].lower()
    body_title = numbering_stripped(label)
    cands = [c for c in (body_title, label) if len(c) >= 2]
    for c in cands:
        if c.lower() in head:
            return True
    if len(label) < 2 and label and label in text[:80]:   # 裸数字章号（Dawnshard）
        return True
    return False


def clean_piece(book, pos, start, end):
    frag = book.body(pos)
    if start is None:
        start = 0
    if end is None:
        end = len(frag)
    piece = frag[start:end]
    return R.clean_fragment("<body>" + piece + "</body>")


def safe_name(label):
    s = re.sub(r"[^A-Za-z0-9_\-一-鿿]+", "_", label).strip("_")
    return (s[:MAX_TITLE_LEN].rstrip("_")) or "chapter"


def assemble(book, start, end, lang, label, warnings):
    """拼接 [start, end)（(spine_pos, off)）为清理后的正文片段列表。"""
    spos, soff = start
    epos, eoff = end
    pieces = []
    if spos == epos:
        if soff < eoff:
            pieces.append((spos, soff, eoff))
    else:
        pieces.append((spos, soff, None))
        for p in range(spos + 1, epos):
            pieces.append((p, None, None))
        if epos < len(book.spine):
            pieces.append((epos, None, eoff))
    frags, texts = [], []
    for pos, a, b in pieces:
        frag = clean_piece(book, pos, a, b)
        frag = frag.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not frag:
            continue
        frags.append(frag)
        texts.append(R.text_of(frag))
    if not frags:
        return "", ""
    total = "".join(texts).strip()
    if len(frags) > 1 and all(len(t) < TINY_TEXT for t in texts):
        # 整章都是分隔页：保留最大的一段，避免空文件
        keep_i = max(range(len(frags)), key=lambda i: len(texts[i]))
        frags, texts = [frags[keep_i]], [texts[keep_i]]
    elif len(frags) > 1:
        keep = [(f, t) for f, t in zip(frags, texts) if len(t) >= TINY_TEXT] or \
               [(frags[0], texts[0])]
        frags = [f for f, _ in keep]
    body = "\n".join(frags).strip()
    text = R.text_of(body).strip()
    if not has_title(label, text):
        body = f'<h1 class="chapter-title">{html_mod.escape(label)}</h1>\n' + body
    return body, text


def write_chapter(outdir, order, label, body, lang):
    safe = safe_name(label)
    fn = os.path.join(outdir, f"{order:03d}_{safe}.html")
    n = 1
    while os.path.exists(fn):
        n += 1
        fn = os.path.join(outdir, f"{order:03d}_{safe}_{n}.html")
    doc = (f"<!DOCTYPE html><html lang='{lang}'><head><meta charset='utf-8'>"
           f"<title>{html_mod.escape(label)}</title></head><body>\n{body}\n</body></html>")
    with open(fn, "w", encoding="utf-8") as f:
        f.write(doc)
    return fn


def apply_splits(label, body, specs, warnings):
    """纠正漏切的章：在正文里的章标题标记处切成两章，标记段落升级为 <h1>。"""
    parts = [(label, body)]
    for spec in specs or []:
        if spec.get("label") != label or not parts:
            continue
        cur_label, cur_body = parts.pop()
        marker, into = spec["at"], spec.get("into", spec["at"])
        m = re.search(
            r"(?is)<(p|h[1-6]|div)[^>]*>[^<>]*" + re.escape(marker) + r"[^<>]*</\1>",
            cur_body)
        if m:
            cut = cur_body.find(m.group(0))
            head, tail = cur_body[:cut], cur_body[cut + len(m.group(0)):]
            parts.append((cur_label, head.strip()))
            parts.append((into, (f'<h1 class="chapter-title">{html_mod.escape(into)}</h1>'
                                 + tail).strip()))
            warnings.append(f"按正文标题切章: {label!r} -> {label!r} + {into!r}")
        else:
            i = cur_body.find(marker)
            if i < 0:
                warnings.append(f"split 标记未找到: {marker!r} in {label!r}")
                parts.append((cur_label, cur_body))
                continue
            cut = cur_body.rfind("<", 0, i)
            parts.append((cur_label, cur_body[:cut].strip()))
            parts.append((into, cur_body[cut:].strip()))
    return parts


def run_toc(book, cfg, outdir, dry_run):
    warnings = book.warnings
    entries = book.resolve_entries()
    keep_pats = list(DEFAULT_KEEP) + list(cfg.get("keep_extra") or [])
    drop_pats = list(DEFAULT_DROP) + list(cfg.get("drop_extra") or [])
    for e in entries:
        e["keep"] = is_keep(e["label"], keep_pats, drop_pats)
    # 同 (pos, off) 的条目归并：组内只要有一个白名单条目，就取 TOC 序最靠前的那个
    groups = {}
    for e in entries:
        groups.setdefault((e["pos"], e["off"]), []).append(e)
    kept = []
    for key in sorted(groups):
        items = groups[key]
        content = [i for i in items if i["keep"]]
        if not content:
            continue
        if len({i["label"] for i in content}) > 1:
            warnings.append(
                "同位置多个章节条目，取第一个: " + " | ".join(i["label"] for i in content))
        kept.append(min(content, key=lambda i: i["toc"]))
    if not kept:
        warnings.append("TOC 里没有命中白名单的章节条目 —— 未产出")
        return 0
    # 末章截断：末章之后第一条非白名单 TOC 条目（尾注/秘典/Annotations…）
    cut = (len(book.spine), 0)
    last_key = (kept[-1]["pos"], kept[-1]["off"])
    for key in sorted(groups):
        if key <= last_key:
            continue
        if any(not i["keep"] for i in groups[key]):
            cut = key
            break
    rows = []
    for i, k in enumerate(kept):
        start = (k["pos"], k["off"])
        end = (kept[i + 1]["pos"], kept[i + 1]["off"]) if i + 1 < len(kept) else cut
        if end <= start:
            warnings.append(f"章节边界异常（起点不早于终点）: {k['label']!r}")
            end = (start[0], start[1])
        rows.append((k["label"], start, end))
    print(f"  TOC 条目 {len(entries)} -> 白名单章节 {len(kept)}，末章截断于 "
          f"{'spine末尾' if cut[0] >= len(book.spine) else os.path.basename(book.spine[cut[0]])}")
    if dry_run:
        for label, s, e in rows:
            print(f"    {label!r}  [{s[0]}:{s[1]}] -> [{e[0]}:{e[1]}]")
        return len(rows)
    out = []
    order = 0
    for label, s, e in rows:
        body, text = assemble(book, s, e, cfg["lang"], label, warnings)
        if not body:
            warnings.append(f"空章节被跳过: {label!r}")
            continue
        for lab, part in apply_splits(label, body, cfg.get("split"), warnings):
            write_chapter(outdir, order, lab, part, cfg["lang"])
            out.append((order, lab, R.text_of(part).strip()))
            order += 1
    report(outdir, out, warnings)
    return len(out)


def run_each_file(book, cfg, outdir, dry_run):
    warnings = book.warnings
    rows = []
    for pos in range(len(book.spine)):
        frag = clean_piece(book, pos, None, None)
        frag = frag.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not frag:
            continue
        text = R.text_of(frag).strip()
        if len(text) < 40:
            continue
        first = next((ln.strip() for ln in text.split("\n") if ln.strip()), "")
        label = first if 0 < len(first) <= 64 else os.path.basename(book.spine[pos])
        rows.append((label, pos, frag, text))
    print(f"  spine 文件 {len(book.spine)} -> 正文文件 {len(rows)}")
    if dry_run:
        for label, pos, _, _ in rows:
            print(f"    {label!r}  [{pos}]")
        return len(rows)
    out = []
    for order, (label, pos, frag, text) in enumerate(rows):
        body = frag
        if not has_title(label, text):
            body = f'<h1 class="chapter-title">{html_mod.escape(label)}</h1>\n' + body
        write_chapter(outdir, order, label, body, cfg["lang"])
        out.append((order, label, text))
    report(outdir, out, warnings)
    return len(out)


def report(outdir, out, warnings):
    if not out:
        print("  !! 没有产出任何章节")
        return
    lens = [len(t) for _, _, t in out]
    short = [(o, lab, len(t)) for o, lab, t in out if len(t) < 500]
    print(f"  ✓ {len(out)} 章 -> {outdir}  正文总长 {sum(lens)} 字符，"
          f"最短 {min(lens)} / 最长 {max(lens)}")
    for o, lab, t in out:
        head = re.sub(r"\s+", " ", t)[:56]
        print(f"     [{o:03d}] {lab[:40]:<42} {len(t):>7}  {head}")
    if short:
        print(f"  ! 短章节（<500 字符）: {[(o, lab) for o, lab, _ in short]}")
    uniq = list(dict.fromkeys(warnings))
    for w in uniq[:20]:
        print(f"  ! {w}")
    if len(uniq) > 20:
        print(f"  ! …共 {len(uniq)} 条告警（已省略 {len(uniq) - 20} 条）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT_DIR)
    ap.add_argument("--book", help="只处理指定输出子目录名")
    ap.add_argument("--dry-run", action="store_true", help="只打印分章方案，不写文件")
    ap.add_argument("--list", action="store_true", help="列出书单")
    args = ap.parse_args()

    if args.list:
        for cfg in BOOKS:
            print(f"{cfg['out']:<28} {cfg.get('mode','toc'):<9} {cfg['lang']}  {cfg['src']}")
        return

    os.makedirs(args.out, exist_ok=True)
    done = 0
    for cfg in BOOKS:
        if args.book and args.book != cfg["out"]:
            continue
        src = os.path.join(ROOT, cfg["src"])
        if not os.path.exists(src):
            print(f"!! 跳过（找不到文件）: {cfg['src']}")
            continue
        outdir = os.path.join(args.out, cfg["out"])
        print(f"== {cfg['out']}  <- {os.path.basename(src)}")
        if not args.dry_run:
            if os.path.isdir(outdir):
                shutil.rmtree(outdir)
            os.makedirs(outdir, exist_ok=True)
        warnings = []
        book = Book(src, warnings, spine_slice=cfg.get("slice"))
        book.apply_strips(cfg.get("strip"))
        mode = cfg.get("mode", "toc")
        if mode == "toc":
            n = run_toc(book, cfg, outdir, args.dry_run)
        else:
            n = run_each_file(book, cfg, outdir, args.dry_run)
        book.zf.close()
        done += 1
        if n == 0:
            print("  !! 未产出")
    print(f"完成：共处理 {done} 本。")


if __name__ == "__main__":
    main()
