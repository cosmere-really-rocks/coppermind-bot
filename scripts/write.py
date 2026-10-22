#!/usr/bin/env python3
"""
写站管道：把 translate.py 产出的 translation.json 写回中文站（红铜智库）。

输入：en_snapshot/<标题>/translation.json（契约：{meta.title_en, meta.revision_id, translation, untranslated_terms}）
流程：读 .env 凭据 → login（logintoken）→ CSRF → action=edit（bot 标记）
权限要求：账号须在中文站 `verified`（认证用户）或 `staff` 群组才有 edit 权，否则 permissiondenied。

用法：
  .venv/bin/python scripts/write.py --title <快照标题>                    # 写回，目标页=meta.title_en
  .venv/bin/python scripts/write.py --title <快照标题> --target <中文页标题>  # 指定目标页
  .venv/bin/python scripts/write.py --title <快照标题> --dry-run           # 登录+CSRF，只打印请求不真正写
  .venv/bin/python scripts/write.py --title <快照标题> --skip-if-same      # 若目标页 ensync revid==meta.revision_id 则跳过（决议#3 增量）
  .venv/bin/python scripts/write.py --summary <自定义摘要>

选项：
  --dry-run        登录+取 CSRF 后只打印编辑载荷，不 send
  --skip-if-same   目标页已含 {{ensync|同一 revid}} 则跳过（增量去重，决议#3）
  --force          即使 --skip-if-same 判定已同步也强制写（默认则不强制）
  --summary        编辑摘要（默认自动生成）
  --target         目标中文页标题（默认取 meta.title_en）
  --env            指定 .env 路径（默认向上找）
依赖：仅 stdlib（urllib/http.cookiejar/re/json）；不需额外库。
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EN_SNAPSHOT = ROOT / "en_snapshot"
DEFAULT_SUMMARY = "bot 搬运：由英文 Coppermind 词条翻译而来（含 {{CmPermission}}/{{en}}/{{ensync}}）"
USER_AGENT = "coppermind-translate-bot/0.1 (python)"


def load_env(env_path: Path | None) -> dict:
    """读取 .env（KEY=VALUE 行，# 注释）。"""
    p = env_path or _find_env()
    if not p or not p.exists():
        raise SystemExit(".env 不存在或未找到（含 HUIJI_WIKI/HUIJI_API_KEY/HUIJI_BOT_USER/HUIJI_BOT_PASS）。")
    env = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def _find_env() -> Path | None:
    cur = ROOT
    while True:
        cand = cur / ".env"
        if cand.exists():
            return cand
        if cur.parent == cur:
            return None
        cur = cur.parent


def resolve_api_url(env: dict) -> str:
    """HUIJI_API（完整 api.php）优先，否则 HUIJI_WIKI 子域拼成 https://<子域>.huijiwiki.com/api.php。"""
    api = env.get("HUIJI_API")
    if api:
        return api
    wiki = env.get("HUIJI_WIKI")
    if not wiki:
        raise SystemExit("缺少 HUIJI_API 或 HUIJI_WIKI。")
    return f"https://{wiki}.huijiwiki.com/api.php"


class HuijiClient:
    """MediaWiki api.php 客户端：x-authkey 头 + bot 登录 cookie 会话（与 huiji-wiki-bot skill 同款逻辑）。"""

    def __init__(self, api_url: str, api_key: str, username: str = "", password: str = ""):
        self.url = api_url
        self.api_key = api_key
        self.username = username
        self.password = password
        self._cj = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self._cj))

    def _post(self, params: dict) -> dict:
        data = urllib.parse.urlencode(params).encode("utf-8")
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": USER_AGENT,
            "x-authkey": self.api_key,
        }
        req = urllib.request.Request(self.url, data=data, headers=headers, method="POST")
        with self._opener.open(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        if body.get("error"):
            raise RuntimeError(f"API error {body['error'].get('code')}: {body['error'].get('info')}")
        return body

    @property
    def is_logged_in(self) -> bool:
        # huiji 站的会话 cookie 名为 huiji_session（并非 skill 里的 huiji_BPsession）
        return any(c.name == "huiji_session" for c in self._cj)

    def get_token(self, typ: str = "csrf") -> str:
        body = self._post({"action": "query", "meta": "tokens", "type": typ, "format": "json"})
        return body["query"]["tokens"][f"{typ}token"]

    def login(self) -> None:
        token = self.get_token("login")
        self._post({
            "action": "login", "lgname": self.username, "lgpassword": self.password,
            "lgtoken": token, "format": "json",
        })
        if not self.is_logged_in:
            raise RuntimeError("登录后未获得有效会话 cookie（huiji_BPsession）。")

    def ensure_logged_in(self) -> None:
        if self.is_logged_in:
            return
        if not self.username or not self.password:
            raise RuntimeError("需要设置 HUIJI_BOT_USER/HUIJI_BOT_PASS。")
        self.login()

    def edit(self, title: str, content: str, summary: str, minor: bool = False) -> dict:
        self.ensure_logged_in()
        token = self.get_token("csrf")
        body = self._post({
            "action": "edit", "title": title, "text": content, "summary": summary,
            "minor": "1" if minor else "0", "bot": "1", "token": token, "format": "json",
        })
        return body["edit"]

    def move(self, from_title: str, to_title: str, reason: str = "") -> dict:
        """移动页面（保留历史与重定向，MediaWiki action=move）。"""
        self.ensure_logged_in()
        token = self.get_token("csrf")
        body = self._post({
            "action": "move", "from": from_title, "to": to_title,
            "reason": reason, "movetalk": "1", "noredirect": "0",
            "bot": "1", "token": token, "format": "json",
        })
        return body.get("move", body)

    def read_page(self, title: str) -> dict | None:
        """读取页面（只读）。返回 {missing, title, pageid, revid, wikitext} 或 None。"""
        body = self._post({
            "action": "query", "titles": title, "prop": "revisions",
            "rvprop": "ids|timestamp|user|comment|content", "rvslots": "main",
            "rvlimit": "1", "format": "json", "formatversion": "2",
        })
        pages = body["query"]["pages"]
        if not pages:
            return None
        page = pages[0]
        rev = page.get("revisions", [{}])[0]
        return {
            "missing": page.get("missing", False),
            "title": page.get("title", title),
            "pageid": page.get("pageid"),
            "revid": rev.get("revid"),
            "timestamp": rev.get("timestamp"),
            "user": rev.get("user"),
            "wikitext": (rev.get("slots") or {}).get("main", {}).get("content"),
        }


def extract_ensync_revid(wikitext: str | None):
    """从页面 wikitext 里抓 {{ensync|<revid>}} 的 revid；无则 None。"""
    if not wikitext:
        return None
    m = re.search(r"\{\{\s*ensync\s*\|([^|}]+)", wikitext, re.IGNORECASE)
    return m.group(1).strip() if m else None


def ensure_aitranslation(text: str) -> str:
    """页首 {{AITranslation}} 标记（2026-10-23 用户指示：每个词条最顶部）。

    与 translate.ensure_aitranslation 同语义（write.py 仅依赖 stdlib，故两处各自
    实现，tests_aitranslation.py 逐输入对等断言防漂移）。写站侧前置的独立价值：
    存量 translation.json（标记落地前的旧产物）走 --stage write 直写也带上标记，
    且不会把站点上人工补的标记行冲掉。幂等：已含则原样返回。
    """
    if "{{AITranslation}}" in text:
        return text
    return "{{AITranslation}}\n" + text


def main():
    ap = argparse.ArgumentParser(description="把 translation.json 写回中文站（红铜智库）")
    ap.add_argument("--title", required=True, help="快照标题（读取 en_snapshot/<标题>/translation.json）")
    ap.add_argument("--target", default=None, help="目标中文页标题（默认 meta.title_en）")
    ap.add_argument("--dry-run", action="store_true", help="登录+CSRF 后只打印编辑载荷，不真正写入")
    ap.add_argument("--skip-if-same", action="store_true", help="目标页 ensync revid==meta.revision_id 则跳过（决议#3 增量）")
    ap.add_argument("--force", action="store_true", help="即使判定已同步也强制写")
    ap.add_argument("--summary", default=None, help="编辑摘要（默认自动）")
    ap.add_argument("--env", default=None, help=".env 路径")
    args = ap.parse_args()

    d = EN_SNAPSHOT / args.title.replace("/", "_")
    tj = d / "translation.json"
    if not tj.exists():
        raise SystemExit(f"找不到 {tj}。请先运行 scripts/translate.py --title {args.title}")
    contract = json.loads(tj.read_text(encoding="utf-8"))
    meta = contract.get("meta", {})
    title_en = meta.get("title_en") or args.title
    revid = meta.get("revision_id")
    text = contract.get("translation", "")
    if not text:
        raise SystemExit(f"{tj} 的 translation 为空，拒绝写入。")
    text = ensure_aitranslation(text)  # 页首标记：存量 translation.json 直写也带上（幂等）
    target = args.target or title_en
    summary = args.summary or f"{DEFAULT_SUMMARY}（{title_en}，ensync {revid}）"

    env = load_env(Path(args.env) if args.env else None)
    client = HuijiClient(resolve_api_url(env), env.get("HUIJI_API_KEY", ""),
                         env.get("HUIJI_BOT_USER", ""), env.get("HUIJI_BOT_PASS", ""))
    client.ensure_logged_in()

    if args.skip_if_same and not args.force:
        cur = client.read_page(target)
        cur_revid = extract_ensync_revid(cur["wikitext"] if cur else None)
        if cur_revid is not None and str(cur_revid) == str(revid):
            print(f"[跳过] {target} 已含 ensync revid={revid}，无需重写（决议#3）。")
            return 0

    if args.dry_run:
        print(f"[dry-run] 目标页={target}（来自 {title_en}）")
        print(f"[dry-run] 摘要={summary}")
        print(f"[dry-run] 内容长度={len(text)} 字符，前 200 字预览：\n")
        print(text[:200])
        print("\n[dry-run] 未真正写入。确认无误后去掉 --dry-run 再执行。")
        return 0

    result = client.edit(target, text, summary)
    newrevid = result.get("newrevid") or result.get("revid")
    print(f"[完成] 已写入「{target}」，newrevid={newrevid}"
          + (f"（原 revid {result.get('oldrevid')}）" if result.get("oldrevid") else ""))
    print(f"      页面：https://coppermind.huijiwiki.com/wiki/{urllib.parse.quote(target)}")
    return 0


if __name__ == "__main__":
    main()
