#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""glossary_scout.py —— 对指定分类的「缺译名词条」批量做中英章节定位（采证前置）。

输入：state/missing_translation_3cats.json（由排查脚本产出的 {分类: [{page, refs, ...}]}）
输出：
  state/glossary_scout_3cats.json —— 每词条的定位结果（en_contexts/zh_region 或未命中原因）
  state/glossary_scout_3cats.md   —— 人工/LLM 采证用「对照卡」（EN 上下文 + ZH 对照区）

判定（用户规则 2026-10-19）：
  - 有 book ref 且书已就绪（sa1-3/伊岚翠/皇帝魂）→ 按 ref 定位章节，中英对照
  - 只有 map/file ref → 跳过（地图词，正文找不到）
  - 无 ref / 只有未就绪书 ref（sa4/sa5/中篇/mb7 等）→ 归入待办/缺书
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

INPUT = ROOT / "state" / "missing_translation_3cats.json"
OUT_JSON = ROOT / "state" / "glossary_scout_3cats.json"
OUT_MD = ROOT / "state" / "glossary_scout_3cats.md"

# 已就绪（可采证）书码；TES 页面 ref 记作 Elantris，命中不到时补扫 tes 全书
READY = {"sa1", "twok", "sa2", "wor", "sa3", "ob", "elantris"}
FALLBACK_BOOKS = {"tes": ("the_emperors_soul", "zh_皇帝魂")}


def find_book(base: str, refs, ctx: int = 200):
    """按 ref 快路径 → 命中即返回 rec；否则 --all-hits 全书扫；TES 再补扫皇帝魂全书。"""
    import argparse
    a = argparse.Namespace(ctx=ctx, all_hits=True)
    pairs = list(dict.fromkeys([(c.lower(), ch) for c, ch in refs if c.lower() in GA.BOOKS]))
    # 就绪书（有中译）优先：避免先撞 sa4/5 无中译书导致「英文命中但无对照区」
    pairs.sort(key=lambda x: 0 if x[0] in READY else 1)
    tried = []
    for code, ch in pairs:
        en_dir, zh_dir = GA.BOOKS[code]
        chnum = int(ch) if str(ch).strip().isdigit() else 0
        text, fname = GA.load_chapter_text(en_dir, chnum)
        if text is None:
            tried.append(f"{code} ch{ch}:无该章")
            continue
        hits = GA.find_in(text, base)
        if hits:
            rec = {"book": code, "chapter": ch, "en_file": fname, "en_dir": en_dir,
                   "term_hits": len(hits),
                   "en_contexts": [GA.context(text, i, base, ctx) for i in hits[:3]]}
            GA.add_zh_region(rec, text, hits, zh_dir, chnum, a, en_dir, fname)
            return rec, tried
    # 全书扫（ref 章无命中 / 人物全名首现他章）
    for code in dict.fromkeys(c for c, _ in pairs):
        en_dir, zh_dir = GA.BOOKS[code]
        fw = GA.find_whole_book(base, en_dir, zh_dir, a)
        if fw and fw["total"]:
            h = fw["hits"][0]
            rec = {"book": code, "chapter": h["chapter"], "en_file": h["file"],
                   "en_dir": en_dir, "term_hits": fw["total"],
                   "en_contexts": [h["context"]], "scan": True}
            GA.add_zh_region(rec, [], [0], zh_dir, h["chapter"], a, en_dir, h["file"])
            return rec, tried
    # TES 补扫（ref 写 Elantris 但正文在皇帝魂）
    if any(c.lower() == "elantris" for c, _ in refs):
        en_dir, zh_dir = FALLBACK_BOOKS["tes"]
        fw = GA.find_whole_book(base, en_dir, zh_dir, a)
        if fw and fw["total"]:
            h = fw["hits"][0]
            rec = {"book": "tes(fallback)", "chapter": h["chapter"], "en_file": h["file"],
                   "en_dir": en_dir, "term_hits": fw["total"],
                   "en_contexts": [h["context"]], "scan": True}
            GA.add_zh_region(rec, [], [0], zh_dir, h["chapter"], a, en_dir, h["file"])
            return rec, tried
    return None, tried


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ctx", type=int, default=200)
    args = ap.parse_args()
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    result, cards = {}, []
    for cat, items in data.items():
        rows = []
        for m in items:
            page, refs = m["page"], [(r[0], r[1]) for r in m["refs"]]
            if m.get("map_only"):
                rows.append({"page": page, "status": "skip_map_only"}); continue
            if not refs:
                rows.append({"page": page, "status": "skip_no_ref"}); continue
            ready = [r for r in refs if r[0].lower() in READY]
            if not ready:
                rows.append({"page": page, "status": "wait_book",
                             "refs": sorted({r[0] for r in refs})}); continue
            base = GA.base_name(page)
            rec, tried = find_book(base, refs, args.ctx)
            if rec and rec.get("term_hits"):
                st = "located" if rec.get("zh_region") else "en_only_no_zh"
                rows.append({"page": page, "base": base, "status": st, **rec,
                             "tried": tried})
                if st == "located":
                    cards.append(f"### {page}\n- base: `{base}` | ref: {ready[0]} | 定位: {rec['book']} ch{rec['chapter']} [{rec.get('en_file')}]\n"
                                 + "\n".join(f"- EN> {c}" for c in rec["en_contexts"])
                                 + f"\n- ZH> {rec.get('zh_region')}\n")
            else:
                rows.append({"page": page, "base": base, "status": "en_not_found",
                             "refs": ready, "tried": tried})
        result[cat] = rows
    OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    head = "# 采证对照卡（3 分类缺译名·已就绪书）\n\n> 逐卡在 ZH> 行内找官方中译；采不到就标 无命中。\n\n"
    OUT_MD.write_text(head + "\n".join(cards), encoding="utf-8")
    from collections import Counter
    for cat, rows in result.items():
        print(cat, dict(Counter(r["status"] for r in rows)))
    print("对照卡:", len(cards), "->", OUT_MD)


if __name__ == "__main__":
    main()
