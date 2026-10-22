# -*- coding: utf-8 -*-
"""门禁③误伤修正回归单测（_field_half_problems 直调）。

背景：门禁第 5 节（| 字段行中英夹杂）在 2026-10-22 豆包评测有 3 类误伤（FP）——
Words of Radiance 4/4 全 FP + Wind and Truth 1/1 FP，两页零真缺陷（+2 页可回）：
- 斜体 `''…''` 外语书名不剔除 → 非 ASCII 断词碎片（Stürme→rme、Câmpiile→mpiile、
  Jurâmântului→ntului）与外语虚词 des 被当英文残留；
- 模板剔除上限 150 字符 → Wind and Truth 186 字符长 {{tor ref|…}} 剔不掉，
  「tor ref」残留被当小写内容词；
- FUNC_WORDS 缺外语虚词 des。

③修法（2026-10-23，判定从 check_one 原位抽出为 _field_half_problems 便于直调）：
斜体整体剔除（镜像 mask_nonprose 第3步：粗体先占位保护、不豁免）+ 上限 150→512
（全语料 |行内最长模板 449）+ FUNC_WORDS 增 des。

覆盖：
- FP×5：评测两页的 5 行逐字原文 → 修后零问题
- 真缺陷不回吞（对照回归核心）：小写内容词残留 / 称号紧邻中文 / 引号外残留 /
  长模板+引号外残留 / 粗体英文 / 外语虚词之外的小写词 → 一律仍拦
- 结构边界：值全中文、非 | 行、{{tag}}/{{en}}/原名行、决议#13原文块内行 → 不判
- FUNC_WORDS 模块级形态：含 des、不含内容词 several

用法：.venv/bin/python scripts/tests_gate_fp.py
"""
import os
import sys
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, fname))
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


tr = _load("translate_mod", "translate.py")
vr = _load("verify_mod", "verify_translation.py")

# 评测实录逐字行（state/doubao_eval_verify.txt Words of Radiance / Wind and Truth）
WOR1 = "| ''Die Stürme des Zorns''（意为“愤怒风暴”）"
WOR2 = "| ''Le Livre des Radieux''（意为“光辉骑士之书”）"
WOR3 = "| ''Câmpiile Sfârâmate''（破碎平原）"
WOR4 = "| ''Poarta Jurâmântului''（誓约之门）"
WAT = ("| 发行日期    = December 6th, 2024{{tor ref|"
       "brandon-sandersons-fifth-stormlight-archive-book-gets-publishing-date|"
       "Brandon Sanderson's Fifth Stormlight Archive Book Gets Publishing Date|"
       "date=2023-12-18|name=release-date}}")

# 造一个 >150 且 <512 的长模板（模拟长 tor ref 变体）
LONG_TOR = "{{tor ref|" + "x" * 300 + "|some title}}"

# ③ 只动 | 字段行 → 问题数即判定
def nprob(body, spans=None):
    return len(vr._field_half_problems(body, [] if spans is None else spans))


CASES = [
    # --- FP×5：两页实录行，修后必须零问题 ---
    ("fp|WoR德语书名des", nprob, WOR1, 0),
    ("fp|WoR法语书名des", nprob, WOR2, 0),
    ("fp|WoR罗马尼亚语断词", nprob, WOR3, 0),
    ("fp|WoR罗马尼亚语属格ntului", nprob, WOR4, 0),
    ("fp|WaT长tor ref残留", nprob, WAT, 0),
    ("fp|长模板300字符", nprob, "| date = 中文说明 " + LONG_TOR, 0),
    # --- 真缺陷对照：一类都不许回吞 ---
    ("real|小写内容词残留", nprob,
     "| lore = 这是设定说明，several noble houses remain", 1),
    ("real|称号紧邻中文B信号", nprob, "| x = 幸存者 of the Flames", 1),
    ("real|斜体书名外残留仍拦", nprob,
     "| note = ''Die Stürme des Zorns''（意为愤怒风暴）several houses remain", 1),
    ("real|长模板+引号外残留仍拦", nprob,
     "| date = 中文 " + LONG_TOR + " several houses remain", 1),
    ("real|粗体不豁免", nprob, "| x = 中文 '''noble houses''' remain", 1),
    ("real|des之外小写词仍拦", nprob, "| y = 术语 des contes restants", 1),
    ("real|夹杂残留短语", nprob,
     "| title = 迷雾之子 lord of drifters", 1),
    # --- 结构边界：按设计不判 ---
    ("edge|值全中文", nprob, "| x = 纯中文值", 0),
    ("edge|非|行不判", nprob, "中文 several noble houses in prose", 0),
    ("edge|tag模板行跳过", nprob, "| {{tag|en}} 中文 several houses", 0),
    ("edge|en标注行跳过", nprob, "| {{en|Foo}} 中文 several houses", 0),
    ("edge|原名行跳过", nprob, "| 原名 = 中文 several houses", 0),
    ("edge|引号未成对不断词", nprob, "| x = 中文 it's several houses", 1),
]


def main():
    failed = 0
    passed = 0

    def check(name, got, want):
        nonlocal failed, passed
        if got == want:
            passed += 1
            print("  OK  %s" % name)
        else:
            failed += 1
            print("  FAIL %s" % name)
            print("    got : %r" % (got,))
            print("    want: %r" % (want,))

    for name, fn, src, want in CASES:
        check(name, fn(src), want)

    # --- 决议#13 原文块内的字段行（含署名行）按设计不判 ---
    body = "{{Quote|\n| x = 中文 several noble houses remain\n}}"
    spans = [(0, len(body))]
    check("edge|原文块内行跳过", nprob(body, spans), 0)
    # 同行不在原文块内时必须判（证明 spans 真的生效，不是恒 0）
    check("edge|块外同行仍判", nprob(body, []), 1)

    # --- FUNC_WORDS 模块级形态 ---
    check("func|des已入", "des" in vr.FUNC_WORDS, True)
    check("func|内容词不入", "several" in vr.FUNC_WORDS, False)
    check("func|既有词保留", {"of", "the", "with"} <= vr.FUNC_WORDS, True)

    # --- 抽出等价性探针：粗体占位不残留占位符 ---
    check("edge|无占位符泄漏",
          "\\x00" in str(vr._field_half_problems("| x = 中文 '''bold''' test", []))
          or "\x00" in str(vr._field_half_problems("| x = 中文 '''bold''' test", [])),
          False)

    total = passed + failed
    print("%d/%d passed" % (passed, total))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
