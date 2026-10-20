#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""glossary_missing.py —— 从类目清单生成「缺译名」清单（归一化匹配，与 translate 管线一致）。

判定顺序（任一命中即视为已有译名，不算缺）：
  1. keep_en（故意保留英文的条目）
  2. dict/mistborn.json 中带 zh 的条目（归一化：屈折/大小写/前后缀）
  3. 中文站标题反查（zhwiki_titles + aliases）
参考书证路由：
  有 {{book ref}} → refs；仅 map/file ref → map_only；皆无 → no_ref
用法：glossary_missing.py --list state/cosmere_lists/Category_X.json --label X --out state/missing_translation_X.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import glossary_assist as GA  # noqa: E402
import translate as T  # noqa: E402

NS_RE = re.compile(
    r"^(Category|Template|Module|File|String|Scenario|Widget|Help|Book|Gallery|"
    r"TimedText|Special|User|Wikipedia|Forum|MediaWiki|Draft|Property|Lexeme|Form|Math):", re.I)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", required=True, help="fetch_category --save-list 的 json")
    ap.add_argument("--label", required=True, help="输出清单的分组键（如 Warbreaker）")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    data = json.loads(Path(args.list).read_text(encoding="utf-8"))
    pages = data.get("pages", data if isinstance(data, list) else [])

    merged = T.load_merged_glossary(getattr(T, "DEFAULT_GLOSSARY"), getattr(T, "DEFAULT_COMMON", None))
    terms = merged.get("terms", merged) if isinstance(merged, dict) else merged
    ng = T.build_norm_glossary(terms)
    keep = T.load_keep_en()
    kterms = keep.get("terms", keep) if isinstance(keep, dict) else keep
    knorm = {T._norm_glossary_key(k) for k in kterms}
    titles = T.load_zhwiki_titles()
    aliases = T.load_zhwiki_aliases()
    rev = T.build_zhwiki_reverse(titles, aliases)
    rn = {T._norm_glossary_key(k) for k in rev}

    entries, stats = [], {"total": len(pages), "ns_skip": 0, "snap_missing": 0,
                          "keep_en": 0, "glossary": 0, "zhwiki": 0, "missing": 0}
    for page in pages:
        if NS_RE.match(page):
            stats["ns_skip"] += 1
            continue
        wt = GA.snap_dir(page) / "wikitext.txt"
        if not wt.exists():
            stats["snap_missing"] += 1
            continue
        base = GA.base_name(page)
        nk = T._norm_glossary_key(base)
        if nk in knorm:
            stats["keep_en"] += 1; continue
        if nk in ng:
            stats["glossary"] += 1; continue
        if nk in rn:
            stats["zhwiki"] += 1; continue
        txt = wt.read_text(encoding="utf-8", errors="replace")
        refs = GA.page_book_refs(page)
        ent = {"page": page, "base": base,
               "refs": [[c, ch] for c, ch in refs]}
        if not refs:
            if GA.MAPREF_RE.search(txt) or GA.FILEREF_RE.search(txt):
                ent["map_only"] = True
            else:
                ent["no_ref"] = True
        entries.append(ent)
        stats["missing"] += 1

    Path(args.out).write_text(json.dumps({args.label: entries}, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    print("统计:", stats, "| 归一化 glossary 键", len(ng), "| keep_en 键", len(knorm),
          "| 中文站 en 键", len(rn))
    print("->", args.out, f"缺译名 {len(entries)} 条")


if __name__ == "__main__":
    main()
