#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""glossary_round2.py —— 对一轮标 unclear 的采证卡重出「加强卡」。

一轮 add_zh_region 按字符比例截 ZH 段，常盖不到原句。本脚本对给定页面：
  - EN> 给含词条的完整段落（比一句长）
  - ZH> 给句对齐候选（按句序 ±3；句数比偏离时退化为 ±4000 字宽窗）
  - 附 EN/ZH 章节文件绝对路径，agent 必要时可读整章

输入：state/glossary_round2_pages.json = {"<page>": {"base":..,"en_dir":..,"en_file":..,"zh_dir":..}}（来自 scout json 的 located 行）
输出：state/glossary_round2_cards.md
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import glossary_assist as GA  # noqa: E402

SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+")


def sentences(text: str):
    return [s.strip() for s in SENT_SPLIT.split(text) if s.strip()]


def zh_sentences(text: str):
    return [s.strip() for s in re.split(r"(?<=[。！？…；])", text) if s.strip()]


def main():
    src = json.loads((ROOT / "state" / "glossary_round2_pages.json").read_text(encoding="utf-8"))
    cards = []
    for page, info in src.items():
        base = info["base"]
        en_f = GA.EPUB_OUT / info["en_dir"] / info["en_file"]
        zh_f = GA.EPUB_OUT / info["zh_dir"] / info["zh_file"]
        en_text = GA.strip_html(en_f.read_text(encoding="utf-8", errors="replace")) if en_f.exists() else ""
        zh_text = GA.strip_html(zh_f.read_text(encoding="utf-8", errors="replace")) if zh_f.exists() else ""
        hits = GA.find_in(en_text, base)
        # EN 段落：命中位置所在的段（按换行块）
        paras = [p for p in en_text.split("\n") if p.strip()]
        en_para = ""
        if hits:
            pos = hits[0]
            acc = 0
            for p in paras:
                acc += len(p) + 1
                if acc >= pos:
                    en_para = p
                    break
            if not en_para:
                en_para = en_text[max(0, pos - 400): pos + 400]
        else:
            en_para = en_text[:600]
        en_para = re.sub(r"(?<![A-Za-z])" + re.escape(base) + r"(?![A-Za-z])",
                         lambda m: "【" + m.group(0) + "】", en_para, flags=re.I)
        # ZH 句对齐候选
        es, zs = sentences(en_text), zh_sentences(zh_text)
        idx = next((i for i, s in enumerate(es) if GA.find_in(s, base)), -1)
        ratio = (hits[0] / max(1, len(en_text))) if hits else 0.5
        cand = ""
        near = 0.75 <= (len(zs) / max(1, len(es))) <= 1.33
        if idx >= 0 and near:
            lo, hi = max(0, idx - 3), min(len(zs), idx + 4)
            cand = " ⏎ ".join(zs[lo:hi])
            near_tag = f"句对齐（EN句{idx+1}/{len(es)}，ZH句{lo+1}-{hi}/{len(zs)}）"
        else:
            zpos = int(ratio * len(zh_text))
            lo, hi = max(0, zpos - 4000), min(len(zh_text), zpos + 4000)
            cand = zh_text[lo:hi].replace("\n", " ⏎ ")
            near_tag = f"宽窗（比例{ratio:.2f}，句数比 {'偏' if not near else '近'} {len(es)}→{len(zs)}）"
        cards.append(
            f"### {page}\n- base: `{base}` | 定位: {info['en_dir']}/{info['en_file']}\n"
            f"- EN段落> {en_para}\n- ZH候选（{near_tag}）> {cand}\n"
            f"- EN文件: {en_f}\n- ZH文件: {zh_f}\n- ZH全章可自行读取定位（禁止臆造）\n"
        )
    out = ROOT / "state" / "glossary_round2_cards.md"
    out.write_text("# 二轮加强采证卡\n\n" + "\n".join(cards), encoding="utf-8")
    print("cards:", len(cards), "->", out)


if __name__ == "__main__":
    main()
