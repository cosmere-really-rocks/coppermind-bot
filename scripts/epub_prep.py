#!/usr/bin/env python3
"""
epub_prep.py —— 中英 epub 章节对齐工具（供译名表补全用）

背景：要补全「Allik Neverfar」这类全名译名，需要在中译本里定位官方译名。
本工具把 epub 解压并按正确阅读顺序（spine）重排成纯文本/可读文本，供：
  1) 英文版 定位关键词出现的章节与上下文
  2) 中文版 在对应章节里找译名

用法：
  python scripts/epub_prep.py <file.epub> --list             # 列章节
  python scripts/epub_prep.py <file.epub> --dump <outdir>    # 按章节导出 <n>_<title>.txt
  python scripts/epub_prep.py <file.epub> --find 'Allik Neverfar'  # 定位关键词
  python scripts/epub_prep.py <en.epub> --find 'Allik Neverfar' --zh <zh.epub>  # 中英同章对照

原则：受版权保护，只做本地处理，绝不提交/传播。
"""
import argparse
import os
import re
import sys
import zipfile
from html import unescape
from xml.etree import ElementTree as ET

OPF_NS = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
PKG_NS = {"p": "http://www.idpf.org/2007/opf"}
XHTML_NS = {"x": "http://www.w3.org/1999/xhtml"}


def read_container(zf):
    """读 META-INF/container.xml 找 opf 路径。"""
    data = zf.read("META-INF/container.xml")
    root = ET.fromstring(data)
    for rf in root.findall(".//c:rootfile", OPF_NS):
        return rf.get("full-path")
    raise RuntimeError("container.xml 里没有 rootfile")


def read_opf(zf, opf_path):
    """读 opf：返回 spine 顺序的 (idref->href) 列表、以及 title。"""
    data = zf.read(opf_path)
    root = ET.fromstring(data)
    base_dir = os.path.dirname(opf_path)
    manifest = {m.get("id"): m.get("href") for m in root.findall("p:manifest/p:item", PKG_NS)}
    spine = [i.get("idref") for i in root.findall("p:spine/p:itemref", PKG_NS)]
    title = ""
    title_el = root.find("p:metadata/p:title", PKG_NS) or root.find(".//{http://purl.org/dc/elements/1.1/}title")
    if title_el is not None and title_el.text:
        title = title_el.text
    chapters = []
    for idref in spine:
        href = manifest.get(idref)
        if href is None:
            continue
        # 统一斜杠，解析相对 opf 目录
        full = os.path.normpath(os.path.join(base_dir, href)).replace("\\", "/")
        # 只收 xhtml/html 章
        if full.lower().endswith((".xhtml", ".html", ".htm")):
            chapters.append(full)
    return title, chapters


def strip_html(html_text):
    """xhtml -> 纯文本：去标签、去脚本/样式、解实体、折叠空白。"""
    html_text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html_text)
    # 段落/块级标签换行
    html_text = re.sub(r"(?i)<(p|/p|div|/div|h[1-6]|/h[1-6]|br|li|/li|tr|/tr|blockquote|/blockquote)[^>]*>", "\n", html_text)
    html_text = re.sub(r"<[^>]+>", " ", html_text)
    html_text = unescape(html_text)
    # 折叠空白
    lines = [re.sub(r"[ \t\u00a0]+", " ", ln).strip() for ln in html_text.split("\n")]
    text = "\n".join(l for l in lines if l)
    return text


def load_chapters(zf, chapters):
    out = []
    for n, path in enumerate(chapters):
        try:
            raw = zf.read(path).decode("utf-8", errors="replace")
        except KeyError:
            raw = ""
        out.append((n, path, strip_html(raw)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("epub")
    ap.add_argument("--list", action="store_true", help="列出章节顺序与标题")
    ap.add_argument("--dump", metavar="OUTDIR", help="按章节导出 txt")
    ap.add_argument("--find", metavar="TERM", help="定位关键词（英文版）")
    ap.add_argument("--zh", metavar="ZH_EPUB", help="对应中文版 epub，配合 --find 做同章对照")
    args = ap.parse_args()

    with zipfile.ZipFile(args.epub) as zf:
        opf = read_container(zf)
        title, chapters = read_opf(zf, opf)
        print(f"# {title}  ({len(chapters)} 章)")
        for n, ch in enumerate(chapters):
            print(f"  [{n:>3}] {ch}")

        if args.dump:
            os.makedirs(args.dump, exist_ok=True)
            for n, path, text in load_chapters(zf, chapters):
                out = os.path.join(args.dump, f"{n:03d}.txt")
                with open(out, "w", encoding="utf-8") as f:
                    f.write(text)
                print(f"  dump {out}  ({len(text)} chars)")

        if args.find:
            term = args.find
            for n, path, text in load_chapters(zf, chapters):
                idx = 0
                while True:
                    i = text.lower().find(term.lower(), idx)
                    if i < 0:
                        break
                    print(f"\n  >>> 章[{n}] {os.path.basename(path)} @ char {i}")
                    print("      ...", text[max(0, i-120):i+120].replace("\n", " "), "...")
                    idx = i + len(term)

        if args.zh and args.find:
            term = args.find
            print(f"\n===== 中文版对照 {args.zh} （同章文本，供人工找译名）=====")
            with zipfile.ZipFile(args.zh) as zc:
                to = read_container(zc)
                _, zh_chapters = read_opf(zc, to)
                # 先找英文词所在章
                hit = None
                for n, path, text in load_chapters(zf, chapters):
                    if term.lower() in text.lower():
                        hit = n
                        break
                if hit is None:
                    print("（英文版未找到该词）")
                elif hit < len(zh_chapters):
                    _, _, ztext = load_chapters(zc, zh_chapters)[hit]
                    out = f"zh_chapter_{hit:03d}.txt"
                    with open(out, "w", encoding="utf-8") as f:
                        f.write(ztext)
                    print(f"  中文版章[{hit}] {os.path.basename(zh_chapters[hit])} -> 已导出 {out}")
                    print(f"  （请在 {out} 里按英文版命中位置附近找译名）")
                else:
                    print(f"（英文命中章 {hit} 超出中文版章数 {len(zh_chapters)}）")


if __name__ == "__main__":
    main()
