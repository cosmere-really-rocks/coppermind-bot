#!/usr/bin/env python3
"""
探测工具：查英文站用到的模板在中站（红铜智库）是否存在对应模板。

背景：把英文 Coppermind 词条搬去灰机红铜智库时，页面里的 {{模板}} 需要中站有对应模板
才能正常渲染。本脚本用于：
  1) 单查：--template <英文模板名> 查中站是否有同名『模板:<名>』（另试常见别名/大小写）。
  2) 全量核对：--audit 扫描 en_snapshot/ 全部词条，提取用到的所有模板名，
     批量查中站『模板:<名>』存在性，输出：同名存在 / 缺失（待人工补建或改名）。

判定规则（模板名首字母不敏感，故按首字母大写后的标题查）：
  - 同名存在 → OK（如 for → 模板:For、book ref → 模板:Book ref）
  - 被 template_map.json 映射为中文 infobox 的 → 单独归到 'infobox-mapped'，不视为缺失
  - 其余不存在 → 'missing'（需人工确认：是改成中站既有中文模板名，还是需要新建模板）

用法：
  .venv/bin/python scripts/probe_template.py --template for          # 单查
  .venv/bin/python scripts/probe_template.py --template 'book ref' --verbose
  .venv/bin/python scripts/probe_template.py --audit                  # 全量核对（写 probe_report.json + .txt）
  .venv/bin/python scripts/probe_template.py --audit --summary        # 只打汇总，不写文件

依赖：仅 stdlib（urllib + write.py 的登录客户端）；不需额外库。
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from collections import Counter
from pathlib import Path

import mwparserfromhell

import write  # 复用 HuijiClient / load_env / resolve_api_url

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EN_SNAPSHOT = ROOT / "en_snapshot"
RULES = ROOT / "rules" / "template_map.json"


def load_infobox_srcs() -> set[str]:
    """读 rules/template_map.json，返回被映射为中文 infobox 的英文模板名集合（小写）。"""
    if not RULES.exists():
        return set()
    rules = json.loads(RULES.read_text(encoding="utf-8"))
    out = set()
    for cfg in rules.values():
        if isinstance(cfg, dict):
            src = cfg.get("src_template")
            if src:
                out.add(src.lower())
    # 简单改名模板也视为有中站对应（同名/中站同名模板）
    return out


def extract_templates() -> Counter:
    """扫描 en_snapshot/ 全部词条，提取所用模板名（去 Template:/模板: 前缀，小写去重计数）。"""
    c = Counter()
    for f in glob.glob(str(EN_SNAPSHOT / "*" / "wikitext.txt")):
        txt = Path(f).read_text(encoding="utf-8", errors="replace")
        try:
            code = mwparserfromhell.parse(txt)
        except Exception:
            continue
        for tpl in code.filter_templates():
            name = re.sub(r"^(?:Template|模板)\s*:", "", str(tpl.name).strip(), flags=re.IGNORECASE).strip()
            name = re.sub(r"^:|^\{\{$", "", name).strip()
            name = name.split("|")[0].strip()
            if not name:
                continue
            c[name] += 1
    return c


class Prober:
    """封装中站模板存在性探测（复用 write.HuijiClient，需登录）。"""

    def __init__(self):
        env = write.load_env(None)
        api = write.resolve_api_url(env)
        self.client = write.HuijiClient(api, env["HUIJI_API_KEY"], env["HUIJI_BOT_USER"], env["HUIJI_BOT_PASS"])
        self._exists_cache: dict[str, bool] = {}

    def ensure_login(self):
        self.client.ensure_logged_in()

    def query_titles(self, titles: list[str]) -> dict[str, bool]:
        """批量查若干『模板:<名>』存在性。返回 {title: exists}。MediaWiki query 一次约 50 个。"""
        result = {}
        for i in range(0, len(titles), 50):
            batch = titles[i:i + 50]
            body = self.client._post({"action": "query", "titles": "|".join(batch), "format": "json"})
            for p in body.get("query", {}).get("pages", {}).values():
                if "missing" in p:
                    result[p["title"]] = False
                else:
                    result[p["title"]] = True
        return result

    def template_exists(self, en_name: str) -> bool:
        # MediaWiki 模板名首字母不敏感：按标题规范（首字母大写）查。
        key = en_name.strip()
        if not key:
            return False
        normalized = key[0].upper() + key[1:]
        title = "模板:" + normalized
        if title in self._exists_cache:
            return self._exists_cache[title]
        r = self.query_titles([title])
        exists = r.get(title, False)
        self._exists_cache[title] = exists
        return exists

    def search_templates(self, term: str, limit: int = 6) -> list[str]:
        """在中站 Template 命名空间（ns=10）按关键词搜近名模板，辅助判断"换名/真缺"。"""
        body = self.client._post({
            "action": "query", "list": "search", "srsearch": term,
            "srnamespace": "10", "srlimit": str(limit), "format": "json",
        })
        return [r["title"] for r in body.get("query", {}).get("search", [])]


def probe_one(prober: Prober, name: str, verbose: bool) -> int:
    exists = prober.template_exists(name)
    status = "OK（中站有 模板:%s）" % (name[0].upper() + name[1:]) if exists else "缺失（中站无同名模板）"
    print(f"{name:24s} -> {status}")
    return 0 if exists else 1


def audit(prober: Prober, summary_only: bool) -> Counter:
    infobox_srcs = load_infobox_srcs()
    c = extract_templates()
    total = sum(c.values())
    print(f"扫描到 {len(c)} 个唯一模板名，共 {total} 处使用。")
    prober.ensure_login()

    ok, missing, mapped = [], [], []
    names = sorted(c, key=lambda n: (-c[n], n))
    for n in names:
        if n.lower() in infobox_srcs:
            mapped.append((n, c[n]))
            continue
        if prober.template_exists(n):
            ok.append((n, c[n]))
        else:
            cands = prober.search_templates(n)
            missing.append({"name": n, "count": c[n], "candidates": cands})

    ok.sort(key=lambda x: -x[1]); mapped.sort(key=lambda x: -x[1])
    missing.sort(key=lambda x: -x["count"])

    print("\n=== 已由 template_map 映射为中站 infobox（.lower() 命中 src_template）===")
    for n, cnt in mapped:
        print(f"  {cnt:5d}  {n}")

    print("\n=== 中站有同名模板（可直接渲染）===")
    for n, cnt in ok:
        print(f"  {cnt:5d}  {n}")

    print(f"\n=== 缺失/待确认（中站无同名模板）—— 共 {len(missing)} 个 ===")
    for m in missing:
        line = f"  {m['count']:5d}  {m['name']}"
        if m["candidates"]:
            line += f"    [近名候选: {', '.join(m['candidates'][:4])}]"
        print(line)

    if summary_only:
        return c

    # 写报告
    report = {
        "total_templates": len(c),
        "total_usages": total,
        "ok_same_name": ok,
        "infobox_mapped": mapped,
        "missing": missing,
    }
    out_json = ROOT / "probe_report.json"
    out_txt = ROOT / "probe_report.txt"
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    buf = []
    buf.append(f"扫到 {len(c)} 个模板 / {total} 处使用\n")
    buf.append(f"同名存在 {len(ok)} 个 | template_map 映射 {len(mapped)} 个 | 缺失待确认 {len(missing)} 个\n")
    buf.append("\n=== 缺失/待确认（含中站近名候选，便于判断换名 or 真缺）===\n")
    for m in missing:
        buf.append(f"{m['count']:5d}  {m['name']}")
        if m["candidates"]:
            buf.append(f"     [近名候选: {', '.join(m['candidates'])}]\n")
        else:
            buf.append("     [中站搜索无近名，疑似真缺]\n")
    out_txt.write_text("".join(buf), encoding="utf-8")
    print(f"\n报告：{out_json}\n缺失清单：{out_txt}")
    return c


def main():
    ap = argparse.ArgumentParser(description="探测英文模板在中站是否有对应（复用 write.py 登录）")
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--template", help="单查一个英文模板名，例如 for / 'book ref'")
    grp.add_argument("--audit", action="store_true", help="全量核对 en_snapshot 里所有模板")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--summary", action="store_true", help="--audit 时只打汇总，不写报告文件")
    args = ap.parse_args()

    prober = Prober()
    if args.template:
        prober.ensure_login()
        sys.exit(probe_one(prober, args.template, args.verbose))
    audit(prober, summary_only=args.summary)


if __name__ == "__main__":
    main()
