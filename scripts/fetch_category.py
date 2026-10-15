#!/usr/bin/env python3
"""
递归抓取英文站某个分类（含所有子分类）下的全部页面快照。

用法：
  # 只列出递归展开后的页面清单（不抓取）
  .venv/bin/python scripts/fetch_category.py Category:Mistborn_Era_2 --list

  # 递归抓取全部页面（限速，决议 #14）
  .venv/bin/python scripts/fetch_category.py Category:Mistborn_Era_2 [--delay 1.0] [--force]

规则：
- 递归展开子分类（分类命名的页面本身不进页面清单）。
- 抓取复用 scripts/fetch_en.py 的 fetch_one（revid 判重跳过）。
- 请求间隔默认 1.0s（决议 #14），避免触发反爬。
- 断点续跑：重跑自动跳过已抓/未变页面。
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import fetch_en as F

EN_API = F.EN_API


def _cm(s, cat, cmtype, cmcontinue=None):
    params = {
        "action": "query", "list": "categorymembers",
        "cmtitle": "Category:" + cat, "cmtype": cmtype,
        "cmlimit": "500", "format": "json",
    }
    if cmcontinue:
        params["cmcontinue"] = cmcontinue
    return s.get(EN_API, params=params, timeout=30).json()


def list_members(s, cat, cmtype):
    """某分类下某类型成员（翻页完整）。type: page | subcat | file"""
    out, cont = [], None
    while True:
        d = _cm(s, cat, cmtype, cont)
        out += [m["title"] for m in d.get("query", {}).get("categorymembers", [])]
        c = d.get("continue")
        if not c:
            break
        cont = c.get("cmcontinue")
    return out


def walk_category(s, root_cat, delay):
    """递归返回 (pages, subcats)。pages 为全部标题（子分类命名页除外）。"""
    seen_cats = set()
    pages = []

    def visit(cat):
        cat = cat.replace("Category:", "")
        if cat in seen_cats:
            return
        seen_cats.add(cat)
        subs = list_members(s, cat, "subcat")
        for sub in subs:
            visit(sub.replace("Category:", ""))
        time.sleep(delay)
        pg = list_members(s, cat, "page")
        for title in pg:
            if title not in pages:
                pages.append(title)

    visit(root_cat.replace("Category:", ""))
    return pages, sorted(seen_cats)


def main():
    ap = argparse.ArgumentParser(description="递归抓取分类下全部页面")
    ap.add_argument("category", help="分类名，如 Category:Mistborn_Era_2")
    ap.add_argument("--list", action="store_true", help="只列出页面清单，不抓取")
    ap.add_argument("--delay", type=float, default=1.0, help="请求间隔秒数（决议#14）")
    ap.add_argument("--force", action="store_true", help="忽略 revid 判重强制重抓")
    ap.add_argument("--save-list", help="把页面清单存到该 json 文件")
    args = ap.parse_args()

    s = F.get_session()
    print(f"== 递归展开分类 {args.category}（delay={args.delay}s）==")
    pages, subcats = walk_category(s, args.category, args.delay)

    summary = {"root": args.category, "pages": len(pages), "subcategories": subcats}
    print(f"子分类数: {len(subcats)}  页面总数: {len(pages)}")
    for sc in subcats:
        print(f"  ▸ {sc}")

    if args.save_list:
        Path(args.save_list).write_text(
            json.dumps({"root": args.category, "pages": pages}, ensure_ascii=False, indent=1),
            encoding="utf-8")

    if args.list:
        for t in pages:
            print("  ", t)
        return

    # 抓取全部页面
    idx = F.load_index()
    t0 = time.time()
    stats = {"fetched": 0, "skip": 0, "missing": 0, "error": 0}
    for i, title in enumerate(pages, 1):
        print(f"[{i}/{len(pages)}] == {title}")
        try:
            r = F.fetch_one(s, idx, title, force=args.force)
            stats[r if r in stats else "fetched"] += 1
        except Exception as e:
            stats["error"] += 1
            print(f"  [{title}] 错误: {e}")
        # 每次抓取后限速（决议 #14）
        if i < len(pages):
            time.sleep(args.delay)
    F.save_index(idx)
    elapsed = time.time() - t0
    print(f"完成！耗时 {elapsed:.0f}s  统计: {stats}")
    print(f"索引已保存: {F.INDEX_FILE}（共 {len(idx)} 页）")


if __name__ == "__main__":
    main()
