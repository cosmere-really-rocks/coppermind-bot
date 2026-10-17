#!/usr/bin/env python3
"""
按清单递归爬取 Category:Mistborn 缺失页面（复用 fetch_en.fetch_one，与 Era_2 同法）。
- 输入：state/mistborn_need_fetch.json（{"root":..., "need":[标题...]}）
- 限速：请求间隔 --delay 秒（默认 2.0，决议#14 慢速防封）
- 断点续跑：每 --save-every 页保存一次索引；重跑自动跳过已抓（fetch_one 内 revid 判重）
- 日志：写 --log 文件（默认 state/mistborn_crawl.log），并实时 flush
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"
sys.path.insert(0, str(ROOT / "scripts"))
import fetch_en as F


def log(msg, fh=None):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    if fh:
        fh.write(line + "\n")
        fh.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=float, default=2.0, help="请求间隔秒数（决议#14 慢速防封）")
    ap.add_argument("--save-every", type=int, default=25, help="每抓 N 页保存一次索引")
    ap.add_argument("--list-file", default=str(STATE / "mistborn_need_fetch.json"))
    ap.add_argument("--log", default=str(STATE / "mistborn_crawl.log"))
    args = ap.parse_args()

    lst = json.loads(Path(args.list_file).read_text(encoding="utf-8"))
    titles = lst["need"]
    root = lst.get("root", "Category:Mistborn")
    print(f"== 目标清单 {root}: {len(titles)} 页（delay={args.delay}s）==")

    fh = open(args.log, "a", encoding="utf-8")
    s = F.get_session()
    idx = F.load_index()

    stats = {"fetched": 0, "skip": 0, "missing": 0, "error": 0}
    t0 = time.time()
    for i, title in enumerate(titles, 1):
        # 逐页：先查缓存，已在索引且快照齐全则跳过（不请求）
        ct = F.canonical_title(title)
        e = idx.get(ct, {})
        snap_ok = (F.EN_SNAPSHOT / ct.replace("/", "_") / "wikitext.txt").exists()
        if e.get("has_wikitext") and snap_ok:
            stats["skip"] += 1
            log(f"[{i}/{len(titles)}] {title} -> skip(已有)", fh)
            continue
        log(f"[{i}/{len(titles)}] {title} ...", fh)
        try:
            r = F.fetch_one(s, idx, title, force=False)
            stats[r if r in stats else "fetched"] += 1
            log(f"   -> {r}", fh)
        except Exception as exc:
            stats["error"] += 1
            log(f"   [错误] {title}: {exc!r}", fh)
            F.save_index(idx)  # 出错也存，避免丢失进度
        # 限速（决议#14 慢速防封）
        time.sleep(args.delay)
        if i % args.save_every == 0:
            F.save_index(idx)

    F.save_index(idx)
    fh.close()
    elapsed = time.time() - t0
    print(f"完成！耗时 {elapsed:.0f}s ({elapsed/60:.1f}min) 统计: {stats}")
    print(f"（已跳过/未抓的后续续跑）")


if __name__ == "__main__":
    main()
