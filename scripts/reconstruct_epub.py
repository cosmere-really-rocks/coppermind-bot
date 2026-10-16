#!/usr/bin/env python3
"""
reconstruct_epub.py —— 新一批 epub 的分章重构（本地、不提交）

背景：handoff 提到 Trilogy（EN 3 本合集）与中文 1-6（partNNNN 流）需要内容驱动重构。
本次用户提供了大量单行本/清晰分章版，重构难度大幅下降；本脚本逐一处理：

  EN era1 单行本（split 流，章节号嵌在正文里）：
    the_final_empire      [Mistborn 1.1] - The Final Empire.epub
    the_well_of_ascension [Mistborn 1.2] - The Well of Ascension.epub
    the_hero_of_ages      [Mistborn 1.3] - The Hero of Ages.epub
  ZH era1 单行本：
    zh_最后帝国           迷雾之子·01·最后帝国.epub  (cpNN / partNNN，章节号在 <hN>)
    zh_升华之井           迷雾之子·02·升华之井.epub  (chapterNNN)
    zh_永世英雄           迷雾之子·03·永世英雄.epub  (chapterNNN / begin / final)
  ZH era2：
    zh_执法镕金           迷雾之子外传（全三卷）.epub → 卷一部分（补全时代二卷一中译）
    zh_旧影森森           迷雾之子外传 卷二 旧影森森.epub   (txtNNN，p.chapterTitle)
    zh_悲悼护腕           迷雾之子外传 卷三 悲悼护腕.epub   (txtNNN，p.chapterTitle)

通用重构思想：按 spine 顺序扫描，每个文件用一个「锚点分类器」判断是否开启新章。
  - 开启新章的锚点：PROLOGUE/EPILOGUE、楔子/序言/尾声、裸数字章节号、第X章标题。
  - 非锚点内容：front matter（第一个锚点前）全部丢弃；第一个锚点后的（PART 页、epigraph、
    插图/占位页、镕金秘典等）挂入待处理缓冲，归属到「下一个」新章。
  - 结尾未归入任何章的缓冲（如 ARS ARCANUM / teaser / 封面）自然丢弃。

输出：dict/epub_out/<book>/NNN_<chapter>.html
用法：
  .venv/bin/python scripts/reconstruct_epub.py               # 全部
  .venv/bin/python scripts/reconstruct_epub.py --book zh_执法镕金
"""
import argparse
import html as html_mod
import os
import re
import zipfile
from xml.etree import ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EPUB_DIR = os.path.join(ROOT, "dict", "epub")
OUT_DIR = os.path.join(ROOT, "dict", "epub_out")

OPF_NS = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
PKG_NS = {"p": "http://www.idpf.org/2007/opf"}


def read_container(zf):
    data = zf.read("META-INF/container.xml")
    root = ET.fromstring(data)
    for rf in root.findall(".//c:rootfile", OPF_NS):
        return rf.get("full-path")
    raise RuntimeError("no rootfile")


def read_opf(zf, opf_path):
    data = zf.read(opf_path)
    root = ET.fromstring(data)
    base = os.path.dirname(opf_path)
    manifest = {m.get("id"): m.get("href") for m in root.findall("p:manifest/p:item", PKG_NS)}
    spine = [i.get("idref") for i in root.findall("p:spine/p:itemref", PKG_NS)]
    title = root.find("p:metadata/p:title", PKG_NS) or root.find(".//{http://purl.org/dc/elements/1.1/}title")
    title = title.text if (title is not None and title.text) else ""
    chapters = []
    for idref in spine:
        href = manifest.get(idref)
        if href is None:
            continue
        full = os.path.normpath(os.path.join(base, href)).replace("\\", "/")
        if full.lower().endswith((".xhtml", ".html", ".htm")):
            chapters.append(full)
    return title, chapters


def clean_fragment(raw):
    """body 内部 HTML：去脚本/样式，图片降为 [图:alt]，链接保留文本。"""
    m = re.search(r"(?is)<body[^>]*>(.*)</body>", raw)
    frag = m.group(1) if m else raw
    frag = re.sub(r"(?is)<(script|style|head|title)[^>]*>.*?</\1>", " ", frag)

    def img_repl(mo):
        alt = mo.group(1) or ""
        return f"[图:{alt}]" if alt.strip() else ""
    frag = re.sub(r'(?is)<img[^>]*?alt=["\']([^"\']*)["\'][^>]*>', img_repl, frag)
    frag = re.sub(r"(?i)<img[^>]*>", "", frag)
    frag = re.sub(r"(?is)<a\b[^>]*>(.*?)</a>", r"\1", frag)
    return frag.strip()


def text_of(frag):
    t = re.sub(r"(?is)<(p|/p|div|/div|h[1-6]|/h[1-6]|br|/br|li|/li)>", "\n", frag)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"[ \t\u00a0]+", " ", html_mod.unescape(t)).strip()


# ---------------------------------------------------------------------------
# 锚点分类器
# ---------------------------------------------------------------------------

H2 = r"""[一二三四五六七八九十百千零]+"""

_ZH_NUM = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
           "六": 6, "七": 7, "八": 8, "九": 9}


def zh_num_to_int(s):
    if not s:
        return 0
    if "十" in s:
        left, _, right = s.partition("十")
        tens = _ZH_NUM.get(left, 1) if left else 1
        ones = _ZH_NUM.get(right, 0) if right else 0
        return tens * 10 + ones
    if "百" in s:
        left, _, right = s.partition("百")
        h = _ZH_NUM.get(left, 1) if left else 1
        return h * 100 + zh_num_to_int(right or "0")
    return sum(_ZH_NUM.get(c, 0) for c in s)


def extract_heading(body):
    """返回正文里第一个「标题文本」：优先 <h1>-<h6>，其次部分中文书的 <p class=chapterTitle>，再次 <b>/<strong>/bold span。"""
    for tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        m = re.search(rf"(?is)<{tag}[^>]*>(.*?)</{tag}>", body)
        if m:
            t = re.sub(r"<[^>]+>", " ", m.group(1)).strip()
            if t:
                return t
    # 中文书常见的 p.chapterTitle
    m = re.search(r'(?is)<p[^>]*class="[^"]*chaptertitle[^"]*"[^>]*>(.*?)</p>', body)
    if m:
        t = re.sub(r"<[^>]+>", " ", m.group(1)).strip()
        if t:
            return t
    # 强调样式（bold / b / strong）
    m = re.search(r'(?is)<(?:span class="[^"]*bold[^"]*"|<b\b|<strong\b)[^>]*>(.*?)</(?:span|b|strong)>', body)
    if m:
        t = re.sub(r"<[^>]+>", " ", m.group(1)).strip()
        if t:
            return t
    # 无标题
    return None


def classify_heading(h):
    """h -> ('chapter', int) | ('prologue',None) | ('epilogue',None) | None（非锚点）"""
    if h is None:
        return None
    h = h.strip()
    if not h:
        return None
    if re.fullmatch(r"\d{1,3}", h):
        return ("chapter", int(h))
    up = h.upper()
    if up in ("PROLOGUE", "PROLOG"):
        return ("prologue", None)
    if up in ("EPILOGUE", "EPILOG"):
        return ("epilogue", None)
    if up in ("POSTSCRIPT", "AFTERWORD", "EPILOGUE 2"):
        return ("postscript", None)
    if h in ("楔子", "序言"):
        return ("prologue", None)
    if h in ("尾声", "终章", "终曲"):
        return ("epilogue", None)
    if h == "后记":
        return ("postscript", None)
    m = re.match(rf"^第({H2})章$", h)
    if m:
        return ("chapter", zh_num_to_int(m.group(1)))
    # 第X章 + 副题（如「第壹章 幸存者继承人」）→ 这是部分/章分页，视作非锚点（作 part 页）
    # —— 目录/前言/版权等 front/back matter 一律丢弃（即使出现在第一章之后）
    if h in _DROP_HEADINGS:
        return ("drop", None)
    return None


# 无论出现在书的任何位置都整页丢弃（目录/前言/版权/鸣谢/作者译者简介/镕金秘典等）
_DROP_HEADINGS = {
    "目录", "目　录", "contents", "contents", "版权信息", "版权", "图书在版编目",
    "前言", "导读", "序", "代序",
    "鸣谢", "致谢", "acknowledgments", "acknowledgements",
    "作者简介", "译者简介", "关于作者",
    "镕金秘典", "金属列表", "名词解释", "ars arcanum", "致读者",
    "封面", "封底", "约稿", "版权页",
}


class Classifier:
    def classify(self, raw):
        m = re.search(r"(?is)<body[^>]*>(.*)</body>", raw)
        body = m.group(1) if m else raw
        h = extract_heading(body)
        return classify_heading(h)


def gen_book(zf, chapters, outdir, lang):
    """通用重构：spine 顺序扫描，锚点开新章，其余挂缓冲归属下一章；front matter 丢弃。"""
    det = Classifier()
    pending = []
    in_front = True
    order = 0
    written = []
    dropped_tail = 0
    for path in chapters:
        raw = zf.read(path).decode("utf-8", "replace")
        cls = det.classify(raw)
        frag = clean_fragment(raw)
        if cls is not None and cls[0] == "drop":
            # 目录/版权/鸣谢/镕金秘典等：永远丢弃，不混入正文章节
            continue
        if cls is not None:
            if in_front:
                in_front = False
                pending = []
            key = cls[0]
            if cls[0] == "chapter":
                key = f"chapter{cls[1]}"
            written.append((order, key, pending + [frag]))
            order += 1
            pending = []
        else:
            if in_front:
                continue
            pending.append(frag)
    # 写入（结尾未归章的缓冲丢弃）
    for o, key, frags in written:
        body = "\n".join(frags)
        safe_key = re.sub(r"[^A-Za-z0-9_\-\u4e00-\u9fff]+", "_", key).strip("_") or f"ch{o:03d}"
        fn = os.path.join(outdir, f"{o:03d}_{safe_key}.html")
        doc = (f"<!DOCTYPE html><html lang='{lang}'><head><meta charset='utf-8'>"
               f"<title>{html_mod.escape(key)}</title></head><body>\n{body}\n</body></html>")
        with open(fn, "w", encoding="utf-8") as f:
            f.write(doc)
    print(f"  {os.path.basename(outdir)}: {len(written)} 章 -> {outdir}  (尾部未归入挂起 {len(pending)} 文件)")
    return written


# ---------------------------------------------------------------------------
# 书单
# ---------------------------------------------------------------------------

# 源文件名 -> (输出子目录, 语言)
ENBOOKS = {
    "[Mistborn 1.1] - The Final Empire.epub": ("the_final_empire", "en"),
    "[Mistborn 1.2] - The Well of Ascension.epub": ("the_well_of_ascension", "en"),
    "[Mistborn 1.3] - The Hero of Ages.epub": ("the_hero_of_ages", "en"),
}

ZHBOOKS = {
    "Brandon Sanderson - 迷雾之子·01·最后帝国 - 9787229105136.epub": "zh_最后帝国",
    "Brandon Sanderson - 迷雾之子·02·升华之井 - 9787229105952.epub": "zh_升华之井",
    "Brandon Sanderson - 迷雾之子·03·永世英雄 - 9787229110000.epub": "zh_永世英雄",
    "迷雾之子外传 卷二 旧影森森 (（美）布兰登·桑德森 著) (z-library.sk, 1lib.sk, z-lib.sk).epub": "zh_旧影森森",
    "迷雾之子外传 卷三 悲悼护腕 (（美）布兰登·桑德森 著) (z-library.sk, 1lib.sk, z-lib.sk).epub": "zh_悲悼护腕",
}

OMNIBUS_ERA2_VOL1 = {
    # 源文件 -> (所有书) -> 我们只取卷一（执法镕金），spine 2..29
    "迷雾之子外传（全三卷）.epub": "zh_执法镕金",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT_DIR)
    ap.add_argument("--book", help="只处理指定输出子目录名")
    args = ap.parse_args()
    outdir = args.out
    os.makedirs(outdir, exist_ok=True)

    processed = 0
    for src_name, (book, lang) in ENBOOKS.items():
        if args.book and args.book != book:
            continue
        src = os.path.join(EPUB_DIR, src_name)
        if not os.path.exists(src):
            print(f"!! 跳过（找不到）: {src_name}")
            continue
        d = os.path.join(outdir, book)
        os.makedirs(d, exist_ok=True)
        with zipfile.ZipFile(src) as zf:
            _, chapters = read_opf(zf, read_container(zf))
            gen_book(zf, chapters, d, lang)
        processed += 1

    for src_name, book in ZHBOOKS.items():
        if args.book and args.book != book:
            continue
        src = os.path.join(EPUB_DIR, src_name)
        if not os.path.exists(src):
            print(f"!! 跳过（找不到）: {src_name}")
            continue
        d = os.path.join(outdir, book)
        os.makedirs(d, exist_ok=True)
        with zipfile.ZipFile(src) as zf:
            _, chapters = read_opf(zf, read_container(zf))
            gen_book(zf, chapters, d, "zh")
        processed += 1

    for src_name, book in OMNIBUS_ERA2_VOL1.items():
        if args.book and args.book != book:
            continue
        src = os.path.join(EPUB_DIR, src_name)
        if not os.path.exists(src):
            print(f"!! 跳过（找不到）: {src_name}")
            continue
        d = os.path.join(outdir, book)
        os.makedirs(d, exist_ok=True)
        with zipfile.ZipFile(src) as zf:
            _, chapters = read_opf(zf, read_container(zf))
            # 只取卷一（执法镕金）：spine 2..29；其余（卷二/卷三）不归此书
            gen_book(zf, chapters[2:29], d, "zh")
        processed += 1

    if args.book and processed == 0:
        print(f"!! 未处理任何书：找不到输出子目录名 {args.book!r}")
    print(f"完成：共处理 {processed} 本。")


if __name__ == "__main__":
    main()
