#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""glossary_noref_scan.py —— 对「无 ref」缺译名词条按分类所属书籍做全文扫描采证前置。

用户指令（2026-10-19）：无 ref 的那批既然知道出自哪本书，就去对应书里全文搜。

映射：
  Elantris 类            -> elantris 全书 -> 回退 tes（皇帝魂）
  The Emperor's Soul 类  -> tes 全书 -> 回退 elantris
  Stormlight_Archive 类  -> sa1/sa2/sa3（有中译）优先，再 sa4/sa5/dawnshard（仅英，命中记缺书）

输出 state/noref_scan.json：{page: {base, status(hit|miss|en_only), hits:[{book,chapter,en_file,zh_file,...}]}}
      state/noref_cards.md：有中文对照区的采证卡（供子代理抽取）
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

ST = ROOT / "state"

CAT_BOOKS = {
    "Elantris": ["elantris", "tes"],
    "The Emperor's Soul": ["tes", "elantris"],
    "Stormlight_Archive": ["sa1", "sa2", "sa3", "sa4", "sa5", "sa3.5"],
    "Warbreaker": ["wb"],
}


def scan_one(base: str, books, ctx: int = 200):
    a = argparse.Namespace(ctx=ctx, all_hits=True)
    hits, en_only = [], []
    for code in books:
        en_dir, zh_dir = GA.BOOKS[code]
        fw = GA.find_whole_book(base, en_dir, zh_dir, a)
        if not fw or not fw["total"]:
            continue
        for h in fw["hits"][:3]:
            rec = {"book": code, "chapter": h["chapter"], "en_file": h["file"],
                   "en_dir": en_dir, "context": h["context"], "zh_file": h.get("zh_file"),
                   "zh_region": h.get("zh_region"), "zh_note": h.get("zh_note")}
            (hits if zh_dir else en_only).append(rec)
        if hits:
            break  # 有中译书命中即停；仅英书命中继续试后面的中译书
    return hits, en_only


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ctx", type=int, default=200)
    ap.add_argument("--input", default=str(ST / "missing_translation_3cats.json"))
    ap.add_argument("--tag", default="3cats")
    ap.add_argument("--books", default="", help="未知分类的兜底书码（逗号分隔）")
    args = ap.parse_args()
    fallback = [b.strip() for b in args.books.split(",") if b.strip()]
    v2 = json.loads(Path(args.input).read_text(encoding="utf-8"))
    out, cards, n_hit, n_en, n_miss = {}, [], 0, 0, 0
    for cat, rows in v2.items():
        books = CAT_BOOKS.get(cat) or fallback
        for m in rows:
            if not m.get("no_ref"):
                continue
            pg = m["page"]
            base = GA.base_name(pg)
            hits, en_only = scan_one(base, books, args.ctx)
            if hits:
                n_hit += 1
                out[pg] = {"base": base, "status": "hit", "hits": hits}
                h = hits[0]
                cards.append(f"### {pg}\n- base: `{base}` | 全文扫命中: {h['book']} ch{h['chapter']} [{h['en_file']}]\n"
                             + "\n".join(f"- EN> {x['context']}" for x in hits[:2])
                             + f"\n- ZH> {h.get('zh_region')}\n"
                             + f"- ZH文件: {GA.EPUB_OUT / GA.BOOKS[h['book']][1] / (h.get('zh_file') or '')}\n")
            elif en_only:
                n_en += 1
                out[pg] = {"base": base, "status": "en_only", "hits": en_only}
            else:
                n_miss += 1
                out[pg] = {"base": base, "status": "miss", "books": books}
    (ST / f"noref_scan_{args.tag}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    (ST / f"noref_cards_{args.tag}.md").write_text("# 无ref全文扫采证卡\n\n" + "\n".join(cards), encoding="utf-8")
    print(f"无ref 总数 {n_hit + n_en + n_miss} | 中译区命中 {n_hit} | 仅英书命中 {n_en} | 无命中 {n_miss}")
    print(f"-> state/noref_scan_{args.tag}.json, state/noref_cards_{args.tag}.md")


if __name__ == "__main__":
    main()
