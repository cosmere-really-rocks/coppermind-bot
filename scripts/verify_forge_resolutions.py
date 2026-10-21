# -*- coding: utf-8 -*-
"""E2E 产物核验：en_snapshot/Forgery/translation.json 的 quote_resolutions 是否符合预期。
用法：.venv/bin/python scripts/verify_forge_resolutions.py（先跑 translate.py --title Forgery）
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
p = HERE / "en_snapshot" / "Forgery" / "translation.json"
if not p.exists():
    print("FAIL translation.json 不存在（先跑 translate.py --title Forgery）")
    sys.exit(1)
c = json.loads(p.read_text(encoding="utf-8"))
res = c.get("quote_resolutions") or []
body = c.get("translation") or ""
txt = (HERE / "en_snapshot" / "Forgery" / "translation.txt")

fails = []


def check(name, cond, detail=""):
    print(("  OK  " if cond else "  FAIL") + " " + name + (f" | {detail}" if detail else ""))
    if not cond:
        fails.append(name)


check("条目数=6", len(res) == 6, f"got {len(res)}")
by_en = {r.get("en_preview", "")[:40]: r for r in res}


def find(pred):
    return next((r for r in res if pred(r)), None)


q1 = find(lambda r: "All things exist in three Realms" in r.get("en_preview", ""))
q2 = find(lambda r: "abomination" in (r.get("en_preview") or ""))
q4 = find(lambda r: "people died" in (r.get("en_preview") or ""))
q5 = find(lambda r: "workers are not Forgers" in (r.get("en_preview") or ""))
q3 = find(lambda r: "Resealing repairs" in (r.get("en_preview") or ""))
q6 = find(lambda r: "fascinating mind" in (r.get("en_preview") or ""))

# --- 正文采证 ---
check("Q1 realms 采到", bool(q1 and q1.get("found")), q1 and q1.get("via"))
if q1 and q1.get("found"):
    z = q1["proposed_cn"]
    check("Q1 是官方中译（三个领域）", "三个领域" in z, z[:60])
    check("Q1 章节=12", str(q1.get("chapter")) == "12", str(q1.get("chapter")))
    check("Q1 同章批量", q1.get("via") == "batch", str(q1.get("via")))
    check("Q1 中文占多数", len(re.findall(r"[一-鿿]", z)) >= 20, z[:80])

check("Q2/Q4（第2天）有采到", any(r.get("found") and str(r.get("chapter")) == "2" for r in res),
      str([(r.get("chapter"), r.get("found"), r.get("reason")) for r in res]))
check("Q5 Rememberers 组采到", bool(q5 and q5.get("found")),
      q5 and (q5.get("reason"), q5.get("via")))

# --- 无 ref 的诚实保留 ---
no_ref = [r for r in res if r.get("reason") in ("no-ref", "unsupported-ref")]
check("无ref条目诚实", len(no_ref) >= 2, str(len(no_ref)))

# --- 出处行翻译 ---
ok_attr = [r for r in res if r.get("attr_reason") == "ok"]
check("出处行译出≥4", len(ok_attr) >= 4,
      str([(r.get("reason"), r.get("attr_reason")) for r in res]))
if q1:
    a = q1.get("attr_zh") or ""
    check("Q1出处: 阿思+塑造术+高图纳+tes ref",
          all(s in a for s in ("阿思", "塑造术", "高图纳", "{{tes ref|12}}")), a)
if q4:
    a = (q4.get("attr_zh") or "")
    check("Q4出处含阿思", "阿思" in a, a)
if q2:
    a = (q2.get("attr_zh") or "")
    check("Q2出处含万思露+tes ref", "万思露" in a and "{{tes ref|2}}" in a, a)
q5a = q5.get("attr_zh") or "" if q5 else ""
check("Q5出处含高图纳+tes ref", "高图纳" in q5a and "{{tes ref|3}}" in q5a, q5a)
if q6:
    check("Q6出处: 纯链接不再翻(保留)", q6.get("attr_reason") in
          ("no-translatable-text", "ok", None, ""), str(q6.get("attr_reason")))

# --- 半自动：quote 正文英文保留、出处行已替换 ---
check("半自动正文未替换", "All things exist in three Realms, Gaotona." in body)
check("出处行已替换进正文", "阿思" in body and "{{tes ref|12}}" in body)
check("无占位残留", "%%ORIGINAL_BLOCK" not in body and "⟦" not in body and "%%REF_" not in body)
check("translation.txt 同步", txt.exists() and (txt.read_text(encoding="utf-8") == body))

# --- untranslated_terms 清洁 ---
ut = c.get("untranslated_terms") or []
bad = [u for u in ut if isinstance(u, dict) and "原始块" in str(u.get("reason", ""))]
check("无原始块残留项", not bad, str(bad[:2]))

print()
print(("ALL PASS" if not fails else f"FAILED: {fails}"))
sys.exit(1 if fails else 0)
