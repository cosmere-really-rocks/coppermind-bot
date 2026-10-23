#!/usr/bin/env python3
"""
tests_chunk_retry.py —— 分块门禁重试（2026-10-23 用户方向：长文档按块二次采样）。

机制总览：verify 门禁输出失败行号 → batch 按产物 chunk_line_starts 映射到失败块 →
translate --redo-chunks 只对失败块重新 LLM 采样，其余块复用现有 chunk_results →
assemble/resolve 同管线重组 → 复验。数据不足（旧产物/结构漂移/无法定位行号）一律
回退整页重跑。门禁默认次数由此调大（DEFAULT_GATE_RETRY=3）。

覆盖（全部零 LLM/零写站）：
  1. parse_gate_failed_lines：第N行通用捕获（章节/半译/结构候选行/占位符/裸词）/
     [导语]→行1（导语恒 chunk0）/ 无行号问题→None（回退整页）
  2. map_lines_to_chunks：块首行归本块、前块末行归前块、越界丢弃（含末哨兵）
  3. select_gate_retry_chunks：有分块数据→块列表；旧产物缺字段→None；行号无从定位→None
  4. compute_chunk_line_starts：结构保持→行表（1 起、末哨兵、严格单调）；标题增删=结构
     漂移→None；头部段（无标题）从第 1 行起
  5. chunk_wikitext 的 seg 区间：首块 [0,1)、连续无缝覆盖全部段（大/小 max_chars 两态）
  6. verify 定位辅助：_bracket_culprit_hint（同号候选行、>5 行噪音不提示）、
     _locate_ref_line（精确/容忍空白/未命中）
  7. DEFAULT_GATE_RETRY == 3（分块化后由 1 调大——重试粒度=失败块≈整页 1/N 成本）

用法：.venv/bin/python scripts/tests_chunk_retry.py → "N/N passed"，sys.exit(main())
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


tr = _load("translate")
vr = _load("verify_translation")
BM = _load("batch")

WIKI = ("lead 导语\n== A ==\na\n== B ==\nb\n=== B1 ===\nb1\n== C ==\nc")
FINAL = ("导语\n== 甲 ==\n甲文\n== 乙 ==\n乙文\n=== 乙一 ===\n乙一文\n== 丙 ==\n丙文")


def t1_parse行号捕获():
    # 章节/半译带行号
    assert BM.parse_gate_failed_lines("[章节] 标题未译（第450行）: 'X'") == {450}
    assert BM.parse_gate_failed_lines("[半译] 正文行残留成句英文（第471行）: xx") == {471}
    # 多候选行（结构）逐个捕获
    got = BM.parse_gate_failed_lines(
        "[结构] 模板括号不配对：{{ ×107 vs }} ×108；模板候选行（行内开闭不等同号）: 第10行、第14行")
    assert got == {10, 14}, got
    # [导语] 无行号 → 行1（chunk0）
    assert BM.parse_gate_failed_lines("[导语] 导语正文仍残留英文句子") == {1}
    # 导语+其他行混合
    assert BM.parse_gate_failed_lines("[导语] …\n[半译] …（第9行）: x") == {1, 9}
    # 无任何行号（纯结构无候选提示）→ None（回退整页重跑）
    assert BM.parse_gate_failed_lines("[结构] 内链括号不配对：[[ ×32 vs ]] ×31") is None
    assert BM.parse_gate_failed_lines("") is None


def t2_行到块边界语义():
    starts = [1, 10, 25, 40]          # 3 块 + 末哨兵
    assert BM.map_lines_to_chunks(starts, {1}) == {0}
    assert BM.map_lines_to_chunks(starts, {9}) == {0}      # 前块末行→前块
    assert BM.map_lines_to_chunks(starts, {10}) == {1}     # 块首行→本块
    assert BM.map_lines_to_chunks(starts, {24}) == {1}
    assert BM.map_lines_to_chunks(starts, {25}) == {2}
    assert BM.map_lines_to_chunks(starts, {39}) == {2}
    assert BM.map_lines_to_chunks(starts, {40}) == set()   # 哨兵/越界→丢弃
    assert BM.map_lines_to_chunks(starts, {7}) == {0}      # chunk0 行1..9（导语恒此块）
    # 多行归并
    assert BM.map_lines_to_chunks(starts, {3, 26}) == {0, 2}


def t3_select三分支():
    tmp = tempfile.mkdtemp(prefix="cr_")
    try:
        snap = Path(tmp) / "en_snapshot" / "TP"
        snap.mkdir(parents=True)
        # 分支一：有数据→块列表
        (snap / "translation.json").write_text(json.dumps({
            "translation": FINAL, "chunk_results": [["x", []]],
            "chunk_line_starts": [1, 4, 10],
        }, ensure_ascii=False), encoding="utf-8")
        assert BM.select_gate_retry_chunks(snap, "[半译] …（第5行）: x") == [1]
        # 分支二：旧产物缺字段→None（整页重跑）
        (snap / "translation.json").write_text(
            json.dumps({"translation": FINAL}), encoding="utf-8")
        assert BM.select_gate_retry_chunks(snap, "[半译] …（第5行）: x") is None
        # 分支三：有字段但行号无从定位→None
        (snap / "translation.json").write_text(json.dumps({
            "translation": FINAL, "chunk_results": [["x", []]],
            "chunk_line_starts": [1, 4, 10],
        }, ensure_ascii=False), encoding="utf-8")
        assert BM.select_gate_retry_chunks(snap, "[结构] 内链括号不配对：[[ ×1 vs ]] ×0") is None
        # 分支四：产物不存在→None
        assert BM.select_gate_retry_chunks(Path(tmp) / "en_snapshot" / "Nope", "第2行") is None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def t4_行表结构保持():
    chunks, _ = tr.chunk_wikitext(WIKI, 7000)
    segs = tr.split_sections(WIKI)
    starts = tr.compute_chunk_line_starts(FINAL, chunks, segs)
    assert starts is not None, "结构保持时必须给出行表"
    assert starts[0] == 1 and starts[-1] == len(FINAL.split("\n")) + 1, starts
    assert all(a < b for a, b in zip(starts, starts[1:])), starts
    # 标题增删 = 结构漂移 → None（回退整页重跑）
    drift = FINAL.replace("== 乙一 ==", "乙一")          # 删一个标题
    assert tr.compute_chunk_line_starts(drift, chunks, segs) is None
    extra = FINAL + "\n== 丁 ==\n丁文"                   # 多一个标题
    assert tr.compute_chunk_line_starts(extra, chunks, segs) is None


def t5_段区间连续覆盖():
    # 大 max_chars：头独立成块 + 其余聚一块
    chunks, _ = tr.chunk_wikitext(WIKI, 7000)
    assert chunks[0].seg_start == 0 and chunks[0].seg_end == 1, "chunk0 必须只含头部段"
    # 小 max_chars：每段独块（含超长告警路径）——区间仍须首尾相接无缝
    chunks2, _ = tr.chunk_wikitext(WIKI, 1)
    prev_end = 0
    for c in chunks2:
        assert c.seg_start == prev_end, (c.index, c.seg_start, prev_end)
        assert c.seg_end > c.seg_start, c
        prev_end = c.seg_end
    assert prev_end == len(tr.split_sections(WIKI)), (prev_end, len(tr.split_sections(WIKI)))


def t6_验证定位辅助():
    # 括号候选行：平衡→无提示
    assert vr._bracket_culprit_hint("x[[y\nz]]w", "[[", "]]", "内链") == ""
    # 单行不闭合→恰 1 候选
    h = vr._bracket_culprit_hint("前文\na[[b\n后文", "[[", "]]", "内链")
    assert "第2行" in h, h
    # 同号净差为负（多 }）
    h2 = vr._bracket_culprit_hint("{{a}}\n}}", "{{", "}}", "模板")
    assert "第2行" in h2, h2
    # >5 候选 = 多行模板噪音 → 不提示
    noisy = "\n".join("{{x" for _ in range(6))
    assert vr._bracket_culprit_hint(noisy, "{{", "}}", "模板") == ""
    # 引用行定位：精确 / 容忍空白 / 未命中
    assert vr._locate_ref_line("a\nb\n{{book ref|mb2|42}}", "book ref:mb2|42") == 3
    assert vr._locate_ref_line("{{book ref | mb2 | 42}}", "book ref:mb2|42") == 1
    assert vr._locate_ref_line("无引用正文", "book ref:mb2|42") is None
    assert vr._locate_ref_line("x", None) is None
    # 行号组装（body 给定时）：换号 ref 在产物中 → 带产物行号
    body = "x\ny\n{{book ref|mb2|99}}"
    probs = vr._ref_mismatch_problems(["book ref:mb2|42"], ["book ref:mb2|99"], body)
    assert probs and "产物第3行" in probs[0], probs
    # 丢引用（该 ref 不在产物里）→ 前邻 ref 回退定位
    body2 = "x\n{{book ref|mb2|37}}\ny"
    probs2 = vr._ref_mismatch_problems(["book ref:mb2|37", "book ref:mb2|42"],
                                       ["book ref:mb2|37"], body2)
    assert probs2 and "产物第2行" in probs2[0], probs2
    # 无 body 不带行号（向后兼容）
    probs3 = vr._ref_mismatch_problems(["book ref:mb2|42"], ["book ref:mb2|99"])
    assert probs3 and "产物第" not in probs3[0], probs3


def t7_默认重试次数():
    assert BM.DEFAULT_GATE_RETRY == 3, BM.DEFAULT_GATE_RETRY


CASES = [
    ("parse_gate_failed_lines 行号捕获与导语归位", t1_parse行号捕获),
    ("map_lines_to_chunks 边界语义", t2_行到块边界语义),
    ("select_gate_retry_chunks 四分支", t3_select三分支),
    ("compute_chunk_line_starts 结构保持/漂移", t4_行表结构保持),
    ("chunk_wikitext 段区间连续覆盖", t5_段区间连续覆盖),
    ("verify 括号候选行与引用行定位", t6_验证定位辅助),
    ("DEFAULT_GATE_RETRY == 3", t7_默认重试次数),
]


def main() -> int:
    passed = 0
    total = len(CASES)
    for name, fn in CASES:
        try:
            fn()
            passed += 1
            print(f"  [OK] {name}")
        except AssertionError as e:
            print(f"  [FAIL] {name}: {e}")
        except Exception as e:  # noqa: BLE001 —— 测试失败也要继续跑完
            print(f"  [ERR] {name}: {type(e).__name__}: {e}")
    print(f"{passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
