#!/usr/bin/env python3
"""
翻译管道（决议 #4/#9/#13）：英文 converted wikitext → 中文 wikitext，产出符合契约的 translation.json。

输入：en_snapshot/<标题>/wikitext.txt（脚本内部用最新 convert_templates.py 转成转换后形态，不依赖脆弱的 converted.txt）
输出：en_snapshot/<标题>/translation.json
      {
        "meta": { "title_en", "revision_id", "target_wiki", "format":"mediawiki",
                  "chunks": N, "note": ... },
        "translation": "<含全部页面级包装({{CmPermission}}/{{en}}/{{ensync}})的完整中文 wikitext>",
        "untranslated_terms": [ { "en":..., "reason":... }, ... ]
      }
  （同步落 translation.txt —— 与 Allik 样板一致的纯 wikitext 视图）

关键能力：
  - 超长词条分块：按 `== 章节 ==` / `=== 小节 ===` 边界切块，每块 ≤ --max-chars，Infobox+导语固定为 chunk0，
    绝不在一节/一模板内部切开；单节过长时独成一块并告警。
  - 术语裁切（决议 #9）：仅把本文出现的译名词条切片送给 LLM，省 token。
  - LLM 配置与 DSH 一致：默认 base_url=https://token.glint-mvt.com/v1、model=deepseek-v4-flash-0731，
    api key 从环境变量 DEEPGLINT2_API_KEY 读取（可 --api-key / .env 覆盖）。
  - 输出遵守 JSON 契约：translation + untranslated_terms（决议 #4），原文引用/称号列表标记「需查中译本」（决议 #13）。

用法：
  .venv/bin/python scripts/translate.py --title <标题>
  .venv/bin/python scripts/translate.py --title <标题> --max-chars 6000 --concurrency 2
  .venv/bin/python scripts/translate.py --title <标题> --llm-base-url ... --llm-model ...   # 覆盖 LLM 配置

选项：
  --title          快照标题（读取 en_snapshot/<标题>/converted.txt）
  --glossary       dict/mistborn.json（默认）
  --max-chars      每块最大字符数（默认 7000；超长词条按此切块）
  --concurrency    并发翻译块数（默认 1，避免触发限速/超时）
  --dry-run        只做分块与提示词预演，不调用 LLM（输出分块清单到 stderr，不写文件）
  --no-wrap        不插入页面级包装（CmPermission/en/ensync），仅输出纯正文翻译
  --llm-base-url   覆盖 baseURL（默认同 DSH：https://token.glint-mvt.com/v1）
  --llm-model      覆盖模型（默认 deepseek-v4-flash-0731）
  --api-key        覆盖 API key（默认读环境变量 DEEPGLINT2_API_KEY）
  --timeout        单次 LLM 请求超时秒（默认 300）
  --max-retries    单块失败重试次数（默认 3）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass
from pathlib import Path

import mwparserfromhell

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EN_SNAPSHOT = ROOT / "en_snapshot"
DEFAULT_GLOSSARY = ROOT / "dict" / "mistborn.json"
DEFAULT_BASE_URL = "https://token.glint-mvt.com/v1"
DEFAULT_MODEL = "deepseek-v4-flash-0731"
DEFAULT_WIKI = "coppermind.huijiwiki.com"


# --------------------------------------------------------------------------- #
# LLM 配置（与 DSH 对齐；DSH 在 profiles/web/cordis.patch.yml 用 provider
# deepglint2, api=openai-completions, baseURL=https://token.glint-mvt.com/v1,
# model=deepseek-v4-flash-0731, apiKeyEnv=DEEPGLINT2_API_KEY）
# --------------------------------------------------------------------------- #
@dataclass
class LLMConfig:
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    api_key: str = ""
    timeout: int = 300
    max_retries: int = 3


def load_llm_config(args) -> LLMConfig:
    """解析 LLM 配置。优先级：命令行 > .env > 环境变量 DEEPGLINT2_API_KEY > DSH 默认。"""
    cfg = LLMConfig()
    cfg.base_url = args.llm_base_url or os.environ.get("LLM_BASE_URL") or DEFAULT_BASE_URL
    cfg.model = args.llm_model or os.environ.get("LLM_MODEL") or DEFAULT_MODEL
    cfg.timeout = args.timeout
    cfg.max_retries = args.max_retries

    key = args.api_key
    if not key:
        key = os.environ.get("DEEPGLINT2_API_KEY") or os.environ.get("LLM_API_KEY")
    if not key:
        # 从项目 .env 读 LLM_API_KEY（若有）
        envf = ROOT / ".env"
        if envf.exists():
            for line in envf.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("LLM_API_KEY="):
                    key = line.split("=", 1)[1].strip()
                    break
    if not key:
        raise SystemExit(
            "未找到 LLM API key：请设置环境变量 DEEPGLINT2_API_KEY（同 DSH）或 LLM_API_KEY，"
            "或用 --api-key 传入。"
        )
    cfg.api_key = key
    return cfg


# --------------------------------------------------------------------------- #
# 术语裁切（决议 #9）：从英文 wikitext 提取候选专名 → 只送给 LLM 相关子集
# --------------------------------------------------------------------------- #
def extract_en_terms(wikitext):
    """从 wikitext 提取候选专名：[[内链]]目标 + 正文大写词（启发式）。"""
    code = mwparserfromhell.parse(wikitext)
    terms = set()
    for tl in code.filter_wikilinks():
        tgt = str(tl.title).strip()
        if not tgt.lower().startswith(("file:", "image:", "category:")):
            terms.add(tgt)
    body = code.strip_code().strip()
    for m in re.finditer(r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)\b", body):
        if len(m.group(1)) > 2:
            terms.add(m.group(1))
    return terms


def load_glossary(path: Path):
    d = json.loads(path.read_text(encoding="utf-8"))
    return d.get("terms", d)


def slice_glossary(glossary, en_terms):
    """返回命中译名表的子集 {EN: zh}，按 EN 排序，供放进提示词。"""
    return {t: glossary[t] for t in sorted(en_terms) if t in glossary}


# --------------------------------------------------------------------------- #
# Infobox 值确定性翻译（决议 #4 落地）：Infobox「字段 = 值」的专名按译名表统一替换。
# 结构化短字段交给确定性替换更可靠，不依赖 LLM 是否记得把值也翻成中文。
# --------------------------------------------------------------------------- #
def _sub_glossary_in_string(value: str, gloss: dict) -> str:
    """对单值做译名替换；返回替换后的字符串。

    - 优先整值匹配：把整个值（含 [[...]] 包裹的目标）视为一个整体，若命中单一译名词条则整值替换。
    - 其次最长匹配优先的片段替换（避免 "Seran" 抢在 "Seran Range" 之前）。
    - 图片文件名（含扩展名/File:）不替换。
    """
    if re.search(r"(?i)(File:|Image:)|\.(png|jpe?g|gif|webp|svg)(\||$)", value):
        return value
    # 整值匹配：去掉 [[ ]] 包裹后整体查表（如 [[Mistborn: The Final Empire]]）
    bare = re.sub(r"^\[\[(.*?)\]\]$", r"\1", value.strip())
    if bare in gloss and gloss[bare].get("zh"):
        zh = gloss[bare]["zh"]
        return "[[" + zh + "]]" if bare != value.strip() else zh
    # 片段替换：按长度降序，长词条优先
    terms = sorted(gloss, key=len, reverse=True)
    out = value
    for t in terms:
        zh = gloss[t].get("zh")
        if not zh:
            continue
        # 链接目标形式
        out = re.sub(r"\[\[" + re.escape(t) + r"\]\]", "[[" + zh + "]]", out)
        # 裸词形式（词边界）
        out = re.sub(r"(?<![A-Za-z])" + re.escape(t) + r"(?![A-Za-z])", zh, out)
    return out


def _find_infobox_block(text: str, start: int) -> int:
    """从 text[start]（'{{'）平衡花括号找模板结束位置。返回闭合 '}}' 后的位置；失败 -1。"""
    depth = 0
    i = start
    n = len(text)
    while i < n:
        if text.startswith("{{", i):
            depth += 1
            i += 2
        elif text.startswith("}}", i):
            depth -= 1
            i += 2
            if depth == 0:
                return i
        else:
            i += 1
    return -1


def translate_infobox_values(wikitext: str, glossary: dict) -> dict:
    """把 wikitext 开头 {{Infobox X ...}} 里各命名参数的值按译名表翻译。

    返回 (modified_wikitext, 替换统计 {参数名: (原文值→新值)} )。
    - 只改 Infobox；不改任何参数名；无译名的不动。
    - 逐行处理（convert_templates.py 输出为一行一参数 `| 键    = 值`），
      精确保留每行格式，避免 mwparserfromhell 重序列化把多行 Infobox 压成一行。
    """
    m = re.search(r"\{\{Infobox\b", wikitext, re.IGNORECASE)
    if not m:
        return wikitext, {}
    start = m.start()
    end = _find_infobox_block(wikitext, start)
    if end < 0:
        return wikitext, {}

    block = wikitext[start:end]
    stats = {}
    out_lines = []
    param_re = re.compile(r"^(\|\s*[^|=]+\s*=\s*)(.*)$")
    for ln in block.split("\n"):
        pm = param_re.match(ln)
        if pm:
            key = pm.group(1)
            val = pm.group(2)
            # 值内部若还藏着未闭合等价的子模板（如图片），跳过该行
            new_val = _sub_glossary_in_string(val, glossary)
            if new_val != val:
                param_name = key.strip().lstrip("|").strip()
                stats[param_name] = (val, new_val)
                out_lines.append(key + new_val)
            else:
                out_lines.append(ln)
        else:
            out_lines.append(ln)
    new_block = "\n".join(out_lines)
    return wikitext[:start] + new_block + wikitext[end:], stats


# --------------------------------------------------------------------------- #
# 决议#13 确定性保护：{{Quote}} 台词、{{columns}} 称号/名单等「原文引用」块
# 在送 LLM 前用唯一占位符替换，强制模型原样保留，翻译后再把英文原文填回。
# 这样模型怎么翻正文都不会污染原文引用块；分块/丢内容也不受影响。
# --------------------------------------------------------------------------- #
_ORIGINAL_TEXT_TYPES = ("quote", "columns", "sidequote")


def _type_label(t: str) -> str:
    return {"quote": "Quote 台词", "columns": "columns 称号/名单", "sidequote": "sidequote 旁引"}.get(t, t)


def mask_protected_blocks(wikitext: str):
    """把顶层 {{Quote}}/{{columns}}/{{sidequote}} 替换为唯一占位符。

    返回 (masked_wikitext, registry)。
    registry: [{'token','type','source','order'}]，token 形如 %%ORIGINAL_BLOCK_N%%。
    仅处理"顶层"模板（不被其它模板包裹），避免把嵌在 Infobox 里的错当原文。
    """
    code = mwparserfromhell.parse(wikitext)
    registry = []
    n = 0
    new_nodes = []
    for node in code.nodes:
        if isinstance(node, mwparserfromhell.nodes.Template):
            name = re.sub(r"^(?:Template|模板)\s*:", "", str(node.name).strip(), flags=re.IGNORECASE)
            key = name.lower()
            if key in _ORIGINAL_TEXT_TYPES:
                n += 1
                token = f"%%ORIGINAL_BLOCK_{n}%%"
                source = str(node).strip()
                registry.append({"token": token, "type": key, "source": source, "order": n})
                new_nodes.append(mwparserfromhell.nodes.Text(token + "\n"))
                continue
        new_nodes.append(node)
    code.nodes = new_nodes
    return str(code), registry


def unmask_protected_blocks(translated_body: str, registry: list[dict]) -> str:
    """把译文里的占位符 %%ORIGINAL_BLOCK_N%% 替换回英文原文块。

    返回 (body, missing_tokens)；missing_tokens 为模型漏掉的占位符（人工复核）。
    """
    out = translated_body
    missing = []
    for blk in registry:
        token = blk["token"]
        if token in out:
            out = out.replace(token, blk["source"])
        else:
            missing.append(blk["token"])
    return out, missing


# --------------------------------------------------------------------------- #
# 分块（超长词条支持）。按 == 章节 == / === 小节 === 边界切，Infobox+导语固定 chunk0。
# --------------------------------------------------------------------------- #
@dataclass
class Chunk:
    index: int
    text: str
    title: str = ""          # 该块的首个标题（纯文本，用于提示词定位）
    char_count: int = 0


_HEADING_RE = re.compile(r"^(={2,4})\s*(.*?)\s*\1[ \t]*$")


def split_sections(wikitext: str):
    """把 wikitext 按标题行切成段。返回 [(heading, level, text, body)]。

    - heading：''标题行原文''（含顶格 `==`，须原样保留）；无标题段为 None。
    - 首段为「头部」（Infobox + 导语，heading=None）。
    - 用行级正则匹配 `== X ==`/`=== X ===`，行首必须是标题（顶格），
      因此不会误切处在一行中间、或模板参数值里的等号。
    """
    lines = wikitext.split("\n")
    segments = []           # 累积段
    cur_heading = None      # (level, text) 标题信息（应输出原行）
    cur_head_line = None
    cur_body: list[str] = []

    def flush():
        nonlocal cur_heading, cur_head_line, cur_body
        if cur_head_line is not None or cur_body:
            segments.append((cur_head_line, cur_heading[0] if cur_heading else 0,
                             cur_heading[1] if cur_heading else "", "\n".join(cur_body)))
            cur_heading, cur_head_line, cur_body = None, None, []

    for ln in lines:
        m = _HEADING_RE.match(ln)
        if m:
            flush()
            cur_heading = (len(m.group(1)), m.group(2).strip())
            cur_head_line = ln  # 原样保留标题行（含顶格等号）
        else:
            cur_body.append(ln)
    flush()
    if not segments:
        segments = [(None, 0, "", wikitext)]
    return segments


def chunk_wikitext(wikitext: str, max_chars: int):
    """把 wikitext 切成 ≤ max_chars 的块。

    规则：
      - 头部（Infobox+导语，首个无标题段）固定为 chunk0。
      - 按段累加；加入下一段会超过 max_chars 时开新块（块边界必在章节边界）。
      - 单段自身超过 max_chars 时独成一块并告警（不硬切，避免破坏模板/语义）。
      - 块内字符数按原始文本计（近似 token 量）。
    """
    segments = split_sections(wikitext)
    chunks: list[Chunk] = []
    cur_parts: list[str] = []
    cur_chars = 0
    cur_title = ""
    warning_oversized: list[str] = []

    def flush():
        nonlocal cur_parts, cur_chars, cur_title
        if cur_parts:
            text = "\n".join(cur_parts)
            chunks.append(Chunk(index=len(chunks), text=text, title=cur_title, char_count=cur_chars))
            cur_parts, cur_chars, cur_title = [], 0, ""

    first = True
    for head_line, level, text, body in segments:
        # 重建段原文（连标题行）
        seg_text = (head_line + "\n" + body) if head_line else body
        seg_chars = len(seg_text)
        if first:
            # 头部固定 chunk0
            cur_parts.append(seg_text)
            cur_chars += seg_chars
            cur_title = text
            first = False
            continue
        if seg_chars > max_chars:
            flush()
            chunks.append(Chunk(index=len(chunks), text=seg_text, title=text, char_count=seg_chars))
            warning_oversized.append(text or "（无标题超长段）")
            continue
        if cur_chars + seg_chars > max_chars:
            flush()
        cur_parts.append(seg_text)
        cur_chars += seg_chars
        cur_title = text
    flush()

    return chunks, warning_oversized


# --------------------------------------------------------------------------- #
# OpenAI 兼容 chat completions（与 DSH 的 openai-completions 一致）
# --------------------------------------------------------------------------- #
def llm_chat(cfg: LLMConfig, messages, max_output_tokens=8000, temperature=0.2):
    """调用 OpenAI 兼容 /chat/completions。失败按指数退避重试。"""
    url = cfg.base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": cfg.model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_output_tokens,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={
            "Authorization": f"Bearer {cfg.api_key}",
            "Content-Type": "application/json",
        },
    )
    last_err = None
    for attempt in range(cfg.max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=cfg.timeout) as resp:
                body = resp.read().decode("utf-8")
                obj = json.loads(body)
            content = obj["choices"][0]["message"]["content"]
            return content
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError, json.JSONDecodeError) as e:
            last_err = e
            if attempt < cfg.max_retries:
                time.sleep(min(2 ** attempt, 10))
    raise RuntimeError(f"LLM 调用失败（重试 {cfg.max_retries} 次后）：{last_err}")


# --------------------------------------------------------------------------- #
# 提示词构造
# --------------------------------------------------------------------------- #
SYSTEM_PROMPT = """你是一名精通「迷雾之子」(Mistborn) 系列英文→简体中文维基编辑的译者，负责把 The Coppermind Wiki 的词条翻译成红铜智库中文维基的 wikitext。

翻译硬规则（必须严格遵守）：
1. 【保留结构】所有模板 {{...}}、内链 [[...]]、引用 {{book ref|...}}/{{date|...}}/{{image|...}}/{{file ref|...}}/{{for|...}}/{{columns|...}} 等一律原样保留、位置不变。不要增删模板与参数，不要改变模板名。只翻译模板之外的自然语言正文。
2. 【专名按译名表】专有名词一律按「译名表」翻译（含正文与 {{Infobox}} 里 `字段 = 值` 的值）；译名表没有的疑似专名**保留英文**，并列入 untranslated_terms。图片文件名、ISBN、日期数字、书目代号等非译文内容的**值**原样保留不译。
3. 【原文引用不译】(决议#13)：文中可能出现形如 %%ORIGINAL_BLOCK_1%% 的占位符，它们是**小说原著引文**（台词/称号列表）的替身。**必须原样保留、不翻译、不增删、不改动**（管道自会填回英文原文）。除此之外，正常叙述正文照常翻译。
4. 【章节标题】== 章节 == / === 小节 === 标题翻译成简体中文；标题行顶格的等号数目与格式必须原样保留。
5. 【首行(仅块0)】第一条正文行='''中文译名'''，并在其后紧跟 {{en|英文词条名}}。只有块0需要，其余块不得重复加。
6. 【输出格式】只输出一个 JSON 对象，不要 markdown 代码围栏、不要任何额外文字：
   {"translation": "<翻译后的完整本块 wikitext，换行转义为\\n，禁止截断/省略>", "untranslated_terms": [{"en": "<保留英文的专名>", "reason": "<原因>", "zh": "<已定译名则填，否则省略>"}]}
   translation 必须包含你收到的**整块**全部内容（含所有模板、占位符、参考文献/分类），不得丢失。
"""


def build_user_prompt(chunk: Chunk, glossary_slice: dict, en_title: str, is_first: bool) -> str:
    gloss_lines = "\n".join(f"- {en} = {data['zh']}" for en, data in glossary_slice.items()) if glossary_slice else "（（本文无命中译名表））"
    parts = []
    parts.append("译名表（仅与本词条相关的子集，优先采用）:\n" + gloss_lines)
    if is_first:
        parts.append(
            "这是**第 1 块**（含 Infobox + 导语）。英文词条名 = " + en_title +
            "。请把条目标题译成简体中文，并在首行的 '''中文译名''' 之后紧跟 {{en|" + en_title + "}}。"
        )
    else:
        parts.append("这是**后续块**（中间章节）。除非已有译名表，否则不要重复加 {{en}}/{{CmPermission}}。")
    if chunk.title:
        parts.append("本块起于章节：\"" + chunk.title + "\"。")
    parts.append("请翻译以下 wikitext（完整输出，禁止截断）:\n\n" + chunk.text)
    return "\n\n".join(parts)


# --------------------------------------------------------------------------- #
# 逐块翻译
# --------------------------------------------------------------------------- #
def parse_chunk_reply(content: str):
    """宽松解析模型返回的 JSON（在 { 与最后一个 } 之间截取，容忍围栏/前后文字）。"""
    content = content.strip()
    # 去掉可能的 ```json ... ``` 围栏
    if content.startswith("```"):
        content = re.sub(r"^```[a-zA-Z]*\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    # 提取 JSON 对象
    idx = content.find("{")
    if idx >= 0:
        try:
            return json.loads(content[idx: content.rfind("}") + 1])
        except json.JSONDecodeError:
            pass
    raise ValueError("无法解析 LLM 返回的 JSON：\n" + content[:500])


def translate_chunk(cfg: LLMConfig, chunk: Chunk, glossary_slice: dict, en_title: str, is_first: bool,
                    max_output_tokens: int = 8000):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(chunk, glossary_slice, en_title, is_first)},
    ]
    reply = llm_chat(cfg, messages, max_output_tokens=max_output_tokens)
    data = parse_chunk_reply(reply)
    translation = str(data.get("translation", "")).strip()
    untranslated = data.get("untranslated_terms") or []
    if not translation:
        raise ValueError("LLM 返回的 translation 为空")
    return translation, untranslated


# --------------------------------------------------------------------------- #
# 组装与校验
# --------------------------------------------------------------------------- #
def validate_translation(text: str, src_chunk: Chunk) -> list[str]:
    """轻量校验：译文是否丢关键模板/内链。返回问题清单（不阻断）。"""
    problems = []
    for pat, name in [
        (r"\{\{[Ii]nfobox\b", "Infobox"),
        (r"\{\{date\|", "date"),
        (r"\{\{book ref\|", "book ref"),
        (r"\[\[", "[["),
    ]:
        if re.search(pat, src_chunk.text) and not re.search(pat, text):
            problems.append(f"原文含 {name} 但译文缺失")
    return problems


def assemble(title_en: str, revid, chunk_results, no_wrap: bool, target_wiki: str,
             registry: list[dict] | None = None):
    """把各块译文拼成完整 wikitext，填回决议#13 的英文原文占位符，并插入页面级包装（决议#10-12）。"""
    body = "\n".join(t for t, _ in chunk_results).strip("\n") + "\n"
    # 决议#13：把 %%ORIGINAL_BLOCK_N%% 填回英文原文（若模型翻掉/漏了一并汇报）
    if registry:
        body, missing_tokens = unmask_protected_blocks(body, registry)
        if missing_tokens:
            sys.stderr.write("[提醒] 以下原文占位符未在译文中保留（模型漏掉，人工复核）：" + ", ".join(missing_tokens) + "\n")
    untranslated = []
    seen = set()
    # 决议#13：原文引用块（{{Quote}}/{{columns}}）确定性填回英文原文，也确定性列入
    # untranslated_terms，标记「需查中译本」，供人工查到中译本后替换。
    if registry:
        for blk in registry:
            ut = {
                "en": f"{_type_label(blk['type'])}（占位符 {blk['token']}）",
                "reason": "原文引用（" + blk["type"] + "），需查中译本对应译文（决议#13）",
            }
            key = (ut["en"], ut["reason"])
            if key not in seen:
                seen.add(key)
                untranslated.append(ut)
    for _, ut in chunk_results:
        for item in ut:
            if not isinstance(item, dict):
                continue
            k = (item.get("en"), item.get("reason"))
            if k in seen:
                continue
            seen.add(k)
            untranslated.append(item)

    if no_wrap:
        meta_note = "纯正文翻译（--no-wrap，未加页面级包装）"
    else:
        body = "{{CmPermission|" + title_en + "}}\n" + body
        if "{{ensync|" not in body:
            body = body.rstrip("\n") + "\n{{ensync|" + str(revid) + "}}\n"
        meta_note = "已加页面级包装 {{CmPermission}}（顶）/{{en}}（首行）/{{ensync}}（尾，revid=" + str(revid) + "）"

    contract = {
        "meta": {
            "title_en": title_en,
            "revision_id": revid,
            "target_wiki": target_wiki,
            "format": "mediawiki",
            "note": meta_note,
        },
        "translation": body,
        "untranslated_terms": untranslated,
    }
    return contract


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="英文 converted wikitext → 中文 wikitext，产出 translation.json 契约")
    ap.add_argument("--title", required=True, help="快照标题（读取 en_snapshot/<标题>/wikitext.txt，内存里转成转换后形态）")
    ap.add_argument("--glossary", default=str(DEFAULT_GLOSSARY))
    ap.add_argument("--max-chars", type=int, default=7000, help="每块最大字符数（超长词条按此切块）")
    ap.add_argument("--concurrency", type=int, default=1, help="并发翻译块数（默认 1）")
    ap.add_argument("--dry-run", action="store_true", help="只做分块+提示词预演，不调用 LLM")
    ap.add_argument("--no-wrap", action="store_true", help="不插入页面级包装，只输出纯正文")
    ap.add_argument("--llm-base-url", default=os.environ.get("LLM_BASE_URL"))
    ap.add_argument("--llm-model", default=os.environ.get("LLM_MODEL"))
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--max-retries", type=int, default=3)
    ap.add_argument("--max-output-tokens", type=int, default=8000, help="单块 LLM 最大输出 token（长块可调大）")
    ap.add_argument("--target-wiki", default=DEFAULT_WIKI)
    args = ap.parse_args()

    d = EN_SNAPSHOT / args.title.replace("/", "_")
    wt_file = d / "wikitext.txt"
    if not wt_file.exists():
        raise SystemExit(f"找不到英文快照 {wt_file}。请先运行 scripts/fetch_en.py {args.title}")
    raw_wikitext = wt_file.read_text(encoding="utf-8")

    # 用当前 convert_templates.py 在内存里重转一遍，避免依赖可能过期的 converted.txt
    # （旧版转换器曾把 {{quote}} 内容清空——必须用最新转换逻辑保证 #13 引文保留）。
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location("convert_templates_mod", HERE / "convert_templates.py")
    _ct = _ilu.module_from_spec(_spec)
    sys.modules[_spec.name] = _ct
    _spec.loader.exec_module(_ct)
    rules = _ct.load_rules()
    wikitext, _convert_report = _ct.convert_wikitext(raw_wikitext, rules)

    # 译名表裁切
    glossary = load_glossary(Path(args.glossary))
    en_terms = extract_en_terms(wikitext)
    gloss_slice = slice_glossary(glossary, en_terms)

    # Infobox「字段 = 值」确定性翻译（决议#4）：把文首 {{Infobox X}} 的专名值按译名表替换，
    # 让结构化短字段不依赖 LLM 是否记得翻值。仅改 Infobox，不动正文。
    wikitext, infobox_stats = translate_infobox_values(wikitext, glossary)
    if infobox_stats:
        sys.stderr.write("[Infobox 值替换]（按译名表确定性替换，正文翻译仍交给 LLM）:\n")
        for k, (old, new) in infobox_stats.items():
            sys.stderr.write(f"  {k}: {old} -> {new}\n")

    # 决议#13：把 {{Quote}}/{{columns}} 等原文块换成唯一占位符，模型原样保留，翻完再填回英文原文
    wikitext, registry = mask_protected_blocks(wikitext)
    if registry:
        sys.stderr.write(f"[原文块保护]（决议#13，占位符替换后填回英文原文）: {len(registry)} 处\n")

    # 从 snapshot meta.json 取 revid（ensync 用）
    revid = "CHANGE_ME_REVID"
    meta_p = d / "meta.json"
    if meta_p.exists():
        try:
            revid = json.loads(meta_p.read_text(encoding="utf-8")).get("revid") or revid
        except Exception:
            pass

    # 分块（对占位符化后的 wikitext 切；占位符不在章节边界内被切开）
    chunks, oversized = chunk_wikitext(wikitext, args.max_chars)

    if oversized:
        sys.stderr.write("[警告] 以下章节单节超过 max_chars，已独成一块（未在内部硬切，可能仍超限）:\n")
        for t in oversized:
            sys.stderr.write(f"  - {t}\n")
    sys.stderr.write(f"[分块] {args.title}: 共 {len(chunks)} 块（max_chars={args.max_chars}），"
                     f"译名表命中 {len(gloss_slice)} 条。\n")
    for c in chunks:
        sys.stderr.write(f"  chunk{c.index}: {c.char_count} 字符「{c.title or '(头部)'}」\n")

    if args.dry_run:
        # 预演：打印每块提示词概要与长度，不调用 LLM
        for c in chunks:
            prompt = build_user_prompt(c, gloss_slice, args.title, is_first=(c.index == 0))
            sys.stderr.write(f"\n--- 提示词 chunk{c.index}（{len(prompt)} 字符）一句预览 ---\n")
            sys.stderr.write(prompt[:300].replace("\n", " ") + "\n")
        sys.stderr.write("[dry-run] 预演完成，未调用 LLM，未写文件。\n")
        return 0

    cfg = load_llm_config(args)

    # 逐块翻译（支持并发，默认串行）
    chunk_results = []
    errs = []
    if args.concurrency > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
            futs = {
                ex.submit(translate_chunk, cfg, c, gloss_slice, args.title, c.index == 0,
                          args.max_output_tokens): c.index
                for c in chunks
            }
            ordered = sorted(futs, key=lambda f: futs[f])
            for f in ordered:
                try:
                    chunk_results.append(f.result())
                except Exception as e:
                    errs.append((futs[f], str(e)))
    else:
        for c in chunks:
            sys.stderr.write(f"[翻译] chunk{c.index}/{len(chunks)-1}（{c.title or '头部'}）…\n")
            try:
                chunk_results.append(translate_chunk(cfg, c, gloss_slice, args.title, c.index == 0,
                                                     args.max_output_tokens))
            except Exception as e:
                errs.append((c.index, str(e)))

    if errs:
        sys.stderr.write("[失败] 以下块翻译失败：\n")
        for idx, e in errs:
            sys.stderr.write(f"  chunk{idx}: {e}\n")
        raise SystemExit(f"共 {len(errs)} 块失败，未写 translation.json。可用 --dry-run 预演排障。")

    # 组装
    contract = assemble(args.title, revid, chunk_results, args.no_wrap, args.target_wiki, registry)

    out_json = d / "translation.json"
    out_txt = d / "translation.txt"
    out_json.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
    out_txt.write_text(contract["translation"], encoding="utf-8")

    # 汇总校验
    all_problems = []
    for i, (t, _) in enumerate(chunk_results):
        all_problems.extend(validate_translation(t, chunks[i]))
    sys.stderr.write(f"[完成] 已写 {out_json} 与 {out_txt}；untranslated_terms 共 {len(contract['untranslated_terms'])} 条。\n")
    if all_problems:
        sys.stderr.write("[提醒] 校验发现问题（不阻断，人工复核）：\n")
        for p in all_problems:
            sys.stderr.write("  - " + p + "\n")
    return 0


if __name__ == "__main__":
    main()
