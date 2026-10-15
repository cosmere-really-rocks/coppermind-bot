#!/usr/bin/env python3
"""
从《迷雾之子第二纪元》名词表.xls 生成 dict/mistborn_era2.json。

用法：
  .venv/bin/python scripts/build_glossary.py <xls路径> [--out dict/mistborn_era2.json]

- 输入：老式 .xls（xlrd 读取），单 sheet 'Glossary'，列 = [英文, 中文]，首行为表头。
- 处理：去重；中文人名分隔符（．/‧/·）统一为 ·；修正已知英文拼写笔误。
"""
import argparse
import datetime
import json
import re
import sys
from pathlib import Path

import xlrd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def norm_zh(s):
    s = str(s).strip()
    s = s.replace("\uFF0E", "·").replace("\u2027", "·")  # ． -> ·, ‧ -> ·
    return s


KNOWN_EN_TOKENS = {
    # 源表批量替换误伤：英文 key 里的汉字 "依蓝德" 实为 Elend
    "依蓝德": "Elend",
}


def fix_en_key(en, fixes_used, zh):
    """修正英文 key 中被误替换成汉字的 token（如 依蓝德->Elend）。"""
    fixed = False
    for bad, good in KNOWN_EN_TOKENS.items():
        if bad in en:
            en = en.replace(bad, good)
            fixed = True
    if fixed:
        fixes_used.append({"from": "含「依蓝德」", "to": "Elend", "zh": zh, "full_en": en})
    return en


def build(rows):
    terms = {}
    fixes_used = []
    for i, (en_raw, zh_raw) in enumerate(rows):
        en = str(en_raw).strip()
        zh = norm_zh(zh_raw)
        if not en or not zh:
            continue
        en = fix_en_key(en, fixes_used, zh)
        if en in terms:
            if terms[en]["zh"] != zh:
                terms[en].setdefault("aliases", [])
                if zh not in terms[en]["aliases"]:
                    terms[en]["aliases"].append(zh)
            continue
        terms[en] = {"zh": zh}
    return terms, fixes_used


def main():
    ap = argparse.ArgumentParser(description="生成迷雾之子第二纪元译名表 JSON")
    ap.add_argument("xls", help="源 xls 路径")
    ap.add_argument("--out", default=str(ROOT / "dict" / "mistborn_era2.json"))
    args = ap.parse_args()

    wb = xlrd.open_workbook(args.xls)
    sh = wb.sheet_by_name("Glossary")
    rows = [(sh.cell_value(i, 0), sh.cell_value(i, 1)) for i in range(1, sh.nrows)]

    terms, fixes = build(rows)
    doc = {
        "meta": {
            "name": "迷雾之子·第二纪元 译名表",
            "en": "Mistborn Era 2 Glossary",
            "source": Path(args.xls).name,
            "source_sheet": "Glossary",
            "entry_count": len(terms),
            "updated": datetime.date.today().isoformat(),
            "en_fixes": fixes,
            "notes": [
                "英文 key 保留原始大小写/拼写。",
                "中文人名分隔符已统一为间隔号 ·。",
                "源表英文 key 中误用的汉字「依蓝德」已统一修正为 Elend（源 xls 已同步修正，此规则兼作兜底）。",
                "内容为草稿，仍需逐条核对。",
            ],
        },
        "terms": terms,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写入 {out}（{len(terms)} 条）")


if __name__ == "__main__":
    main()
