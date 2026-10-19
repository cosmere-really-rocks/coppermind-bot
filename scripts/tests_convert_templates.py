# -*- coding: utf-8 -*-
"""convert_templates.py 引用模板修复的回归单测。

覆盖三件套：单参 book ref 补空参 / fn 内嵌引用模板展开 / text-only ref 归一。
用法：.venv/bin/python scripts/tests_convert_templates.py
"""
import os
import sys
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_spec = importlib.util.spec_from_file_location("convert_templates_mod", os.path.join(HERE, "convert_templates.py"))
ct = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = ct
_spec.loader.exec_module(ct)

CASES = [
    # --- _fix_single_arg_book_refs ---
    ("单参补空", ct._fix_single_arg_book_refs,
     "见{{book ref|11m}}。", "见{{book ref|11m|}}。"),
    ("单参mb4", ct._fix_single_arg_book_refs,
     "引{{book ref|mb4}}。", "引{{book ref|mb4|}}。"),
    ("多参不动", ct._fix_single_arg_book_refs,
     "见{{book ref|AoL|2}}。", "见{{book ref|AoL|2}}。"),
    ("三参不动", ct._fix_single_arg_book_refs,
     "见{{book ref|Sa2|i|9}}。", "见{{book ref|Sa2|i|9}}。"),
    ("命名参不动", ct._fix_single_arg_book_refs,
     "见{{book ref|mb4|part=ars}}。", "见{{book ref|mb4|part=ars}}。"),
    ("正文多参", ct._fix_single_arg_book_refs,
     "见{{book ref|mb4|1}}{{book ref|mb7|2}}。", "见{{book ref|mb4|1}}{{book ref|mb7|2}}。"),
    # --- _expand_nested_refs_in_fn ---
    ("fn内嵌bookref", ct._expand_nested_refs_in_fn,
     '<ref group="fn">见{{book ref|mb4|1}}{{book ref|mb4|17}}。</ref>',
     '<ref group="fn">见[[{{b|mb4}}/梗概#第1章|《{{b|mb4}}》第1章]][[{{b|mb4}}/梗概#第17章|《{{b|mb4}}》第17章]]。</ref>'),
    ("fn内嵌序幕", ct._expand_nested_refs_in_fn,
     '<ref group="fn">引{{book ref|mb7|prologue}}。</ref>',
     '<ref group="fn">引[[{{b|mb7}}/梗概#序幕|《{{b|mb7}}》序幕]]。</ref>'),
    ("fn内嵌插曲", ct._expand_nested_refs_in_fn,
     '<ref group="fn">见{{book ref|mb4|i|3}}。</ref>',
     '<ref group="fn">见[[{{b|mb4}}/梗概#插曲3|《{{b|mb4}}》插曲3]]。</ref>'),
    ("fn内嵌单参", ct._expand_nested_refs_in_fn,
     '<ref group="fn">外{{book ref|mb4}}。</ref>',
     '<ref group="fn">外《{{b|mb4}}》。</ref>'),
    ("fn内嵌wob", ct._expand_nested_refs_in_fn,
     '<ref group="fn">引{{wob ref|5508}}。</ref>',
     '<ref group="fn">引[[wob:5508|wob:5508]]。</ref>'),
    ("fn内嵌file", ct._expand_nested_refs_in_fn,
     '<ref group="fn">见{{file ref|Hemalurgy table.jpg|表}}。</ref>',
     '<ref group="fn">见[[文件:Hemalurgy table.jpg|表]]。</ref>'),
    ("fn内嵌map", ct._expand_nested_refs_in_fn,
     '<ref group="fn">查{{map ref|Elendel Basin}}。</ref>',
     '<ref group="fn">查[[文件:Elendel Basin.png|Elendel Basin]]。</ref>'),
    ("fn内嵌epigraph", ct._expand_nested_refs_in_fn,
     '<ref group="fn">题{{epigraph ref|mb3|36}}。</ref>',
     '<ref group="fn">题《{{b|mb3}}》题词第36章。</ref>'),
    ("fn内嵌msh", ct._expand_nested_refs_in_fn,
     '<ref group="fn">秘{{msh ref|1|2}}。</ref>',
     '<ref group="fn">秘[[迷雾之子：秘史/梗概#第1部分第2章|《迷雾之子：秘史》第1部分第2章]]。</ref>'),
    ("fn内嵌date保留", ct._expand_nested_refs_in_fn,
     '<ref group="fn">日期{{date|348|PC}}。</ref>',
     '<ref group="fn">日期{{date|348|PC}}。</ref>'),
    ("正文wob不动", ct._expand_nested_refs_in_fn,
     '正文{{wob ref|5508}}。', '正文{{wob ref|5508}}。'),
    # --- _scan_refs text-only ---
    ("text-only", ct._scan_refs,
     "见{{ref|text=旁注内容}}。", "见<ref>旁注内容</ref>。"),
    ("fn组", ct._scan_refs,
     "见{{ref|group=fn|text=脚注}}。", '见<ref group="fn">脚注</ref>。'),
    ("占位", ct._scan_refs,
     '见{{ref|name=X}}。', '见<ref name="X"/>。'),
    # --- _convert_lang_links ---
    ("es简单", ct._convert_lang_links,
     "[[es: Mistborn (saga)]]",
     "[https://es.coppermind.net/wiki/Mistborn_(saga) es: Mistborn (saga)]"),
    ("uk西里尔", ct._convert_lang_links,
     "[[uk: З-імли-народжені (серія)]]",
     "[https://uk.coppermind.net/wiki/%D0%97-%D1%96%D0%BC%D0%BB%D0%B8-%D0%BD%D0%B0%D1%80%D0%BE%D0%B4%D0%B6%D0%B5%D0%BD%D1%96_(%D1%81%D0%B5%D1%80%D1%96%D1%8F) uk: З-імли-народжені (серія)]"),
    ("en保留", ct._convert_lang_links,
     "[[en: Mistborn (series)]]", "[[en: Mistborn (series)]]"),
    ("wob保留", ct._convert_lang_links,
     "[[wob:9171|wob:9171]]", "[[wob:9171|wob:9171]]"),
    ("category不动", ct._convert_lang_links,
     "[[category: series]]", "[[category: series]]"),
    ("es带显示文本", ct._convert_lang_links,
     "[[es: Foo|自定义文本]]",
     "[https://es.coppermind.net/wiki/Foo 自定义文本]"),
]


def main():
    failed = 0

    def check(name, got, want):
        nonlocal failed
        if got == want:
            print("  OK  %s" % name)
        else:
            failed += 1
            print("  FAIL %s" % name)
            print("    got : %r" % got)
            print("    want: %r" % want)

    for name, fn, src, want in CASES:
        check(name, fn(src), want)

    # --- 写站标题解析（batch.py::_resolve_zh_title / translate.py::resolve_zh_title）---
    _bspec = importlib.util.spec_from_file_location("batch_mod", os.path.join(HERE, "batch.py"))
    bt = importlib.util.module_from_spec(_bspec)
    sys.modules[_bspec.name] = bt
    _bspec.loader.exec_module(bt)
    title_cases = [
        ("有译名|Ghostbloods", "Ghostbloods", "鬼血会"),
        ("有译名|Spook", "Spook", "鬼影"),
        ("有译名|Elendel", "Elendel", "依蓝戴"),
        ("站内既有页|Mistborn (series)", "Mistborn (series)", "迷雾之子(系列)"),
        ("无译名|Red (Scadrial)", "Red (Scadrial)", "Red (Scadrial)"),
        ("无译名|Demoux (city)", "Demoux (city)", "Demoux (city)"),
        ("无译名|Tyrian Sea", "Tyrian Sea", "Tyrian Sea"),
        ("无译名|Harmontide", "Harmontide", "Harmontide"),
    ]
    for name, src, want in title_cases:
        check("标题|" + name, bt._resolve_zh_title(src), want)

    # --- Post/Pre 时代前缀（translate.py::translate_prepost_links，LLM 前确定性转换）---
    _tspec = importlib.util.spec_from_file_location("translate_mod", os.path.join(HERE, "translate.py"))
    _tr = importlib.util.module_from_spec(_tspec)
    sys.modules[_tspec.name] = _tr
    _tspec.loader.exec_module(_tr)
    _gl = _tr.load_merged_glossary(_tr.DEFAULT_GLOSSARY, _tr.DEFAULT_COMMON)
    prepost_cases = [
        ("Post链接", "Post [[Catacendre]]", "[[灰烬灾变|灰烬灾变后]]"),
        ("post连字符", "post-[[Catacendre]]", "[[灰烬灾变|灰烬灾变后]]"),
        ("post空格", "post [[Catacendre]]", "[[灰烬灾变|灰烬灾变后]]"),
        ("pre连字符", "pre-[[Catacendre]]", "[[灰烬灾变|灰烬灾变前]]"),
        ("Pre首个", "Pre [[Catacendre]]", "[[灰烬灾变|灰烬灾变前]]"),
        ("pre空格", "pre [[Final Empire]]", "[[最后帝国|最后帝国前]]"),
        ("带管道", "post-[[Catacendre|Catacendric]]", "[[灰烬灾变|灰烬灾变后]]"),
        ("中文目标(infobox已译)", "Post [[灰烬灾变]]", "[[灰烬灾变|灰烬灾变后]]"),
        ("小写归一", "pre-[[catacendre]]", "[[灰烬灾变|灰烬灾变前]]"),
        ("无译名保留", "Post [[UnknownThing]]", "Post [[UnknownThing]]"),
        ("幂等", "[[灰烬灾变|灰烬灾变后]]", "[[灰烬灾变|灰烬灾变后]]"),
        ("不误伤独立词", "Post office", "Post office"),
    ]
    for name, src, want in prepost_cases:
        check("PrePost|" + name, _tr.translate_prepost_links(src, _gl)[0], want)

    print("\n%d/%d passed" % (len(CASES) + len(title_cases) + len(prepost_cases) - failed,
                              len(CASES) + len(title_cases) + len(prepost_cases)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())