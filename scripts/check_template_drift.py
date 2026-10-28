#!/usr/bin/env python3
"""
模板漂移巡检（决议#3 复用到模板层·方案C 本地侧）。

背景：决议#3 的 revid 去重只覆盖**页面**（{{ensync|revid}} 写在中文页尾）；模板是单向
移植的，站上没有任何地方记着「我是从英文站哪个 revid 移过来的」，英文侧模板改了无从
察觉（Template:Sidequote 的 EN 双形参数当初就是靠人工排查才偶然发现的）。

本脚本读移植账本 state/zh_template_port_rev.json，逐条比对 state/en_index.json 里英文
模板的当前 revid，输出漂移报告：

  OK        英文侧未变
  DRIFTED   英文侧 revid 已变 → 需复核中文移植
  NO_INDEX  账本里的英文源不在索引（索引过旧）→ 需 --refresh

用法：
  .venv/bin/python scripts/check_template_drift.py            # 巡检报告
  .venv/bin/python scripts/check_template_drift.py --json     # 机读输出
  .venv/bin/python scripts/check_template_drift.py --refresh  # 先补抓英文 revid 再巡
  .venv/bin/python scripts/check_template_drift.py --synced 模板:Quote
      # 复核/重移植完成后，把该条基线更新为英文当前 revid（清零漂移）
  .venv/bin/python scripts/check_template_drift.py --marked 模板:Quote
      # 站端标记加完后，置 marked=true
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LEDGER = ROOT / "state" / "zh_template_port_rev.json"
INDEX = ROOT / "state" / "en_index.json"


def _load():
    if not LEDGER.exists():
        sys.exit(f"缺账本 {LEDGER}")
    if not INDEX.exists():
        sys.exit(f"缺索引 {INDEX}")
    return json.loads(LEDGER.read_text(encoding="utf-8")), json.loads(INDEX.read_text(encoding="utf-8"))


def _en_srcs(entry):
    s = entry.get("en_src")
    if isinstance(s, list):
        return s
    return [s]


def _revs(entry):
    r = entry.get("en_rev_synced")
    if isinstance(r, list):
        return r
    return [r]


def inspect(ledger, index):
    """逐条判定，返回 (rows, counts)。"""
    rows, counts = [], {"OK": 0, "DRIFTED": 0, "NO_INDEX": 0}
    for zh, e in ledger.items():
        if zh.startswith("_"):
            continue
        srcs, sync = _en_srcs(e), _revs(e)
        # 一 ZH 多 EN 源时按位对应；单源对单值
        pairs = list(zip(srcs, sync)) if len(srcs) == len(sync) else [(s, None) for s in srcs]
        state, detail = "OK", []
        for src, base in pairs:
            cur = index.get(src, {}).get("revid")
            if cur is None:
                state = "NO_INDEX"
                detail.append(f"{src} 索引缺")
            elif base is None or cur != base:
                state = "DRIFTED" if state != "NO_INDEX" else state
                detail.append(f"{src} {base}→{cur}")
        if state != "DRIFTED" and any(d.endswith("索引缺") for d in detail):
            state = "NO_INDEX"
        counts[state] += 1
        rows.append({"zh": zh, "state": state, "kind": e.get("kind"),
                     "marked": e.get("marked", False), "detail": "; ".join(detail)})
    return rows, counts


def refresh(ledger):
    """补抓账本里全部英文源的当前 revid（单页，走既定 fetch_en.py）。"""
    srcs = set()
    for zh, e in ledger.items():
        if not zh.startswith("_"):
            srcs.update(_en_srcs(e))
    cmd = [sys.executable, str(HERE / "fetch_en.py"), *sorted(srcs)]
    print(f"[refresh] 抓取 {len(srcs)} 个英文模板 revid …")
    subprocess.run(cmd, check=False)
    time.sleep(1.0)


def _save(ledger):
    LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="模板漂移巡检（英文 revid 基线比对）")
    ap.add_argument("--json", action="store_true", help="机读输出")
    ap.add_argument("--refresh", action="store_true", help="先补抓英文 revid 再巡检")
    ap.add_argument("--synced", metavar="ZH_TITLE", help="复核完成：基线更新为英文当前 revid")
    ap.add_argument("--marked", metavar="ZH_TITLE", help="站端标记已加：置 marked=true")
    a = ap.parse_args()

    ledger, index = _load()

    if a.synced:
        if a.synced not in ledger:
            sys.exit(f"账本无此条: {a.synced}")
        srcs = _en_srcs(ledger[a.synced])
        missing = [s for s in srcs if s not in index]
        if missing:
            sys.exit(f"英文源不在索引，先 --refresh: {missing}")
        ledger[a.synced]["en_rev_synced"] = [index[s]["revid"] for s in srcs]
        if len(ledger[a.synced]["en_rev_synced"]) == 1:
            ledger[a.synced]["en_rev_synced"] = ledger[a.synced]["en_rev_synced"][0]
        ledger[a.synced]["last_synced_ts"] = time.strftime("%Y-%m-%d")
        _save(ledger)
        print(f"[基线已更新] {a.synced} → {ledger[a.synced]['en_rev_synced']}")
        return

    if a.marked:
        if a.marked not in ledger:
            sys.exit(f"账本无此条: {a.marked}")
        ledger[a.marked]["marked"] = True
        ledger[a.marked]["marked_ts"] = time.strftime("%Y-%m-%d")
        _save(ledger)
        print(f"[标记已记] {a.marked} marked=true")
        return

    if a.refresh:
        refresh(ledger)
        ledger, index = _load()

    rows, counts = inspect(ledger, index)

    if a.json:
        print(json.dumps({"counts": counts, "rows": rows}, ensure_ascii=False, indent=1))
    else:
        print(f"模板漂移巡检  共 {sum(counts.values())} 条"
              f"  OK={counts['OK']}  DRIFTED={counts['DRIFTED']}  NO_INDEX={counts['NO_INDEX']}")
        for st, label in (("DRIFTED", "⚠ 英文侧已变，需复核中文移植"),
                          ("NO_INDEX", "✗ 索引缺英文源，先跑 --refresh")):
            bad = [r for r in rows if r["state"] == st]
            if bad:
                print(f"\n[{st}] {len(bad)} 条 — {label}")
                for r in bad:
                    print(f"  {r['zh']:34} [{r['kind']}] {r['detail']}")
        mk = [r for r in rows if r["marked"]]
        print(f"\n站端已标 marked=true: {len(mk)}/{sum(counts.values())}")
    # 有漂移/缺索引即非零退出，便于接门禁
    sys.exit(1 if (counts["DRIFTED"] or counts["NO_INDEX"]) else 0)


if __name__ == "__main__":
    main()
