#!/usr/bin/env python3
"""
译名表数据模型迁移：为需要多义/长语块/变译的词条补上 renderings / variants / zh_variable 字段。
规则见 rules/glossary_alignment.md「数据模型（定稿）」。
向后兼容：仅新增可选字段，不动既有 zh/aliases/note。
用法：python3 scripts/glossary_migrate.py
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
GLOSS = HERE.parent / "dict" / "mistborn.json"


def main():
    d = json.loads(GLOSS.read_text(encoding="utf-8"))
    t = d["terms"]

    # 1) Allik：长语块整句（名+敬称）
    if "Allik" in t:
        t["Allik"].setdefault("renderings", [])
        rend = {"en": "Allik Neverfar, Tall One", "zh": "高个子亚历克·奈弗法", "note": "名+敬称整句"}
        existing = [r for r in t["Allik"]["renderings"] if r["en"] == rend["en"]]
        if not existing:
            t["Allik"]["renderings"].append(rend)

    # 2) Demoux：同名多义（人物 + 待 tlm 中译的城市）
    if "Demoux" in t:
        v = t["Demoux"].setdefault("variants", [])
        kinds = {x.get("kind") for x in v}
        if "person" not in kinds:
            v.append({"kind": "person", "zh": "德穆"})
        if "city" not in kinds:
            v.append({"kind": "city", "zh": None, "pending": "tlm-untranslated"})
        t["Demoux"].setdefault("note",
            "人物（前存留者/Originator）；同名城市 Demoux (city) 中译待 The Lost Metal（tlm）。")

    # 3) The Village：无固定专名，中译随上下文
    if "The Village" in t:
        t["The Village"]["zh"] = None
        t["The Village"]["zh_variable"] = True
        t["The Village"]["renders_note"] = (
            "泰瑞司定居点昵称；中译随上下文：村/村里/村子（旧影森森 ch5/6），村寨（悲悼护腕 prologue）")

    # 1') 用新模型：Allik Neverfar 全名词条保留（不并入 Allik.renderings，仍作独立书名证）
    GLOSS.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print("migration done. entries:", len(t))
    for k in ("Allik", "Demoux", "The Village"):
        print(f"  {k}:", json.dumps(t[k], ensure_ascii=False))


if __name__ == "__main__":
    main()
