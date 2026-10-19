#!/usr/bin/env python3
"""规则 review：机械化检查「译名表内词在正文被保留英文」等 R2 遵守问题。

与 verify_translation.py 分离（batch 写站门禁保持不变），供批次后逐条 review 使用。
用法：
  python scripts/review_rules.py --title-file state/bot_test_titles.txt
  python scripts/review_rules.py --title Spook
每篇输出规则遵守问题清单；退出码 0=无问题。
"""
from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import importlib.util as ilu


def load_mod(name, path):
    spec = ilu.spec_from_file_location(name, path)
    m = ilu.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


def strip_protected(body: str) -> str:
    """剥离保护区域：只保留需要翻译的自然语言文本。

    - Quote/columns/sidequote 块（英文原文，决议#13）
    - wikilink 目标 [[X|Y]] → 保留 Y；[[X]] → 替换为空（目标页名不译）
    - {{en|X}} → 删；原名行 → 删；File: → 删
    - <ref>...</ref> 内容（说明文字要译，保留）；<ref name=X/> → 删
    - {{msh ref}} 等纯结构模板参数不产生英文残留（占位已 unmask 回模板形态）
    """
    out = body
    # Quote / sidequote 块（配对花括号）
    out = re.sub(r"\{\{\s*(?:Quote|sidequote|columns)\b.*?\n\}\}", "", out, flags=re.S | re.I)
    out = re.sub(r"\{\{\s*(?:Quote|sidequote)\b.*?\}\}", "", out, flags=re.I | re.S)
    # {{en|X}}
    out = re.sub(r"\{\{\s*en\s*\|[^}]*\}\}", "", out, flags=re.I)
    # 原名行
    out = re.sub(r"^\|?\s*原名\s*=.*$", "", out, flags=re.M)
    # 文件链接
    out = re.sub(r"\[\[File:[^\]]*\]\]", "", out, flags=re.I)
    # [[目标|显示]] → 显示；[[目标]] → 删目标（页名保留英文合法）
    out = re.sub(r"\[\[([^\[\]|]+)\|([^\[\]]+)\]\]", r"\2", out)
    out = re.sub(r"\[\[[^\[\]]+\]\]", "", out)
    # 自闭合 ref
    out = re.sub(r'<ref name="[^"]*"\s*/>', "", out, flags=re.I)
    # 模板整体（infobox 参数行值除外——infobox 是行式 | 值，非 {{}} 包裹，保留在下面）
    # 粗体标记
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--title")
    ap.add_argument("--title-file")
    ap.add_argument("--glossary", default=None)
    args = ap.parse_args()

    tr = load_mod("tr_mod", HERE / "translate.py")
    gl_path = Path(args.glossary) if args.glossary else Path(tr.DEFAULT_GLOSSARY)
    gl = tr.load_merged_glossary(gl_path, tr.DEFAULT_COMMON)
    keep_en = set(tr.load_keep_en())

    titles = []
    if args.title:
        titles = [args.title]
    else:
        titles = [l.strip() for l in Path(args.title_file).read_text(encoding="utf-8").splitlines() if l.strip()]

    # 译名表有 zh 的英文词（跳过含链接/占位符的键），按长度降序
    terms = []
    for en, v in gl.items():
        zh = v.get("zh") if isinstance(v, dict) else None
        if not zh or not en or en in keep_en:
            continue
        if any(c in en for c in "[{|%/"):
            continue
        if len(en) < 3:
            continue
        terms.append((en, zh))
    terms.sort(key=lambda x: -len(x[0]))

    total_problems = 0
    for title in titles:
        tf = Path(tr.ROOT) / "en_snapshot" / title.replace("/", "_") / "translation.json"
        if not tf.exists():
            print(f"### {title}: [缺 translation.json]")
            total_problems += 1
            continue
        import json
        body = json.load(open(tf, encoding="utf-8"))["translation"]
        clean = strip_protected(body)
        probs = []
        reported_spans = []
        for en, zh in terms:
            # 词边界匹配（含 's 所有格）；跳过 keep_en 命中
            if en in keep_en:
                continue
            pat = re.compile(r"(?<![A-Za-z])" + re.escape(en) + r"(?:'s)?(?![A-Za-z])")
            for m in pat.finditer(clean):
                # 与已报告跨度重叠则跳过（长词已覆盖）
                if any(m.start() < b and m.end() > a for a, b in reported_spans):
                    continue
                # 上下文
                i = m.start()
                ctx = clean[max(0, i - 35):i + len(m.group(0)) + 25].replace("\n", " ")
                probs.append(f"[表内词未译] {m.group(0)!r}（应译 {zh}）| …{ctx}…")
                reported_spans.append((m.start(), m.end()))
                if len(probs) >= 12:
                    break
            if len(probs) >= 12:
                break
        if probs:
            total_problems += len(probs)
            print(f"### {title}: {len(probs)} 个问题")
            for p in probs:
                print("   ", p)
        else:
            print(f"### {title}: OK")
    print(f"\n== 合计 {total_problems} 个 R2 问题 ==")
    sys.exit(1 if total_problems else 0)


if __name__ == "__main__":
    main()
