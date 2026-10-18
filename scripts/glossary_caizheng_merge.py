#!/usr/bin/env python3
"""
Merge glossary_caizheng consolidated ok-results into dict/mistborn.json.

Input: state/glossary_caizheng/consolidated.json (produced by the per-batch
glossary_assist caizheng runs). Its "ok" list items have the shape:
  {en, zh, note, status, confidence, evidence}

For each ok item we add/update the glossary term:
  key        = en's disambiguation base name (strip trailing "(...)" )
  zh         = confirmed Chinese rendering
  note       = "书证 <bookref>: <evidence>" (compact evidence), keeping any
               existing note's zh/meaning decisions if already present.

Found-not---ok / pending items are left out of the glossary (they stay in
consolidated.json as the running pending archive) --- do NOT re-merge those.

Also appends a changelog line to meta.notes and bumps meta.entry_count/updated.

Usage: .venv/bin/python scripts/glossary_caizheng_merge.py
"""
import json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GLOSS = HERE.parent / "dict" / "mistborn.json"
CONS = HERE.parent / "state" / "glossary_caizheng" / "consolidated.json"

def base_name(en: str) -> str:
    # strip parenthetical disambiguators: "Vent (Scadrial)" -> "Vent"
    return re.sub(r"\s*\(.*\)\s*$", "", en).strip()

def main() -> int:
    if not CONS.exists():
        print(f"missing {CONS}", file=sys.stderr); return 1
    c = json.loads(CONS.read_text(encoding="utf-8"))
    ok = c.get("ok", [])
    d = json.loads(GLOSS.read_text(encoding="utf-8"))
    t = d["terms"]
    fold = {k.lower(): k for k in t}
    added, updated, conflict = [], [], []

    for item in ok:
        en = item.get("en")
        zh = (item.get("zh") or "").strip()
        if not en or not zh:
            continue
        ref = item.get("note") or ""
        ev = (item.get("evidence") or "").strip()
        conf = item.get("confidence", "")
        key = base_name(en)
        if key.lower() in fold:
            key = fold[key.lower()]
        # build note: book-ref + compact evidence + confidence
        parts = []
        if ref:
            parts.append(f"书证 {ref}")
        if ev:
            parts.append(ev)
        if conf and conf != "high":
            parts.append(f"(采证置信 {conf})")
        note = "；".join(parts)

        if key in t:
            prev = t[key]
            if not isinstance(prev, dict):
                prev = {"zh": prev}
            old_zh = prev.get("zh")
            if old_zh and old_zh != zh:
                # keep existing authoritative zh, but record the batch confirmed zh
                conflict.append((key, old_zh, zh))
                prev.setdefault("aka", []).append({"zh": zh, "src": "caizheng-20261018"})
                prev.setdefault("note", "")
                if note and not prev.get("note"):
                    prev["note"] = note
            else:
                prev["zh"] = zh
                if note and not prev.get("note"):
                    prev["note"] = note
            t[key] = prev
            updated.append(key)
        else:
            new = {"zh": zh}
            if note:
                new["note"] = note
            t[key] = new
            added.append(key)

    d["terms"] = t
    d["meta"]["entry_count"] = len(t)
    d["meta"]["updated"] = "2026-10-18"
    cmt = (f"2026-10-18 译名表补全轮·caizheng 采证并入：新增 {len(added)}、更新 {len(updated)} 条"
           f"（源 state/glossary_caizheng/consolidated.json，168 条 ok；159 条不可采证已存 pending，见该文件）")
    d["meta"]["notes"].append(cmt)
    GLOSS.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"merged: +{len(added)} new, ~{len(updated)} updated, {len(conflict)} conflicts")
    print("NEW:", " ".join(added))
    print("UPD:", " ".join(updated))
    for c0 in conflict:
        print("CONFLICT:", c0)
    return 0

if __name__ == "__main__":
    sys.exit(main())
