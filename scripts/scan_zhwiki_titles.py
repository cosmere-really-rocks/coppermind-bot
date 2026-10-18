#!/usr/bin/env python3
"""扫描中文站全部主命名空间页面，提取「英文原名 → 中文站标题」映射。

来源信号（按优先级）：
  1. 页首 {{CmPermission|英文原名}}（本项目 bot 写页的包装，最可靠）
  2. 页首 {{en|英文原名}} 或 {{En|...}}（人工/其他工具页的对应标记）
  3. {{Infobox ... | 原名 = X }} 字段（人工建的条目页）

输出 dict/zhwiki_titles.json：{"zh_title": "en_title", ...}（同 En 名多页取标题最短者）。

用法：python scripts/scan_zhwiki_titles.py [--limit N]   （--limit 用于小规模试跑）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import write as W  # noqa: E402


def all_main_titles(client, limit=None):
    """遍历主命名空间（ns=0）所有页面标题，跳过 bot测试:/BOT测试: 前缀。"""
    titles = []
    apcontinue = None
    while True:
        params = {
            "action": "query", "list": "allpages", "apnamespace": "0",
            "aplimit": "500", "format": "json", "formatversion": "2",
        }
        if apcontinue:
            params["apcontinue"] = apcontinue
        body = client._post(params)
        pages = body.get("query", {}).get("allpages", [])
        for p in pages:
            t = p.get("title", "")
            if t.lower().startswith(("bot测试:", "bot测试")):
                continue
            titles.append(t)
            if limit and len(titles) >= limit:
                return titles
        cont = body.get("continue", {}).get("apcontinue")
        if not cont:
            break
        apcontinue = cont
    return titles


def extract_en_name(wikitext: str) -> str | None:
    """从页面 wikitext 提取英文原名。返回 None 表示该页没有可靠原名信号。"""
    if not wikitext:
        return None
    head = wikitext[:2000]
    # 1) {{CmPermission|X}}
    m = re.search(r"\{\{\s*CmPermission\s*\|\s*([^}|]+)", head)
    if m:
        return m.group(1).strip()
    # 2) {{en|X}} / {{En|X}}
    m = re.search(r"\{\{\s*[Ee]n\s*\|\s*([^}|]+)", head)
    if m:
        return m.group(1).strip()
    # 3) {{Infobox ...| 原名 = X }}（任意括号字段其后第一个 原名 = 值）
    m = re.search(r"\{\{\s*Infobox[^{}]*?\|\s*原名\s*=\s*([^|\n}{]+)", head)
    if m:
        return m.group(1).strip()
    return None


def _resolve_redirect(client, title, depth=0):
    """解析重定向链到最终中文目标（限 4 层）。纯英文目标继续追，中文目标即止。"""
    if depth > 4:
        return None
    try:
        wt = client.read_page(title).get("wikitext") or ""
    except Exception:
        return None
    m = re.search(r"#\s*(?:重定向|REDIRECT)\s*\[\[([^\]|]+)", wt, re.I)
    if not m:
        return None
    tgt = m.group(1).strip().replace("_", " ")
    if re.search(r"[\u4e00-\u9fff]", tgt):
        return tgt
    return _resolve_redirect(client, tgt, depth + 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="只扫前 N 个标题（试跑）")
    ap.add_argument("--out", default=str(ROOT / "dict" / "zhwiki_titles.json"))
    args = ap.parse_args()

    env = W.load_env(ROOT / ".env")
    api = W.resolve_api_url(env)
    client = W.HuijiClient(api, env.get("HUIJI_API_KEY", ""), env.get("HUIJI_BOT_USER", ""),
                           env.get("HUIJI_BOT_PASS", ""))
    client.ensure_logged_in()

    titles = all_main_titles(client, limit=args.limit)
    sys.stderr.write(f"[扫描] 主命名空间页面（跳过 bot测试:）共 {len(titles)} 个\n")

    mapping = {}   # zh_title -> en_title
    no_signal = 0
    skipped_en_title = 0
    t00 = time.time()
    for i, t in enumerate(titles):
        # 只处理含中文的标题：英文标题页 = 尚未翻译的占位页，不是「已确立译名」来源
        if not re.search(r"[\u4e00-\u9fff]", t):
            skipped_en_title += 1
            continue
        try:
            r = client.read_page(t)
        except Exception:
            continue
        wt = r.get("wikitext") if r else None
        en = extract_en_name(wt)
        if en and en != t and "#" not in en and "|" not in en and en.strip() == en:
            prev = mapping.get(t)
            if prev is None or len(en) < len(prev):
                mapping[t] = en
        else:
            no_signal += 1
        if (i + 1) % 100 == 0:
            sys.stderr.write(f"  {i+1}/{len(titles)} 已映射 {len(mapping)}，无信号 {no_signal} "
                             f"（{time.time()-t00:.0f}s）\n")
    sys.stderr.write(f"[完成] 中文标题页映射 {len(mapping)}，无信号 {no_signal}，英文标题页跳过 {skipped_en_title}\n")

    # 第二阶段：英文标题重定向页（如 Elend → 依蓝德·泛图尔）是「英文→中文」的直接映射。
    # 用 apfilterredir=redirects 只取重定向页（远少于全量），跳过 bot测试:/bot测试:。
    sys.stderr.write("[第二段] 收集重定向页…\n")
    redir_titles = []
    apcontinue = None
    while True:
        params = {"action": "query", "list": "allpages", "apnamespace": "0", "aplimit": "500",
                  "apfilterredir": "redirects", "format": "json", "formatversion": "2"}
        if apcontinue:
            params["apcontinue"] = apcontinue
        body = client._post(params)
        for p in body.get("query", {}).get("allpages", []):
            t = p.get("title", "")
            if t.lower().startswith(("bot测试:", "bot测试")):
                continue
            redir_titles.append(t)
        apcontinue = body.get("continue", {}).get("apcontinue")
        if not apcontinue:
            break
    sys.stderr.write(f"[第二段] 重定向页共 {len(redir_titles)} 个，读英文标题者…\n")

    redir_added = 0
    aliases = {}   # en 别名 -> zh（如 Elend -> 依蓝德·泛图尔），不覆盖 mapping 的规范原名
    t10 = time.time()
    for i, t in enumerate(redir_titles):
        if not re.match(r"^[A-Za-z0-9 :'&#()\-,\.]+$", t):
            continue  # 只处理英文标题重定向（中文标题页已在第一阶段映射）
        zh = _resolve_redirect(client, t)
        if zh and zh != t:
            # 重定向短名是别名，不覆盖 mapping（mapping 保留 CmPermission 规范原名）
            prev = aliases.get(t)
            if prev is None or len(zh) < len(prev):
                aliases[t] = zh
                redir_added += 1
        if (i + 1) % 100 == 0:
            sys.stderr.write(f"  重定向 {i+1}/{len(redir_titles)} 别名 {redir_added} "
                             f"（{time.time()-t10:.0f}s）\n")
    sys.stderr.write(f"[第二段完成] 重定向别名 {redir_added}，总映射 {len(mapping)}\n")

    ROOT.joinpath("dict").mkdir(exist_ok=True)
    out = Path(args.out)
    out.write_text(json.dumps(mapping, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    sys.stderr.write(f"[写出] {out}（{out.stat().st_size} 字节）\n")
    # 别名独立文件：en_alias -> zh（译名表/mapping 缺失时的补充译名）
    alias_file = Path(args.out).with_name("zhwiki_aliases.json")
    alias_file.write_text(json.dumps(aliases, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    sys.stderr.write(f"[写出] {alias_file}（{alias_file.stat().st_size} 字节，{len(aliases)} 条）\n")
    # 抽样展示
    for zh, en in list(mapping.items())[:10]:
        print(f"  {zh!r} <- {en!r}")


if __name__ == "__main__":
    main()