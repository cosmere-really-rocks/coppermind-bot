#!/usr/bin/env python3
"""
Merge verified glossary batch results into dict/mistborn.json.
Input: a JSON file (path as argv[1]) that is a LIST of result dicts, each:
  {name, found, canonical_name, zh, note, reason?}
Rules:
  - found=true and zh -> add/update terms[canonical_name] = {"zh": zh, "note": note}
  - found=false -> leave out of glossary; record into a pending-log in the results file itself
  - skips missing/None entries
  - canonical_name is used as the glossary key (disambiguation base name).
Also updates meta.entry_count.
Usage: python scripts/glossary_merge.py <results.json>
"""
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GLOSS = HERE.parent / "dict" / "mistborn.json"

def main():
    if len(sys.argv) < 2:
        print("usage: glossary_merge.py <results.json>"); return 1
    resp = Path(sys.argv[1])
    res = json.loads(resp.read_text(encoding='utf-8'))
    d = json.loads(GLOSS.read_text(encoding='utf-8'))
    t = d["terms"]
    added, skipped = [], []
    fold = {k.lower(): k for k in t}
    for item in res:
        if not item or not isinstance(item, dict):
            continue
        name = item.get("name")
        if not item.get("found") or not item.get("zh"):
            skipped.append({"name": name, "reason": item.get("reason")})
            continue
        zh = item["zh"].strip()
        # pick key
        key = (item.get("canonical_name") or name).strip()
        if key.lower() in fold:
            key = fold[key.lower()]
        note = item.get("note") or ""
        if key in t:
            # augment existing: set zh if it was empty, keep existing note if present
            prev = t[key]
            if not isinstance(prev, dict):
                prev = {"zh": prev}
            if isinstance(prev.get("zh"), str) and prev["zh"]:
                pass  # keep
            else:
                prev["zh"] = zh
            if note and not prev.get("note"):
                prev["note"] = note
            t[key] = prev
        else:
            new = {"zh": zh}
            if note:
                new["note"] = note
            t[key] = new
        added.append(key)
    d["terms"] = t
    d["meta"]["entry_count"] = len(t)
    GLOSS.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"merged {len(added)} added/updated; {len(skipped)} skipped(pending)")
    print("ADDED:", " ".join(added))
    for s in skipped:
        print("SKIP:", json.dumps(s, ensure_ascii=False))

if __name__ == '__main__':
    main()
