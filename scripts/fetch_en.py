#!/usr/bin/env python3
"""
英文站抓取落盘脚本（决策 B/C）：
  1. 对给定标题查询英文站当前 revid
  2. 与 state/en_index.json 比对：revid 相同 -> 跳过；否则抓取
  3. 抓取 wikitext 落盘 en_snapshot/<title>/wikitext.txt + meta.json
  4. 用 mwparserfromhell 提取该页用到的 templates / files / categories / redirect
  5. 更新 state/en_index.json
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

import cloudscraper

# 项目路径
HERE = Path(__file__).resolve().parent          # scripts/
ROOT = HERE.parent                               # coppermind/
EN_SNAPSHOT = ROOT / "en_snapshot"
STATE = ROOT / "state"
INDEX_FILE = STATE / "en_index.json"
EN_API = "https://coppermind.net/w/api.php"

EN_TITLES = "_redirects"  # 不存在的页，API 在 titles 里用 _redirects 标记


def get_session():
    s = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "windows", "mobile": False, "desktop": True}
    )
    return s


def api_get(s, params):
    params = dict(params, format="json")
    r = s.get(EN_API, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def load_index():
    if INDEX_FILE.exists():
        return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    return {}


def save_index(idx):
    STATE.mkdir(exist_ok=True)
    tmp = INDEX_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(INDEX_FILE)


def canonical_title(title: str) -> str:
    """MediaWiki 标题规范化：首字母大写、下划线转空格。"""
    t = title.strip().replace("_", " ")
    if t:
        t = t[0].upper() + t[1:]
    return t


def normalize_file_name(fn: str) -> str:
    """文件/模板名规范化：去掉前缀与多余空白。"""
    fn = fn.strip()
    fn = re.sub(r"^[^:]+:", "", fn)  # 去掉 File: / Template: 等前缀
    fn = fn.split("|", 1)[0]        # 去掉竖线参数
    fn = fn.strip()
    return fn


IMG_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".tif", ".tiff")


def looks_like_file(value: str) -> bool:
    """判断一个字符串是否像文件名（含图片扩展名，或含 File:/Image: 前缀）。"""
    v = value.strip()
    if not v:
        return False
    low = v.lower()
    if low.startswith(("file:", "image:")):
        return True
    if "|" in v:
        v = v.split("|", 1)[0].strip()
    return v.lower().endswith(IMG_EXT)


def extract_assets(wikitext: str, title: str):
    """用 mwparserfromhell 解析，返回 {templates, files, categories, wikilinks, redirect_target}。

    文件提取策略（决策第 7 条：静态分析可能不完整，允许手动补充）：
      1. [[File:...]] 直接链接
      2. {{image}} 模板的「第一个位置参数」（Coppermind 约定：图片文件名）
      3. 任意模板中像文件名的「命名参数值」（如 character 的 image=、封面 logo= 等）
    人工无法覆盖的仍可在 meta.json 里手动补充。
    """
    import mwparserfromhell

    code = mwparserfromhell.parse(wikitext)

    templates = set()
    for t in code.filter_templates():
        templates.add(normalize_file_name(str(t.name)))

    # 1) [[File:...]] 直接链接
    files = set()
    for tl in code.filter_wikilinks():
        target = str(tl.title)
        if target.lower().startswith(("file:", "image:")):
            files.add(normalize_file_name(target))

    # 2/3) 扫描模板参数里的文件
    for t in code.filter_templates():
        tname = normalize_file_name(str(t.name)).lower()
        # {{image|文件名|...}} —— 第一个位置参数
        params = t.params
        first_pos = None
        for p in params:
            if p.showkey is None:
                first_pos = str(p.value).strip()
                break
        if tname == "image" and first_pos and looks_like_file(first_pos):
            files.add(normalize_file_name(first_pos))
        # 任意模板里「文件感的命名参数值」
        for p in params:
            if p.showkey is None:
                continue
            key = str(p.name).strip().lower()
            val = str(p.value).strip()
            if looks_like_file(val):
                files.add(normalize_file_name(val))

    categories = set()
    for c in code.filter_wikilinks():
        target = str(c.title)
        if target.lower().startswith("category:"):
            name = normalize_file_name(target)
            categories.add(name)
            # 去掉 #锚点 与排序键
            name = re.sub(r"\|.*$", "", name)
            categories.discard(name)

    wikilinks = set()
    for tl in code.filter_wikilinks():
        tgt = str(tl.title)
        if not tgt.lower().startswith(("file:", "image:", "category:")):
            wikilinks.add(normalize_file_name(tgt))

    # redirect 目标 (#REDIRECT [[目标]])
    redirect_target = None
    m = re.match(r"\s*#+?\s*redirect\s*:?\s*\[\[([^\]]+)\]\]", wikitext, re.IGNORECASE)
    if m:
        redirect_target = m.group(1).split("|")[0].strip()

    return {
        "templates": sorted(templates),
        "files": sorted(files),
        "categories": sorted(categories),
        "wikilinks": sorted(wikilinks),
        "redirect_target": redirect_target,
    }


def fetch_one(s, idx, title, force=False):
    """抓取单个页面并落盘。redirect 页按自身标题记录（决策第 8 条）。"""
    ctitle = canonical_title(title)

    # 1) 一次请求：取 content + revid + timestamp + redirects 解析
    #    注意：不用 redirects=1，否则重定向会被自动跟随、丢失 redirect 信号。
    r = api_get(s, {
        "action": "query",
        "prop": "revisions",
        "rvprop": "content|ids|timestamp",
        "rvslots": "main",
        "titles": ctitle,
    })
    pages = r.get("query", {}).get("pages", {})

    if not pages or "-1" in pages:
        print(f"  [{ctitle}] 不存在 (missing)")
        idx[ctitle] = {
            "revid": None, "ts": None, "has_wikitext": False,
            "is_redirect": False, "target": None, "missing": True,
        }
        return "missing"

    _, p = next(iter(pages.items()))
    real_title = p.get("title", ctitle)
    ctitle = canonical_title(real_title)
    rev = (p.get("revisions") or [{}])[0]
    revid = rev.get("revid")
    ts = rev.get("timestamp")
    wikitext = rev.get("slots", {}).get("main", {}).get("*", "")

    # 2) 解析重定向目标
    assets = extract_assets(wikitext, ctitle)
    is_redirect = assets["redirect_target"] is not None

    # 3) 判重：revid 相同且已有快照 -> 跳过（除非 --force）
    prev = idx.get(ctitle, {})
    if (not force) and prev.get("revid") is not None and prev.get("revid") == revid and prev.get("has_wikitext"):
        print(f"  [{ctitle}] revid={revid} 未变，跳过")
        return "skip"

    # 4) 落盘
    d = EN_SNAPSHOT / ctitle.replace("/", "_")
    d.mkdir(parents=True, exist_ok=True)
    (d / "wikitext.txt").write_text(wikitext, encoding="utf-8")

    meta = {
        "title": ctitle,
        "revid": revid,
        "timestamp": ts,
        "is_redirect": is_redirect,
        "target": assets["redirect_target"],
        "templates": assets["templates"],
        "files": assets["files"],
        "categories": assets["categories"],
        "wikilinks": assets["wikilinks"],
        "content_length": len(wikitext),
    }
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    idx[ctitle] = {
        "revid": revid,
        "ts": ts,
        "has_wikitext": True,
        "is_redirect": is_redirect,
        "target": assets["redirect_target"],
        "missing": False,
        "snapshot": str(d.relative_to(ROOT)),
        "assets": {
            "templates": assets["templates"],
            "files": assets["files"],
            "categories": assets["categories"],
        },
    }

    kind = "REDIRECT→" + assets["redirect_target"] if is_redirect else "页"
    print(f"  [{ctitle}] 已抓取 {kind} revid={revid} len={len(wikitext)} "
          f"tmpl={len(assets['templates'])} files={len(assets['files'])}")
    return "fetched"


def main():
    ap = argparse.ArgumentParser(description="抓取英文站页面到本地快照")
    ap.add_argument("titles", nargs="+", help="一个或多个页面标题")
    ap.add_argument("--force", action="store_true", help="忽略 revid 判重，强制重抓")
    args = ap.parse_args()

    s = get_session()
    idx = load_index()
    for t in args.titles:
        print(f"== {t}")
        try:
            fetch_one(s, idx, t, force=args.force)
        except Exception as e:
            print(f"  [{t}] 错误: {e}")
    save_index(idx)
    print(f"索引已保存: {INDEX_FILE}（共 {len(idx)} 页）")


if __name__ == "__main__":
    main()
