# -*- coding: utf-8 -*-
"""章节标题长尾批次（②）与 LLM 后再断言回归单测。

背景：2026-10-22 豆包 100 页评测 25 处 [章节] 漏译标题，两类成因——
- 24 处：确定性表未覆盖 → 留给 LLM 原生翻译 → 豆包漏译（机制 A）；
- 1 处：表已覆盖但 LLM 回退（The Village 预译「村庄」被改回「Village」，机制 B）。
修法：①19 个有语料源的标题入 _SECTION_HEADING_MAP（17 处取 DeepSeek 基线同页产物，
radiant 取词表 Radiant(s)，village 承 520ad8f 同指称）；②assemble 在译名收尾后再跑
一遍 translate_section_headings（LLM 后再断言，修机制 B 与晚到漏译）；③_SECTION_HEAD_RE
补 `&` 与门禁 3a 字符类对齐（否则 Arts & Games 两头不一致）。
5 个无源标题（Zeenid-daughter-Beth/Molli 待 sa5 中译本；The Child/Formless/Vaporspren
各模型均按专名保留英文）刻意不录——宁保英文；2026-10-23 起门禁 3a 同步豁免
（verify_translation.UNSCOURCED_HEADS，用户裁定「修门禁口径」方向1），translate
与门禁两侧同口径。

覆盖：
- 19 条批次逐条命中（2026-10-23 表修复 +4 → 23 条）+ 大小写/层级变体 + 既有条目（Notes）零回归
- 再断言语义：ASCII 表内标题 → 中文；表外 ASCII 原样（留门禁）；中文标题零接触；
  正文行非标题零接触；幂等；闭合等号不等时内容照译、等号原样（结构另由门禁管）
- 门禁 3a 对齐探针：门禁会拦 ⇒ 查表正则必匹配（含 & 字符类一致）
- 门禁视角回放：19 条英文形态经再断言后不再被 3a 拦；无源 5 条 translate 侧仍留英文、
  门禁 3a 侧同豁免（2026-10-23 口径对齐，两侧一致不拦）
- assemble 确实接线了再断言

用法：.venv/bin/python scripts/tests_section_headings.py
"""
import os
import re
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


def head(s):
    """LLM 前预译与 LLM 后再断言同一函数：返回替换后文本。"""
    return tr.translate_section_headings(s)[0]


# ② 批次 19 条（口径见 _SECTION_HEADING_MAP 注释）：EN 形态 → 期望中文
# 2026-10-23 表修复 +4（Vessels/Primeval Spren/Enlightened/The Contest，同页基线
# 取证，见 map 注释）——变量名沿用 BATCH19，现共 23 条。
BATCH19 = [
    ("Village", "村庄"),
    ("Vessel", "容器"),
    ("The Roost", "栖木"),
    ("Main Assembly", "全体议会"),
    ("Type I", "一类"),
    ("Universal Stamps", "通用印"),
    ("Soulstamps", "魂印"),
    ("Soulforging", "塑魂术"),
    ("Resealing", "封印修复"),
    ("Remembering", "忆塑"),
    ("The Breakaway", "裂口市场"),
    ("Kata", "剑式"),
    ("Canton of Orthodoxy", "正统教区"),
    ("Contest of champions", "冠军对决"),
    ("Contest of Champions (1175)", "冠军对决 (1175)"),
    ("Gray Remnant", "灰色残部"),
    ("Lifelight", "生命之光"),
    ("Champion", "冠军"),
    ("Radiant", "光辉骑士"),
    # --- 2026-10-23 表修复 +4 ---
    ("Vessels", "容器"),
    ("Primeval Spren", "原始灵"),
    ("Enlightened", "启蒙"),
    ("The Contest", "较量"),
]

# 无源 5 条：刻意不录，必须仍留英文（宁保英文 + 门禁拦截的既定分工）
UNSOURCED = [
    "Zeenid-daughter-Beth",
    "Molli",
    "The Child",
    "Formless",
    "Vaporspren",
]


def gate_flags(txt):
    """门禁 3a「标题未译」判定（与 verify_translation._heading_problems 同构：ASCII +
    3 连字母 + keep_en 之外；无源 5 条 UNSOURCED 设计豁免 2026-10-23 起对齐；
    闭合等号不等属 [结构] 另一类，此处不判）。"""
    for hm in re.finditer(r"^(={2,6})[ \t]*(.*?)[ \t]*(={2,6})[ \t]*$", txt, re.M):
        op, htxt, cl = hm.group(1), hm.group(2).strip(), hm.group(3)
        if len(op) != len(cl):
            continue
        if (re.fullmatch(r"[A-Za-z][A-Za-z0-9 ,:'&\-()]*", htxt or "")
                and re.search(r"[A-Za-z]{3}", htxt)
                and htxt not in UNSOURCED):
            return True
    return False


CASES = [
    # --- 批次 19 条逐条命中（=== X === → === 中文 ===） ---
    ("batch|(%s)" % en, head, "=== %s ===" % en, "=== %s ===" % zh)
    for en, zh in BATCH19
] + [
    # --- 变体 ---
    ("case|全大写", head, "=== KATA ===", "=== 剑式 ==="),
    ("case|首字母大写长尾", head, "=== The Roost ===", "=== 栖木 ==="),
    ("level|二级标题", head, "== Lifelight ==", "== 生命之光 =="),
    ("level|五级标题", head, "===== Champion =====", "===== 冠军 ====="),
    ("revert|豆包回退Village", head, "=== Village ===", "=== 村庄 ==="),
    ("keep|既有条目Notes", head, "=== Notes ===", "=== 注释 ==="),
    ("keep|既有条目The Village", head, "=== The Village ===", "=== 村庄 ==="),
    # --- 再断言边界：不该动的一律不动 ---
    ("touch|中文标题不动", head, "=== 历史 ===", "=== 历史 ==="),
    ("touch|表外ASCII留门禁", head, "=== Zeenid-daughter-Beth ===",
     "=== Zeenid-daughter-Beth ==="),
    ("touch|含模板标题不匹配", head,
     "=== Early Life ({{Rosharan date|1156}}–{{Rosharan date|1173}}) ===",
     "=== Early Life ({{Rosharan date|1156}}–{{Rosharan date|1173}}) ==="),
    ("touch|正文行零接触", head, "Village life is good", "Village life is good"),
    ("touch|中文段落零接触", head, "他住在[[Village]]里。", "他住在[[Village]]里。"),
    ("struct|闭合不等内容照译等号原样", head, "=== Kata ==", "=== 剑式 =="),
    # --- 再断言幂等 ---
    ("idempotent|二次执行零变化",
     lambda s: head(head(s)), "=== Village ===", "=== 村庄 ==="),
    # --- 门禁 3a 字符类对齐探针：门禁会拦 ⇒ 查表正则必匹配 ---
    ("align|&标题可匹配", lambda s: tr._SECTION_HEAD_RE.search(s) is not None,
     "=== Arts & Games ===", True),
    ("align|&标题门禁也拦", lambda s: gate_flags(s), "=== Arts & Games ===", True),
    ("align|两字母门禁不拦但正则可匹配", lambda s: (
        tr._SECTION_HEAD_RE.search("=== A B ===") is not None
        and not gate_flags("=== A B ===")), "", True),
    ("align|含花括号两边都不匹配", lambda s: (
        tr._SECTION_HEAD_RE.search(s) is None and not gate_flags(s)),
     "=== X {{foo}} Y ===", True),
    # --- 接线：assemble 必须调用再断言 ---
    ("wire|assemble含标题再断言",
     lambda _s: "head_stats2" in getattr(tr, "assemble").__code__.co_varnames
     and "translate_section_headings" in getattr(tr, "assemble").__code__.co_names,
     "", True),
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

    # --- 门禁视角回放：19 条英文形态再断言后必须不再被 3a 拦 ---
    for en, zh in BATCH19:
        out = head("=== %s ===" % en)
        check("gate|拦后再断言放行(%s)" % en, gate_flags(out), False)
        check("gate|译文即口径(%s)" % en, "=== %s ===" % zh in out, True)

    # --- 无源 5 条：translate 侧仍留英文；门禁 3a 侧自 2026-10-23 口径对齐后同豁免 ---
    for en in UNSOURCED:
        out = head("=== %s ===" % en)
        check("gate|无源留英文且门禁放行(%s)" % en, (out, gate_flags(out)),
              ("=== %s ===" % en, False))

    # --- stats 形态：供 assemble 日志 ---
    out, stats = tr.translate_section_headings("=== Village ===")
    check("stats|替换统计", stats, ["Village -> 村庄"])
    out2, stats2 = tr.translate_section_headings("=== Zeenid-daughter-Beth ===")
    check("stats|未命中无统计", stats2, [])

    total = passed + failed
    print("%d/%d passed" % (passed, total))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
