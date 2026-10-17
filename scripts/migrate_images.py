#!/usr/bin/env python3
"""
迁移图片脚本（画师授权后放行，覆盖决议 #15 的旧限制）：
  从英文站把图片「本体文件」与「File: 页内容」一起搬到中文站（红铜智库）。

背景：
  - 中文站站长已获得英文站的图片授权（含画师），可搬运图片。
  - 决议 #15 原为「File 命名空间不得自动搬运（需逐个授权）」，本脚本即该授权的落地：
    被本脚本发现的图片 = 已获授权，允许上传图片本体 + File: 页 wikitext。

步骤：
  1. 扫描英文 wikitext，用「正则」发现其中的图片引用，格式支持：
       - [[File:x.jpg]]
       - [[Image:x.jpg]]
       - [[file:x.jpg|width=...]]（任意竖线参数）—— 文件名可含空格
       - 模板命名参数值：|image=x.png / |logo=... etc.（仅在文件名不含空格时可靠）
       - 裸写 x.jpg（可选 --include-bare，默认关闭——裸文件名易误报）
     另合并各快照 meta.json 里的「files」（fetch_en.py 用 mwparserfromhell 已确定性提取
     {{image}} 首位置参 / 文件感命名参数，作为正则的补充，最稳妥）。两来源去重合并。
  2. 对每个发现的图片 File:X：
       - 英文站取 File: 页 wikitext（内容）→ 作为中文站 File: 页的描述文本
       - 英文站 imageinfo 取图片 bytes
       - 上传到中文站：action=upload（bytes + text=File 内容），图片本体与 File: 页内容一次到位
  3. 增量：中文站该 File 页「已存在」即视为已迁移而跳过（决策 #3 精神；幂等判等以存在性
     为准，不用 sha1——英文站内容协商取回的字节对部分文件 ≠ 规范哈希）；`--force` 才对已存在文件覆盖。
  4. 限速与幂等（决议 #14）：默认 --delay 1.0s；失败退避重试（最多 5 次）。

用法：
  # 只做「发现」：扫描全部快照，输出用到的图片清单（不联网下载/上传）
  .venv/bin/python scripts/migrate_images.py --scan --all
  .venv/bin/python scripts/migrate_images.py --scan --title "Allik Neverfar" --title "Spook"

  # 只看某标题正则能发现什么（含明细）
  .venv/bin/python scripts/migrate_images.py --title "Allik Neverfar" --report

  # 正式迁移：把已发现清单里的图片 + File: 内容搬到中文站
  .venv/bin/python scripts/migrate_images.py --title "Allik Neverfar"            # 迁移该标题用到的图
  .venv/bin/python scripts/migrate_images.py --all                               # 全快照
  .venv/bin/python scripts/migrate_images.py --titles 清单.txt                   # 或按清单
  .venv/bin/python scripts/migrate_images.py --title X --dry-run                 # 报告将上传，不实际写站
  .venv/bin/python scripts/migrate_images.py --title X --include-bare              # 把裸 x.jpg 纳入候选（仅列出待人工复核）
  .venv/bin/python scripts/migrate_images.py --title X --include-bare --confirm-bare  # 核实为真实 File 的裸候选一并迁移（慎用）

扩展名白名单：IMG_EXT（png/jpg/jpeg/webp/gif/svg/tif/tiff）。白名单外的文件仅报告、不上传。
依赖：cloudscraper（英文站）+ write.py 的 HuijiClient（中文站写）。不需额外库。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import types
import urllib.request
from pathlib import Path

import cloudscraper

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EN_SNAPSHOT = ROOT / "en_snapshot"
EN_API = "https://coppermind.net/w/api.php"

# 与 fetch_en.py 保持一致
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".tif", ".tiff")

# 中文站（灰机 Huiji）允许上传的图片扩展名。
# 原实测其 API 报 ".svg is not a permitted file type..."（仅 png/jpg/jpeg/gif/webp/ogg），
# 但 2025-10-17 用户已联系管理员开放 .svg 上传——现已加入白名单。
# 仍被拒的：.tif/.tiff。如有需要可联系管理员后加入。
ZH_ALLOWED_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg")

UPLOAD_EXT_DEFAULT_TEXT = "本文件由脚本从英文 The Coppermind Wiki 授权搬运（含 File: 页原文）。"

# 扩展名 -> MIME（下载时用其对英文站做内容协商以取得「原始格式」字节；上传中文站也用它）
EXT_MIME = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".gif": "image/gif", ".svg": "image/svg+xml",
    ".tif": "image/tiff", ".tiff": "image/tiff",
}
DEFAULT_MIME = "application/octet-stream"


class RateLimiter:
    """简单的「最小请求间隔」限速器：每次 wait() 保证距上次至少 delay 秒才放行。

    用于英文站读请求（决议 #14：礼貌爬取，避免触发反爬封禁）。并发场景下由调用方
    保证不并发命中（本脚本默认单线程串行，够用）。
    """

    def __init__(self, delay: float):
        self.delay = max(0.0, float(delay))
        self._last = 0.0

    def wait(self):
        if self.delay <= 0:
            return
        now = time.monotonic()
        gap = self._last + self.delay - now
        if gap > 0:
            time.sleep(gap)
        self._last = time.monotonic()

# ---------------------------------------------------------------------------
# 1) 发现：正则提取图片
# ---------------------------------------------------------------------------

# 图片扩展名（正则片段）
_EXT = "|".join(re.escape(e.lstrip(".")) for e in IMG_EXT)
_EXT_RE = rf"(?:{_EXT})"

# [[File:x.jpg]] / [[Image:x.jpg]] / [[file:x.jpg|width=...]] / [[File:a b c.png|right|300px]]
# 捕获文件名（可含空格/目录，不可含 ] | ），后跟可选 ……|参数]
WIKILINK_RE = re.compile(
    rf"\[\[\s*(?:file|image)\s*:\s*([^\]\|]+?\.{_EXT_RE})\b(?:\s*\|[^\]]*)?\]\]",
    re.IGNORECASE,
)

# 模板「命名参数」里的文件：|image= x.png / |logo=cover.png 等。
# 注意：仅当文件名不含空格（或文件名整体作为最后一个词）时才相对可靠——文件名含空格的
# （如 {{image|Allik Neverfar by X.jpg}} 用首位置参）正则会漏，由 meta.json 的 files 兜底。
TEMPLATE_PARAM_RE = re.compile(
    rf"(?:^|\||\n)\s*[A-Za-z0-9_ -]*\s*(?:image|logo|cover|art|file|img|pic|photo)\s*=\s*"
    rf"([^\[\]|\s{{}}]+?\.{_EXT_RE})\b",
    re.IGNORECASE,
)

# 裸写文件名（仅 --include-bare 启用）：不含空格/括号/管道，带图片扩展名。
# 注意：正则只能做「候选」——Coppermind 大量文件名含空格（如 "Allik Neverfar by X.jpg"），
# 纯正则会把这类名字切成 "L.jpg" 之类的碎片误报。因此裸写候选一律**不直接信任**，
# 交给 later 的 verify_bare_candidates() 用英文站「是否存在对应 File」来核实，碎片会被滤掉。
BARE_RE = re.compile(
    rf"(?<![\w/])[^\[\]|\s{{}}]+?\.{_EXT_RE}(?![\w])",
    re.IGNORECASE,
)


def normalize_file_name(fn: str) -> str:
    """文件名规范化：去前后空白、去可能前缀（File:/目录/）、去竖线参数后段，
    并把下划线转空格（MediaWiki 文件名里下划线≡空格，避免两个写法当成两个文件上传）。"""
    fn = fn.strip()
    fn = fn.split("|", 1)[0].strip()
    fn = re.sub(r"^[^:]+:", "", fn).strip()   # 去掉 File: / Image: 前缀
    fn = re.sub(r".*[/\\]", "", fn).strip()    # 去掉可能的最末目录段（保留纯文件名）
    fn = fn.replace("_", " ")
    fn = re.sub(r"\s+", " ", fn).strip()
    return fn


def is_local_file_name(fn: str) -> bool:
    """过滤明显不是本地 wiki 文件的候选（如外链 URL / 无扩展名）。"""
    low = fn.lower()
    if "://" in low or low.startswith("//"):
        return False
    if not os.path.splitext(fn)[1].lower():
        return False
    return True


def regex_discover(wikitext: str, include_bare: bool) -> tuple[set[str], set[str]]:
    """用正则从 wikitext 里提取图片文件名。

    返回 (确定匹配, 裸写候选)。裸写候选不能直接信任——文件名含空格时正则
    会切成碎片（见 BARE_RE 注释），需后续 verify_bare_candidates() 核实存在性。
    """
    found: set[str] = set()
    bare: set[str] = set()
    for m in WIKILINK_RE.finditer(wikitext):
        found.add(normalize_file_name(m.group(1)))
    for m in TEMPLATE_PARAM_RE.finditer(wikitext):
        found.add(normalize_file_name(m.group(1)))
    if include_bare:
        for m in BARE_RE.finditer(wikitext):
            bare.add(normalize_file_name(m.group(0)))
    found = {f for f in found if f}
    bare = {f for f in bare if f}
    return found, bare


def snapshot_titles() -> list[str]:
    """en_snapshot 下所有含 wikitext.txt 的标题（目录名）。"""
    return sorted(
        d for d in os.listdir(EN_SNAPSHOT)
        if (EN_SNAPSHOT / d / "wikitext.txt").is_file()
    )


def discover_from_snapshot(titles: list[str], include_bare: bool,
                           use_meta_files: bool = True) -> tuple[dict[str, dict], set[str]]:
    """扫描指定标题。

    返回 (确定匹配图片 {文件名: 来源信息}, 裸写候选 set)。
    来源信息：{titles:[...], via_regex:bool, via_meta:bool}
    """
    out: dict[str, dict] = {}
    bare_all: set[str] = set()
    for t in titles:
        d = EN_SNAPSHOT / t.replace("/", "_")
        wt = d / "wikitext.txt"
        if not wt.exists():
            continue
        wikitext = wt.read_text(encoding="utf-8")
        found, bare = regex_discover(wikitext, include_bare)
        bare_all |= {f for f in bare if is_local_file_name(f)}
        for f in found:
            if not is_local_file_name(f):
                continue
            entry = out.setdefault(f, {"titles": [], "via_regex": False, "via_meta": False})
            if t not in entry["titles"]:
                entry["titles"].append(t)
            entry["via_regex"] = True
        if use_meta_files:
            meta_p = d / "meta.json"
            if meta_p.exists():
                meta = json.loads(meta_p.read_text(encoding="utf-8"))
                for f0 in meta.get("files", []):
                    # 先按原始值过滤外链/无扩展名（避免 normalize 把 URL 切剩文件名后误放行），再规范化
                    if not is_local_file_name(str(f0)):
                        continue
                    f = normalize_file_name(f0)
                    if not f:
                        continue
                    entry = out.setdefault(f, {"titles": [], "via_regex": False, "via_meta": False})
                    if t not in entry["titles"]:
                        entry["titles"].append(t)
                    entry["via_meta"] = True
    return out, bare_all


def verify_bare_candidates(s, candidates: set[str], limiter: RateLimiter | None = None) -> set[str]:
    """把裸写候选拿英文站核实「是否有对应 File 页」，只保留真实存在的（滤掉正则碎片/误报）。

    批量探测（决策 #7 精神：存在性判定用 pageid != null）。走英文站只读 query。
    """
    if not candidates:
        return set()
    cands = list(candidates)
    verified: set[str] = set()
    # 一次最多查 50 个，分批
    for i in range(0, len(cands), 50):
        batch = cands[i:i + 50]
        titles = "|".join("File:" + b for b in batch)
        try:
            d = _en_api(s, {"action": "query", "titles": titles}, limiter)
        except Exception as e:
            print(f"    [warn] 裸写候选核实失败：{e}")
            continue
        pages = d.get("query", {}).get("pages", {})
        for _, p in pages.items():
            if p.get("pageid") is not None:
                # title 形如 File:xyz —— 取文件名
                t = p.get("title", "")
                if t.lower().startswith("file:"):
                    verified.add(t.split(":", 1)[1].strip())
                else:
                    verified.add(t)
    return verified


# ---------------------------------------------------------------------------
# 2) 迁移：下载（英文站）+ 上传（中文站）
# ---------------------------------------------------------------------------

def get_en_session():
    return cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "windows", "mobile": False, "desktop": True}
    )


def _en_api(s, params, limiter: RateLimiter | None = None):
    if limiter:
        limiter.wait()
    r = s.get(EN_API, params=dict(params, format="json"), timeout=60)
    r.raise_for_status()
    return r.json()


def fetch_en_file(s, filename: str, limiter: RateLimiter | None = None):
    """从英文站取一个文件的 (内容wikitext, bytes, sha1, ext)。File 不存在返回 None。"""
    title = "File:" + filename
    # 1) File: 页 wikitext（内容）
    d = _en_api(s, {
        "action": "query", "prop": "revisions", "rvprop": "content|ids",
        "rvslots": "main", "titles": title,
    }, limiter)
    pages = d.get("query", {}).get("pages", {})
    if not pages or "-1" in pages:
        print(f"    [skip] {filename}: 英文站无该 File 页")
        return None
    _, p = next(iter(pages.items()))
    content = (p.get("revisions") or [{}])[0].get("slots", {}).get("main", {}).get("*", "")
    if content is None:
        content = ""

    # 2) 图片 bytes + sha1 + url
    info = _en_api(s, {
        "action": "query", "prop": "imageinfo", "iiprop": "url|size|sha1",
        "titles": title,
    }, limiter)
    ipages = info.get("query", {}).get("pages", {})
    ii = None
    for _, p2 in ipages.items():
        ii = (p2.get("imageinfo") or [None])[0]
        if ii:
            break
    if not ii:
        print(f"    [skip] {filename}: 英文站取不到 imageinfo")
        return None
    ext = os.path.splitext(filename)[1].lower()
    url = ii.get("url")
    if not url:
        print(f"    [skip] {filename}: imageinfo 无 url")
        return None
    # 英文站 CDN 做内容协商（Accept 优先 webp 时会给 webp 转码版，而中文站引用的是
    # 原始扩展名）。这里显式带原始格式 Accept，取回与文件名扩展一致的「原始字节」。
    want = EXT_MIME.get(ext)
    headers = {}
    if want:
        headers["Accept"] = f"{want}, image/*, */*;q=0.1"
    if limiter:
        limiter.wait()
    r = s.get(url, headers=headers, timeout=60)
    r.raise_for_status()
    data = r.content
    # 记录本地字节 sha1 与英文站规范 sha1，仅作信息；幂等判等以「中文站 File 页是否存在」为准
    # （见 upload_to_zh：实测英文站内容协商取回的字节，对部分文件等于规范哈希、对部分不等于，
    # 因此不用 sha1 判等）。
    return {
        "filename": filename,
        "content": content,
        "bytes": data,
        "sha1": hashlib.sha1(data).hexdigest(),
        "en_sha1": ii.get("sha1"),  # 英文站规范哈希，仅作信息保留
        "ext": ext,
        "url": url,
    }


def _zh_file_sha1(client, title: str):
    """查询中文站某 File 的 sha1；不存在返回 None。"""
    body = client._post({
        "action": "query", "titles": title, "prop": "imageinfo",
        "iiprop": "sha1", "format": "json", "formatversion": "2",
    })
    pages = body.get("query", {}).get("pages", [])
    if not pages:
        return None
    page = pages[0]
    if page.get("missing"):
        return None
    ii = page.get("imageinfo")
    if not ii:
        return None
    return ii[0].get("sha1")


def _patch_upload(client):
    """给 HuijiClient 实例绑定 upload_raw（multipart POST）。复用它已就绪的登录/CSRF/会话。"""

    def upload_raw(self, name, data: bytes, mime: str, comment: str, text: str, overwrite: bool = True):
        import urllib.request as urlreq

        self.ensure_logged_in()
        token = self.get_token("csrf")
        boundary = "----dshImageBot" + str(os.getpid() * 17 + 3)

        params = {
            "action": "upload", "filename": name, "async": "1",
            "ignorewarnings": "1" if overwrite else "0",
            "token": token, "comment": comment, "format": "json",
        }
        if text:
            params["text"] = text

        parts: list = []
        for k, v in params.items():
            parts.append(
                (f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n'
                 f"{v}\r\n").encode("utf-8")
            )
        # multipart 的 filename 属性仅作展示，去掉命名空间前缀；真正的目标名由
        # params['filename']（如 "File:Test Img.png"）决定。
        fn = os.path.basename(name)
        fn = re.sub(r"^[^:]+:", "", fn)
        parts.append(
            (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
             f'filename="{fn}"\r\nContent-Type: {mime}\r\n\r\n').encode("utf-8")
        )
        parts.append(data)
        parts.append(b"\r\n--" + boundary.encode() + b"--\r\n")
        body_bytes = b"".join(parts)

        req = urlreq.Request(
            self.url, data=body_bytes,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": "coppermind-image-bot/0.1 (python)",
                "x-authkey": self.api_key,
            },
            method="POST",
        )
        with self._opener.open(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        if body.get("error"):
            raise RuntimeError(f"API error {body['error'].get('code')}: {body['error'].get('info')}")
        return body.get("upload", {})

    client.upload_raw = types.MethodType(upload_raw, client)


def upload_to_zh(client, file_obj: dict, force: bool, dry_run: bool, delay: float) -> str:
    """把 (bytes + File 内容) 上传到中文站。返回状态字符串（ok/skip/exists/dry/fail）。

    force=False（默认）：中文站若已有该 File 页则跳过（幂等，本脚本是唯一上传者，存在即视为已迁移）。
    force=True：忽略“已存在”，重新上传（覆盖）。注意：覆盖要求账号有 reupload 权限，
    否则 MediaWiki 仍报 fileexists-forbidden（权限门，非参数问题），脚本会给出明确提示。
    """
    title = "File:" + file_obj["filename"]
    existed = False  # 中文站是否已存在该 File 页（用于 force 覆盖后补写 File: 描述）
    if (not dry_run) and (not force):
        # 幂等：File 页已存在即跳过。不用 sha1 判等——实测英文站内容协商取回的字节
        # 对部分文件 ≠ 规范哈希，sha1 不可靠；存在性最稳。
        try:
            found = _zh_file_sha1(client, title)
            if found is not None:
                print(f"    [skip] {title}: 中文站已有该 File（sha1={found}），视为已迁移，跳过（用 --force 才覆盖）")
                return "skip"
        except Exception as e:
            print(f"    [warn] 查询中文站 {title} 失败：{e}（继续尝试上传）")
    elif force and not dry_run:
        try:
            found = _zh_file_sha1(client, title)
            if found is not None:
                existed = True
                print(f"    [force] {title}: 中文站已有该 File（sha1={found}），将尝试覆盖上传（需账号 reupload 权限）")
            else:
                print(f"    [force] {title}: 中文站无该 File，直接上传")
        except Exception as e:
            print(f"    [warn] 查询中文站 {title} 失败：{e}（继续尝试上传）")

    mime = EXT_MIME.get(file_obj["ext"], DEFAULT_MIME)

    # File: 页描述 = 英文站原文（含 {{art}} 授权/来源模板，保留出处）；无原文给默认占位。
    text = file_obj["content"] or UPLOAD_EXT_DEFAULT_TEXT

    if dry_run:
        print(f"    [dry] 将上传 {title}（{len(file_obj['bytes'])} bytes, ext={file_obj['ext']}）")
        return "dry"

    comment = f"bot 搬运：由英文站授权迁移图片 + File: 内容（sha1 {file_obj.get('sha1','')}）"
    # 永久性错误码：重试毫无意义，直接判定结果，不再退避轰炸 API。
    PERMANENT_ERR = ("fileexists-forbidden", "fileexists-shared-forbidden", "filename-tooshort",
                     "empty-file", "badtype", "filetype-banned", "protectedpage", "uploaddisabled",
                     "verification-error", "stashfailed")
    last_err = None
    for attempt in range(1, 6):  # 退避重试
        try:
            body = client.upload_raw(title, file_obj["bytes"], mime, comment, text, overwrite=force)
            result = body.get("result")
            if result == "Success":
                info = body.get("imageinfo") or {}
                print(f"    [ok] {title} 上传成功 sha1={info.get('sha1')}")
                # force 覆盖的是一个已存在 File 页：action=upload 只更新图片本体，
                # 不更新已存在 File 页的描述文字。这里补写 File: 页为英文站原样内容（含 {{art}}）。
                if force and existed:
                    try:
                        cedit = client.edit(title, text, "bot 搬运：覆盖图片同时补写 File: 内容为英文站原样")
                        print(f"    [ok] {title} File: 描述已补写（newrevid={cedit.get('newrevid')}）")
                    except Exception as ee:
                        print(f"    [warn] {title}: 图片已覆盖但 File: 描述补写失败：{ee}")
                return "ok"
            print(f"    [warn] {title} 上传返回 result={result} -> {body.get('warnings','')}")
            return "result:" + str(result)
        except Exception as e:
            msg = f"{e}"
            last_err = e
            if "fileexists-no-change" in msg:
                # 内容与当前版本完全一致，无需覆盖——视为已同步。
                print(f"    [ok] {title}: 上传内容与中文站当前版本完全一致（fileexists-no-change），无需覆盖")
                return "ok"
            if any(tok in msg for tok in PERMANENT_ERR):
                # 覆盖已是存在的文件时：MediaWiki 对无 reupload 权限账号报 fileexists-forbidden（权限门）。
                print(f"    [exists] {title}: 已存在同名文件，覆盖被拒（{msg[:160]}）。")
                print(f"           提示：覆写需账号有 reupload 权限，或先用 delete 删除后重传——"
                      f"当前 bot 账号（水蛭一号）无 reupload/delete 权，请管理员开这两种权限之一后重试。")
                return "exists"
            if attempt < 5:
                print(f"    [retry] {title} 第{attempt}次失败：{e}")
                time.sleep(delay * (2 ** (attempt - 1)))
    print(f"    [FAIL] {title}: {last_err}")
    return "fail"


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="从英文站迁移图片（本体 + File: 内容）到中文站")
    ap.add_argument("--title", action="append", default=[], help="扫描/迁移指定快照标题（可多次）")
    ap.add_argument("--titles", default=None, help="清单文件，每行一个标题")
    ap.add_argument("--all", action="store_true", help="扫描/迁移 en_snapshot 全部标题")
    ap.add_argument("--scan", action="store_true", help="只发现图片清单（不联网下载/上传），可配 --all")
    ap.add_argument("--report", action="store_true", help="对给定标题打印正则发现明细（不迁移）")
    ap.add_argument("--include-bare", action="store_true", help="把裸写 x.jpg 也纳入候选（默认关；碎片需再核实）")
    ap.add_argument("--confirm-bare", action="store_true",
                    help="允许把核实为英文站真实 File 的裸写候选自动迁移（默认只列出待人工确认，不迁移）")
    ap.add_argument("--no-meta-files", action="store_true", help="不合并 meta.json 里的 files（只信正则）")
    ap.add_argument("--dry-run", action="store_true", help="只报告将上传，不实际写中文站")
    ap.add_argument("--force", action="store_true",
                    help="即使中文站已存在同名 File 也重新上传（覆盖；需账号 reupload/delete 权，否则报 fileexists-forbidden）")
    ap.add_argument("--status-file", default=None,
                    help="把每个文件的迁移结果（ok/skip/exists/fail）逐条追加写入该文件（JSONL），"
                         "并写最终汇总。用于后台长任务/会话断开后由后续 AI 接手查看进度。")
    ap.add_argument("--delay", type=float, default=1.0, help="中文站写入/下载间停顿秒数（决议#14，默认1.0）")
    ap.add_argument("--en-delay", type=float, default=1.0, help="英文站读请求间隔秒数（默认1.0，防反爬）")
    ap.add_argument("--env", default=None, help=".env 路径（默认向上找）")
    args = ap.parse_args()

    titles = list(args.title)
    if args.titles:
        p = Path(args.titles)
        if not p.exists():
            raise SystemExit(f"清单文件不存在：{p}")
        for line in p.read_text(encoding="utf-8").splitlines():
            t = line.strip()
            if t and not t.startswith("#"):
                titles.append(t)
    if args.all:
        titles += snapshot_titles()
    seen = set()
    titles = [t for t in titles if not (t in seen or seen.add(t))]
    if not titles:
        raise SystemExit("未指定任何标题。用 --title / --titles / --all 之一。")

    # ---- 发现 ----
    print(f"[发现] 扫描 {len(titles)} 个标题...")
    discovered, bare_all = discover_from_snapshot(
        titles, args.include_bare, use_meta_files=not args.no_meta_files)

    migrateable = {}      # 可迁移（英文站有、中文站也允许上传）
    unsupported = {}      # 已发现但在中文站不能上传（如 .svg/.tif/.tiff——灰机不允许）
    others = {}           # 压根不是图片扩展名
    for fn, info in discovered.items():
        ext = os.path.splitext(fn)[1].lower()
        if ext in IMG_EXT:
            if ext in ZH_ALLOWED_EXT:
                migrateable[fn] = info
            else:
                unsupported[fn] = info
        else:
            others[fn] = info

    print(f"[发现] 图片（可上传）{len(migrateable)} 个，中文站不支持上传（如 .svg/.tif）{len(unsupported)} 个，"
          f"非图片扩展名 {len(others)} 个"
          + (f"，裸写候选 {len(bare_all)} 个（待核实）" if args.include_bare else "") + "。")
    for fn, info in sorted(migrateable.items()):
        via = []
        if info["via_regex"]:
            via.append("regex")
        if info["via_meta"]:
            via.append("meta")
        print(f"  - {fn}  (来源:{'+'.join(via)}, 页数:{len(info['titles'])})")
    for fn in sorted(unsupported):
        print(f"  - (中文站不支持上传) {fn}")
    for fn in sorted(others):
        print(f"  - (非图片扩展名) {fn}")

    if args.scan or args.report:
        if args.report:
            for t in titles:
                d = EN_SNAPSHOT / t.replace("/", "_")
                wt = d / "wikitext.txt"
                if not wt.exists():
                    continue
                txt = wt.read_text(encoding="utf-8")
                print(f"\n== {t} ==")
                print(f"    匹配 [[File:/[[Image:]] : {[m.group(1).strip() for m in WIKILINK_RE.finditer(txt)]}")
                print(f"    匹配模板命名参数: {[m.group(1).strip() for m in TEMPLATE_PARAM_RE.finditer(txt)]}")
                if args.include_bare:
                    print(f"    裸写候选: {sorted(bare_all)}")
        print("\n[发现] 完成。未执行任何下载/上传（--scan/--report）。")
        return 0

    # ---- 迁移 ----
    # 若请求了裸写候选，先在英文站核实存在性（碎片/误报在此滤掉）。
    # 默认：核实通过的文件仅「列出待人工确认」（--include-bare 的证据显示：即使是真实存在的
    # File——如无关的 L.jpg——也可能被碎片误命中），只有显式 --confirm-bare 才自动并入迁移。
    en = get_en_session()
    limiter = RateLimiter(args.en_delay)
    if args.include_bare and bare_all:
        print(f"[核实] 对 {len(bare_all)} 个裸写候选向英文站确认是否存在对应 File ...")
        verified = verify_bare_candidates(en, bare_all, limiter)
        dropped = bare_all - verified
        for fn in sorted(dropped):
            print(f"  - (滤掉，英文站无此 File) {fn}")
        if verified:
            for fn in sorted(verified):
                flag = "" if args.confirm_bare else "（未加 --confirm-bare，仅列出，不自动迁移）"
                print(f"  - (英文站确有此 File，但来源是裸写候选，请人工复核) {fn} {flag}")
            if not args.confirm_bare:
                print("[提示] 裸写候选可被『文件名含空格』的碎片误命中（例：'...Laurys L.jpg' 会切出 'L.jpg'，"
                      "且英文站恰有无关的 File:L.jpg）。请人工逐一核对上面的清单；确认无误后加 --confirm-bare 再迁移。")
            else:
                print("[确认] 已加 --confirm-bare，将把上述裸写候选一并迁移。")
                for fn in sorted(verified):
                    if fn not in migrateable:
                        migrateable[fn] = {"titles": [], "via_regex": True, "via_meta": False}

    if not migrateable:
        raise SystemExit("没有可迁移的图片，结束。")

    print(f"\n[迁移] 将通过英文站下载 {len(migrateable)} 个图片并上传到中文站"
          f"（en-delay={args.en_delay}s, delay={args.delay}s）"
          + ("（dry-run，不写站）" if args.dry_run else ""))

    sys.path.insert(0, str(HERE))
    import write as W
    env = W.load_env(Path(args.env) if args.env else None)
    client = W.HuijiClient(W.resolve_api_url(env), env.get("HUIJI_API_KEY", ""),
                           env.get("HUIJI_BOT_USER", ""), env.get("HUIJI_BOT_PASS", ""))
    if not args.dry_run:
        client.ensure_logged_in()
    _patch_upload(client)

    status = {"ok": 0, "skip": 0, "exists": 0, "dry": 0, "fail": 0}
    st_path = Path(args.status_file) if args.status_file else None
    if st_path:
        st_path.parent.mkdir(parents=True, exist_ok=True)
        meta_line = {
            "type": "start", "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "total": len(migrateable), "dry_run": args.dry_run,
        }
        with st_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(meta_line, ensure_ascii=False) + "\n")

    def _log_status(rec: dict):
        if st_path:
            rec.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%S"))
            with st_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    for i, fn in enumerate(sorted(migrateable), 1):
        print(f"\n[{i}/{len(migrateable)}] {fn}")
        try:
            fobj = fetch_en_file(en, fn, limiter)
        except Exception as e:
            print(f"    [FAIL] 下载 {fn}: {e}")
            status["fail"] += 1
            _log_status({"type": "file", "file": fn, "result": "fail", "stage": "download", "error": str(e)})
            continue
        if fobj is None:
            status["skip"] += 1
            _log_status({"type": "file", "file": fn, "result": "skip", "reason": "en-no-file"})
            continue
        st = upload_to_zh(client, fobj, force=args.force,
                          dry_run=args.dry_run, delay=args.delay)
        status[st if st in status else "fail"] = status.get(st, 0) + 1
        _log_status({"type": "file", "file": fn, "result": st if st in status else "fail",
                     "sha1": fobj.get("sha1")})
        if not args.dry_run:
            time.sleep(args.delay)

    if st_path:
        summary = {"type": "summary", "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                   "ok": status["ok"], "skip": status["skip"], "exists": status["exists"],
                   "dry": status["dry"], "fail": status["fail"]}
        with st_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(summary, ensure_ascii=False) + "\n")
        print(f"[状态] 进度已写入 {st_path}（最终 {summary}）")

    print(f"\n[迁移] 结束：ok={status['ok']} skip={status['skip']} "
          f"exists={status['exists']} dry={status['dry']} fail={status['fail']}")
    return 1 if status["fail"] else 0


if __name__ == "__main__":
    sys.exit(main())
