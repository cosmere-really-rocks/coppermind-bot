#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
glossary_split_names.py — 全名条目拆出「裸名专项」条目（用户口径 2026-10-19）：
  明显人名的全名（en=多 token 且全为人名形态、zh=同数音节 · 分隔）
  → 裸名（名/姓）也各自入典，如 Shallan Davar=沙兰·达瓦 拆出
    Shallan=沙兰、Davar=达瓦。

规则（防误拆）：
  - en 每个 token 都须大写开头、纯姓名字符，且不在 stopwords/title/GENERIC_EN_STOPLIST；
  - zh 必须是同数的「·/‧」分隔、每段纯 CJK —— 公司/地名（zh 无间隔号）天然被排除；
  - 裸名 key 已存在且译名不同 -> 冲突（现表/先到者优先），记入报告不覆盖；
  - 幂等：重跑时已存在的裸名按「一致/冲突」归档，不重复添加。

用法:
  .venv/bin/python scripts/glossary_split_names.py            # 只生成提案 split_names.json
  .venv/bin/python scripts/glossary_split_names.py --apply    # 备份并并入 dict/mistborn.json
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parent
GLOSSARY = ROOT / "dict" / "mistborn.json"
OUTDIR = ROOT / "state" / "glossary_xlsx_import"

from glossary_xlsx_import import zh_equal  # noqa: E402
from translate import GENERIC_EN_STOPLIST  # noqa: E402

STOPWORDS = {
    "of", "the", "and", "de", "van", "van der", "del", "da", "di", "la", "le",
    "el", "bin", "ibn", "st", "saint", "son", "daughter",
}
TITLES = {
    "lord", "lady", "king", "queen", "prince", "princess", "duke", "duchess",
    "count", "countess", "earl", "sir", "mr", "mrs", "ms", "dr", "general",
    "captain", "admiral", "emperor", "empress", "father", "mother", "brother",
    "sister", "master", "mistress", "miss", "president", "chancellor",
}
ZH_SEP = re.compile(r"[·‧．•∙⋅]")
NAME_TOK = re.compile(r"[A-Z][A-Za-z'’.\-]*")
ZH_TOK = re.compile(r"[一-鿿]{1,10}")


def is_name_token(t: str) -> bool:
    return (len(t) >= 2 and bool(NAME_TOK.fullmatch(t))
            and t.lower() not in STOPWORDS and t.lower() not in TITLES
            and t.lower() not in GENERIC_EN_STOPLIST)


def split_full(en: str, zh: str):
    """-> [(token, zh, role)] 或 None"""
    toks = en.split()
    if len(toks) < 2 or not all(is_name_token(t) for t in toks):
        return None
    zt = [x.strip() for x in ZH_SEP.split(zh) if x.strip()]
    if len(zt) != len(toks) or not all(ZH_TOK.fullmatch(x) for x in zt):
        return None
    out = [(toks[0], zt[0], "名")]
    if toks[-1] != toks[0]:
        out.append((toks[-1], zt[-1], "姓"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="并入 dict/mistborn.json")
    args = ap.parse_args()

    glossary = json.loads(GLOSSARY.read_text(encoding="utf-8"))
    terms = glossary["terms"]
    snapshot = sorted(terms.items())
    fold = {k.casefold(): k for k in terms}
    applied, conflicts, already = [], [], 0
    skipped_stop, skipped_shape = 0, 0
    claimed: dict[str, str] = {}

    for full_en, entry in snapshot:
        zh = (entry or {}).get("zh") if isinstance(entry, dict) else entry
        if not isinstance(zh, str) or not zh:
            continue
        toks = full_en.split()
        if len(toks) < 2:
            continue
        if any(is_name_token(t) is False for t in toks):
            if all(len(t) >= 2 and NAME_TOK.fullmatch(t) for t in toks) and \
               len(ZH_SEP.split(zh)) == len(toks):
                skipped_stop += 1  # 形状像但撞 stopword/title/通用词
            else:
                skipped_shape += 1
            continue
        parts = split_full(full_en, zh)
        if not parts:
            skipped_shape += 1
            continue
        for tok, tz, role in parts:
            k = tok if tok in terms else fold.get(tok.casefold())
            if k:
                exzh = (terms[k] or {}).get("zh") if isinstance(terms[k], dict) else terms[k]
                if exzh and zh_equal(exzh, tz):
                    already += 1
                else:
                    conflicts.append({"key": tok, "existing_zh": exzh or "",
                                      "candidate_zh": tz, "from": full_en, "role": role,
                                      "src": (entry or {}).get("src", "") if isinstance(entry, dict) else ""})
                continue
            if tok.casefold() in claimed and not zh_equal(claimed[tok.casefold()], tz):
                conflicts.append({"key": tok, "existing_zh": claimed[tok.casefold()],
                                  "candidate_zh": tz, "from": full_en, "role": role,
                                  "src": (entry or {}).get("src", "") if isinstance(entry, dict) else ""})
                continue
            if tok.casefold() in claimed:
                already += 1
                continue
            claimed[tok.casefold()] = tz
            applied.append({"key": tok, "zh": tz, "from": full_en, "role": role,
                            "src": (entry or {}).get("src", "") if isinstance(entry, dict) else ""})

    stats = {"full_names_scanned": sum(1 for k, _ in snapshot if len(k.split()) >= 2),
             "applied": len(applied), "conflicts": len(conflicts),
             "already_covered": already, "skipped_stopword": skipped_stop,
             "skipped_shape": skipped_shape}
    OUTDIR.mkdir(parents=True, exist_ok=True)

    if args.apply and applied:
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        shutil.copy2(GLOSSARY, GLOSSARY.with_name(GLOSSARY.name + f".bak.splitname-{ts}"))
        for x in applied:
            en = x["key"]
            entry = {"zh": x["zh"],
                     "note": f"由全名 {x['from']} 拆出（{x['role']}）"}
            if x["src"]:
                entry["src"] = x["src"]
            terms[en] = entry
        glossary["terms"] = terms
        m = glossary["meta"]
        m["entry_count"] = len(terms)
        m["updated"] = datetime.now().strftime("%Y-%m-%d")
        m.setdefault("notes", []).append(
            f"{datetime.now():%Y-%m-%d} 拆名专项：全名条目拆出裸名 {len(applied)} 条"
            f"（名/姓各自入典，用户口径；提案与冲突见 state/glossary_xlsx_import/split_names.json）")
        GLOSSARY.write_text(json.dumps(glossary, ensure_ascii=False, indent=2), encoding="utf-8")

    payload = {"generated_at": datetime.now().isoformat(timespec="seconds"),
               "applied": applied, "conflicts": conflicts, "stats": stats}
    (OUTDIR / "split_names.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[split_names] applied={len(applied)} conflicts={len(conflicts)} "
          f"already={already} skipped(stop/shape)={skipped_stop}/{skipped_shape} "
          f"apply={args.apply}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
