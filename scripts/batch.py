#!/usr/bin/env python3
"""
批量管道：对一批标题串联「fetch → convert+translate → write」，复用一个已逐页验证过的脚本逻辑。

策略：batch.py 是编排脚本，逐页以子进程调用已就绪的脚本（translate.py / write.py），
避免复制阶段逻辑；页与页之间可并发，单页内仍是 translate.py 自己的多块串行/并发。

用法：
  .venv/bin/python scripts/batch.py --titles 清单.txt              # 清单每行一个标题
  .venv/bin/python scripts/batch.py --title A --title B --title C   # 直接列标题
  .venv/bin/python scripts/batch.py --all                           # 跑 en_snapshot 现有全部（含 infobox 的）标题
  .venv/bin/python scripts/batch.py --titles 清单.txt --stage translate,write
  .venv/bin/python scripts/batch.py --titles 清单.txt --dry-run    # 全程预演，不写站
  .venv/bin/python scripts/batch.py --titles 清单.txt --concurrency 3

阶段：fetch（缺快照才抓）/convert+translate（translate.py）/write（write.py）。
  --stage 默认 "translate,write"；fetch 默认仅在快照缺失时补抓（除非 --fetch 强制）。
选项透传：--max-chars/--concurrency/--skip-if-same/--summary 会转发给对应脚本。
门禁重试（2026-10-23 起默认 3 次；同日分块化）：质量门禁 verify 未过时，按「门禁行号→
  失败块」映射只重采样失败块（translate --redo-chunks，其余块复用现有 chunk_results——
  长文档"第二次做对"的正确粒度）；产物缺分块数据/问题无法定位行号时回退整页重跑；
  复验过才写，仍不过记 verify:FAIL；--gate-retry 0 关闭。

退出码：0 全部成功；1 有失败（部分成功也报 1，末尾打印汇总表）。
依赖：无额外库；调用 .venv/bin/python 运行本项目脚本。
"""
from __future__ import annotations

import argparse
import bisect
import concurrent.futures
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EN_SNAPSHOT = ROOT / "en_snapshot"
PY = ROOT / ".venv" / "bin" / "python"
# 门禁重试默认次数（2026-10-23 分块化后由 1 调大）：重试粒度=失败块（约整页 1/N 成本），
# 长文档多给几次采样机会不心疼；0=关闭。
DEFAULT_GATE_RETRY = 3
INFOBOX_TYPES = ("business", "book", "character", "culture", "disease", "food", "geography",
                 "group", "item", "lifeform", "literature", "location", "magic", "metal",
                 "nation", "noble house", "settlement", "vehicle", "architecture")


def read_titles_from_file(path: str) -> list[str]:
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"清单文件不存在：{p}")
    titles = []
    for line in p.read_text(encoding="utf-8").splitlines():
        t = line.strip()
        if t and not t.startswith("#"):
            titles.append(t)
    return titles


def snapshot_titles() -> list[str]:
    """en_snapshot 下所有含 wikitext.txt 的标题（目录名）。"""
    return sorted(
        d for d in os.listdir(EN_SNAPSHOT)
        if (EN_SNAPSHOT / d / "wikitext.txt").is_file()
    )


_ZH_TITLE_GLOSSARY = None
_ZH_TITLE_ZHWIKI = None


def _resolve_zh_title(title_en: str) -> str:
    """英文标题 -> 中文页标题（惰性加载译名表；查无可靠中译名则保留英文）。"""
    global _ZH_TITLE_GLOSSARY, _ZH_TITLE_ZHWIKI
    if _ZH_TITLE_GLOSSARY is None:
        import importlib.util as _ilu
        _sp = _ilu.spec_from_file_location("tr_resolve", HERE / "translate.py")
        _tr = _ilu.module_from_spec(_sp)
        sys.modules[_sp.name] = _tr
        _sp.loader.exec_module(_tr)
        _ZH_TITLE_GLOSSARY = _tr.load_merged_glossary(
            ROOT / "dict" / "mistborn.json", ROOT / "dict" / "common.json")
        _ZH_TITLE_ZHWIKI = _tr.load_zhwiki_titles()
    ent = _ZH_TITLE_GLOSSARY.get(title_en)
    if isinstance(ent, dict):
        zh = ent.get("zh")
        if isinstance(zh, str) and zh.strip():
            return zh.strip()
    elif isinstance(ent, str) and ent.strip():
        return ent.strip()
    # 中文站既有页面标题（如 Mistborn (series) -> 迷雾之子(系列)）
    for zh, en in _ZH_TITLE_ZHWIKI.items():
        if en == title_en and zh and zh.strip():
            return zh.strip()
    return title_en


def has_infobox(title: str) -> bool:
    p = EN_SNAPSHOT / title / "wikitext.txt"
    if not p.exists():
        return False
    try:
        txt = (p.read_text(encoding="utf-8")).lower()
    except Exception:
        return False
    return any("{{" + t.lower() in txt for t in INFOBOX_TYPES)


def build_translate_cmd(args, title: str) -> list[str]:
    """构造 translate.py 子进程命令（首跑与门禁单次重跑共用一份，避免两处漂移）。"""
    translate_cmd = [str(PY), str(HERE / "translate.py"), "--title", title]
    if args.max_chars:
        translate_cmd += ["--max-chars", str(args.max_chars)]
    if args.dry_run:
        translate_cmd += ["--dry-run"]
    if args.no_wrap:
        translate_cmd += ["--no-wrap"]
    if args.api_key:
        translate_cmd += ["--api-key", args.api_key]
    if args.max_output_tokens:
        translate_cmd += ["--max-output-tokens", str(args.max_output_tokens)]
    # quote 自动替换默认开启（2026-10-21）：显式透传两态，避免依赖子进程默认值
    translate_cmd += ["--auto-quote-cn" if args.auto_quote_cn else "--no-auto-quote-cn"]
    if args.no_resolve_quotes:
        translate_cmd += ["--no-resolve-quotes"]
    return translate_cmd


_GATE_LINE_RE = re.compile(r"第(\d+)行")


def parse_gate_failed_lines(verify_stdout: str) -> set | None:
    """从门禁 verify 输出提取失败行号集合（产物终文行号）；无从定位→None→整页重跑。
    「第N行」通用捕获（章节/半译/结构候选行/占位符/裸词/干扰提示）；[导语] 问题不带
    行号 → 按 chunk0=第1行归位（导语恒在 chunk0，分块契约）。"""
    if not verify_stdout:
        return None
    lines = {int(x) for x in _GATE_LINE_RE.findall(verify_stdout)}
    if "[导语]" in verify_stdout:
        lines.add(1)
    return lines or None


def map_lines_to_chunks(chunk_line_starts: list, lines: set) -> set:
    """门禁失败行 → 块号集合（0基）。chunk_line_starts=[块0起始行,…,总行数+1] 含末哨兵
    （translate.compute_chunk_line_starts 同源），二分定位。"""
    n = len(chunk_line_starts) - 1
    out = set()
    for ln in lines:
        k = bisect.bisect_right(chunk_line_starts, ln) - 1
        if 0 <= k < n:
            out.add(k)
    return out


def select_gate_retry_chunks(snapshot_dir: Path, verify_stdout: str) -> list | None:
    """本轮重试应重采样哪些块（0基升序列表）；None=回退整页重跑（旧产物无
    chunk_results/chunk_line_starts、结构漂移缺行表、或问题无法定位行号）。"""
    try:
        data = json.loads((snapshot_dir / "translation.json").read_text(encoding="utf-8"))
    except Exception:
        return None
    if not data.get("chunk_line_starts") or not data.get("chunk_results"):
        return None
    lines = parse_gate_failed_lines(verify_stdout)
    if not lines:
        return None
    chunks = map_lines_to_chunks(data["chunk_line_starts"], lines)
    return sorted(chunks) or None


def run_stage(args, title: str) -> list[str]:
    """执行一个标题的全部阶段；返回该页的 [阶段...] 状态串。"""
    status = []
    snapshot_dir = EN_SNAPSHOT / title.replace("/", "_")

    # ---- fetch（如需）----
    if "fetch" in args.stage and not (snapshot_dir / "wikitext.txt").exists():
        st = subprocess.run([str(PY), str(HERE / "fetch_en.py"), title],
                            capture_output=True, text=True)
        if st.returncode != 0:
            status.append("fetch:FAIL")
            return status
        status.append("fetch:ok")
    elif not (snapshot_dir / "wikitext.txt").exists():
        # 快照缺失但没开 fetch 阶段
        status.append("skipped:no-snapshot")
        return status

    # ---- convert + translate（受 --stage 门控：--stage write 时跳过，不再白花 LLM） ----
    if "translate" not in args.stage and "convert" not in args.stage:
        # --stage write：跳过翻译、直接门禁+写回（2026-10-20 修：此前门控缺失会白翻一轮 LLM）
        if (snapshot_dir / "translation.json").exists():
            status.append("translate:skip")
        else:
            status.append("translate:no-input")
            return status
    else:
        translate_cmd = build_translate_cmd(args, title)
        tr = subprocess.run(translate_cmd, capture_output=True, text=True)
        # 子进程 stderr 记录进度，只保留足够诊断
        if tr.returncode != 0:
            status.append("translate:FAIL")
            sys.stderr.write(f"[{title}] translate 失败：{(tr.stderr or '')[-600:]}\n")
            return status
        status.append("translate:dry" if args.dry_run else "translate:ok")

    # ---- 自动质量门禁（零 review 机制保证：写回前自动核对，不过则拒绝写回）----
    # 覆盖：引用编号与英文源一致（防 LLM 幻觉）、占位符无残留、导语无英文残留、
    # 无裸词/半译残留、{{en}} 不错位。全部通过才允许 write；失败记 verify:FAIL 并跳过写回。
    # 门禁单次重跑（2026-10-23 用户定为默认）：门禁本身是确定性的，重跑的对象是
    # translate——换一次 LLM 采样后复验，仍不过才拒写。仅本批含 translate/convert 阶段时
    # 生效（尊重 --stage write "不白花 LLM"的契约）；--gate-retry N 可调，0 关闭。
    if "write" in args.stage and not args.dry_run:
        gate_cmd = [str(PY), str(HERE / "verify_translation.py"), "--title", title]
        can_retry = ("translate" in args.stage or "convert" in args.stage)
        attempts_left = max(0, args.gate_retry) if can_retry else 0
        while True:
            gc = subprocess.run(gate_cmd, capture_output=True, text=True)
            if gc.returncode == 0:
                status.append("verify:ok")
                break
            if attempts_left <= 0:
                status.append("verify:FAIL")
                sys.stderr.write(f"[{title}] 质量门禁未通过（拒绝写回）：\n{(gc.stdout or '')[-1200:]}"
                                 f"{(gc.stderr or '')[-1200:]}\n")
                return status
            attempts_left -= 1
            # 分块重试（2026-10-23）：门禁行号→失败块→只重采样那些块（其余复用
            # 现有 chunk_results）；数据不足/行号无法定位 → 回退整页重跑。
            redo = select_gate_retry_chunks(snapshot_dir, gc.stdout or "")
            cmd2 = build_translate_cmd(args, title)
            if redo is not None:
                cmd2 = cmd2 + ["--redo-chunks", ",".join(str(i) for i in redo)]
                sys.stderr.write(f"[{title}] 质量门禁未过，分块重采样 {redo} 后复验…\n")
            else:
                sys.stderr.write(f"[{title}] 质量门禁未过，整页重跑 translate 后复验…\n")
            tr2 = subprocess.run(cmd2, capture_output=True, text=True)
            if tr2.returncode != 0:
                status.append("translate:retry:FAIL")
                sys.stderr.write(f"[{title}] 重跑 translate 失败：{(tr2.stderr or '')[-600:]}\n")
                return status
            status.append("translate:retry:ok")

    # ---- write ----
    if "write" in args.stage:
        # dry-run 时 translate 未产出/未更新 translation.json：若本无该文件，则 write 无从 dry-run，
        # 记 write:no-input（信息，非失败），否则照常 dry-run write。
        tj = snapshot_dir / "translation.json"
        if args.dry_run and not tj.exists():
            status.append("write:no-input")
            return status
        write_cmd = [str(PY), str(HERE / "write.py"), "--title", title]
        if args.write_target_prefix:
            # 非破坏性验证：写到计划前缀下的临时页（如 "BOT测试:Allik Neverfar"）。
            # 目标标题经 resolve_zh_title 解析为中文（Ghostbloods->鬼血会）；查无可靠
            # 中译名的标题（Red (Scadrial)/Demoux (city)/Tyrian Sea 等）保留英文，
            # 与正文 keep_en 铁律一致，避免自造译名。
            target_title = args.write_target_prefix + _resolve_zh_title(title)
            write_cmd += ["--target", target_title]
        if args.skip_if_same:
            write_cmd += ["--skip-if-same"]
        if args.force:
            write_cmd += ["--force"]
        if args.dry_run:
            write_cmd += ["--dry-run"]
        if args.summary:
            write_cmd += ["--summary", args.summary]
        wr = subprocess.run(write_cmd, capture_output=True, text=True)
        if wr.returncode != 0:
            status.append("write:FAIL")
            sys.stderr.write(f"[{title}] write 失败：{(wr.stderr or '')[-600:]}\n")
            return status
        out = (wr.stdout or "").strip()
        if "跳过" in out or "已含 ensync" in out:
            status.append("write:skipped")
        elif "dry-run" in out.lower():
            status.append("write:dry")
        else:
            status.append("write:ok")
    return status


def main():
    ap = argparse.ArgumentParser(description="批量 fetch→convert+translate→write 管道")
    ap.add_argument("--titles", default=None, help="清单文件，每行一个标题")
    ap.add_argument("--title", action="append", default=[], help="单个标题（可多次）")
    ap.add_argument("--all", action="store_true", help="跑 en_snapshot 现有全部含 infobox 的标题")
    ap.add_argument("--stage", default="translate,write", help="逗号分隔阶段：fetch,translate,write（默认 translate,write）")
    ap.add_argument("--concurrency", type=int, default=1, help="并发标题数（默认 1）")
    ap.add_argument("--max-chars", type=int, default=0, help="透传给 translate.py 的分块上限")
    ap.add_argument("--max-output-tokens", type=int, default=0, help="透传单块最大输出 token")
    ap.add_argument("--skip-if-same", action="store_true", help="透传：目标页 ensync 相同则跳过写")
    ap.add_argument("--force", action="store_true", help="透传：即使已同步也强制写")
    ap.add_argument("--no-wrap", action="store_true", help="透传：不插页面包装")
    ap.add_argument("--summary", default=None, help="透传自定义写站摘要")
    ap.add_argument("--api-key", default=None, help="透传 LLM api key")
    ap.add_argument("--auto-quote-cn", action=argparse.BooleanOptionalAction, default=True,
                    help="透传 translate quote 书证采证自动替换（默认开；--no-auto-quote-cn 退回半自动 review）")
    ap.add_argument("--no-resolve-quotes", action="store_true",
                    help="透传 translate 关闭原文块书证采证（回到纯英文占位符）")
    ap.add_argument("--write-target-prefix", default=None, help="写站目标页前缀（如 'BOT测试:'，用于非破坏性验证）")
    ap.add_argument("--dry-run", action="store_true", help="全程预演（translate/write 均 dry-run，不真正调 LLM/写站）")
    ap.add_argument("--gate-retry", type=int, default=DEFAULT_GATE_RETRY,
                    help=f"质量门禁未过时自动重跑 translate 并复验的次数"
                         f"（默认 {DEFAULT_GATE_RETRY}，2026-10-23 分块重试后由 1 调大；0=关闭）。"
                         "有分块数据时按门禁行号只重采样失败块，否则整页重跑；"
                         "仅本批含 translate/convert 阶段时生效")
    args = ap.parse_args()

    # 收集标题
    titles = []
    if args.titles:
        titles += read_titles_from_file(args.titles)
    titles += args.title
    if args.all:
        titles += [t for t in snapshot_titles() if has_infobox(t)]
    # 去重保序
    seen = set()
    titles = [t for t in titles if not (t in seen or seen.add(t))]
    if not titles:
        raise SystemExit("未指定任何标题。用 --titles/--title/--all 之一。")

    stages = [s.strip() for s in args.stage.split(",") if s.strip()]
    print(f"[批量] {len(titles)} 个标题，阶段={stages}，并发={args.concurrency}"
          + ("（dry-run）" if args.dry_run else "") + "\n")

    results = []
    if args.concurrency <= 1:
        for t in titles:
            results.append((t, run_stage(args, t)))
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as ex:
            futs = {ex.submit(run_stage, args, t): t for t in titles}
            for f in concurrent.futures.as_completed(futs):
                t = futs[f]
                results.append((t, f.result()))
    results.sort(key=lambda r: titles.index(r[0]) if r[0] in titles else 0)

    # 汇总
    print("\n========== 汇总 ==========")
    ok = fail = 0
    for t, st in results:
        joined = " ".join(st)
        print(f"  {t}: {joined}")
        if "FAIL" in joined:
            fail += 1
        elif "no-snapshot" in joined or "no-input" in joined:
            # 信息态：缺快照 / dry-run 下无 translation.json（非失败，标记待办）
            print(f"       ^ 待办/信息（不计数失败）")
            ok += 1
        elif "write:ok" in joined or "write:dry" in joined or "write:skipped" in joined:
            ok += 1
        else:
            # translate 成功但 write 未真正 ok（如 dry-run）——dry-run 按成功算
            if args.dry_run:
                ok += 1
            else:
                fail += 1
    print(f"\n成功 {ok}，失败 {fail}。")
    return 1 if fail else 0


if __name__ == "__main__":
    main()
