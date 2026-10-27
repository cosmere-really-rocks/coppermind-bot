#!/usr/bin/env python3
"""回填未翻译的 {{Image|...}} 图片说明（2026-10-27 · 与提示词规则 2.6、门禁
[图片说明] 同源口径）。

只改说明文字本身：页面其余字节一律不碰——写回前做**掩码不变量校验**（把新旧
两侧的说明参数都替换成占位后全文必须逐字节相同），不满足即中止该页；另有结构
校验（内链/模板/标签 token 列表必须与原文完全一致、必须含中文），失败重试 1 次
仍不达标就保留原文并记 failed，绝不写入可疑结果。

用法：
  .venv/bin/python scripts/fix_image_captions.py --scan                 # 全站扫描→state/image_caption_scan.json（新鲜）
  .venv/bin/python scripts/fix_image_captions.py --pages 20 --dry-run   # 试点干跑（默认），打印旧→新对照
  .venv/bin/python scripts/fix_image_captions.py --pages 20 --write     # 试点写站
  .venv/bin/python scripts/fix_image_captions.py --all --write          # 放量
  .venv/bin/python scripts/fix_image_captions.py --page 誓约之门 --write

写站前逐页 action=parse 冒烟（wikitext 不合法不写）；每次写站 summary 固定
「图片说明中文化」；进度/失败落 state/image_caption_fix_status.jsonl（幂等：已译的
说明重跑自动跳过）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import verify_translation as vt  # 复用其 _IMG_* 提取口径与词数判定（门禁同源）

tr = vt.tr  # translate 模块（vt 已加载）
from write import HuijiClient, load_env, resolve_api_url  # noqa: E402

SCAN_FILE = ROOT / "state" / "image_caption_scan.json"
STATUS_FILE = ROOT / "state" / "image_caption_fix_status.jsonl"
_CJK = re.compile(r"[一-鿿]")
# 跨页一致性记忆：完全相同的说明原文 → 同一译文（同一 run 内，多页共用一条
# `With the crew of the ''[[Dynamic]]''` 时不会出现两种译法）。只存通过校验的。
_MEMO: dict[str, str] = {}


# --------------------------------------------------------------------------- #
# 提取：返回说明参数的绝对区间（拼接用），判定口径与门禁同源（vt._IMG_*）
# --------------------------------------------------------------------------- #
def extract_caption_spans(text: str) -> list[tuple[int, int, str]]:
    """[(start, end, caption_text)]，start/end 为说明参数在 text 中的绝对区间。"""
    spans = []
    for m in vt._IMG_TPL_RE.finditer(text):
        # depth 初值必须是 1：m 已吞掉外层 `{{`（Image|），只数其后新增的嵌套开括号。
        # 2026-10-27 实录 bug：初值 0 会让嵌套 {{book ref|...}} 的 `}}` 触发 depth<=0
        # 当成外层闭合，说明被截断在 `{{book ref|sa2|16`（全中文说明因此被误判"待译/
        # 残留英文"、LLM 收到断串产生引号提前收口的坏 JSON）。
        depth, i, end = 1, m.end(), -1
        while i < len(text):
            if text.startswith("{{", i):
                depth += 1; i += 2
            elif text.startswith("}}", i):
                depth -= 1; i += 2
                if depth <= 0:
                    end = i; break
            else:
                i += 1
        if end < 0:
            end = len(text)
        inner_start = m.end()
        inner = text[inner_start:end - 2] if end > 0 else text[inner_start:]
        # 顶层 | 切分，记录每个参数的绝对区间。
        # 2026-10-27 修复：必须同时跟踪 [[]] 深度——[[Trell (Trellism)|Trell]] 里的
        # 链接竖线若按顶层切，说明会被拦腰截断（当时靠校验兜底未写坏，这里根治）。
        args, cur, cur_start, d, ld = [], [], inner_start, 0, 0
        j = 0
        while j < len(inner):
            if inner.startswith("{{", j):
                d += 1
            elif inner.startswith("}}", j):
                d -= 1
            elif inner.startswith("[[", j):
                ld += 1
            elif inner.startswith("]]", j):
                ld -= 1
            if inner[j] == "|" and d == 0 and ld <= 0:
                args.append(("".join(cur), cur_start, inner_start + j))
                cur, cur_start = [], inner_start + j + 1
            else:
                cur.append(inner[j])
            j += 1
        args.append(("".join(cur), cur_start, inner_start + len(inner)))
        # 2026-10-27 关键修复：MW 里 `|side=right` 是**命名参数、不占位次**，未命名
        # 位置参数才是 {{1}}/{{2}}…。模板契约 {{1}}=文件名、{{2}}=说明——必须先过滤出
        # 未命名参数再取位次。旧逻辑按裸管道跳 args[0]，在 `|side=|width=|文件名|说明`
        # 形态下把**文件名**当时说明翻译（天颂/奇里奇里 2 例，已回滚 revid 30731/30732）。
        pos = [(a, s, e) for (a, s, e) in args if not vt._IMG_NAMED_RE.match(a)]
        for a, s, e in pos[1:]:                       # pos[0] = 文件名
            if vt._IMG_BARE_OPT_RE.match(a):
                continue
            cap = a.strip()
            if FILELIKE_RE.match(cap):                # 防御：文件名形态绝不当说明
                continue
            ls = text.index(cap, s, e)
            spans.append((ls, ls + len(cap), cap))
    return spans


FILELIKE_RE = re.compile(
    r".*\.(jpe?g|png|gif|webp|svg|tif|bmp)$", re.I)  # 以图片扩展名结尾=文件名
# （2026-10-27 两轮调：①原字符集不容 ’/! 等，`The_Forger’s…jpg`、`DESTROY EVIL!!!.jpeg`
#  被误报；②前缀必须写 `.*`——调用点全用 .match()（行首锚），裸 `\.(...)$` 永不匹配。
#  位次逻辑（pos[0]=文件名）才是主判，这里只做形态防御。）


def needs_translation(cap: str, keep_set: set) -> bool:
    """纯英文说明，或中英夹杂仍残留 ≥2 个叙述性英文词 → 需译（与门禁 3d 同口径）。"""
    if FILELIKE_RE.match(cap.strip()):
        return False                       # 文件名形态永远不是说明
    on = vt._cap_norm(cap)
    if not on:
        return False
    total = len(re.findall(r"[A-Za-z']+", on))
    if total < 2:
        return False
    if not _CJK.search(on):
        return True
    return vt._cap_en_words(on, keep_set) >= 2


# --------------------------------------------------------------------------- #
# LLM：批量说明翻译 + 结构校验（含 1 次修复重试）
# --------------------------------------------------------------------------- #
def _tpl_tag_tokens(s: str) -> list[str]:
    """说明中的模板/HTML 标签 token——译文必须原样保留（不可增删改）。"""
    return re.findall(r"\{\{[^{}]*\}\}", s) + re.findall(r"<[^<>]+>", s)


_LINK_TARGET_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")


def _link_targets(s: str) -> list[str]:
    """内链**目标**列表（piped 显示文本剥除）——[[目标|显示]]→目标。"""
    return _LINK_TARGET_RE.findall(s)


_ZH_PAGE_SET = None


def _zh_page_set() -> set:
    """既有中文页名集合：zhwiki 标题键 + zhwiki 别名值 + 译名表 zh 值（懒加载）。"""
    global _ZH_PAGE_SET
    if _ZH_PAGE_SET is None:
        s = set()
        try:
            s |= set(tr.load_zhwiki_titles().keys())
            s |= set(tr.load_zhwiki_aliases().values())
            g = tr.load_merged_glossary(tr.DEFAULT_GLOSSARY, tr.DEFAULT_COMMON)
            s |= {v.get("zh") for v in g.values() if isinstance(v, dict) and v.get("zh")}
        except Exception:
            pass
        _ZH_PAGE_SET = s
    return _ZH_PAGE_SET


def validate(old: str, new: str, keep_set=None) -> str | None:
    """返回 None=通过，否则是失败原因。keep_set：保留英文名单（豁免，同门禁口径）。"""
    if FILELIKE_RE.match((old or "").strip()):
        return "原文是文件名（提取位次异常，禁止改写）"     # 防御性硬拦
    new = (new or "").strip()
    if not new:
        return "空译文"
    on = vt._cap_norm(new)
    if not _CJK.search(on):
        return "无中文（疑似未译/全 keep_en）"
    if len(re.findall(r"[A-Za-z']+", on)) >= 2 and vt._cap_en_words(on, keep_set or set()) >= 2:
        return "残留叙述性英文词（featuring/of/the 等未译）"
    # 结构校验（2026-10-27 试点实录放宽两项）：
    #  ① piped 链接的**显示文本可译**（[[羽类|red chicken]]→[[羽类|红鸡]]，与正文管线
    #    同口径）——只比对链接**目标**多重集；
    #  ② **新增链接**仅当目标是既有中文页（zhwiki 标题键/别名值/译名表 zh）；
    #  删链、改目标、模板/标签变动、'' 增删仍一律拒。
    if Counter(_tpl_tag_tokens(old)) != Counter(_tpl_tag_tokens(new)):
        return "结构 token 集合变化（模板/标签被增删或改写）"
    ol, nl = Counter(_link_targets(old)), Counter(_link_targets(new))
    if ol - nl:
        return "链接被删除或改写目标"
    if nl - ol:
        zs = _zh_page_set()
        for tgt in (nl - ol).elements():
            if tgt not in zs:
                return f"新增链接非既有中文页：{tgt[:60]}"
    if old.count("''") != new.count("''"):
        return "'' 斜体记号数不匹配（''不得换成《》/“”）"
    if len(new) > len(old) * 4 + 40:
        return "长度异常"
    return None


def build_llm_cfg():
    import argparse
    args = argparse.Namespace(llm_base_url=None, llm_model=None, timeout=120,
                              max_retries=3, api_key=None)
    return tr.load_llm_config(args)


_CAP_SYS = (
    "你是维基图片说明的英→中译者。把每条说明的自然语言译成简体中文，只输出一个 JSON 对象：\n"
    '{"items":[{"i":<编号>,"zh":"<译文>"}]}，items 数量与输入一致，按编号，不加任何其它文字。\n'
    "硬规则（违反即被拒收）：\n"
    "1. [[...]] 内链、{{...}} 模板、<...> 标签、'' 斜体记号一律原样保留：链接的**目标**"
    "必须一模一样（显示文本可译，如 `[[羽类|red chicken]]`→`[[羽类|红鸡]]`），模板/标签"
    "原样，**不得把 '' 换成《》或“”**，不得删除链接；**可以**给既有中文页名补链接"
    "（目标必须是中文页名），**不得**添加英文目标或臆造链接。**被 [[...]] 包裹的名称**"
    "整段按目标保留，只翻译它之外的文字"
    "（如 `With the crew of the ''[[Dynamic]]''` → `与''[[Dynamic]]''的船员们`）。\n"
    "2. 专名按「译名表」；表中没有的保留英文。\n"
    "3. 说明整句译成中文，featuring/with/on 等普通词也要译；**普通英文词必须用常见中文"
    "词义，禁止音译**（crew=船员、cover=封面、map=地图、petroglyph=岩刻、map/地图…），"
    "不得残留半句英文。\n"
    "4. **未被链接包裹**的对象名（船名/作品名）译成中文时采用所给页面标题的中文名"
    "（页面「“风之愉悦”号」→ 说明里 'Wind's Pleasure' 译作 风之愉悦），同一批内同一对象"
    "统一译法；译名仍用 '' 包裹（'' 出现次数与原文一致，如 ''风之愉悦''号）。\n"
    "5. 无对应译法的专名原样保留。"
)


def translate_batch(cfg, caps: list[str], gloss_slice: dict, keep_en: list[str],
                    page_hint: str, feedback: str | None = None) -> dict[int, str] | None:
    gloss_lines = "\n".join(f"- {e} = {d['zh']}" for e, d in gloss_slice.items()) or "（无命中）"
    body = "\n".join(f"⟦{i}⟧ {c}" for i, c in enumerate(caps, 1))
    user = (f"页面: {page_hint}\n译名表切片:\n{gloss_lines}\n"
            f"保留英文名单（出现时保留英文）: {', '.join(keep_en) or '（无）'}\n\n{body}")
    if feedback:
        user = f"你上一次的输出被拒收：{feedback}\n请修正后重新输出整批 JSON（其余要求不变）。\n\n" + user
    msgs = [{"role": "system", "content": _CAP_SYS}, {"role": "user", "content": user}]
    for attempt in (0, 1):
        try:
            out = tr.llm_chat(cfg, msgs, max_output_tokens=4000, temperature=0.2)
        except Exception as e:
            print(f"    LLM 调用失败: {e}")
            return None
        txt = re.sub(r"^```(?:json)?|```$", "", out.strip(), flags=re.M).strip()

        def _load(s: str):
            try:
                return json.loads(s)["items"]
            except Exception:
                # 机械修复：模型在嵌套模板 }} 前把字符串引号提前收口
                # （"...35"}}]}`）。本 schema 是对象数组，合法输出里 `"}}` 不可能出现，
                # 定向改写为 `}}"` 再解析一次。
                fixed_s = s.replace('"}}', '}}"')
                return json.loads(fixed_s)["items"]

        try:
            items = _load(txt)
            got = {int(it["i"]): str(it["zh"]).strip() for it in items}
        except Exception:
            if attempt == 0:
                # 诊断：截断（JSON 没闭合）还是格式（说明首行/尾行，便于对症处置）
                print(f"    LLM JSON 解析失败（已试修复） | 头: {txt[:90]!r} | 尾: {txt[-90:]!r}")
            continue
        if all(i in got for i in range(1, len(caps) + 1)):
            return got
        if attempt == 1:
            return None
    return None


# --------------------------------------------------------------------------- #
# 扫描（--scan）：与初次调查同口径，生成/刷新候选清单
# --------------------------------------------------------------------------- #
def do_scan(client) -> None:
    def srch(q: str) -> list[str]:
        out, off = [], None
        while True:
            pr = {"action": "query", "list": "search", "srsearch": q, "srnamespace": 0,
                  "srlimit": 50, "format": "json", "formatversion": "2"}
            if off:
                pr["sroffset"] = off
            r = client._post(pr)
            res = r.get("query", {}).get("search", [])
            out += [x["title"] for x in res]
            off = (r.get("continue") or {}).get("sroffset")
            if not off or len(res) < 50:
                break
            time.sleep(0.12)
        return out

    keep_set = {t.lower() for t in tr.load_keep_en()}
    pages = sorted(set(srch('insource:"{{Image"')) | set(srch('insource:"{{image"')))
    hits, n_img = [], 0
    for t in pages:
        w = (client.read_page(t) or {}).get("wikitext", "") or ""
        if not w:
            continue
        for _s, _e, cap in extract_caption_spans(w):
            n_img += 1
            if needs_translation(cap, keep_set):
                hits.append({"page": t, "caption": cap[:200]})
        time.sleep(0.05)
    SCAN_FILE.parent.mkdir(exist_ok=True)
    SCAN_FILE.write_text(json.dumps(
        {"scanned_at": time.strftime("%F %T"), "pages_scanned": len(pages),
         "image_templates": n_img, "untranslated": hits},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"扫描完成：{len(pages)} 页 / {n_img} 个 Image / 未译说明 {len(hits)} 条"
          f"（涉页 {len({h['page'] for h in hits})}）→ {SCAN_FILE}")


# --------------------------------------------------------------------------- #
# 单页处理
# --------------------------------------------------------------------------- #
def process_page(client, cfg, title: str, glossary: dict, keep_en: list[str],
                 write: bool) -> dict:
    w = (client.read_page(title) or {}).get("wikitext", "") or ""
    if not w:
        return {"page": title, "skip": "空页/无权限"}
    keep_set = {t.lower() for t in keep_en}
    spans = [(s, e, c) for s, e, c in extract_caption_spans(w) if needs_translation(c, keep_set)]
    if not spans:
        return {"page": title, "fixed": 0, "note": "无需处理（幂等跳过）"}
    caps = [c for _s, _e, c in spans]
    gloss_slice = tr.slice_glossary(glossary, tr.extract_en_terms("\n".join(caps)))
    m_en = re.search(r"\{\{en\|([^}|]+)", w)
    hint = f"{title}（en: {m_en.group(1) if m_en else '-'}）"
    print(f"  [{title}] {len(caps)} 条说明待译…")
    # 先查跨页一致性记忆（命中即免调 LLM），其余成批翻译
    memo_hit = {}
    pending = []
    for i, c in enumerate(caps, 1):
        mv = _MEMO.get(c)
        if mv is not None and validate(c, mv, keep_set) is None:
            memo_hit[i] = mv
        else:
            pending.append(i)
    got: dict[int, str] = dict(memo_hit)
    if pending:
        raw = translate_batch(cfg, [caps[i - 1] for i in pending], gloss_slice, keep_en, hint)
        if raw:
            for k, v in raw.items():
                if 1 <= k <= len(pending):
                    got[pending[k - 1]] = v
    fixed, failed, parts = [], [], []
    prev = 0
    for idx, (s, e, old) in enumerate(spans, 1):
        new = (got or {}).get(idx)
        reason = validate(old, new, keep_set) if new else "LLM 批次失败（JSON/调用）"
        if reason:
            # 单条修复重试 1 次：把具体拒因反馈给模型（同 translate 主管道的回喂口径）
            got2 = translate_batch(cfg, [old], gloss_slice, keep_en, hint, feedback=reason)
            cand = (got2 or {}).get(1)
            if cand:                      # 注意：cand=None = 批次失败，≠ 校验通过
                r2 = validate(old, cand, keep_set)
                if r2 is None:
                    new, reason = cand, None
                else:
                    new, reason = cand, r2
        if reason:
            failed.append({"caption": old[:120], "reason": reason, "tried": (new or "")[:160]})
            if not write:
                print(f"    ✗ 保留原文: {old[:96]} ← {reason}")
                if new:
                    print(f"      尝试稿: {new.strip()[:140]!r}")
            continue
        # 单残词清扫：校验已过但仍残留恰好 1 个非保留英文词（featuring 类漏网），
        # 回喂要一版更干净的；不更干净则保留原结果（防回喂劣化）。
        if new and vt._cap_en_words(vt._cap_norm(new), keep_set) == 1:
            got3 = translate_batch(
                cfg, [old], gloss_slice, keep_en, hint,
                feedback="上一版译文里仍残留 1 个未翻译的英文词，请把普通英文词译掉"
                         "（保留专名除外）；其它已合格部分不要改动。")
            cand = (got3 or {}).get(1)
            if (cand and validate(old, cand, keep_set) is None
                    and vt._cap_en_words(vt._cap_norm(cand), keep_set) == 0):
                new = cand
        parts.append(w[prev:s]); parts.append(new); prev = e
        _MEMO[old] = new          # 跨页一致性：后续页同文案直接复用
        fixed.append({"old": old, "new": new})

    def _save_rec(fx, fl, written, res=None):
        """write 模式凡处理必落账——含全失败页/掩码/冒烟中止页（2026-10-27 补：
        pass2 曾有 11 条 fixed=0 的失败未落盘，审计不留白）。"""
        if not write:
            return
        rec = {"page": title, "fixed": len(fx), "failed": fl,
               "pairs": [{"old": f["old"], "new": f["new"]} for f in fx],
               "ts": time.strftime("%F %T"), "written": bool(written)}
        if isinstance(res, dict):
            rec["edit"] = {k: res.get(k) for k in ("result", "revid", "newrevid") if k in res}
        with STATUS_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    if not fixed:
        if not write:
            for f in failed:
                print(f"    ✗ 保留原文: {f['caption'][:96]} ← {f['reason']}")
        _save_rec(fixed, failed, False)
        return {"page": title, "fixed": 0, "failed": failed}
    parts.append(w[prev:])
    new_w = "".join(parts)
    # 掩码不变量：新旧两侧把说明替换成占位后必须逐字节相同（只动 caption 的硬保证）
    def mask(text: str) -> str:
        out, prev_i = [], 0
        for s, e, c in extract_caption_spans(text):
            out.append(text[prev_i:s]); out.append("␀CAP␀"); prev_i = e
        out.append(text[prev_i:])
        return "".join(out)
    if mask(w) != mask(new_w):
        fl = failed + [{"caption": "-", "reason": "掩码不变量失败（中止写入）"}]
        _save_rec(fixed, fl, False)
        return {"page": title, "fixed": 0, "failed": fl}
    # 写站前 parse 冒烟
    if write:
        try:
            pr = {"action": "parse", "text": new_w, "prop": "text", "format": "json",
                  "formatversion": "2", "disabletoc": "1", "disableeditsection": "1", "noimages": "1"}
            r = client._post(pr)
            if "parse" not in r:
                fl = failed + [{"caption": "-", "reason": f"parse 冒烟失败: {str(r)[:160]}"}]
                _save_rec(fixed, fl, False)
                return {"page": title, "fixed": 0, "failed": fl}
        except Exception as ex:
            fl = failed + [{"caption": "-", "reason": f"parse 冒烟异常: {ex}"}]
            _save_rec(fixed, fl, False)
            return {"page": title, "fixed": 0, "failed": fl}
        time.sleep(0.2)
        res = client.edit(title, new_w, summary=f"图片说明中文化（{len(fixed)} 条，只改动说明文字）")
        time.sleep(0.7)
    else:
        for f in fixed:
            print(f"    旧: {f['old'][:96]}\n    新: {f['new'][:96]}")
        res = None
    _save_rec(fixed, failed, bool(write), res)
    if write:
        print(f"    ✅ 写入 {len(fixed)} 条说明（failed {len(failed)}）")
    return {"page": title, "fixed": len(fixed), "failed": failed, "written": bool(write)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--page", action="append", default=[], help="指定页（可多次）")
    ap.add_argument("--pages", type=int, default=0, help="从候选清单取前 N 页（0=不限）")
    ap.add_argument("--all", action="store_true", help="候选清单全部页（等价 --pages 0）")
    ap.add_argument("--scan", action="store_true", help="先全站扫描刷新候选清单")
    ap.add_argument("--write", action="store_true", help="写站（默认 dry-run 只打印对照）")
    ap.add_argument("--dry-run", action="store_true",
                    help="显式声明干跑（默认行为；仅为文档好读，无额外作用）")
    ap.add_argument("--status-file", default=str(STATUS_FILE))
    args = ap.parse_args()

    env = load_env(ROOT / ".env")
    client = HuijiClient(resolve_api_url(env), env.get("HUIJI_API_KEY", ""),
                         env.get("HUIJI_BOT_USER", ""), env.get("HUIJI_BOT_PASS", ""))
    client.ensure_logged_in()

    if args.scan:
        do_scan(client)
        if not args.page and not args.pages and not args.all:
            return
    if args.page:
        titles = list(dict.fromkeys(args.page))
    else:
        if not SCAN_FILE.exists():
            raise SystemExit("缺候选清单：先 --scan")
        hits = json.loads(SCAN_FILE.read_text(encoding="utf-8"))["untranslated"]
        titles = list(dict.fromkeys(h["page"] for h in hits))
        if args.pages:
            titles = titles[:args.pages]
    cfg = build_llm_cfg()
    glossary = tr.load_merged_glossary(tr.DEFAULT_GLOSSARY, tr.DEFAULT_COMMON)
    keep_en = tr.load_keep_en()
    print(f"处理 {len(titles)} 页 | 模式={'写站' if args.write else 'DRY-RUN'} | 模型 {cfg.model}")
    stats = {"pages": 0, "fixed": 0, "failed": 0}
    for t in titles:
        try:
            r = process_page(client, cfg, t, glossary, keep_en, args.write)
        except Exception as ex:
            print(f"  [{t}] 异常: {ex}")
            r = {"page": t, "fixed": 0, "failed": [{"caption": "-", "reason": str(ex)}]}
        stats["pages"] += 1
        stats["fixed"] += r.get("fixed", 0)
        stats["failed"] += len(r.get("failed", []))
    print(f"\n汇总：{stats['pages']} 页 | 修复说明 {stats['fixed']} 条 | 失败 {stats['failed']} 条"
          f"{' | 已写站' if args.write else ' | 未写站(dry-run)'}"
          f"\n明细: {args.status_file}（write 模式才落盘）")


if __name__ == "__main__":
    main()
