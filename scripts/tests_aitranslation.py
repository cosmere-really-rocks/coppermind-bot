# -*- coding: utf-8 -*-
"""页首 {{AITranslation}} 标记回归单测（2026-10-23 用户指示）。

需求（样例 Bot测试(豆包Seed):陆沙德，2026-10-22 站点人工实装）：
每个词条最顶部放裸 {{AITranslation}}（无参）—— 第 1 行、压在 {{CmPermission}} 之上。

落点（三处，各有独立价值）：
- translate.ensure_aitranslation + assemble 包装分支：**后置**于
  CmPermission → ensure_en_tag → ensure_lead_title → ensync——前两者依赖
  body 以 CmPermission 起头的置顶假设，先置标记会改写 {{en}} 兜底分支；
- write.ensure_aitranslation + main 前置：存量 translation.json（标记落地前
  的旧产物）走 --stage write 直写也带上，且不冲掉站点上人工补的标记行；
- verify 2b（导语检查）：判条件前先剥离页首标记，保持「CmPermission 置顶 or
  头部 Infobox」原口径——否则无 Infobox 词条的导语检查被静默跳过（漏报）。

覆盖：
- 两处 helper 语义 + 逐输入对等（防 stdlib-only 双实现漂移）
- assemble 接线与调用序（源序：en/lead/ensync 之前不得出现、之后必须一次、缩进 8 = 包装分支内）
- write main 接线（在 client.edit 之前）
- 门禁行为：脏夹具（CmPermission 无 Infobox + 导语残留英文）带/不带标记
  问题列表逐条相等（此断言即 2b 修复的回归探针：未修则带标记侧漏掉 [导语]）；
  净夹具两侧全通；行号类问题做「第N行-1」归一
- untranslated_lead_english 对标记行天然免疫（模板剥离 + }}\\n\\n 定位不受单行模板影响）

用法：.venv/bin/python scripts/tests_aitranslation.py
"""
import os
import sys
import json
import dis
import re
import tempfile
import inspect
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
wm = _load("write_mod", "write.py")

AIT = "{{AITranslation}}\n"
BODY = ("{{CmPermission|Luthadel}}\n"
        "'''陆沙德'''{{en|Luthadel}} is the very middle of a small quiet zone "
        "and it slowly flows onward here.\n")
SRC = ("'''Luthadel''' is the very middle of a small quiet zone "
       "and it slowly flows onward here.\n")
CLEAN_BODY = ("{{CmPermission|Luthadel}}\n"
              "'''陆沙德'''{{en|Luthadel}}是司卡德瑞尔上最后帝国的首都。\n")
CLEAN_SRC = "'''Luthadel''' is the capital of the final empire on Scadrial.\n"


def _norm_lines(probs, shift=0):
    """把问题串里的「第N行」减去 shift（带标记侧整体 +1）→ 可比形态。"""
    def dec(m):
        return "第%d行" % (int(m.group(1)) - shift)
    return [re.sub(r"第(\d+)行", dec, p) for p in probs]


def run_gate(body_text, src_text):
    """临时 cwd 下跑完整 check_one（check_one 只 cwd 相对读 en_snapshot）。"""
    old = os.getcwd()
    with tempfile.TemporaryDirectory() as td:
        d = os.path.join(td, "en_snapshot", "Luthadel")
        os.makedirs(d)
        with open(os.path.join(d, "translation.json"), "w", encoding="utf-8") as f:
            json.dump({"translation": body_text}, f, ensure_ascii=False)
        with open(os.path.join(d, "wikitext.txt"), "w", encoding="utf-8") as f:
            f.write(src_text)
        os.chdir(td)
        try:
            return vr.check_one("Luthadel", tr.DEFAULT_WIKI)
        finally:
            os.chdir(old)


CASES = [
    # --- translate helper 语义 ---
    ("tr|前置标记", tr.ensure_aitranslation, BODY, AIT + BODY),
    ("tr|幂等", tr.ensure_aitranslation, AIT + BODY, AIT + BODY),
    ("tr|首行裸模板无参",
     lambda b: tr.ensure_aitranslation(b).split("\n")[0], BODY, "{{AITranslation}}"),
    ("tr|空串", tr.ensure_aitranslation, "", AIT),
    # --- write/translate 双实现对等（防 stdlib-only 漂移）---
    ("par|正文", lambda b: wm.ensure_aitranslation(b), BODY, tr.ensure_aitranslation(BODY)),
    ("par|已带标记", lambda b: wm.ensure_aitranslation(b),
     AIT + BODY, tr.ensure_aitranslation(AIT + BODY)),
    ("par|无CmPermission", lambda b: wm.ensure_aitranslation(b),
     "{{Infobox x\n}}\ny", tr.ensure_aitranslation("{{Infobox x\n}}\ny")),
    ("par|空", lambda b: wm.ensure_aitranslation(b), "", tr.ensure_aitranslation("")),
]

# --- 带参变体（2026-10-23 转人工标记）：识别即幂等，绝不补出双标记横幅 ---
AITP = "{{AITranslation|转人工}}\n"
CASES += [
    ("tr|带参标记幂等", tr.ensure_aitranslation, AITP + BODY, AITP + BODY),
    ("par|带参标记幂等", lambda b: wm.ensure_aitranslation(b),
     AITP + BODY, tr.ensure_aitranslation(AITP + BODY)),
    ("tr|带参不再补裸标", lambda b: tr.ensure_aitranslation(b).count("{{AITranslation"),
     AITP + BODY, 1),
    ("par|带参不再补裸标", lambda b: wm.ensure_aitranslation(b).count("{{AITranslation"),
     AITP + BODY, 1),
]

# --- assemble 接线：调用存在、位于三个前置步骤与 ensync 之后、缩进 8 = 包装分支内 ---
_asm_src = inspect.getsource(tr.assemble)
_call_lines = [l for l in _asm_src.splitlines() if "body = ensure_aitranslation(body)" in l]
CASES += [
    ("asm|恰一次调用", lambda _: len(_call_lines), None, 1),
    ("asm|在包装(else)分支内",
     lambda _: bool(_call_lines) and _call_lines[0][:8] == "        "
     and _call_lines[0][8] != " ",
     None, True),
    ("asm|调用序在CmPermission后",
     lambda _: _asm_src.index('{{CmPermission|" + title_en') 
     < _asm_src.index("body = ensure_aitranslation(body)"),
     None, True),
    ("asm|调用序在en_tag后",
     lambda _: _asm_src.index("body = ensure_en_tag(body, title_en)")
     < _asm_src.index("body = ensure_aitranslation(body)"), None, True),
    ("asm|调用序在lead_title后",
     lambda _: _asm_src.index("body, _lead_fixed = ensure_lead_title(body, title_en)")
     < _asm_src.index("body = ensure_aitranslation(body)"), None, True),
    ("asm|调用序在ensync后",
     lambda _: _asm_src.index('{{ensync|" not in body')
     < _asm_src.index("body = ensure_aitranslation(body)"), None, True),
    ("asm|函数已定义", lambda _: hasattr(tr, "ensure_aitranslation"), None, True),
]

# --- write main 接线：读文本后、client.edit 前 ---
_wm_ins = [i.argval for i in dis.get_instructions(wm.main)
           if i.opname.startswith(("LOAD_", "IMPORT")) and i.argval]
CASES += [
    ("wr|main调用标记", lambda _: "ensure_aitranslation" in _wm_ins, None, True),
    ("wr|在edit之前",
     lambda _: ("ensure_aitranslation" in _wm_ins and "edit" in _wm_ins
                and _wm_ins.index("ensure_aitranslation") < _wm_ins.index("edit")),
     None, True),
    ("wr|源码直推不改文",
     lambda _: "text = ensure_aitranslation(text)" in inspect.getsource(wm.main),
     None, True),
]

# --- lead 判定对标记行天然免疫 ---
CASES += [
    ("lead|脏夹具True",
     lambda b: tr.untranslated_lead_english(SRC, b), BODY, True),
    ("lead|带标记仍True",
     lambda b: tr.untranslated_lead_english(SRC, b), AIT + BODY, True),
    ("lead|净夹具False",
     lambda b: tr.untranslated_lead_english(CLEAN_SRC, b), CLEAN_BODY, False),
    ("lead|净+标记仍False",
     lambda b: tr.untranslated_lead_english(CLEAN_SRC, b), AIT + CLEAN_BODY, False),
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

    # --- 门禁行为（核心）：脏夹具带/不带标记问题列表逐条相等 ---
    p_no = run_gate(BODY, SRC)
    p_yes = run_gate(AIT + BODY, SRC)
    check("gate|脏夹具不带标记有[导语]",
          any(p.startswith("[导语]") for p in p_no), True)
    check("gate|带标记问题列表与不带标记逐条相等",
          _norm_lines(p_yes, 1), _norm_lines(p_no, 0))
    # 净夹具两侧全通
    c_no = run_gate(CLEAN_BODY, CLEAN_SRC)
    c_yes = run_gate(AIT + CLEAN_BODY, CLEAN_SRC)
    check("gate|净夹具不带标记全通", c_no, [])
    check("gate|净夹具带标记全通", c_yes, [])

    total = passed + failed
    print("%d/%d passed" % (passed, total))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
