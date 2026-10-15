#!/usr/bin/env python3
"""
汇总 en_snapshot/ 下所有已抓页面的模板使用情况。

用法：
  .venv/bin/python scripts/analyze_templates.py [--out state/template_usage.json]
输出 JSON：
  {
    "total_pages": N,
    "templates": { "模板名": {"pages": 使用它的页面数, "examples": [前几个页面] } }
  }
按使用页面数降序；另有 markdown 表格输出（--md）。
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAP = ROOT / "en_snapshot"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "state" / "template_usage.json"))
    ap.add_argument("--md", action="store_true", help="同时输出 markdown 表格")
    args = ap.parse_args()

    usage = defaultdict(lambda: {"pages": 0, "examples": []})
    total = 0
    for d in sorted(SNAP.iterdir()):
        if not d.is_dir():
            continue
        meta = d / "meta.json"
        if not meta.exists():
            continue
        total += 1
        m = json.loads(meta.read_text(encoding="utf-8"))
        title = m.get("title", d.name)
        for tpl in m.get("templates", []):
            u = usage[tpl]
            u["pages"] += 1
            if len(u["examples"]) < 5:
                u["examples"].append(title)

    ordered = sorted(usage.items(), key=lambda kv: (-kv[1]["pages"], kv[0]))
    doc = {
        "total_pages": total,
        "root_usage": {name: u for name, u in ordered},
    }
    # 按 pages 数重新组织输出对象
    out_obj = {"total_pages": total, "templates": {}}
    for name, u in ordered:
        out_obj["templates"][name] = {"pages": u["pages"], "examples": u["examples"]}

    Path(args.out).write_text(json.dumps(out_obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写入 {args.out}（共 {total} 页，{len(out_obj['templates'])} 种模板）")

    if args.md:
        print("\n| 模板 | 使用页数 | 示例 |")
        print("|---|---|---|")
        for name, u in ordered[:200]:
            ex = ",".join(u["examples"][:3]) or "—"
            print(f"| `{name}` | {u['pages']} | {ex} |")


if __name__ == "__main__":
    main()
