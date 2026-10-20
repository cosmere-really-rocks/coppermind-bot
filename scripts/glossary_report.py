#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""glossary_report.py —— 3 分类缺译名排查 + 采证结果 终报生成（行级计数）。

输入（state/）：
  missing_translation_3cats.json   v2 缺译名清单（归一化查表后，每行一条 [分类,页]）
  glossary_scout_3cats.json        定位结果（located / en_not_found / en_only_no_zh / skip_*）
  round1_batches.json              一轮采证判定
  round2_batches.json              二轮加强采证判定（优先于一轮）
输出：state/missing_translation_report.md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ST = ROOT / "state"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import glossary_assist as GA  # noqa: E402
# 已就绪书码：有中译 + 英书按序号对齐（动态，含新就绪书）
READY = {c for c, (en, zh) in GA.BOOKS.items() if zh and en in GA.INDEX_ALIGN_EN}
BOOK_CN = {"sa1": "飓光志1·王者之路", "twok": "飓光志1·王者之路",
           "sa2": "飓光志2·光辉真言", "wor": "飓光志2·光辉真言",
           "sa3": "飓光志3·渡誓", "ob": "飓光志3·渡誓",
           "elantris": "伊岚翠", "tes": "皇帝魂", "wb": "破战者", "warbreaker": "破战者"}


def load(name, default=None):
    p = Path(name) if str(name).startswith("/") or "/" in str(name) else ST / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def chs(ch):
    return f"ch{ch}" if str(ch).strip().isdigit() else f"（{ch}）"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--missing", default="missing_translation_3cats.json")
    ap.add_argument("--scout", default="glossary_scout_3cats.json")
    ap.add_argument("--r1", default="round1_batches.json")
    ap.add_argument("--r2", default="round2_batches.json")
    ap.add_argument("--nscan", default="noref_scan.json")
    ap.add_argument("--nver", default="noref_batches.json")
    ap.add_argument("--out", default="missing_translation_report.md")
    ap.add_argument("--total", type=int, default=2554, help="该清单范围的主命名空间词条页总数")
    ap.add_argument("--label", default="三分类（Elantris / The Emperor's Soul / Stormlight_Archive）")
    args = ap.parse_args()
    v2 = load(args.missing)
    scout = load(args.scout)
    r1 = load(args.r1, {})
    r2 = load(args.r2, {})
    nscan = load(args.nscan, {}) or {}
    nver = {}
    for rows in (load(args.nver, {}) or {}).values():
        for x in rows:
            pg = x.get("page")
            if not isinstance(pg, str):
                continue
            if x.get("zh"):
                nver[pg] = {"zh": x["zh"], "evidence": x.get("evidence", "")}
            else:
                nver.setdefault(pg, {"zh": None, "reason": x.get("reason", "")})

    # page -> 判定；二轮优先覆盖一轮
    verdict = {}
    for rnd, batches in (("一", r1), ("二", r2)):
        for bn, rows in batches.items():
            for x in rows:
                pg = x["page"]
                if isinstance(pg, int):
                    continue
                cur = verdict.get(pg)
                if x.get("zh"):
                    if rnd == "二" or not cur or not cur.get("zh"):
                        verdict[pg] = {"zh": x["zh"], "evidence": x.get("evidence", ""),
                                       "round": rnd, "batch": bn,
                                       "ch": x.get("ch")}
                elif cur is None or not cur.get("zh"):
                    verdict[pg] = {"zh": None, "reason": x.get("reason", ""),
                                   "round": rnd, "batch": bn}

    scout_by = {}
    for cat, rows in scout.items():
        for r in rows:
            scout_by[r["page"]] = r

    confirmed, unclear, en_not_found, wait_book, skip_map, skip_noref = [], [], [], [], [], []
    noref_confirmed, noref_unclear, noref_enonly, noref_miss = [], [], [], []
    for cat, rows in v2.items():
        for m in rows:
            pg = m["page"]
            rs = [r for r in m["refs"] if r[0].lower() in READY]
            codes = sorted({r[0].lower() for r in m["refs"]})
            v = verdict.get(pg, {})
            s = scout_by.get(pg, {})
            if m.get("map_only"):
                skip_map.append((cat, pg)); continue
            if m.get("no_ref"):
                # 用户指令（2026-10-19）：无 ref 批按分类所属书全文扫
                s2 = nscan.get(pg)
                if not s2:
                    skip_noref.append((cat, pg)); continue
                if s2.get("status") == "hit":
                    vnd = nver.get(pg) or {}
                    h = s2["hits"][0]
                    if vnd.get("zh"):
                        noref_confirmed.append({"cat": cat, "page": pg, "base": s2["base"],
                                                "zh": vnd["zh"], "evidence": vnd.get("evidence", ""),
                                                "book": h["book"], "file": h["en_file"]})
                    else:
                        noref_unclear.append((cat, pg, s2["base"],
                                              vnd.get("reason") or "对照区未取到"))
                elif s2.get("status") == "en_only":
                    noref_enonly.append((cat, pg, sorted({h["book"] for h in s2["hits"]})))
                else:
                    noref_miss.append((cat, pg))
                continue
            if not rs:
                wait_book.append((cat, pg, codes, "仅引未就绪书")); continue
            ref = (cat, rs[0][0].lower(), rs[0][1].strip())
            st = s.get("status")
            if st == "located" and v.get("zh"):
                ref_v = (ref[0], ref[1], v.get("ch") or ref[2])
                confirmed.append({"cat": cat, "page": pg,
                                  "base": v.get("base") or s.get("base", pg),
                                  "zh": v["zh"], "evidence": v.get("evidence", ""),
                                  "ref": ref_v, "round": v.get("round", "一")})
            elif st == "located" or (v and not v.get("zh")):
                unclear.append((cat, pg, ref, v.get("reason") or "ZH 未覆盖原句"))
            elif st == "en_only_no_zh":
                wait_book.append((cat, pg, codes, "英文命中仅在未就绪书"))
            elif st == "wait_book":
                wait_book.append((cat, pg, codes, "仅引未就绪书"))
            else:
                en_not_found.append((cat, pg, ref))

    total_rows = sum(len(r) for r in v2.values())
    got = (len(confirmed) + len(unclear) + len(en_not_found) + len(wait_book)
           + len(skip_map) + len(skip_noref)
           + len(noref_confirmed) + len(noref_unclear) + len(noref_enonly) + len(noref_miss))

    out = []
    a = out.append
    a(f"# 缺译名排查 + 电子书采证报告（{args.label}）\n")
    a(f"> 范围：{args.label}")
    a("> 规则（用户 2026-10-19）：有 book ref → 按 ref 到已就绪电子书（飓光志1~3·伊岚翠·皇帝魂）采证；")
    a("> 仅 map/file ref → 跳过；无 ref / 只引未就绪书 → 如实列出。")
    a("> 判定为「译名必须在中文原文真实出现」，附书证；未采到的一律标 unclear，不臆造。\n")
    a("## §0 总览\n")
    a("| 项 | 行数 |")
    a("|---|---|")
    a(f"| 词条页（主命名空间，本清单范围） | {args.total} |")
    a(f"| 已有译名（译名表/中文站/keep_en，归一化匹配） | {args.total - total_rows} |")
    a(f"| **缺译名（v2）** | **{total_rows}** |")
    a(f"| ├ 可用书 ref · 已采到官方中译（**待裁定入表**） | {len(confirmed)} |")
    a(f"| ├ 可用书 ref · 已定位但中译未取到 | {len(unclear)} |")
    a(f"| ├ 可用书 ref · 就绪书正文无该词 | {len(en_not_found)} |")
    a(f"| ├ 仅引未就绪书 / 命中在未就绪书（缺中译本） | {len(wait_book)} |")
    a(f"| ├ 仅 map/file ref（按规则跳过） | {len(skip_map)} |")
    a(f"| ├ 无 ref · 全书扫**采到中译** | {len(noref_confirmed)} |")
    a(f"| ├ 无 ref · 全书扫命中但未取到 | {len(noref_unclear)} |")
    a(f"| ├ 无 ref · 全书扫仅英书命中（缺中译） | {len(noref_enonly)} |")
    a(f"| ├ 无 ref · 全书扫无命中 | {len(noref_miss)} |")
    if skip_noref:
        a(f"| └ 无 ref · 未扫（异常残留） | {len(skip_noref)} |")
    a(f"\n（分节合计校验：{got} = 缺译名 {total_rows} {'✓' if got == total_rows else '✗ 不一致!'}）\n")

    a("## §1 采到官方中译（待你裁定入表）\n")
    a("| # | 分类 | 词条 | 译名 | 书证 | 出处 | 轮 |")
    a("|---|---|---|---|---|---|---|")
    for i, d in enumerate(sorted(confirmed, key=lambda x: (x["cat"], x["page"])), 1):
        _, code, ch = d["ref"]
        ev = (d["evidence"] or "").replace("|", "｜") or "—"
        a(f"| {i} | {d['cat']} | {d['page']} | **{d['zh']}** | {ev} | {BOOK_CN.get(code, code)} {chs(ch)} | {d['round']} |")
    a("")

    a("## §2 已定位但未取到中译（二轮后仍 unclear）\n")
    for cat, pg, (c, code, ch), why in unclear:
        a(f"- [{cat}] **{pg}**（{BOOK_CN.get(code, code)} {chs(ch)}）— {why}")
    a("")

    a("## §3 就绪书正文无命中（英书全书扫无该词，多为事件名/编页名）\n")
    for cat, pg, (c, code, ch) in en_not_found:
        a(f"- [{cat}] {pg}（ref: {BOOK_CN.get(code, code)} {chs(ch)}）")
    a("")

    a("## §4 缺中译本（仅引 sa4/sa5/中篇/mb7 等，等书；含英文命中在未就绪书者）\n")
    for cat, pg, codes, why in wait_book:
        a(f"- [{cat}] {pg} — {why} refs: {', '.join(codes)}")
    a("")

    a("## §5 按规则跳过（仅 map/file ref / 无 ref 未扫残留）\n")
    a(f"**仅 map/file ref {len(skip_map)} 条：**")
    for cat, pg in skip_map: a(f"- [{cat}] {pg}")
    if skip_noref:
        a(f"\n**无 ref 未扫残留 {len(skip_noref)} 条：**")
        for cat, pg in skip_noref: a(f"- [{cat}] {pg}")
    a("")

    a("## §6 无 ref · 全书扫采到官方中译（新，待裁定入表）\n")
    if noref_confirmed:
        a("| # | 分类 | 词条 | 译名 | 书证 | 出处（全书扫） |")
        a("|---|---|---|---|---|---|")
        for i, d in enumerate(sorted(noref_confirmed, key=lambda x: (x["cat"], x["page"])), 1):
            ev = (d["evidence"] or "").replace("|", "｜") or "—"
            a(f"| {i} | {d['cat']} | {d['page']} | **{d['zh']}** | {ev} | "
              f"{BOOK_CN.get(d['book'], d['book'])} [{d['file']}] |")
    else:
        a("（暂无：采证结果未回）")
    a("")
    if noref_unclear:
        a("## §7 无 ref · 全书扫命中但对照区未取到\n")
        for cat, pg, base, why in noref_unclear:
            a(f"- [{cat}] **{pg}**（`{base}`）— {why}")
        a("")
    if noref_enonly:
        a("## §8 无 ref · 仅英书命中（缺中译本）\n")
        for cat, pg, books in noref_enonly:
            a(f"- [{cat}] {pg} — 命中: {', '.join(books)}")
        a("")
    if noref_miss:
        a("## §9 无 ref · 对应书全书扫无命中（rpg/访谈/未出版等，书里查无此词）\n")
        for cat, pg in noref_miss:
            a(f"- [{cat}] {pg}")
        a("")

    (ST / args.out if not str(args.out).startswith("/") else Path(args.out)).write_text("\n".join(out), encoding="utf-8")
    print(f"confirmed={len(confirmed)} unclear={len(unclear)} en_not_found={len(en_not_found)} "
          f"wait_book={len(wait_book)} map={len(skip_map)} noref={len(skip_noref)} "
          f"| noref_scan: hit={len(noref_confirmed)} unclear={len(noref_unclear)} "
          f"en_only={len(noref_enonly)} miss={len(noref_miss)} "
          f"| sum={got} v2={total_rows} {'OK' if got == total_rows else 'MISMATCH'}")
    print("->", args.out)


if __name__ == "__main__":
    main()
