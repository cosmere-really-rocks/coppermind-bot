# -*- coding: utf-8 -*-
"""quote/columns 书证采证（决议#13 增强）的回归单测。

覆盖：书证 ref 解析（book/epigraph/tes、插曲、命名参数滤除）/ quote 块参数拆分与重建
（出处行与 side/size 结构保留、正文内 ref 保留）/ 定位文本清洗（small caps 解包、链接反查、
实体还原）/ 官方中译逐字校验（子串+位置+拼接覆盖+拒绝幻觉）/ 批量回复 JSON 解析 /
出处行占位掩码与译名表校验 / glossary_assist 的 TES 天数↔文件映射与容错定位。
全部为纯函数用例，不发 LLM。

用法：.venv/bin/python scripts/tests_quote_resolve.py
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
ga = _load("glossary_assist_mod", "glossary_assist.py")

Q_REALM = ("{{Quote|All things exist in three Realms, Gaotona. |"
           "Shai discussing Forgery with [[Gaotona]]{{tes ref|12}}}}")
# 模拟 translate_plain_links 已把链接目标译中的块内状态（文本与出处行均含译中链接）
Q_REALM_ZH = ("{{Quote|All things exist in three Realms, [[高图纳]].|"
              "阿思与[[高图纳]]讨论塑造术{{tes ref|12}}}}")


def _split_texts(src):
    p = tr.split_quote_block(src)
    if not p:
        return None
    return (p["text_val"].strip(),
            [v.strip() for v in p["attr_vals"]],
            p["attrs_i"])


def _rebuild_auto(src):
    return tr.rebuild_quote_block(src, zh_text="中文台词",
                                  zh_attr="阿思与[[高图纳]]讨论塑造术{{tes ref|12}}")


def _rebuild_attr(src):
    return tr.rebuild_quote_block(src, zh_attr="阿思与[[高图纳]]{{tes ref|12}}")


def _rebuild_text(src):
    return tr.rebuild_quote_block(src, zh_text="中文台词")


ZH_FULL = ("　　“高大人，所有事物都在三个领域存在。现实、认知以及灵魂。"
           "灵魂的领域包含这件事物的灵魂——它的本源，以及它与周遭的人或事的关联。”"
           "　“你要明白，改变一个东西，首先要让它成为另一个东西。”")
ZH_HEAD = "高大人，所有事物都在三个领域存在。现实、认知以及灵魂。"
STITCH_OK = "高大人，所有事物都在三个领域存在。你要明白，改变一个东西"
STITCH_FAKE = "高大人，所有事物都在三个领域存在。这里是我编造的一句话来测试"

CASES = [
    # --- extract_book_ref：书证解析 ---
    ("ref|book两参", tr.extract_book_ref, "{{quote|x|Y{{book ref|mb6|20}}}}", ("mb6", "20")),
    ("ref|book插曲", tr.extract_book_ref, "{{book ref|wor|i|4}}", ("wor", "i-4")),
    ("ref|book epilogue段", tr.extract_book_ref, "{{book ref|mb7|epilogue|4}}", ("mb7", "epilogue")),
    ("ref|review滤除", tr.extract_book_ref, "{{book ref|ws|15|review=yes}}", ("ws", "15")),
    ("ref|epigraph", tr.extract_book_ref, "{{epigraph ref|mb3|34}}", ("mb3", "34")),
    ("ref|epigraph空参", tr.extract_book_ref, "{{epigraph ref|sa2||20}}", ("sa2", "20")),
    ("ref|tes", tr.extract_book_ref, "{{tes ref|12}}", ("tes", "12")),
    ("ref|tes postscript", tr.extract_book_ref, "{{tes ref|postscript}}", ("tes", "postscript")),
    ("ref|msh不支持", tr.extract_book_ref, "{{msh ref|1|2}}", None),
    ("ref|单参整书", tr.extract_book_ref, "{{book ref|mb4}}", None),
    ("ref|跨书怪参", tr.extract_book_ref, "{{book ref|sa5|sa2|i|1}}", None),
    ("ref|无", tr.extract_book_ref, "plain text", None),
    ("ref|检测msh", tr.has_ref_any, "{{msh ref|1|2}}", True),
    ("ref|检测无", tr.has_ref_any, "abc", False),
    # --- split_quote_block：参数拆分 ---
    ("split|两参", _split_texts,
     "{{Quote|Hello there|Shai discussing Forgery with [[Gaotona]]{{tes ref|12}}}}",
     ("Hello there", ["Shai discussing Forgery with [[Gaotona]]{{tes ref|12}}"], [1])),
    ("split|命名1=2=", _split_texts, "{{quote|1=Hi there|2=Shai}}",
     ("Hi there", ["Shai"], [1])),
    ("split|四参side/size", _split_texts, "{{quote|Hi|Attr|right|400px;}}",
     ("Hi", ["Attr"], [1])),
    ("split|出处即ref", _split_texts, "{{quote|Hi|Sesemalex{{book ref|sa1|55}}}}",
     ("Hi", ["Sesemalex{{book ref|sa1|55}}"], [1])),
    ("split|空出处参滤除", _split_texts, "{{quote|Hi|Siri describing the Lowlands|}}",
     ("Hi", ["Siri describing the Lowlands"], [1])),
    ("split|多行", _split_texts,
     "{{quote\n| Our workers are not Forgers. We don't use that word.\n"
     "| Gaotona{{tes ref|3}}\n}}",
     ("Our workers are not Forgers. We don't use that word.",
      ["Gaotona{{tes ref|3}}"], [1])),
    ("split|纯side无出处", _split_texts, "{{quote|Hi|left}}", ("Hi", [], [])),
    # --- 正文提取/清洗（不含出处行；small caps 解包；链接处理） ---
    ("text|不含出处", tr.quote_inner_text,
     "{{quote|Our workers are not Forgers. We don't use that word. They are Rememberers."
     "|Gaotona{{tes ref|3}}}}",
     "Our workers are not Forgers. We don't use that word. They are Rememberers."),
    ("text|small caps解包", tr.quote_inner_text,
     "{{quote|{{small caps|I control all things}}|X{{book ref|sa3|20}}}}",
     "I control all things"),
    ("text|正文内ref剔除", tr.quote_inner_text,
     "{{quote|A saying.{{book ref|sa1|55}}|X}}", "A saying."),
    ("text|链接取显示名", tr.quote_inner_text, "{{quote|See [[Saolin|the monk]].|X}}",
     "See the monk."),
    ("text|实体还原", tr.quote_inner_text,
     "{{quote|It&#39;s done &amp; dusted.|X}}", "It's done & dusted."),
    # --- rebuild：重建保结构 ---
    # 注：Q_REALM 正文参数原文带尾随空格（`Gaotona. |`），重建保留原样 → 译文后也保留
    ("build|全自动换正文+出处", _rebuild_auto, Q_REALM,
     "{{Quote|中文台词 |阿思与[[高图纳]]讨论塑造术{{tes ref|12}}}}"),
    ("build|半自动只换出处", _rebuild_attr, Q_REALM,
     "{{Quote|All things exist in three Realms, Gaotona. |"
     "阿思与[[高图纳]]{{tes ref|12}}}}"),
    ("build|side/size不动", _rebuild_auto, "{{quote|Hi|Attr|right|400px;}}",
     "{{quote|中文台词|阿思与[[高图纳]]讨论塑造术{{tes ref|12}}|right|400px;}}"),
    ("build|正文内ref保留", _rebuild_text, "{{quote|A saying.{{book ref|sa1|55}}|X}}",
     "{{quote|中文台词{{book ref|sa1|55}}|X}}"),
    ("build|非块原样返回", _rebuild_text, "not a template", "not a template"),
    # --- verify_zh_official：官方原文逐字校验 ---
    ("verify|整段子串", lambda s: bool(tr.verify_zh_official(s, ZH_FULL)), ZH_HEAD, True),
    ("verify|空白归一子串", lambda s: bool(tr.verify_zh_official(s, ZH_FULL)),
     "高大人，所有事物都在\n三个领域存在。现实、认知以及灵魂。", True),
    ("verify|拒绝改写", lambda s: tr.verify_zh_official(s, ZH_FULL),
     "所有的事物都存在于三个界域里", None),
    ("verify|拒绝__NONE__", lambda s: tr.verify_zh_official(s, ZH_FULL), "__NONE__", None),
    ("verify|去包装引号变体", lambda s: tr.verify_zh_official(s, ZH_FULL),
     '"' + ZH_HEAD + '"', ZH_HEAD),
    ("verify|拼接覆盖", lambda s: bool(tr.verify_zh_official(s, ZH_FULL)), STITCH_OK, True),
    ("verify|拼接杜撰拒绝", lambda s: tr.verify_zh_official(s, ZH_FULL), STITCH_FAKE, None),
    ("verify|空zh_full拒绝", lambda s: tr.verify_zh_official(s, ""), ZH_HEAD, None),
    ("verify|位置过远拒绝", lambda s: tr.verify_zh_official(s, ZH_FULL, 0, 5),
     "你要明白，改变一个东西", None),
    # --- parse_batch_reply ---
    ("batch|裸JSON", tr.parse_batch_reply, '{"1":"你好","2":"__NONE__"}',
     {"1": "你好", "2": "__NONE__"}),
    ("batch|围栏", tr.parse_batch_reply, '```json\n{"1":"好"}\n```', {"1": "好"}),
    ("batch|数组形态", tr.parse_batch_reply, '[{"id":1,"zh":"行"}]', {"1": "行"}),
    ("batch|垃圾回复", tr.parse_batch_reply, "抱歉我不能", None),
    # --- 出处行占位/译名表校验 ---
    ("attr|掩码回填", lambda s: tr.unmask_attr_atoms(*tr.mask_attr_atoms(s)),
     "阿思与[[高图纳]]讨论塑造术{{tes ref|12}}",
     "阿思与[[高图纳]]讨论塑造术{{tes ref|12}}"),
    ("attr|掩码生成", lambda s: tr.mask_attr_atoms(s)[0],
     "Shai discussing [[高图纳]]{{tes ref|12}}", "Shai discussing ⟦0⟧⟦1⟧"),
    ("attr|占位齐且序对", lambda s: tr.attr_placeholders_ok(
        s, ["[[高图纳]]", "{{tes ref|12}}"]), "⟦0⟧⟦1⟧", True),
    ("attr|占位错序", lambda s: tr.attr_placeholders_ok(
        s, ["[[高图纳]]", "{{tes ref|12}}"]), "⟦1⟧⟦0⟧", False),
    ("attr|占位缺", lambda s: tr.attr_placeholders_ok(
        s, ["[[高图纳]]", "{{tes ref|12}}"]), "⟦0⟧", False),
    ("attr|译名缺失拒绝", lambda s: tr._attr_gloss_ok(
        s, {"Shai": {"zh": "阿思"}}, "Shai doing X"), "Someone doing X", False),
    ("attr|译名命中", lambda s: tr._attr_gloss_ok(
        s, {"Shai": {"zh": "阿思"}}, "Shai doing X"), "阿思 doing X", True),
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

    # --- 反查译名：块内 [[高图纳]] 要能还原回英文书的 [[Gaotona]] 才能定位 ---
    check("text|链接目标反查译名",
          tr.quote_inner_text(Q_REALM_ZH, {"高图纳": "Gaotona"}),
          "All things exist in three Realms, 高图纳.".replace("高图纳", "Gaotona"))
    check("text|无反查保留中文",
          tr.quote_inner_text(Q_REALM_ZH, None),
          "All things exist in three Realms, 高图纳.")

    # --- zh_pos → 归一化坐标换算与按位校验 ---
    exp = tr._zh_expect_pos({"zh_pos": 130}, ZH_FULL)
    check("verify|zh_pos换算", exp, len(tr._norm_ws(ZH_FULL[:130])))
    check("verify|按zh_pos命中",
          bool(tr.verify_zh_official("“" + ZH_HEAD, ZH_FULL, exp)), True)

    # --- locate_verbatim：书码不在 BOOKS / 该书无中译 → None（保留英文的原因链入口）---
    check("loc|未知书码None", tr.locate_verbatim("x", ("nope", "1"), 160), None)
    check("loc|无ref None", tr.locate_verbatim("x", None, 160), None)
    no_zh = next((k for k, v in ga.BOOKS.items() if v[1] is None), None)
    if no_zh:
        check("loc|无中译版None", tr.locate_verbatim("x", (no_zh, "1"), 160), None)

    # --- glossary_assist：TES 天数↔文件映射 / 容错定位（真实 epub）---
    epubs_ok = (ga.EPUB_OUT / "the_emperors_soul").is_dir()
    if epubs_ok:
        def _fname(book, ch):
            f = ga.chapter_file(book, ch)
            return f.name if f else None
        check("file|TES英文第12天", _fname("the_emperors_soul", 12), "004_Day_Twelve.html")
        check("file|TES英文101天(尾章)", _fname("the_emperors_soul", 101),
              "015_Epilogue_Day_One_Hundred_and_One.html")
        check("file|TES标签epilogue", _fname("the_emperors_soul", "epilogue"),
              "015_Epilogue_Day_One_Hundred_and_One.html")
        check("file|TES标签postscript", _fname("the_emperors_soul", "postscript"),
              "016_Postscript.html")
        check("file|TES标签prologue", _fname("the_emperors_soul", "prologue"),
              "000_Prologue.html")
        check("file|TES无此日诚实None", _fname("the_emperors_soul", 41), None)
        check("file|TES中文第12天", _fname("zh_皇帝魂", 12), "004_第十二天.html")
        check("file|TES中文101天", _fname("zh_皇帝魂", 101), "015_终章_第一百零一天.html")
        check("file|英文插曲i-4", _fname("words_of_radiance", "i-4"),
              "016_I-4_Last_Legion.html")
        check("file|中文插曲i-4", _fname("zh_渡誓", "i-4"), "061_I-4_卡扎.html")
        check("file|常规章号", _fname("the_final_empire", 24), "024_chapter24.html")

        r = ga.locate("Get a Flesh Forgery wrong, and people died.", "tes", 2,
                      ctx=160, full_zh=True, fallback_whole_book=True)
        check("loc|TES直查命中", r.get("found"), True)
        check("loc|zh_full回填", bool(r.get("zh_full")), True)
        check("loc|zh_pos在篇幅内",
              isinstance(r.get("zh_pos"), int) and 0 <= r["zh_pos"] <= len(r.get("zh_full", "")),
              True)
        r2 = ga.locate("no such phrase hello test abcdefg", "tes", 41,
                       ctx=160, fallback_whole_book=True)
        check("loc|无此日+整书回退诚实", (r2.get("found"), r2.get("error") is not None),
              (False, True))
        check("loc|破折号零空白", ga.find_in(
            "an object’s soul—its essence—as well as",
            "soul— its essence— as well as"), [12])
        check("loc|直弯撇号", ga.find_in("we don’t use that word",
                                         "we don't use that word"), [0])
        check("loc|词边界拒绝", ga.find_in("Remembererss", "Rememberers"), [])
    else:
        print("  SKIP epub 用例（dict/epub_out/the_emperors_soul 不存在）")

    total = passed + failed
    print(f"{passed}/{total} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
