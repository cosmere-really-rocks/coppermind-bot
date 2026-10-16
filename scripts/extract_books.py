#!/usr/bin/env python3
"""
extract_books.py —— 把英文 epub 按书拆成「分章节 HTML」（本地、不提交）

背景：为译名表补全（如 Allik Neverfar 全名）做中英章节对齐。本脚本处理
「一文件一章节」的干净英文书（Alloy/Shadows/Bands/Lost Metal/Secret History）。
Trilogy（3 本合集）与中文 1-6（partNNNN 流）需要内容驱动重构，另见 HANDOFF。

输出：dict/epub_out/<book>/NNN_<chapter>.html —— 保留阅读顺序、跳过 front/back matter。

用法：
  .venv/bin/python scripts/extract_books.py --out dict/epub_out
"""
import argparse
import html
import os
import re
import zipfile
from xml.etree import ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EPUB_DIR = os.path.join(ROOT, "dict", "epub")

OPF_NS = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
PKG_NS = {"p": "http://www.idpf.org/2007/opf"}

# 每本书：源 epub 文件名 -> 输出子目录名
BOOKS = {
    "THE_ALLOY_OF_LAW_EPUB.epub": "the_alloy_of_law",
    "SHADOWS_OF_SELF_EPUB.epub": "shadows_of_self",
    "THE_BANDS_OF_MOURNING_EPUB.epub": "the_bands_of_mourning",
    "Mistborn 07 - The Lost Metal (Brandon Sanderson) (z-lib.org).epub": "the_lost_metal",
    "[Mistborn 1.5] - Secret History (epub).epub": "secret_history",
}

# front/back matter 文件名（去掉扩展名后 base 名匹配即跳过）
SKIP_BASE = {
    "cover", "cover_page", "title", "titlepage", "title_page", "package_notice",
    "dedication", "acknowledgments", "acknowledgement", "contents", "copyright",
    "copyrightnotice", "abouttheauthor", "adcard", "backad", "backad1", "backad2",
    "backad-1", "backad-2", "backad3", "teaser", "teaser-pro", "teaser-c1", "teaser-c2",
    "newsletter", "torad", "arcanum", "map1", "maps", "map", "alsoby", "preface",
    "frontmatter", "backmatter", "half", "halftitle",
    "part", "part1", "part2", "part3",  # 这些是章节分隔页，通常无正文；单独决定
}


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
    title = (root.find("p:metadata/p:title", PKG_NS) or root.find(".//{http://purl.org/dc/elements/1.1/}title"))
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


def is_content(path):
    """判断 spine 文件是否为正文章节（跳过 front/back matter）。"""
    base = os.path.basename(path).rsplit(".", 1)[0].lower()
    # Secret History 部件：Part-N, N-M, Epilogue, Postscript
    if re.match(r"^(part-\d+|epilogue|postscript)$", base):
        return True
    if re.match(r"^\d+-\d+$", base):
        return True
    if base in SKIP_BASE:
        return False
    # 标准章节（含 split 片段、Alloy 的 978..._chnN 插页）
    if re.match(r"^(prologue|chapter\d+(_split_\d+)?|978\w*_ch\d+|epilogue|postscript)$", base):
        return True
    return False


def group_key(path, idx):
    """逻辑章节分组：chapterN_split_NNN 归并到 chapterN；其余一文件一章节。"""
    base = os.path.basename(path).rsplit(".", 1)[0].lower()
    m = re.match(r"^(chapter\d+)_split_\d+$", base)
    if m:
        return m.group(1)
    # Alloy 的 978..._ch0N 插页、Part-N、N-M、prologue 等：独立章节
    return base


def clean_fragment(path, raw):
    """取 body 内部 HTML，去脚本/样式，保留段落/标题/强调，去图片链接成文本。"""
    # 取 body
    m = re.search(r"(?is)<body[^>]*>(.*)</body>", raw)
    frag = m.group(1) if m else raw
    # 去掉 script/style/head 残留
    frag = re.sub(r"(?is)<(script|style|head|title)[^>]*>.*?</\1>", " ", frag)
    # 图片 -> 保留 alt/标题文本（图片文件不上传，但文本引用值得留）
    def img_repl(mo):
        alt = mo.group(1) or ""
        return f"[图:{alt}]" if alt.strip() else ""
    frag = re.sub(r'(?is)<img[^>]*?alt=["\']([^"\']*)["\'][^>]*>', img_repl, frag)
    frag = re.sub(r"(?i)<img[^>]*>", "", frag)
    # 链接保留文本、去 href（保留内链文本供找词）
    frag = re.sub(r"(?is)<a\b[^>]*>(.*?)</a>", r"\1", frag)
    return frag.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "dict", "epub_out"))
    ap.add_argument("--book", help="只处理指定书的源文件名（可选）")
    args = ap.parse_args()

    for epub_name, out_name in BOOKS.items():
        if args.book and args.book != epub_name:
            continue
        src = os.path.join(EPUB_DIR, epub_name)
        if not os.path.exists(src):
            print(f"!! 跳过（找不到文件）: {epub_name}")
            continue
        outdir = os.path.join(args.out, out_name)
        os.makedirs(outdir, exist_ok=True)
        with zipfile.ZipFile(src) as zf:
            opf = read_container(zf)
            title, chapters = read_opf(zf, opf)
            # 按逻辑章节分组（chapterN_split_NNN 归并为 chapterN）
            groups = []
            seen = {}
            order = 0
            for idx, ch in enumerate(chapters):
                if not is_content(ch):
                    continue
                key = group_key(ch, idx)
                raw = zf.read(ch).decode("utf-8", "replace")
                frag = clean_fragment(ch, raw)
                if not frag and key not in seen:
                    continue
                if key in seen:
                    groups[seen[key]]["frag"].append(frag)
                else:
                    seen[key] = len(groups)
                    groups.append({"key": key, "order": order, "frag": [frag]})
                    order += 1
            n_content = 0
            for g in groups:
                body = "\n".join(g["frag"])
                safe = re.sub(r"[^A-Za-z0-9_-]+", "_", g["key"]).strip("_") or f"ch{g['order']:03d}"
                fn = os.path.join(outdir, f"{g['order']:03d}_{safe}.html")
                doc = (f"<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
                       f"<title>{html.escape(g['key'])}</title></head><body>\n{body}\n</body></html>")
                with open(fn, "w", encoding="utf-8") as f:
                    f.write(doc)
                n_content += 1
            print(f"✓ {out_name}: {n_content} 正文章节 -> {outdir}")
            skipped = [os.path.basename(c) for c in chapters if not is_content(c)]
            print(f"    跳过 {len(skipped)} 个 front/back文件（示例: {skipped[:5]}）")


if __name__ == "__main__":
    main()
