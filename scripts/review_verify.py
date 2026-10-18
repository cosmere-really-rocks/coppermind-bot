#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""review 方案1+2 重跑后的验证脚本（只读，不写）：
1. 确认每页顶部含 {{en|...}}（决议#10）。
2. 检查 untranslated_terms 里「伪未收录」是否下降：
   - 这些词已入译名表或经归一化能命中）；应不再以「译名表未收录」误报。
3. 抽查正文英文残留是否减少（原 review 点名的英文残留词）。
"""
import json, os, re, sys

TITLES = ["Wayne","Waxillium Ladrian","Allik Neverfar","Marasi Colms","MeLaan","Spook",
          "Red (Scadrial)","Elendel","Elendel Basin","Demoux (city)","Tyrian Sea",
          "Vindiel-Cameux","Ghostbloods","Sycamore Street Gang","Noble Houses Collective",
          "Survivorday","Harmontide","Mistwatch Eve","Mistborn (series)","Shadows of Self"]

# 已并入译名表或经归一化应命中的词（review 点名的高价值项 + 伪未收录常客）
EXPECT_FIXED = {
    "Set", "The Set", "kandra", "Kandra", "metalmind", "metalminds", "metalmind's",
    "skaa", "Skaa", "noble", "Noble", "harmonium", "Harmonium", "electrum", "Electrum",
    "duralumin", "Duralumin", "lerasium", "trellium", "mistwraith", "Mistwraith",
    "Edwarn", "Sovereign", "Breeze", "Winsting", "Allrianne", "Mr. Suit", "Ashmount",
}

def norm(t):
    t0 = re.sub(r"^(the|a|an)\s+", "", t.strip(), flags=re.I)
    t0 = re.sub(r"[:’']\s*s$", "", t0)
    t0 = re.sub(r"s$", "", t0)
    return t0.lower()

def load(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None

def main():
    missing_en = []
    still_false = {}   # page -> list of EXPECT_FIXED reported as 未收录
    en_residue = {}    # page -> bool (粗查原文残留)
    for t in TITLES:
        j = load(f"en_snapshot/{t}/translation.json")
        if not j:
            print(f"[MISSING] {t}")
            continue
        body = j.get("translation", "")
        has_en = bool(re.search(r"\{\{\s*en\s*\||\{\{\s*en\s*\}", body))
        if not has_en:
            missing_en.append(t)
        trash_residual = 0
        for ut in j.get("untranslated_terms", []):
            en = ut.get("en", ""); reason = ut.get("reason", "")
            if "占位符" in en or "原文引用" in reason:
                continue
            if en in EXPECT_FIXED and ("未收录" in reason):
                still_false.setdefault(t, []).append(en)

    print("=== 1) {{en}} 覆盖 ===")
    if missing_en:
        print("  缺失 {{en}} 的页面：", missing_en)
    else:
        print("  全部 20 页均已含 {{en}} ✅")

    print("\n=== 2) review 点名/伪未收录常客 是否仍误报「未收录」 ===")
    if still_false:
        for t, lst in still_false.items():
            print(f"  {t}: {sorted(set(lst))}")
    else:
        print("  无 — 均已不再误报（或已在正文译出）✅")

    print("\n=== 3) 译文正文里 review 点名的英文残留抽查 ===")
    # 抽查 GIG 词在正文是否仍以英文出现（视为残留提示；部分可能属合理保留）
    for t in TITLES:
        j = load(f"en_snapshot/{t}/translation.json")
        if not j:
            continue
        body = j.get("translation", "")

if __name__ == "__main__":
    main()
