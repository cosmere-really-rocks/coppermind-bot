#!/usr/bin/env python3
"""把英文站超中文站 10MB 上限的大图压缩后上传中文站。

要点：
- **File: 标题不变**（如 `File:X.png`），只替换文件内容字节（转 jpg/webp）。
- 无透明通道优先 JPEG（兼容性最好）；有透明通道用 WebP（支持 alpha）。
  都按质量阶梯 + 必要时等比缩尺寸，直到 < --max-bytes（默认 9.5MB，中文站上限 10MB）。
- 下载 / 限速 / 上传复用 migrate_images.py 的成熟逻辑（EN 原始字节 Accept、
  中文站幂等 skip、退避重试、File: 页描述=英文站原文）。
- 幂等：中文站已有该 File 页 → skip（除非 --force）。--dry-run 只压缩报告不上传。

用法：
  .venv/bin/python scripts/shrink_oversized_images.py --all            # 处理内置 12 张清单
  .venv/bin/python scripts/shrink_oversized_images.py --file X.png     # 单张（可多次）
  .venv/bin/python scripts/shrink_oversized_images.py --all --dry-run  # 只看压缩效果
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import migrate_images as MI  # noqa: E402
import write as W  # noqa: E402
from PIL import Image  # noqa: E402

# 中文站 maxuploadsize=10485760(10MB)；默认留 0.5MB 余量
DEFAULT_MAX_BYTES = int(9.5 * 1048576)

BIG_FILES = [
    "Adolin fighting Terushal.png",
    "Aethers by cosmiciaria.png",
    "Angerspren by BrightWatcher.png",
    "Chasmfiend Fight by Ellie L..png",
    "Design and Yumi by Gar leyva.png",
    "Dynamic Crew by Starling Illu.png",
    "Harmony and Discord by Ashley Coad.png",
    "Passionspren by BrightWatcher.png",
    "SLWG Roshar by Bruce Brenneise.png",
    "Sigzil and Auxiliary by madxmellonart.jpg",
    "Taln Neirr.png",
    "Yumi Returns by botanicaxu.jpg",
]

QUALITY_LADDER = [90, 85, 80, 75, 70, 65]
SCALE_LADDER = [1.0, 0.85, 0.75, 0.6, 0.5]


def _has_alpha(img: Image.Image) -> bool:
    if img.mode in ("RGBA", "LA", "PA"):
        return True
    return img.mode == "P" and "transparency" in img.info


def _encode(img: Image.Image, fmt: str, quality: int) -> bytes:
    buf = io.BytesIO()
    if fmt == "JPEG":
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
    elif fmt == "WEBP":
        img.save(buf, "WEBP", quality=quality, method=4)
    else:
        raise ValueError(fmt)
    return buf.getvalue()


def compress(data: bytes, max_bytes: int, ext: str) -> tuple[bytes, str, tuple[int, int], tuple[int, int]]:
    """返回 (新字节, 实际格式, 原尺寸, 新尺寸)。保证 len < max_bytes（极端情况取最小者）。

    中文站服务端强制「真实格式 = 扩展名」（verification-error），所以策略按扩展名走：
    - `.png` → **保持 PNG**：只做无损缩尺寸（LANCZOS），色彩无损、不转码不量化。
    - `.jpg/.jpeg` → JPEG 质量阶梯（质量优先于尺寸，逐档降 q，再缩尺寸）。
    """
    img = Image.open(io.BytesIO(data))
    img.load()
    orig_size = img.size

    if ext.lower() in (".png", ""):
        best: tuple[bytes, str] | None = None
        for scale in SCALE_LADDER:
            cur = img if scale == 1.0 else img.resize(
                (max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.LANCZOS)
            buf = io.BytesIO()
            cur.save(buf, "PNG", optimize=True)
            out = buf.getvalue()
            if best is None or len(out) < len(best[0]):
                best = (out, "PNG", cur.size)
            if len(out) < max_bytes:
                return out, "PNG", orig_size, cur.size
        return best[0], "PNG", orig_size, orig_size

    # jpg：质量阶梯，必要时缩尺寸（无 alpha 问题）
    alpha = _has_alpha(img)
    formats = ["WEBP"] if alpha else ["JPEG"]
    best2: tuple[bytes, str] | None = None
    for scale in SCALE_LADDER:
        cur = img if scale == 1.0 else img.resize(
            (max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.LANCZOS)
        for fmt in formats:
            for q in QUALITY_LADDER:
                try:
                    out = _encode(cur, fmt, q)
                except Exception:
                    continue
                if best2 is None or len(out) < len(best2[0]):
                    best2 = (out, fmt, cur.size)
                if len(out) < max_bytes:
                    return out, fmt, orig_size, cur.size
    assert best2 is not None
    return best2[0], best2[1], orig_size, img.size


def process(filename: str, client, en_session, limiter, *, max_bytes: int,
            dry_run: bool, force: bool, delay: float) -> str:
    title = "File:" + filename
    print(f"\n[处理] {title}")

    # 幂等：中文站已存在 -> skip（不覆盖），与 migrate_images 一致
    if not dry_run and not force:
        found = MI._zh_file_sha1(client, title)
        if found is not None:
            print(f"    [skip] 中文站已有该 File（sha1={found}），不覆盖")
            return "skip"

    fo = MI.fetch_en_file(en_session, filename, limiter)
    if fo is None:
        print("    [fail] 英文站取不到该文件")
        return "fail"

    orig_len = len(fo["bytes"])
    if orig_len < max_bytes and not dry_run and force is False:
        # 不该进本清单的情况：本就未超限，原样传
        new_bytes, fmt, o, n = fo["bytes"], fo["ext"].lstrip(".").upper(), (0, 0), (0, 0)
    else:
        new_bytes, fmt, o, n = compress(fo["bytes"], max_bytes, fo["ext"])
    ratio = len(new_bytes) / orig_len if orig_len else 0

    print(f"    压缩: {orig_len/1048576:.1f}MB {o[0]}x{o[1]} -> "
          f"{len(new_bytes)/1048576:.2f}MB {n[0]}x{n[1]} [{fmt}] ({ratio:.0%})")
    if len(new_bytes) >= 10 * 1048576:
        print("    [fail] 压缩后仍超 10MB，放弃")
        return "fail"

    if dry_run:
        print("    [dry] 不上传")
        return "dry"

    ext_map = {"JPEG": ".jpg", "WEBP": ".webp", "PNG": ".png"}
    mime_map = {"JPEG": "image/jpeg", "WEBP": "image/webp", "PNG": "image/png"}
    real_ext = ext_map.get(fmt, fo["ext"])
    real_mime = mime_map.get(fmt.split(".")[0], MI.EXT_MIME.get(fo["ext"], MI.DEFAULT_MIME))

    # 标题（filename 参数）保持原样；multipart 展示名同样原样，只有字节/mime 是新格式。
    # File: 页描述 = 英文站原文（与 migrate_images 相同）。
    comment = (f"bot 搬运：压缩至 {len(new_bytes)} bytes（{orig_len} bytes，{fmt}）"
               f"以适配中文站 10MB 上限；标题不变")
    text = fo["content"] or MI.UPLOAD_EXT_DEFAULT_TEXT
    # overwrite=True -> ignorewarnings=1（新文件不存在，仅用于放行扩展名/内容不符的 filetype-mismatch 警告）
    last_err = None
    for attempt in range(1, 4):
        try:
            body = client.upload_raw(title, new_bytes, real_mime, comment, text, overwrite=True)
            result = body.get("result")
            if result == "Success":
                info = body.get("imageinfo") or {}
                print(f"    [ok] 上传成功 sha1={info.get('sha1')} size={info.get('size')}")
                MI._log_status_note(client, title) if hasattr(MI, "_log_status_note") else None
                return "ok"
            print(f"    [warn] 上传 result={result} warnings={body.get('warnings')}")
            return "result:" + str(result)
        except Exception as e:
            last_err = e
            if any(t in str(e) for t in ("filetype-banned", "verification-error", "badtype",
                                         "filename-tooshort", "empty-file", "stashfailed")):
                print(f"    [fail] 永久错误: {e}")
                return "fail"
            if attempt < 3:
                print(f"    [retry] 第{attempt}次失败: {e}")
                time.sleep(delay * (2 ** (attempt - 1)))
    print(f"    [fail] {last_err}")
    return "fail"


def main() -> int:
    ap = argparse.ArgumentParser(description="压缩超 10MB 大图并上传中文站（File: 标题不变）")
    ap.add_argument("--file", action="append", default=[], help="指定文件名（可多次）")
    ap.add_argument("--all", action="store_true", help=f"处理内置清单（{len(BIG_FILES)} 张）")
    ap.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES,
                    help="压缩目标上限字节（默认 9.5MB，中文站硬上限 10MB）")
    ap.add_argument("--dry-run", action="store_true", help="只压缩打印，不上传")
    ap.add_argument("--force", action="store_true", help="覆盖中文站已存在文件")
    ap.add_argument("--delay", type=float, default=1.0, help="中文站写入间隔秒数")
    ap.add_argument("--en-delay", type=float, default=1.2, help="英文站读请求间隔秒数")
    ap.add_argument("--env", default=None)
    ap.add_argument("--status-file", default=None, help="结果逐条追加 JSONL")
    args = ap.parse_args()

    files = list(args.file)
    if args.all:
        files += BIG_FILES
    if not files:
        ap.error("需要 --file 或 --all")

    env = W.load_env(Path(args.env) if args.env else None)
    client = W.HuijiClient(W.resolve_api_url(env), env.get("HUIJI_API_KEY", ""),
                           env.get("HUIJI_BOT_USER", ""), env.get("HUIJI_BOT_PASS", ""))
    client.ensure_logged_in()
    MI._patch_upload(client)

    en_session = MI.get_en_session()
    limiter = MI.RateLimiter(args.en_delay)

    status = {"ok": 0, "skip": 0, "fail": 0, "dry": 0}
    for i, fn in enumerate(files, 1):
        print(f"\n=== [{i}/{len(files)}] {fn}")
        try:
            r = process(fn, client, en_session, limiter, max_bytes=args.max_bytes,
                        dry_run=args.dry_run, force=args.force, delay=args.delay)
        except Exception as e:
            print(f"    [fail] 未捕获异常: {e}")
            r = "fail"
        key = r if r in status else "fail"
        status[key] += 1
        if args.status_file:
            with open(args.status_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({"type": "file", "file": fn, "result": r,
                                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}, ensure_ascii=False) + "\n")
        if r == "ok":
            time.sleep(args.delay)

    print(f"\n[结束] {status}")
    return 0 if status["fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
