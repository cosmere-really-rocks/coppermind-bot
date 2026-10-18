#!/usr/bin/env python3
"""Generate state/glossary_caizheng/pending_archive.md from consolidated.json."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONS = HERE.parent / "state" / "glossary_caizheng" / "consolidated.json"
TERMS = HERE.parent / "state" / "mistborn_glossary_terms.json"
OUT = CONS.parent / "pending_archive.md"

c = json.loads(CONS.read_text(encoding="utf-8"))
nt = json.loads(TERMS.read_text(encoding="utf-8"))
total = nt.get("count", len(nt.get("terms", [])))
ok_n = len(c["ok"])
pend = sorted(c["pending"], key=lambda r: r.get("en", ""))

L = []
L.append("# pending 归档（2026-10-18 译名表补全轮·不可采证词条）")
L.append("")
L.append(f"> 本轮候选词条 `state/mistborn_glossary_terms.json` 共 {total} 条；{ok_n} 条已采证并入 `dict/mistborn.json`，")
L.append(f"> 以下 {len(pend)} 条正文无书证/不可采证，标 pending，**勿再重跑**（除非失落金属等中译出版/新书证出现）。")
L.append("> 原始数据见 `state/glossary_caizheng/consolidated.json`（pending 数组）。")
L.append("")
L.append(f"## {len(pend)} 条不可采证清单")
L.append("")
for r in pend:
    note = (r.get("note") or "").strip()
    ev = (r.get("evidence") or "").strip()
    line = f"- **{r['en']}** — {note}"
    if ev:
        line += f" — {ev[:80]}"
    L.append(line)

OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
print(f"wrote {OUT} ({len(L)} lines)")
