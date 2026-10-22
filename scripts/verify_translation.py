# -*- coding: utf-8 -*-
"""翻译产物自动质量门禁（把「人工 review」固化成脚本，批次写站前自动跑）。

用法：
    .venv/bin/python scripts/verify_translation.py --title <快照标题> [--wiki <站>]
    .venv/bin/python scripts/verify_translation.py --title-file state/bot_test_titles.txt

检查项（全部失败即退出码非 0）：
  [引用]   对比英文源（convert 后）与翻译产物的引用标记序列
           {{book ref|X|Y}} / {{msh ref|X|Y}} / {{Rpg ref|X|Y}} / {{wob ref|N}} /
           {{date|X|Y}} 参数逐一相同——抓 LLM 引用编号幻觉（§4.8 教训：
           Ghostbloods 重跑 mb7|47→mb7|39 等）。
  [占位符] %%ORIGINAL_BLOCK_%% 无残留（unmask 应全部填回）。
  [模板]   {{en|词条名}} 只剩页首/导语正确位置，未错位进 notice 等参数。
  [裸词]   正文中仍以英文裸词出现的译名表专名（有译名却未译）：
           Spook/Elendel/Catacendre 等（排除结构位置：原名/CmPermission/File:/Image 文件名/en 参数/quote 占位）。
  [半译]   infobox「字段 = 值」行内中英夹杂（如 `幸存者 of the Flames`、
           `Several ... noble houses`）——LLM 半译残留。
"""
import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import importlib.util

_ts = importlib.util.spec_from_file_location("translate_mod", HERE / "translate.py")
tr = importlib.util.module_from_spec(_ts)
sys.modules[_ts.name] = tr
_ts.loader.exec_module(tr)

_cts = importlib.util.spec_from_file_location("convert_templates_mod", HERE / "convert_templates.py")
ct = importlib.util.module_from_spec(_cts)
sys.modules[_cts.name] = ct
_cts.loader.exec_module(ct)

GLOS_DEFAULT = getattr(tr, "DEFAULT_GLOSSARY", "dict/mistborn.json")

# 掩码与词表逻辑以 translate.py 为单一来源（tr.mask_nonprose / tr.glossary_finish_terms），
# 保证「收尾替换能修的 = 门禁会判错的」两侧行为完全同源、零漂移。
mask_nonprose = tr.mask_nonprose
glossary_finish_terms = tr.glossary_finish_terms


REF_PATS = [
    (r"\{\{\s*book ref\s*\|([^}]+)\}\}", "book ref"),
    (r"\{\{\s*msh ref\s*\|([^}]+)\}\}", "msh ref"),
    (r"\{\{\s*Rpg ref\s*\|([^}]+)\}\}", "Rpg ref"),
    (r"\{\{\s*wob ref\s*\|([^}]+)\}\}", "wob ref"),
    (r"\{\{\s*date\s*\|([^}]+)\}\}", "date"),
]


def extract_refs(text: str) -> list[str]:
    out = []
    for pat, _name in REF_PATS:
        for m in re.finditer(pat, text):
            arg = re.sub(r"\s+", " ", m.group(1).strip())
            out.append(f"{_name}:{arg}")
    return out


# 结构位置：这些位置的英文专名不算「漏译」
STRUCT = [
    r"\| 原名\s*=",          # infobox 原名
    r"\{\{CmPermission\|",   # 页权模板
    r"\[\[File:",            # 文件
    r"\{\{Image\|",          # 图像模板文件名/参数区（整体跳过，单独看 caption）
    r"\{\{en\|",             # 英文名标注
    r"\{\{ensync\|",
]


def is_in_struct(text: str, pos: int) -> bool:
    for pat in STRUCT:
        for m in re.finditer(pat, text):
            if m.start() <= pos < m.end() + 80:  # 80 字符容忍文件路径
                return True
    return False


_WIKILINK_RE = re.compile(r"\[\[[^\[\]]*\]\]")






def _inside_wikilink_target(text: str, pos: int) -> bool:
    """pos 是否在 [[...]] 链接内部（链接目标或显示文本）→ 链接目标按译名表处理，
    含所有格独立词条页（Spook's note 等）译名表无条目时保留英文是正确行为，不算漏译。"""
    for m in _WIKILINK_RE.finditer(text):
        if m.start() <= pos < m.end():
            return True
    return False


# 5) 半译：同一字段内「中文与英文夹杂在同一短语 / 英文普通词残留」才算漏译。
#    两个互补信号：
#    A) 行内含中文 + 剥模板/链接后仍有「小写**内容词**」英文（noble houses/several/post…）
#       —— 普通英文没译全（保留英文专名不受影响，专名首字母大写）。
#    B) 英文片段与中文字符紧邻（空格/连字符分隔，同一称号内夹杂）且含任何小写词
#       —— 如「幸存者 of the Flames」（Survivor 被拆译成幸存者、of the Flames 残留）
#       或「Lord 迷雾之子」。逗号分隔的独立项（「Survivor of the Flames, 迷雾之子领主」、
#       「杰戴, Lestibournes」）不算——保留英文专名/称号是铁律。
FUNC_WORDS = {"of", "the", "a", "an", "in", "on", "for", "to", "and", "or", "at",
              "by", "with", "from", "is", "was", "be", "that", "this", "it",
              # ③（2026-10-23）外语虚词不作「英文残留」证据：德/法语 des（…des Zorns/
              # …des Radieux）实测 4 处误伤 Words of Radiance。只豁免该词本身，
              # 其余小写内容词照判（contes/several 等仍拦）。
              "des"}


def _field_half_problems(body: str, quote_spans) -> list:
    """第 5 节半译（| 字段行中英夹杂）判定（2026-10-23 ③自 check_one 原位抽出，
    供误伤回归单测直调；抽出前后判定语义逐字一致，除③三处修正）：
    - 斜体 `''…''` 标题整体剔除（与 mask_nonprose/3c 同口径：斜体书名按规则保留英文；
      粗体先占位保护不豁免——粗体可承载译文）→ 修 Words of Radiance 4 处外语书名
      非ASCII断词碎片误伤（Stürme→rme、Câmpiile→mpiile、Jurâmântului→ntului）；
    - 模板剔除上限 150→512 → 修 Wind and Truth 长 {{tor ref|…}}（186 字符，全语料
      |行内最长 449）残留「tor ref」误伤；
    - FUNC_WORDS 增 des。
    判不出新问题类型：只减少误报，绝不新增拦截（对照回归 tests_gate_fp.py + 全量A/B）。"""
    problems = []
    keep_en_terms = set(tr.load_keep_en())
    for ln in body.split("\n"):
        if not ln.startswith("|"):
            continue
        if re.search(r"\{\{tag|\{\{en\||原名", ln):
            continue
        # 原文块（Quote/sidequote/columns）内的行：含署名行（|Spook to Sazed...），
        # 按决议#13 保留英文，不属于「LLM 半译漏译」
        ln_pos = body.find(ln)
        if any(a <= ln_pos < b and a >= 0 for a, b in quote_spans):
            continue
        if re.search(r"[\u4e00-\u9fff]", ln) and re.search(r"[A-Za-z]{4,}", ln):
            # 字段行只判值（2026-10-20 修）：|world= / |prereq= 的 key 是模板/表格结构位，
            # 按设计英文——剔除 key 后只在 value 上做残留/夹杂信号；值全中文则整行跳过。
            _k = re.match(r"^(\s*\|\s*[A-Za-z][\w \-]{0,40})=(.*)$", ln)
            src_ln = ("|" + _k.group(2)) if _k else ln
            if not re.search(r"[A-Za-z]{4,}", src_ln):
                continue
            stripped = re.sub(r"\{\{[^{}]{0,512}\}\}", " ", src_ln)  # ③ 上限 150→512
            stripped = re.sub(r"\[\[[^\]]*\]\]", " ", stripped)
            stripped = re.sub(r"<[^>]+>", " ", stripped)
            # ③ 斜体 ''…'' 剔除（镜像 mask_nonprose 第3步：粗体先占位保护）
            _bolds: list = []

            def _save_bold(m, _b=_bolds):
                _b.append(m.group(0))
                return "\x00%d\x00" % (len(_b) - 1)

            stripped = re.sub(r"'''.+?'''", _save_bold, stripped, flags=re.S)
            stripped = re.sub(r"''[^'\n]+''", " ", stripped)
            stripped = re.sub(r"\x00(\d+)\x00", lambda m: _bolds[int(m.group(1))],
                              stripped)
            for m in re.finditer(r"[A-Za-z][A-Za-z'\- ]{3,}", stripped):
                frag = m.group(0).strip()
                left = stripped[max(0, m.start() - 2):m.start()]
                right = stripped[m.end():m.end() + 2]
                words = re.findall(r"[A-Za-z][A-Za-z'\-]*", frag)
                # 大写词（首字母大写，如 Survivor/Flames/Mistborn）计为专名词
                cap_words = [w for w in words if w[:1].isupper()]
                lower_any = any(w != w.upper() and not w[:1].isupper() for w in words)
                lower_content = [
                    w for w in words
                    if not w[:1].isupper()
                    and w.lower().strip("'") not in FUNC_WORDS
                    and w.lower().strip("'") not in keep_en_terms
                ]
                adjacent_zh = (
                    re.search(r"[\u4e00-\u9fff]", left.replace(" ", "").replace("-", ""))
                    or re.search(r"[\u4e00-\u9fff]", right.replace(" ", "").replace("-", ""))
                )
                # 信号A：小写内容词残留（noble houses / several post-…），行内有中文 → 漏译
                if lower_content and len(words) >= 2:
                    problems.append(f"[半译] {ln.strip()[:88]}… ← 残留: {frag[:50]}")
                    break
                # 信号B：英文片段紧邻中文、且不是「多专名词的完整称号」
                # （of the Flames 紧邻幸存者 → 报；Survivor of the Flames 作为完整
                #  称号与中文并列 → 不报；Lord 紧邻迷雾之子 → 报）
                if adjacent_zh and lower_any and len(cap_words) <= 1:
                    problems.append(f"[半译] {ln.strip()[:88]}… ← 夹杂残留: {frag[:50]}")
                    break
    return problems


def check_one(title_en: str, wiki: str) -> list[str]:
    problems = []
    snap = Path("en_snapshot") / title_en
    tl = snap / "translation.json"
    if not tl.exists():
        return [f"缺 translation.json: {title_en}"]
    data = json.loads(tl.read_text(encoding="utf-8"))
    body = data.get("translation", "")
    src = (snap / "wikitext.txt").read_text(encoding="utf-8")

    # 1) 引用序列（英文源经 convert 后 vs 产物）
    try:
        conv, _ = ct.convert_wikitext(src, ct.load_rules())
    except Exception as e:
        problems.append(f"convert 英文源失败: {e}")
        return problems
    src_refs = extract_refs(conv)
    out_refs = extract_refs(body)
    if src_refs != out_refs:
        n = min(len(src_refs), len(out_refs))
        first_diff = None
        for i in range(n):
            if src_refs[i] != out_refs[i]:
                first_diff = i
                break
        if first_diff is None:
            first_diff = n if n < max(len(src_refs), len(out_refs)) else -1
        problems.append(
            f"[引用] 序列不一致：英文 {len(src_refs)} 处 vs 产物 {len(out_refs)} 处"
            + (f"；首个差异 @{first_diff}: 英文={src_refs[first_diff] if first_diff < len(src_refs) else '—'}"
               f" 产物={out_refs[first_diff] if first_diff < len(out_refs) else '—'}" if first_diff >= 0 else "")
        )
        # 列出产物中所有与英文不同的项（去重前 10）
        diffs = []
        for i, (a, b) in enumerate(zip(src_refs, out_refs)):
            if a != b and len(diffs) < 10:
                diffs.append(f"  @{i} 英文={a} 产物={b}")
        for d in diffs:
            problems.append(d)

    # 2) 占位符残留
    for pat, name in [(r"%%ORIGINAL_BLOCK_\d+%%", "原文块"), (r"%%REF_\d+%%", "引用"),
                  (r"%%LINKLIST_\d+%%", "infobox内链列表"), (r"%%ORIGINAL_NAME%%", "原名")]:
        left = re.findall(pat, body)
        if left:
            problems.append(f"[占位符] {name}占位符残留 {len(left)} 个: {left[:5]}")

    # 2a) LLM 干扰标记残留：单 % 包裹（%{{date|...}}% / %%%x%% 等）——旧版单 % 占位符
    #     被 LLM 改编的产物会留下这种噪音（实测 rerun6 出现 在%{{date|1021|fe}}%早期）。
    pct = re.findall(r"%(?!%)(?!ORIGINAL)(?!REF)[^%\n]{1,80}%", body)
    # 过滤掉正常文本中的百分号对（如 “100%” 出现两次的情况几乎不可能且长度短）；只报包裹模板/英文的
    pct_bad = [p for p in pct if ("{{" in p or re.search(r"[A-Za-z]{3,}", p)) and len(p) > 2]
    if pct_bad:
        problems.append(f"[干扰标记] %...% 残留 {len(pct_bad)} 个（LLM 改编占位符的噪音）: {pct_bad[:5]}")

    # 2b) 导语残留英文（复用 translate.py 的 lead 判定：标题译了但导语正文留英文）
    if body.startswith("{{CmPermission") or "{{Infobox" in body[:200]:
        try:
            if tr.untranslated_lead_english(src, body):
                problems.append("[导语] 导语正文仍残留英文句子（只译标题未译正文）——"
                                "按机制应带反馈重试后仍失败：写回前必须处理（重跑或人工补译）")
        except Exception:
            pass

    # 3) {{en|...}} 错位：出现在 notice 参数内 → 错位
    for m in re.finditer(r"\{\{notice\b[^}]*\{\{en\|", body):
        problems.append(f"[模板] {{{{en}}}} 错位进 notice: ...{body[max(0,m.start()-40):m.end()+20]}...")
    # {{en|X}} 数量应等于 1（页首导语标注）或 0（无 en 包装）
    en_cnt = len(re.findall(r"\{\{en\|", body))
    if en_cnt > 1:
        problems.append(f"[模板] {{{{en}}}} 出现 {en_cnt} 次（应 1 次或 0 次）")

    # 3a) 标题结构：a) 纯 ASCII 标题=漏翻（keep_en 豁免） b) 开闭等号数不匹配
    keep_heads = {t.lower() for t in tr.load_keep_en()}
    n_head_bad = 0
    for hm in re.finditer(r"^(={2,6})[ \t]*(.*?)[ \t]*(={2,6})[ \t]*$", body, re.M):
        op, htxt, cl = hm.group(1), hm.group(2).strip(), hm.group(3)
        hline = body[:hm.start()].count("\n") + 1
        if len(op) != len(cl):
            problems.append(f"[结构] 标题闭合等号不匹配（第{hline}行）: {hm.group(0).strip()!r}")
            n_head_bad += 1
        elif (re.fullmatch(r"[A-Za-z][A-Za-z0-9 ,:'&\-()]*", htxt or "")
              and re.search(r"[A-Za-z]{3}", htxt)
              and htxt.lower() not in keep_heads):
            problems.append(f"[章节] 标题未译（第{hline}行）: {htxt!r}")
            n_head_bad += 1
        if n_head_bad >= 8:
            break

    # 3b) 括号配对：[[ ]] 与 {{ }} 全文计数必须自平衡（断链/断模板 = 渲染坏）
    wk_o, wk_c = body.count("[["), body.count("]]")
    if wk_o != wk_c:
        problems.append(f"[结构] 内链括号不配对：[[ ×{wk_o} vs ]] ×{wk_c}")
    tp_o, tp_c = body.count("{{"), body.count("}}")
    if tp_o != tp_c:
        problems.append(f"[结构] 模板括号不配对：{{ ×{tp_o} vs }} ×{tp_c}")

    # 3c) 正文半译：导语之外的散文行残留成句英文（qwen3.8-27b 实测 8 段
    #     「英文句架+中文专名」逃过全部旧门禁）。mask_nonprose 全文等长掩码
    #     （模板/链接/斜体/引文/keep_en/ref-name 均不计），只数叙述性英文词
    #     （全小写或停用词；首字母大写专名不计）。信息框行（| 开头）交给第 5 节。
    try:
        _masked_body = tr.mask_nonprose(body)
        _stops = getattr(tr, "_UNTRANSLATED_STOPWORDS", set())
        n_half = 0
        for lidx, (orig_ln, mask_ln) in enumerate(zip(body.split("\n"),
                                                     _masked_body.split("\n")), 1):
            # ! 行=表格属性行（class/colspan/style 本为英文结构位）、<!-- -->=源注释
            # （读者不可见、按设计保留英文）——均不属正文半译（2026-10-20 修，level2 实测误伤）。
            if (not orig_ln or orig_ln[0] in "|={!" or orig_ln.startswith("[[category")
                    or orig_ln.lstrip().startswith("<!--")):
                continue
            l = re.sub(r"<ref[^>]*>.*?</ref>", " ", mask_ln)
            l = re.sub(r"</?ref[^>]*>", " ", l)
            # 整链剔除（含显示文本）：链接属结构位——显示要么已按表译中、
            # 要么表外按「宁保英文」保留，都不算散文半译（gemheart/spores 类）
            l = re.sub(r"\[\[[^\[\]]*\]\]", " ", l)
            words = re.findall(r"[A-Za-z]+", l)
            prose = [w for w in words
                     if w.lower() in _stops or w == w.lower()]
            if len(prose) >= 6:
                n_half += 1
                problems.append(f"[半译] 正文行残留成句英文（第{lidx}行）: {orig_ln.strip()[:76]}…")
                if n_half >= 8:
                    problems.append("[半译] …（更多半译行已截断）")
                    break
    except Exception:
        pass

    # 4) 裸词残留：**全译名表**有译名的词仍以英文裸词出现在正文（结构位置 + 掩码区 +
    #    决议#13 原文块内除外）。2026-10-18 由 7 词硬编码升级为全表扫描（零 review：
    #    Kelsier/Mistborn/Lestibournes 等任意表内词漏译都必须被机械拦截）。
    glossary = tr.load_merged_glossary(Path(GLOS_DEFAULT), tr.DEFAULT_COMMON)
    # 词表与 translate 的收尾替换同源（glossary_finish_terms）：修得掉的一定不报、
    # 报得出的一定已被收尾替换 → 零漂移。
    glos_terms = glossary_finish_terms(glossary)  # 已按 en 长度降序（长词优先）
    # 决议#13 原文块范围（填入英文原文的整块模板：Quote/sidequote/columns）。
    # 块内含署名行（|Spook to Sazed...）也按决议保留英文 —— unmask 整块填回，
    # 不是 LLM 漏译。
    quote_spans = []
    for m in re.finditer(r"\{\{\s*(?:Quote|sidequote|columns)\b", body, re.I):
        start = m.start()
        # 简单括号平衡：找该模板的闭合 }}（模板体不含裸 }}}}
        depth = 0
        i = m.end()
        end = -1
        while i < len(body):
            if body.startswith("{{", i):
                depth += 1
                i += 2
            elif body.startswith("}}", i):
                depth -= 1
                i += 2
                if depth <= 0:
                    end = i
                    break
            else:
                i += 1
        if end < 0:
            end = len(body)
        quote_spans.append((start, end))
    masked = mask_nonprose(body)
    reported_bare: list[tuple[int, int]] = []
    bare_cnt = 0
    for _en, _zh in glos_terms:
        if bare_cnt >= 15:
            break
        try:
            _pat = re.compile(r"(?<![A-Za-z])" + re.escape(_en) + r"(?:'s)?(?![A-Za-z])")
        except re.error:
            continue
        for m in _pat.finditer(body):
            if bare_cnt >= 15:
                break
            # 长词已报跨度内的短词命中不重复报
            if any(m.start() < b and m.end() > a for a, b in reported_bare):
                continue
            # 掩码区（模板参数/外链 URL/斜体书名/括号英文标注/自闭合 ref id）→ 非正文，不查
            if masked[m.start():m.end()].strip() == "":
                continue
            if is_in_struct(body, m.start()):
                continue
            if re.match(r"\{\{en\|", body[max(0, m.start() - 6):m.start()]):
                continue
            if any(a <= m.start() < b for a, b in quote_spans):
                continue  # 决议#13 原文块内（Quote 台词/署名），按设计保留英文
            # 链接目标内（[[Spook's note|一条消息]] 等独立词条页，译名表无 → 保留英文目标）
            if _inside_wikilink_target(body, m.start()):
                continue
            ctx = body[max(0, m.start() - 30):m.end() + 20].replace("\n", "\\n")
            problems.append(f"[裸词] {m.group(0)}（应译 {_zh}）: ...{ctx}...")
            reported_bare.append((m.start(), m.end()))
            bare_cnt += 1

    # 5) 半译（同字段夹杂）：判定抽出为 _field_half_problems（2026-10-23 ③自此处原位
    #    移出，含③三处误伤修正——斜体''…''剔除/模板剔除上限512/FUNC_WORDS+des；
    #    对照回归 tests_gate_fp.py + 全量门禁A/B）。
    problems.extend(_field_half_problems(body, quote_spans))

    return problems


def main():
    global args_glossary
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", default=None)
    ap.add_argument("--title-file", default=None)
    ap.add_argument("--glossary", default=str(tr.DEFAULT_GLOSSARY))
    ap.add_argument("--wiki", default=tr.DEFAULT_WIKI)
    a = ap.parse_args()
    args_glossary = a.glossary
    global GLOS_DEFAULT
    GLOS_DEFAULT = a.glossary

    titles = []
    if a.title_file:
        titles = [l.strip() for l in Path(a.title_file).read_text(encoding="utf-8").splitlines() if l.strip()]
    elif a.title:
        titles = [a.title]
    if not titles:
        print("需 --title 或 --title-file"); return 2

    failed = 0
    for t in titles:
        probs = check_one(t, a.wiki)
        if probs:
            failed += 1
            print(f"\n### {t}: {len(probs)} 个问题")
            for p in probs:
                print("   ", p)
        else:
            print(f"### {t}: 全部通过")
    print(f"\n== 通过 {len(titles) - failed}/{len(titles)} ==")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())