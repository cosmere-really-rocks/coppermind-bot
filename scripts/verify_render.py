#!/usr/bin/env python3
"""批量渲染校验：对 Bot测试: 前缀页面逐个 parse，检查渲染错误/红链/{{{2}}}/引用错误。

用法：
  python scripts/verify_render.py --prefix "Bot测试:" --titles state/bot_test_titles.txt
  python scripts/verify_render.py --prefix "Bot测试:"        # 校验该前缀下全部页面

退出码：0 全部通过；1 有问题。
每个页面检查：
  - parse API 错误（页面本身 wikitext 解析失败）
  - class="error" / 引用错误 / 脚本错误 / 模板循环
  - {{{2}}} 等未展开模板参数残留（HTML 属性+可见文本）
  - 红链（title="X" class="new"）
  - 脚注数（cite_note 锚点）> 0（有引用的页面）
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ENV = ROOT / ".env"
API = "https://coppermind.huijiwiki.com/api.php"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"


def load_env():
    env = {}
    if ENV.exists():
        for l in ENV.read_text().splitlines():
            if "=" in l and not l.strip().startswith("#"):
                k, v = l.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def api_get(params, key, timeout=40):
    url = API + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    req = urllib.request.Request(url, headers={"x-authkey": key, "User-Agent": UA})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def check_page(title: str, key: str) -> list[str]:
    problems = []
    try:
        r = api_get({"action": "parse", "page": title, "prop": "text",
                     "format": "json", "formatversion": "2"}, key)
    except Exception as e:
        return [f"[parse] API 失败: {e}"]
    if "error" in r:
        err = r["error"]
        # 不该有页面（missing）也算问题——写站应该创建了
        return [f"[parse] 解析错误: {err.get('code')} {err.get('info','')[:150]}"]
    html = r["parse"]["text"]

    for pat, name in [
        (r'class="error"', "渲染错误(class=error)"),
        (r'引用错误', "引用错误"),
        (r'脚本错误', "脚本错误"),
        (r'Template loop detected', "模板循环"),
    ]:
        n = len(re.findall(pat, html))
        if n:
            problems.append(f"[渲染] {name}: {n} 处")

    # {{{N}}} 未展开参数（id/href 属性 + 可见文本都会命中，任何出现都算）
    n_tpl = html.count("{{{")
    if n_tpl:
        m = re.search(r'.{60}\{\{\{.{60}', html, re.S)
        sample = re.sub(r"<[^>]{0,50}>", " ", m.group(0)) if m else ""
        problems.append(f"[渲染] 未展开参数 {{{{...}}}}: {n_tpl} 处 | 示例: {sample[:120]}")

    # 红链
    red = re.findall(r'<a href="[^"]*" title="([^"]+)" class="new"', html)
    if red:
        uniq = sorted(set(red))
        problems.append(f"[红链] {len(red)} 个（{len(uniq)} 个不同目标）: {uniq[:8]}")

    # 脚注：有 ref 的页应该有 cite_note（pages without any ref are fine too）
    notes = re.findall(r'id="cite_note-', html)
    marks = re.findall(r'&\#91;\d+&\#93;', html)
    info = f"脚注 {len(notes)} 个 / 上标 {len(marks)} 个"
    return problems, info


def list_prefix_pages(prefix: str, key: str) -> list[str]:
    """列出指定前缀下的全部主命名空间页面。"""
    titles = []
    cont = None
    while True:
        params = {"action": "query", "list": "allpages", "apprefix": prefix,
                  "apnamespace": "0", "aplimit": "500", "format": "json", "formatversion": "2"}
        if cont:
            params["apcontinue"] = cont
        r = api_get(params, key)
        batch = [p["title"] for p in r["query"]["allpages"]]
        titles += batch
        if "continue" in r:
            cont = r["continue"]["apcontinue"]
        else:
            break
    return titles


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", default="Bot测试:")
    ap.add_argument("--titles-file", default=None, help="按 zh 标题清单校验（用 _resolve_zh_title 解析）")
    args = ap.parse_args()
    env = load_env()
    key = env.get("HUIJI_API_KEY")
    if not key:
        print("[fail] .env 缺 HUIJI_API_KEY", file=sys.stderr)
        sys.exit(1)

    if args.titles_file:
        # 清单是英文快照标题 → 解析为 zh 目标标题
        sys.path.insert(0, str(HERE))
        import importlib.util as ilu
        spec = ilu.spec_from_file_location("bt_mod", HERE / "batch.py")
        bt = ilu.module_from_spec(spec)
        sys.modules[spec.name] = bt
        spec.loader.exec_module(bt)
        en_titles = [l.strip() for l in Path(args.titles_file).read_text(encoding="utf-8").splitlines()
                     if l.strip()]
        titles = [args.prefix + bt._resolve_zh_title(t) for t in en_titles]
    else:
        titles = list_prefix_pages(args.prefix, key)

    print(f"[渲染校验] {len(titles)} 个页面")
    failed = 0
    for i, t in enumerate(titles, 1):
        res = check_page(t, key)
        if isinstance(res, tuple):
            problems, info = res
        else:
            problems, info = res, ""
        status = "PASS" if not problems else f"FAIL({len(problems)})"
        print(f"  [{i:02d}/{len(titles)}] {status}  {t}  {info}")
        for p in problems:
            print(f"         {p}")
        if problems:
            failed += 1
        time.sleep(0.6)  # 限速（决议#14 精神）
    print(f"\n== {len(titles) - failed}/{len(titles)} 通过 ==")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
