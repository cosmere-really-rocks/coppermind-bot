# -*- coding: utf-8 -*-
"""译名表替换的引用模板保护（④）回归单测。

背景：_sub_glossary_in_string 在 mask_ref_templates **之前**运行，一旦引用首参与
词条同名（{{book ref|Elantris|62}} → {{book ref|伊岚翠|62}}），掩码/解码原样带过，
门禁 extract_refs 按字面比对引用序列必判「[引用] 序列不一致」——Dilaf/Hrathen/Shaor
三页实测同因失败。修法：先 _mask_ref_spans 把引用族模板（精确 date/裸 ref/* ref，
大小写不敏感）挖成 %%REFSPAN_i%% 占位符，替换后单趟原样填回。

覆盖：
- 保护本体：book/wob/map/date/裸 ref 首参与展示参不被译；含引用的值引用段逐字节还原
- 零行为漂移：无引用值与旧实现逐字节一致（核心替换体未动）；图片早退；整值匹配
  （含 [[...]] 包裹与归一化兜底）；链接目标形式；in_phrase 跳过；非引用模板
 （{{tag+|…}}）照常替换；嵌套引用（非引用模板包引用）内层受保护、外层照常替换
- 大小写变体（Book ref）与数字开头（17s ref）命中；复合 date 名（Rosharan date）
  刻意不保护（门禁只查 \{\{\s*date\s*\|）
- 端到端：translate_infobox_values 对 Dilaf 形态值 → [[拉森]] 译中而书码原样，
  extract_refs 前后序列一致；translate_for_template 同保护
- 占位符不泄漏：任何用例输出不含 %%REFSPAN

用法：.venv/bin/python scripts/tests_glossary_sub.py
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

# 精简词条表：真实 JSON 的子集（Elantris/Hrathen 命中实测缺陷），键值与 mistborn.json 同构。
GLOSS = {
    "Elantris": {"zh": "伊岚翠"},
    "Hrathen": {"zh": "拉森"},
    "Kelsier": {"zh": "凯西尔"},
    "Luthadel": {"zh": "陆沙德"},
    "Mistborn: The Final Empire": {"zh": "迷雾之子：最终帝国"},
    "Survivor": {"zh": "幸存者"},
    "Elendel Basin": {"zh": "恩德湖盆地"},
}


def sub(s):
    return tr._sub_glossary_in_string(s, GLOSS)


def masked(s):
    return tr._mask_ref_spans(s)


def name_ok(s):
    return bool(tr._REF_NAME_RE.match(s))


def ib_vals(wikitext):
    out, _stats = tr.translate_infobox_values(wikitext, GLOSS)
    return out


CASES = [
    # --- 保护本体：引用首参不译、相邻链接照译（Dilaf 实测形态） ---
    ("prot|book ref首参", sub,
     "Killed by [[Hrathen]]{{book ref|Elantris|62}}",
     "Killed by [[拉森]]{{book ref|Elantris|62}}"),
    ("prot|整值即引用", sub, "{{book ref|Elantris|62}}", "{{book ref|Elantris|62}}"),
    ("prot|wob ref参数", sub, "See {{wob ref|Elantris interview}}", "See {{wob ref|Elantris interview}}"),
    ("prot|date模板", sub, "dated {{date|Kelsier}} ok", "dated {{date|Kelsier}} ok"),
    ("prot|裸ref", sub, "note{{ref|Elantris}}", "note{{ref|Elantris}}"),
    ("prot|大小写Book ref", sub, "{{Book ref|Elantris|62}}", "{{Book ref|Elantris|62}}"),
    ("prot|数字开头17s ref", sub, "{{17s ref|Elantris}}", "{{17s ref|Elantris}}"),
    ("prot|引用外裸词照译", sub,
     "Elantris{{book ref|Elantris|62}}", "伊岚翠{{book ref|Elantris|62}}"),
    ("prot|多引用分段", sub,
     "x{{book ref|mb1|1}} Elantris, y{{tes ref|12}}",
     "x{{book ref|mb1|1}} 伊岚翠, y{{tes ref|12}}"),
    # --- 刻意不保护：复合 date 名（门禁 REF_PATS 只查 {{date|） ---
    ("skip|Rosharan date不保护", sub,
     "{{Rosharan date|Kelsier}}", "{{Rosharan date|凯西尔}}"),
    ("skip|update不保护", sub, "{{update|Elantris}}", "{{update|伊岚翠}}"),
    # --- 零行为漂移：无引用值与旧实现等价 ---
    ("none|整值裸匹配", sub, "Kelsier", "凯西尔"),
    ("none|整值链接包裹", sub, "[[Mistborn: The Final Empire]]", "[[迷雾之子：最终帝国]]"),
    ("none|归一化兜底小写", sub, "kelsier", "凯西尔"),  # 小写键 → idx 归一命中
    ("none|链接目标形式", sub, "[[Hrathen]] met [[Kelsier]]", "[[拉森]] met [[凯西尔]]"),
    ("none|in_phrase跳过", sub,
     "Survivor of the Flames fought", "Survivor of the Flames fought"),
    ("none|非引用模板照译", sub, "{{tag+|Kelsier}}", "{{tag+|凯西尔}}"),
    ("none|图片早退", sub, "[[File:Kelsier.jpg|cap]]", "[[File:Kelsier.jpg|cap]]"),
    ("none|纯文本", sub, "plain text", "plain text"),
    # --- 嵌套：非引用模板包引用 → 外层照常替换、内层引用保护 ---
    ("nest|tag内嵌ref", sub,
     "{{tag|Kelsier {{book ref|Elantris|62}}}}",
     "{{tag|凯西尔 {{book ref|Elantris|62}}}}"),
    # --- _mask_ref_spans 探针 ---
    ("mask|无模板恒等", masked, "abc", ("abc", [])),
    ("mask|引用挖出", masked, "a{{book ref|mb1|1}}b",
     ("a%%REFSPAN_0%%b", ["{{book ref|mb1|1}}"])),
    ("mask|非模板不挖", masked, "{{tag|x}}", ("{{tag|x}}", [])),
    ("mask|未闭合不挖", masked, "{{book ref|x", ("{{book ref|x", [])),
    # --- 名称判定（保护面 = 精确 date/裸 ref/* ref） ---
    ("name|book ref", name_ok, "book ref", True),
    ("name|Rpg ref", name_ok, "Rpg ref", True),
    ("name|date", name_ok, "date", True),
    ("name|Date", name_ok, "Date", True),
    ("name|ref", name_ok, "ref", True),
    ("name|Rosharan date", name_ok, "Rosharan date", False),
    ("name|update", name_ok, "update", False),
    ("name|tag+", name_ok, "tag+", False),
    ("name|for", name_ok, "for", False),
    # --- translate_for_template 同保护 ---
    ("for|首参照译", lambda s: tr.translate_for_template(s, GLOSS)[0],
     "{{for|Elantris|62}}", "{{for|伊岚翠|62}}"),
    ("for|描述内ref保护", lambda s: tr.translate_for_template(s, GLOSS)[0],
     "{{for|Elantris|see {{book ref|Elantris|62}}}}",
     "{{for|伊岚翠|see {{book ref|Elantris|62}}}}"),
]

# --- 端到端：translate_infobox_values（Dilaf 形态） ---
IB_SRC = ("{{Infobox character\n"
          "| name     = Dilaf\n"
          "| died     = Killed by [[Hrathen]]{{book ref|Elantris|62}}\n"
          "| location = Luthadel\n"
          "}}")

# 门禁视角：convert 源 vs 确定性替换产物的引用序列必须一致
CONV_SRC = ("intro\n| died = Killed by [[Hrathen]]{{book ref|Elantris|62}}\n"
            "{{book ref|mb4|32}} tail {{date|308|PC}}")


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

    # --- 端到端：infobox 行级替换 ---
    out = ib_vals(IB_SRC)
    check("ib|链接译中", "| died     = Killed by [[拉森]]{{book ref|Elantris|62}}" in out, True)
    check("ib|书码原样", "{{book ref|Elantris|62}}" in out, True)
    check("ib|书码未污染", "book ref|伊岚翠" in out, False)
    check("ib|无引用字段照译", "| location = 陆沙德" in out, True)
    check("ib|引用序列一致",
          vr.extract_refs(CONV_SRC) == vr.extract_refs(tr._sub_glossary_in_string(
              CONV_SRC, GLOSS)), True)

    # --- 占位符零泄漏：所有字符串产出不含 %%REFSPAN（mask 探针除外，其本就是掩码态） ---
    all_outputs = [out] + [fn(src) for _n, fn, src, _w in CASES]
    check("leak|无占位符残留",
          any("%%REFSPAN" in o for o in all_outputs if isinstance(o, str)), False)

    # --- 无引用值恒等：对照 _sub_glossary_core 直调（掩码恒等变换） ---
    plain = "Kelsier of [[Luthadel]], Survivor of the Flames"
    check("ident|无引用=core直调", sub(plain), tr._sub_glossary_core(plain, GLOSS))

    total = passed + failed
    print(f"{passed}/{total} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
