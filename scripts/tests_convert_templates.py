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
]


def main():
    failed = 0
    for name, fn, src, want in CASES:
        got = fn(src)
        if got == want:
            print("  OK  %s" % name)
        else:
            failed += 1
            print("  FAIL %s" % name)
            print("    got : %r" % got)
            print("    want: %r" % want)
    print("\n%d/%d passed" % (len(CASES) - failed, len(CASES)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())