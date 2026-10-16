#!/usr/bin/env python3
"""
术语裁切（决议 #9 省 token）：从英文 wikitext 提取候选专名，仅从大译名表里筛出本文用得到的子集。

用法：
  .venv/bin/python scripts/glossary_slice.py --title <标题> [--glossary dict/mistborn_era2.json] [--cn-json cn_terms.json]
输出 JSON：{en_terms, from_glossary, in_cn_site, glossary_slice}

- en_terms   : 从正文提取的候选专名（[[内链]]目标 + 大写词）
- from_glossary: 命中用户译名表的子集
- in_cn_site : 在中文站有对应（由 --cn-json 提供的中文站查表结果）
"""
import argparse
import json
import re
import sys
from pathlib import Path

import mwparserfromhell

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EN_SNAPSHOT = ROOT / "en_snapshot"
DEFAULT_GLOSS = ROOT / "dict" / "mistborn.json"


def extract_en_terms(wikitext):
    code = mwparserfromhell.parse(wikitext)
    terms = set()
    # [[内链]] 目标
    for tl in code.filter_wikilinks():
        tgt = str(tl.title).strip()
        if not tgt.lower().startswith(("file:", "image:", "category:")):
            terms.add(tgt)
    # 正文大写词（粗略启发式，供参考，可能误抓）
    body = code.strip_code().strip()
    for m in re.finditer(r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)\b", body):
        w = m.group(1)
        if len(w) > 2:
            terms.add(w)
    return terms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", required=True)
    ap.add_argument("--glossary", default=str(DEFAULT_GLOSS))
    ap.add_argument("--cn-json", default="/tmp/cn_terms.json", help="中文站查表结果(json)")
    args = ap.parse_args()

    d = EN_SNAPSHOT / args.title.replace("/", "_")
    wt = (d / "wikitext.txt").read_text(encoding="utf-8")

    en_terms = sorted(extract_en_terms(wt))

    gloss = {}
    if Path(args.glossary).exists():
        gloss = json.loads(Path(args.glossary).read_text(encoding="utf-8"))["terms"]
    from_glossary = {t: gloss[t] for t in en_terms if t in gloss}

    cn_site = {}
    if Path(args.cn_json).exists():
        cn_site = json.loads(Path(args.cn_json).read_text(encoding="utf-8"))

    result = {
        "en_terms": en_terms,
        "from_glossary": from_glossary,
        "cn_site_hits": {t: cn_site.get(t, []) for t in en_terms},
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
