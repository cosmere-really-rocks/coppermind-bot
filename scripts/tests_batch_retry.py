#!/usr/bin/env python3
"""
tests_batch_retry.py —— batch.py 门禁重试（--gate-retry，默认 3；2026-10-23 分块化：
按门禁行号只重采样失败块 translate --redo-chunks，数据不足回退整页重跑）。

覆盖语义（全部经 mock subprocess 断言，不碰 LLM/写站/磁盘翻译产物）：
  1. 门禁首败 → 自动重跑 translate → 复验过 → write:ok（重跑兑现为成功）
  2. 复验仍败 → verify:FAIL，且绝不调 write
  3. --gate-retry 0 → 首败即拒写，translate 只调 1 次（关闭语义）
  4. --stage write（不含 translate）→ 门禁败也不重跑（尊重"不白花 LLM"契约）
  5. 重跑 translate 自身失败 → translate:retry:FAIL，不再复验
  6. 首跑即过 → 状态与无此特性时代完全一致（回归保护）
  7. build_translate_cmd：首跑/重跑共用一份构造；两态 quote 与 dry-run 透传正确
  8. 有分块数据 + 门禁行号 → 重跑命令带 --redo-chunks 且块号=行号映射结果
  9. 旧产物（缺 chunk_results/chunk_line_starts）→ 回退整页重跑（无 --redo-chunks）
  10. DEFAULT_GATE_RETRY == 3（分块化后默认值）

用法：.venv/bin/python scripts/tests_batch_retry.py → "N/N passed"，sys.exit(main())
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
import tempfile
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load_batch():
    spec = importlib.util.spec_from_file_location("batch_mod", HERE / "batch.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


BM = _load_batch()


def make_args(**kw):
    d = dict(stage="translate,write", concurrency=1, max_chars=0, max_output_tokens=0,
             skip_if_same=False, force=False, no_wrap=False, summary=None, api_key=None,
             auto_quote_cn=True, no_resolve_quotes=False, write_target_prefix=None,
             dry_run=False, gate_retry=1)
    d.update(kw)
    return argparse.Namespace(**d)


def _kind(cmd: str) -> str:
    s = " ".join(str(c) for c in cmd)
    if "verify_translation.py" in s:
        return "verify"
    if "translate.py" in s:
        return "translate"
    if "write.py" in s:
        return "write"
    return "?"


def _cp(rc: int, out: str = "", err: str = ""):
    return types.SimpleNamespace(returncode=rc, stdout=out, stderr=err)


class FakeSub:
    """按脚本种类弹队列的 subprocess.run 替身；记录全部调用（kind 与完整 cmd）。"""

    def __init__(self, verify_rcs, translate_rcs, write_rcs=(0,), verify_outs=None):
        self.queues = {"verify": list(verify_rcs), "translate": list(translate_rcs),
                       "write": list(write_rcs)}
        self.verify_outs = list(verify_outs or [])   # verify stdout 队列（门禁行号解析用）
        self.calls = []
        self.cmds = []

    def run(self, cmd, capture_output=True, text=True):
        k = _kind(cmd)
        self.calls.append(k)
        self.cmds.append([str(c) for c in cmd])
        q = self.queues[k]
        rc = q.pop(0) if q else 0
        out = ""
        if k == "verify":
            out = self.verify_outs.pop(0) if self.verify_outs else ""
        elif k == "write":
            out = "[完成] 已写入\n"
        return _cp(rc, out=out)

    def count(self, k: str) -> int:
        return self.calls.count(k)

    def translate_cmds(self) -> list:
        return [c for c in self.cmds if _kind(c) == "translate"]


def _fixture(tmp: str) -> Path:
    snap = Path(tmp) / "en_snapshot" / "TestPage"
    snap.mkdir(parents=True)
    (snap / "wikitext.txt").write_text("== Section ==\ntext\n", encoding="utf-8")
    (snap / "translation.json").write_text('{"translation": "…"}', encoding="utf-8")
    return Path(tmp) / "en_snapshot"


def _run(fake, tmp, args, title="TestPage"):
    orig_sn, orig_sub = BM.EN_SNAPSHOT, BM.subprocess
    BM.EN_SNAPSHOT = _fixture(tmp)
    BM.subprocess = fake
    try:
        return BM.run_stage(args, title)
    finally:
        BM.EN_SNAPSHOT, BM.subprocess = orig_sn, orig_sub


# ---------------- 用例 ----------------

def t1_首败重跑复验过写站():
    tmp = tempfile.mkdtemp(prefix="bt_")
    try:
        fake = FakeSub(verify_rcs=[1, 0], translate_rcs=[0, 0])
        st = _run(fake, tmp, make_args(gate_retry=1))
        assert st == ["translate:ok", "translate:retry:ok", "verify:ok", "write:ok"], st
        assert fake.count("translate") == 2 and fake.count("verify") == 2, fake.calls
        assert fake.count("write") == 1, fake.calls
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def t2_复验仍败拒写():
    tmp = tempfile.mkdtemp(prefix="bt_")
    try:
        fake = FakeSub(verify_rcs=[1, 1], translate_rcs=[0, 0])
        st = _run(fake, tmp, make_args(gate_retry=1))
        assert st == ["translate:ok", "translate:retry:ok", "verify:FAIL"], st
        assert fake.count("write") == 0, fake.calls
        assert fake.count("verify") == 2, fake.calls
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def t3_零重跑即关():
    tmp = tempfile.mkdtemp(prefix="bt_")
    try:
        fake = FakeSub(verify_rcs=[1], translate_rcs=[0, 0])
        st = _run(fake, tmp, make_args(gate_retry=0))
        assert st == ["translate:ok", "verify:FAIL"], st
        assert fake.count("translate") == 1, f"关闭后不得重跑 translate：{fake.calls}"
        assert fake.count("verify") == 1 and fake.count("write") == 0, fake.calls
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def t4_只写阶段不重跑():
    tmp = tempfile.mkdtemp(prefix="bt_")
    try:
        fake = FakeSub(verify_rcs=[1], translate_rcs=[0, 0])
        st = _run(fake, tmp, make_args(stage="write", gate_retry=1))
        assert st == ["translate:skip", "verify:FAIL"], st
        assert fake.count("translate") == 0, f"stage=write 不得花 LLM：{fake.calls}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def t5_重跑translate失败():
    tmp = tempfile.mkdtemp(prefix="bt_")
    try:
        fake = FakeSub(verify_rcs=[1], translate_rcs=[0, 1])
        st = _run(fake, tmp, make_args(gate_retry=1))
        assert st == ["translate:ok", "translate:retry:FAIL"], st
        assert fake.count("verify") == 1, f"重译失败不应复验：{fake.calls}"
        assert fake.count("write") == 0, fake.calls
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def t6_首跑即过回归():
    tmp = tempfile.mkdtemp(prefix="bt_")
    try:
        fake = FakeSub(verify_rcs=[0], translate_rcs=[0])
        st = _run(fake, tmp, make_args())
        assert st == ["translate:ok", "verify:ok", "write:ok"], st
        assert fake.count("translate") == 1 and fake.count("verify") == 1, fake.calls
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def t7_命令构造两态():
    a = BM.build_translate_cmd(make_args(), "T")
    assert a[2:4] == ["--title", "T"], a
    assert "--auto-quote-cn" in a and "--no-auto-quote-cn" not in a, a
    b = BM.build_translate_cmd(make_args(auto_quote_cn=False, dry_run=True, max_chars=7), "T")
    assert "--no-auto-quote-cn" in b and "--auto-quote-cn" not in b, b
    assert "--dry-run" in b and b[b.index("--max-chars") + 1] == "7", b
    # 门禁重跑与首跑共用同一构造函数（函数即契约）：
    import inspect
    src = inspect.getsource(BM.run_stage)
    assert src.count("build_translate_cmd(") == 2, "首跑与重跑必须同源构造"


def _chunk_fixture(tmp: str, starts) -> Path:
    snap = Path(tmp) / "en_snapshot" / "TestPage"
    snap.mkdir(parents=True)
    (snap / "wikitext.txt").write_text("== Section ==\ntext\n", encoding="utf-8")
    (snap / "translation.json").write_text(json.dumps({
        "translation": "== 甲 ==\nbody",
        "chunk_results": [["== 甲 ==\nbody", []]] * (len(starts) - 1),
        "chunk_line_starts": starts,
    }, ensure_ascii=False), encoding="utf-8")
    return Path(tmp) / "en_snapshot"


def t8_分块重试带redo参数():
    tmp = tempfile.mkdtemp(prefix="bt_")
    try:
        orig_sn = BM.EN_SNAPSHOT
        BM.EN_SNAPSHOT = _chunk_fixture(tmp, [1, 4, 10])   # 2 块：行1-3 / 行4-9
        fake = FakeSub(verify_rcs=[1, 0], translate_rcs=[0, 0],
                       verify_outs=["[半译] 正文行残留成句英文（第6行）: xx…", ""])
        orig_sub = BM.subprocess
        BM.subprocess = fake
        try:
            st = BM.run_stage(make_args(gate_retry=1), "TestPage")
        finally:
            BM.subprocess, BM.EN_SNAPSHOT = orig_sub, orig_sn
        assert st == ["translate:ok", "translate:retry:ok", "verify:ok", "write:ok"], st
        tcmds = fake.translate_cmds()
        assert len(tcmds) == 2, fake.calls
        assert "--redo-chunks" in tcmds[1], tcmds[1]
        assert tcmds[1][tcmds[1].index("--redo-chunks") + 1] == "1", \
            f"第6行应映射到 chunk1：{tcmds[1]}"
        # 首跑命令不带 --redo-chunks（全量）
        assert "--redo-chunks" not in tcmds[0], tcmds[0]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def t9_旧产物回退整页重跑():
    tmp = tempfile.mkdtemp(prefix="bt_")
    try:
        fake = FakeSub(verify_rcs=[1, 0], translate_rcs=[0, 0],
                       verify_outs=["[半译] 正文行残留成句英文（第6行）: xx…", ""])
        st = _run(fake, tmp, make_args(gate_retry=1))
        assert st == ["translate:ok", "translate:retry:ok", "verify:ok", "write:ok"], st
        tcmds = fake.translate_cmds()
        assert len(tcmds) == 2 and "--redo-chunks" not in tcmds[1], \
            f"旧产物（_fixture 无分块字段）必须整页重跑：{tcmds[1]}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def t10_默认重试次数为3():
    assert BM.DEFAULT_GATE_RETRY == 3, BM.DEFAULT_GATE_RETRY


CASES = [
    ("门禁首败→自动重跑→复验过→write:ok", t1_首败重跑复验过写站),
    ("复验仍败→verify:FAIL且不写", t2_复验仍败拒写),
    ("--gate-retry 0→首败即拒写、translate只调1次", t3_零重跑即关),
    ("stage=write→门禁败也不重跑(不白花LLM)", t4_只写阶段不重跑),
    ("重跑translate失败→translate:retry:FAIL", t5_重跑translate失败),
    ("首跑即过→状态回归一致", t6_首跑即过回归),
    ("build_translate_cmd 两态与共用契约", t7_命令构造两态),
    ("有分块数据→重跑带 --redo-chunks 且块号=行映射", t8_分块重试带redo参数),
    ("旧产物缺分块字段→回退整页重跑", t9_旧产物回退整页重跑),
    ("DEFAULT_GATE_RETRY == 3", t10_默认重试次数为3),
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
