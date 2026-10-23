#!/usr/bin/env python3
"""
翻译管道（决议 #4/#9/#13）：英文 converted wikitext → 中文 wikitext，产出符合契约的 translation.json。

输入：en_snapshot/<标题>/wikitext.txt（脚本内部用最新 convert_templates.py 转成转换后形态，不依赖脆弱的 converted.txt）
输出：en_snapshot/<标题>/translation.json
      {
        "meta": { "title_en", "revision_id", "target_wiki", "format":"mediawiki",
                  "chunks": N, "note": ... },
        "translation": "<含全部页面级包装({{AITranslation}}/{{CmPermission}}/{{en}}/{{ensync}})的完整中文 wikitext>",
        "untranslated_terms": [ { "en":..., "reason":... }, ... ]
      }
  （同步落 translation.txt —— 与 Allik 样板一致的纯 wikitext 视图）

关键能力：
  - 超长词条分块：按 `== 章节 ==` / `=== 小节 ===` 边界切块，每块 ≤ --max-chars，Infobox+导语固定为 chunk0，
    绝不在一节/一模板内部切开；单节过长时独成一块并告警。
  - 术语裁切（决议 #9）：仅把本文出现的译名词条切片送给 LLM，省 token。
  - LLM 配置与 DSH 一致：默认 base_url=https://token.glint-mvt.com/v1、model=deepseek-v4-flash-0731
    （2026-10-20 用户裁定换回 deepseek），api key 从环境变量 LLM_API_KEY 读取（可 --api-key / .env 覆盖）。
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
  --no-wrap        不插入页面级包装（{{AITranslation}}/CmPermission/en/ensync），仅输出纯正文翻译
  --llm-base-url   覆盖 baseURL（默认同 DSH：https://token.glint-mvt.com/v1）
  --llm-model      覆盖模型（默认 deepseek-v4-flash-0731）
  --api-key        覆盖 API key（默认读环境变量 DEEPGLINT2_API_KEY）
  --timeout        单次 LLM 请求超时秒（默认 300）
  --max-retries    单块失败重试次数（默认 3）
"""
from __future__ import annotations

import argparse
import html
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
DEFAULT_COMMON = ROOT / "dict" / "common.json"
KEEP_EN_FILE = ROOT / "dict" / "keep_en.json"
ZHWIKI_TITLES_FILE = ROOT / "dict" / "zhwiki_titles.json"
ZHWIKI_ALIASES_FILE = ROOT / "dict" / "zhwiki_aliases.json"
DEFAULT_BASE_URL = "https://token.glint-mvt.com/v1"
DEFAULT_MODEL = "deepseek-v4-flash-0731"  # 2026-10-20 用户裁定换回（mimo 试跑 20 条不如 deepseek；.env LLM_MODEL / --llm-model 可覆盖）
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
    # 推理开关："disabled"（默认）| "enabled"。实测 deepseek-v4-flash-0731 对长 wikitext
    # 翻译块会病态地无限推理（reasoning 吃光 max_tokens，content 为空 -> JSON 解析失败），
    # 关闭 thinking 后稳定产出。保留 enabled 供需要深思的模型/任务切换。
    thinking: str = "disabled"
    # 推理强度（OpenAI 兼容 reasoning_effort）："minimal"|"low"|"medium"|"high"|缺省。
    # 2026-10-21 豆包 seed-2-1-turbo 实测：minimal 会把独白写进 content（同 disabled
    # 的坑，JSON 必坏）；low 稳定产出干净 JSON 且延迟可控（~100s/块）；不传则 auto
    # 思考量更大更慢。仅在设置时随请求发送。
    effort: str = ""


def _load_env_file():
    """把项目 .env 里的 LLM_*/DEEPGLINT2_* 键灌入 os.environ（setdefault，不覆盖已有）。"""
    envf = ROOT / ".env"
    if not envf.exists():
        return
    for line in envf.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        if k.startswith(("LLM_", "DEEPGLINT2_")):
            os.environ.setdefault(k, v.strip())


def load_llm_config(args) -> LLMConfig:
    """解析 LLM 配置。优先级：命令行 > 环境变量 > .env > 内置默认。"""
    _load_env_file()
    cfg = LLMConfig()
    cfg.base_url = args.llm_base_url or os.environ.get("LLM_BASE_URL") or DEFAULT_BASE_URL
    cfg.model = args.llm_model or os.environ.get("LLM_MODEL") or DEFAULT_MODEL
    cfg.timeout = args.timeout or int(os.environ.get("LLM_TIMEOUT", "300"))
    cfg.max_retries = args.max_retries
    cfg.thinking = os.environ.get("LLM_THINKING") or "disabled"
    cfg.effort = (os.environ.get("LLM_EFFORT") or "").strip()

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
    """从 wikitext 提取候选专名：[[内链]]目标 + 正文大写词（启发式）。

    review 修复（方案2a）：除大写词外，也捕获**小写**候选词（如 kandra/metalmind/
    harmonium/skaa/noble 等，译名表键本身可能是小写），否则这些小写金属/概念词不会进
    gloss_slice → LLM 看不到译名 → 误报「未收录」且正文残留英文。
    """
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
    # 大写短语里的**单个**大写词也单独捕获（如 "Lady Allrianne Ladrian" 分离出 Allrianne、
    # "Mr. Suit" 里 Suit 单独命中），否则这类带头衔/句点的裸正文专名进不了切片 →
    # LLM 得不到规范译名、自造音译（如 苏特先生/阿莉安 而非 西装先生/奥瑞安妮）。
    # slice_glossary 只会保留命中译名表的，故无害。
    for m in re.finditer(r"\b[A-Z][a-z]{3,}\b", body):
        terms.add(m.group(0))
    # 小写候选：单个[阿尔法]词（≥3 字母），用于命中译名表里的小写键/屈折形式。
    # 数量可能较多，但 slice_glossary 只会保留「命中译名表」的，噪声会在此被过滤。
    for m in re.finditer(r"\b([a-z][a-z\-]+)\b", body):
        w = m.group(1)
        if len(w) >= 3 and not w.lower().startswith(("the ", "and ", "for ")):
            terms.add(w)
    return terms


def _norm_glossary_key(s: str) -> str:
    """把词条键/正文形式归一化用于「大小写/屈折/冠词」模糊匹配。

    规则：去前导冠词（The/A/An）、去尾属格 's/’s、去尾复数 s（±撇号），再小写。
    例：The Set→set；Set→set；kandra/Kandra/kandra's→kandra；metalminds→metalmind。
    """
    t = re.sub(r"\s+", " ", s.strip())
    t = re.sub(r"^(the|a|an)\s+", "", t, flags=re.I)
    t = re.sub(r"[:’']\s*s$", "", t)
    t = re.sub(r"s$", "", t)
    return t.lower()


def build_norm_glossary(glossary):
    """归一化译名索引：{norm_key: (规范英文键, 词条)}，优先保留更长(更具体)的键。

    让正文里的屈折/大小写/缺冠词形式能命中规范词条（如 Set 命中 The Set）。
    仅收录有 zh 的词条（zh_variable 无固定译名者不入，避免 LLM 拿到 None）。
    """
    idx = {}
    for k, entry in glossary.items():
        zh = (entry or {}).get("zh")
        if not zh:
            continue
        nk = _norm_glossary_key(k)
        if nk not in idx or len(k) > len(idx[nk][0]):
            idx[nk] = (k, entry)
    return idx


# 通用英文词（小写正文里出现时，不自动按译名表匹配）。
# 用途：extract_en_terms 额外捕获小写词后，若不设防，常见英文词会误命中专名译名
# （如正文小写 red/blue/well → 专名 雷德/布卢/威尔斯，或动词/名词/数词被误翻）。
# 仅对「全小写正文形态」生效；大写专名（如 Set）仍按规范归一匹配。
GENERIC_EN_STOPLIST = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with", "at", "by",
    "as", "from", "is", "are", "was", "were", "be", "been", "being", "do", "does", "did",
    "have", "has", "had", "this", "that", "these", "those", "it", "its", "he", "she",
    "they", "we", "you", "his", "her", "their", "our", "your", "him", "them", "not",
    "no", "but", "if", "so", "such", "which", "what", "when", "where", "who", "why",
    "how", "will", "would", "can", "could", "should", "shall", "may", "might", "must",
    "into", "over", "under", "about", "after", "before", "between", "through", "during",
    "same", "very", "only", "just", "also", "than", "then", "there", "here", "one",
    "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
    "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
    "nineteen", "twenty", "thirty", "forty", "fifty", "hundred", "thousand",
    # 与专名/金属译名撞车的通用词、颜色词、动词、数词
    "red", "blue", "green", "yellow", "black", "white", "well", "felt", "dug", "rough",
    "trap", "traps", "chain", "chains", "path", "paths", "collapse", "origin",
    "origins", "sequence", "resolution", "sentry", "consortium", "governor",
    "governors", "senate", "citizen", "citizens", "butler", "crack", "rioting",
    "set", "sets",
    "mark", "marks", "side", "back", "front", "top", "bottom", "left", "right", "old",
    "new", "good", "bad", "big", "small", "hard", "soft", "high", "low", "far",
    "near", "long", "short", "full", "empty", "open", "closed", "light", "dark",
    "city", "town", "street", "road", "house", "door", "window", "room", "wall",
    "floor", "table", "water", "fire", "day", "night", "year", "month", "week",
    "hour", "minute", "second", "time", "person", "man", "woman", "child", "people",
    "life", "death", "love", "war", "peace", "king", "queen", "court", "law",
    "order", "power", "world", "land", "sea", "river", "mountain", "valley", "north",
    "south", "east", "west", "greater", "less", "more", "most", "few", "many",
    "much", "little", "human", "humans", "survivors", "survivor",
}


def _is_lowercase(t: str) -> bool:
    """判断是否为全小写正文形态（用于决定是否套用通用词停用表）。"""
    return any(ch.isalpha() for ch in t) and all(ch.islower() or ch in "-'’ " for ch in t)


def load_glossary(path: Path):
    d = json.loads(path.read_text(encoding="utf-8"))
    return d.get("terms", d)


def load_merged_glossary(primary: Path, secondary: Path | None = None) -> dict:
    """合并加载译名表：primary（如 mistborn.json）为主，secondary（如 common.json）为辅。

    common.json 是跨站通用词条（如子页后缀 Statistical analysis=数据分析），与主译名表并列、
    不混写进 mistborn.json。合并规则：主表键优先（同键以主表为准），次表仅补主表没有的键。
    返回 {en_key: entry}；entry 保持各表自带字段（zh/note/...）。
    """
    merged = dict(load_glossary(primary))
    if secondary is not None and secondary.exists():
        merged.update({k: v for k, v in load_glossary(secondary).items() if k not in merged})
    return merged


def load_keep_en(path: Path = KEEP_EN_FILE) -> list[str]:
    """读取「保留英文」名单（dict/keep_en.json）。

    规则 2 要求：译名表/中文书证均未收录、又无官方中文译名的疑似专名**保留英文**并列入
    untranslated_terms，不得自造译名。keep_en 名单正是这类词的显式提示：LLM 在块里遇到
    这些词（书名/作品名等）时保留英文，避免「像专名就自译」（如 The Long Way In→长路漫漫）。
    """
    if not path.exists():
        return []
    d = json.loads(path.read_text(encoding="utf-8"))
    return d.get("terms", [])


def resolve_zh_title(title_en: str, glossary: dict | None = None) -> str:
    """把英文快照标题解析为中文页标题（供写站目标页使用）。

    背景：batch.py 曾直接以「前缀+英文标题」写站（bot测试:Ghostbloods），而正文词条已按
    译名表译为中文（鬼血会）→ 标题与正文割裂。这里把标题解析优先级：
      1. 合并译名表命中且有非空 zh -> 用中文（Ghostbloods -> 鬼血会）
      2. 中文站既有页面（zhwiki_titles 反查，如 Mistborn (series) -> 迷雾之子(系列)，
         中文站已有该页）-> 用既有页面标题
      3. 否则 -> 保留英文（Red (Scadrial)/Demoux (city)/Tyrian Sea 等查无可靠中译名，
        宁可留英文不自造译名，与 keep_en 铁律一致）
    注意 entry 可能是 {"zh": "..."} 或 {"zh": None, ...}（待定），None 视为未命中。
    """
    if glossary is None:
        glossary = load_merged_glossary(DEFAULT_GLOSSARY, DEFAULT_COMMON)
    ent = glossary.get(title_en)
    if isinstance(ent, dict) and isinstance(ent.get("zh"), str) and ent["zh"].strip():
        return ent["zh"].strip()
    if isinstance(ent, str) and ent.strip():
        return ent.strip()
    # 中文站既有页面标题（zhwiki_titles zh->en 反查，同一 en 可能有多个 zh 页面，取第一个）
    try:
        zt = load_zhwiki_titles()
        for zh, en in zt.items():
            if en == title_en and zh and zh.strip():
                return zh.strip()
    except Exception:
        pass
    return title_en


# 命名空间/维护前缀：这些词条不是需要翻译的正文专名（站务页、interwiki 外链、文件/分类）
_KEEP_EN_IGNORE_PREFIXES = (
    "user:", "user talk:", "category:", "file:", "image:", "template:", "module:",
    "wob:", "bws:", "wp:", "wikipedia:", "coppermind: arcanum", "es:", "uk:", "de:",
    "fr:", "ru:", "zh:", "en:", "talk:", "portal:", "draft:",
)
# 属格/数词/普适后缀：拆译判定时跳过（"'s", " s" 等）
_WORD_SPLIT_RE = re.compile(r"[^A-Za-z]+")


def _can_split_translate(phrase: str, glossary: dict, idx: dict) -> bool:
    """贪心判定 phrase 能否完全拆译：每个实词都能命中译名表（或归一命中），
    或属于通用停用词。如 "Mistborn: The Final Empire" = Mistborn(✓)+The(stop)+Final Empire(✓)
    可拆译（迷雾之子/最后帝国都在表）→ 不该保留英文；"The Long Way In" 有 Long/Way
    拆不动 → 应保留英文。用于过滤「形似专名但实际由已收专名组成」的词条。
    """
    tokens = _WORD_SPLIT_RE.split(phrase)
    i = 0
    n = len(tokens)
    while i < n:
        w = tokens[i]
        if not w:
            i += 1
            continue
        if w.lower() in GENERIC_EN_STOPLIST:
            i += 1
            continue
        # 贪心：从当前词起找最长的连续词条（含空格）命中译名表
        matched = False
        for end in range(n, i, -1):
            cand = " ".join(tokens[i:end])
            if not cand:
                continue
            if cand in glossary or idx.get(_norm_glossary_key(cand)):
                matched = True
                i = end
                break
        if matched:
            continue
        # 单词也不命中 → 拆译不了
        return False
    return True


def detect_keep_en_terms(chunk_text: str, glossary: dict, zhwiki_rev: dict | None = None) -> list[str]:
    """动态识别本块「应保留英文」的疑似专名（不再依赖逐页人工 review）。

    信号：''斜体书名'' 与 [[链接目标]]（书名/作品名惯例形态），过滤命名空间前缀；
    排除已在译名表（精确/归一命中）的词；排除能整体拆译的词（如 Mistborn: The Final
    Empire 由已收专名组成）；排除中文站已建页面的词（zhwiki_rev 命中——有可用译名，
    不该保留英文，改由 zhwiki 参考提示给出）。剩余词提示 LLM 保留英文——机制对任意
    页面自动生效，dict/keep_en.json 静态名单仅作为已确认词的补充（两者提示词里合并）。
    """
    idx = build_norm_glossary(glossary)
    candidates = []

    def _ok(t: str) -> bool:
        t = t.strip()
        low = t.lower()
        if len(t) < 3:
            return False
        if low.startswith(_KEEP_EN_IGNORE_PREFIXES):
            return False
        if "/" in t or "#" in t:  # 子页/锚点不是独立专名
            return False
        if t in glossary or idx.get(_norm_glossary_key(t)):
            return False
        if zhwiki_rev and t in zhwiki_rev:  # 中文站已有页面 → 不保留英文
            return False
        if _can_split_translate(t, glossary, idx):
            return False
        return True

    # 1) 内链目标 [[...]]（含 ''[[X]]'' 斜体内链）
    for mm in re.finditer(r"\[\[\s*([^\]|]+?)\s*(?:\|[^\]]*)?\]\]", chunk_text):
        t = mm.group(1).strip()
        if _ok(t) and t not in candidates:
            candidates.append(t)
    # 2) 斜体书名 ''X''（非链接）——排除 '''粗体'''（三个引号里嵌两个引号，会误匹配）
    for mm in re.finditer(r"''([^''\n]{3,80})''", chunk_text):
        # 前后皆单引号 → '''粗体'''，跳过
        if (mm.start() > 0 and chunk_text[mm.start() - 1] == "'") or \
           (mm.end() < len(chunk_text) and chunk_text[mm.end()] == "'"):
            continue
        t = mm.group(1).strip().strip("[]")
        if not re.match(r"^[A-Z][A-Za-z :'.,\-()0-9]*$", t):
            continue  # 斜体只取「大写开头、字母字符」形态（书名/作品名，容忍 (rule book) 后缀）
        if _ok(t) and t not in candidates:
            candidates.append(t)
    return sorted(candidates)


def detect_zhwiki_refs(chunk_text: str, glossary: dict, zhwiki_rev: dict) -> list[tuple[str, str]]:
    """动态识别本块「中文站已有页面」的专名（不在译名表、但中文站有页）。

    返回 [(en, zh_page_title), ...]：提示 LLM 采用中文站页面标题作为译名参考
    （如 Brandon Sanderson → 布兰登·桑德森），而不是保留英文或自造译名。
    仅取内链/斜体形态的本块出现词，避免对普通正文扫词。
    """
    idx = build_norm_glossary(glossary)
    out = []

    def _ref(t: str):
        t = t.strip()
        if len(t) < 3 or "/" in t or "#" in t:
            return None
        if t in glossary or idx.get(_norm_glossary_key(t)):
            return None  # 已进译名表，走译名表即可
        zhs = zhwiki_rev.get(t)
        if not zhs:
            return None
        # 取最短中文标题（避免「三界宙/历史」这类子页）
        zh = min((z for z in zhs if "/" not in z), key=len, default=None)
        if not zh:
            return None
        return (t, zh)

    for mm in re.finditer(r"\[\[\s*([^\]|]+?)\s*(?:\|[^\]]*)?\]\]", chunk_text):
        r = _ref(mm.group(1))
        if r and r not in out:
            out.append(r)
    for mm in re.finditer(r"''([^''\n]{3,80})''", chunk_text):
        if (mm.start() > 0 and chunk_text[mm.start() - 1] == "'") or \
           (mm.end() < len(chunk_text) and chunk_text[mm.end()] == "'"):
            continue
        t = mm.group(1).strip().strip("[]")
        if not re.match(r"^[A-Z][A-Za-z :'.,\-()0-9]*$", t):
            continue
        r = _ref(t)
        if r and r not in out:
            out.append(r)
    return out


def _dedup_keep_en(terms: list[str]) -> list[str]:
    """合并静态 + 动态保留英文名单：保序去重。"""
    seen, out = set(), []
    for t in terms:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def load_zhwiki_titles(path: Path = ZHWIKI_TITLES_FILE) -> dict:
    """读取「中文站已建页面」映射（dict/zhwiki_titles.json: zh_title -> en_title）。

    由 scripts/scan_zhwiki_titles.py 全站扫描生成：凡中文站有对应页面的专名，说明该译名
    已被社区/本项目确立（或该词不该按「无译名」处理）。动态 keep_en 用它排除候选——
    中文站已有页面的专名不保留英文（它有可用的中文页面/译名）。
    """
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_zhwiki_aliases(path: Path = ZHWIKI_ALIASES_FILE) -> dict:
    """读取「英文重定向短名 → 中文目标页」别名（dict/zhwiki_aliases.json: en_alias -> zh）。

    由扫描器第二阶段生成：中文站常见「英文短名页重定向到中文规范页」（如 Elend → 依蓝德·
    泛图尔、Kelsier → 卡西尔、Wax → 瓦克斯利姆·拉德利安）。这些是链接目标里最常见的形态
    （[[Elend]] 而非 [[Elend Venture]]），补进反向索引让它们也能命中「中文站已有页面」。
    """
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def build_zhwiki_reverse(zh_map: dict, aliases: dict | None = None) -> dict:
    """反向索引：en_title -> [zh_title,...]（同一英文名可能有多个中文页面）。

    合并两个来源：
      - zh_map：中文页标题 -> 规范英文原名（CmPermission）
      - aliases：英文短名 -> 中文目标页（重定向页，如 Elend -> 依蓝德·泛图尔）
    """
    inv: dict = {}
    for zh, en in zh_map.items():
        if not en or not zh:
            continue
        if en not in inv:
            inv[en] = []
        if zh not in inv[en]:
            inv[en].append(zh)
    for en, zh in (aliases or {}).items():
        if not en or not zh:
            continue
        if en not in inv:
            inv[en] = []
        if zh not in inv[en]:
            inv[en].append(zh)
    return inv


def slice_glossary(glossary, en_terms):
    """返回命中译名表的子集，按 EN 排序，供放进提示词。

    review 修复（方案2a）：用归一化索引匹配，正文写成 Set/kandra/metalminds 也能命中
    规范词条（The Set/Kandra/metalmind）。返回键用**正文实际出现的形态**，值带 {zh,
    canonical}，让 LLM 明确「正文这个英文 → 这个中文」；canonical 供需要时核对规范名。
    对**全小写**正文形态额外套用 GENERIC_EN_STOPLIST，避免把通用英文词误当专名翻译
    （如正文小写 red→雷德），只让真正的领域词（kandra/mistwraith/金属名等）命中。
    """
    idx = build_norm_glossary(glossary)
    sliced = {}
    for t in sorted(en_terms):
        if _is_lowercase(t) and _norm_glossary_key(t) in GENERIC_EN_STOPLIST:
            continue
        hit = idx.get(_norm_glossary_key(t))
        if not hit:
            continue
        canonical, entry = hit
        sliced[t] = {"zh": entry["zh"], "canonical": canonical}
    return sliced


# --------------------------------------------------------------------------- #
# Infobox 值确定性翻译（决议 #4 落地）：Infobox「字段 = 值」的专名按译名表统一替换。
# 结构化短字段交给确定性替换更可靠，不依赖 LLM 是否记得把值也翻成中文。
# --------------------------------------------------------------------------- #
# 引用族模板名（精确 date/裸 ref，或「* ref」结尾，大小写不敏感；17s ref 等数字开头亦有）。
# 刻意不含「Rosharan date」等复合 date 名——门禁 REF_PATS 只查 \{\{\s*date\s*\|，
# 保护面外扩=不必要的行为变更。
_REF_NAME_RE = re.compile(r"^(?:date|ref|.+\sref)$", re.I)
_REF_PFX = "%%REFSPAN_"


def _mask_ref_spans(value: str) -> tuple:
    """把 value 内的引用族模板整段挖成占位符，返回 (掩码文本, 原模板列表)。

    引用模板的参数是标识符（书码 `{{book ref|Elantris|62}}`、文件名 `{{map ref|…}}`、
    wob 编号、URL/时期），即使与词条同名也绝不可被译名替换——translate_infobox_values
    在 mask_ref_templates 之前运行，确定性替换一旦改掉书码，掩码/解码会原样带过，
    门禁 extract_refs 按字面比对引用序列必判不一致（实测 Dilaf/Hrathen/Shaor 三页
    `book ref|Elantris|62`→`book ref|伊岚翠|62`；map/file ref 文件名同理会被译烂）。
    按花括号平衡扫描：引用模板整段保护（内层嵌套一并）；非引用模板（{{tag|…}} 等）
    不整体保护，只继续深入找它内部的引用。占位符 `%%REFSPAN_i%%` 两侧均为非字母，
    词边界与 in_phrase 判定和原 `{{`/`}}` 语境等价 → 引用之外的替换行为零变化。
    """
    spans: list = []
    out: list = []
    pos = 0
    i = 0
    n = len(value)
    while i < n:
        if value.startswith("{{", i):
            end = _find_infobox_block(value, i)
            if end > 0:
                name = value[i + 2:end - 2].split("|", 1)[0].strip()
                if _REF_NAME_RE.match(name):
                    out.append(value[pos:i])
                    out.append(_REF_PFX + str(len(spans)) + "%%")
                    spans.append(value[i:end])
                    pos = end
                    i = end
                    continue
            i += 2  # 非引用模板或未闭合 '{{'：越过/深入，继续找其内部的引用
            continue
        i += 1
    out.append(value[pos:])
    return "".join(out), spans


def _sub_glossary_in_string(value: str, gloss: dict) -> str:
    """对单值做译名替换；返回替换后的字符串。

    - 优先整值匹配：把整个值（含 [[...]] 包裹的目标）视为一个整体，若命中单一译名词条则整值替换。
    - 其次最长匹配优先的片段替换（避免 "Seran" 抢在 "Seran Range" 之前）。
    - 图片文件名（含扩展名/File:）不替换。
    - review 方案2 延伸：整值匹配增加**归一化**兜底——正文/字段写成小写（kandra）、缺冠词（Set）
      或屈折形式时也能命中规范词条（Kandra/组织）；对全小写值套 GENERIC_EN_STOPLIST 防通用英文误翻。
    - 引用族模板整段保护（④）：先 _mask_ref_spans 挖占位符、替换后原样填回——书码/文件名等
      标识符参数即使与词条同名也绝不可译；无引用的值掩码是恒等变换，行为与旧版逐字节一致。
    """
    if re.search(r"(?i)(File:|Image:)|\.(png|jpe?g|gif|webp|svg)(\||$)", value):
        return value
    masked, ref_spans = _mask_ref_spans(value)
    if not ref_spans:
        return _sub_glossary_core(masked, gloss)
    out = _sub_glossary_core(masked, gloss)
    # 单趟还原：每个占位符只替换一次，填回的原文不会被再次扫描/替换。
    return re.sub(re.escape(_REF_PFX) + r"(\d+)%%",
                  lambda m: ref_spans[int(m.group(1))], out)


def _sub_glossary_core(value: str, gloss: dict) -> str:
    """（内部）对已挖去引用模板的文本做整值/归一化/片段替换；引用挖填见 _sub_glossary_in_string。"""
    # 整值匹配：去掉 [[ ]] 包裹后整体查表（如 [[Mistborn: The Final Empire]]）
    bare = re.sub(r"^\[\[(.*?)\]\]$", r"\1", value.strip())
    if bare in gloss and gloss[bare].get("zh"):
        zh = gloss[bare]["zh"]
        return "[[" + zh + "]]" if bare != value.strip() else zh
    # 整值匹配（归一化兜底）：kandra→Kandra、Set→The Set、metalminds→metalmind
    idx = build_norm_glossary(gloss)
    if not (_is_lowercase(bare) and _norm_glossary_key(bare) in GENERIC_EN_STOPLIST):
        hit = idx.get(_norm_glossary_key(bare))
        if hit is not None:
            _canonical, entry = hit
            zh = entry["zh"]
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
        # 裸词形式（词边界），但跳过「嵌在更长英文短语中」的命中：
        # 如 Survivor of the Flames（无整条译名的称号）只应整体保留英文，不可把
        # Survivor 单独换成 幸存者 造成「幸存者 of the Flames」半译。t 若是短语的
        # 一部分（后随「空格+小写词」/前有「小写词+空格」/带 's 所有格），跳过。
        # 2026-10-19 修：原实现在 finditer 遍历中直接改写 out，同一词条在一个值里多次
        # 命中时后续匹配的旧偏移落在已被改短的字符串上 → 错位切片（实测把
        # `[[Maxillium Ladrian|Maxillium]], [[...]]` 切成 `[[麦克斯利姆 Ladrian|Maxi麦克斯利姆[[…`，
        # 吞掉 `]], `——历史「内链括号不配对」多源于此）。改为：先在未改动的 out 上收集
        # 待替换区间与 in_phrase 判定，再按倒序一次性应用（倒序保证已应用的替换不影响
        # 尚未应用区间的偏移）。
        reps = []
        for m in re.finditer(r"(?<![A-Za-z])" + re.escape(t) + r"(?![A-Za-z])", out):
            before = out[max(0, m.start() - 24):m.start()]
            after = out[m.end():m.end() + 24]
            in_phrase = (
                re.search(r"[a-z]{2,}\s+$", before)      # 前有小写英文词
                or re.search(r"^\s+[a-z]", after)         # 后有空格+小写英文词
                or re.search(r"'\s*$", before)            # 所有格 's 前段
                or re.search(r"^\s*-?\s*[a-z][a-z'\-]{1,}", after)  # 后随连字符小写
            )
            if in_phrase:
                continue
            reps.append((m.start(), m.end()))
        for s, e in reversed(reps):
            out = out[:s] + zh + out[e:]
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
            new_val = _translate_cat_residents(val, glossary)
            new_val2 = _sub_glossary_in_string(new_val, glossary)
            if new_val2 != val:
                param_name = key.strip().lstrip("|").strip()
                stats[param_name] = (val, new_val2)
                out_lines.append(key + new_val2)
            else:
                out_lines.append(ln)
        else:
            out_lines.append(ln)
    new_block = "\n".join(out_lines)
    return wikitext[:start] + new_block + wikitext[end:], stats


_CAT_RESIDENTS_RE = re.compile(
    r"cat\s*=\s*Residents of\s+([A-Za-z][A-Za-z' \-]*?)(?=[,}\|]|$)", re.I)


def _translate_cat_residents(value: str, glossary: dict) -> str:
    """把 {{tag|X|cat=Residents of Y}} 的分类参数 `cat=Residents of Y` 确定性地
    转为 `cat=Y的居民`（Y 按译名表译中；Y 无可靠译名则原样保留英文，不自造）。

    背景：英文站 {{tag|Luthadel|cat=Residents of Luthadel}} 实际归入
    Category:Residents of Luthadel；中文站对应分类是「陆沙德的居民」。LLM 会把
    cat 参数当普通英文混译（Residents of Elen依蓝戴）或改回英文——确定性转换
    在 LLM 前完成，LLM 只能原样保留（规则 1/3b 已要求占位符与参数不动）。
    """
    def repl(m):
        place = m.group(1).strip()
        zh = _lookup_glossary_zh(glossary, place)
        if zh:
            return "cat=" + zh + "的居民"
        return m.group(0)

    return _CAT_RESIDENTS_RE.sub(repl, value)


def _lookup_glossary_zh(glossary, term: str) -> str | None:
    """取单个词条的译名 zh：精确键优先，归一化兜底（复用以译名替换的一致口径）。"""
    if term in glossary and glossary[term].get("zh"):
        return glossary[term]["zh"]
    idx = build_norm_glossary(glossary)
    if not (_is_lowercase(term) and _norm_glossary_key(term) in GENERIC_EN_STOPLIST):
        hit = idx.get(_norm_glossary_key(term))
        if hit:
            return hit[1]["zh"]
    return None


# Post/Pre 时代前缀：`Post [[Catacendre]]` / `post-[[Catacendre]]` / `pre-[[Catacendre]]` /
# `pre [[Final Empire]]` 等，后接 [[链接]]（可带管道显示文本）。这类前缀在历史/事件/时代
# 语境广泛出现（全库 55 处、跨 40+ 页），LLM 常只译内链目标、把 Post/Pre 留英文。
# 确定性转换为 `[[中文目标|中文目标后/前]]`（如 [[灰烬灾变|灰烬灾变后]]），链接文本与
# 目标语义一致；目标无可靠译名则原样保留（不自造译名，与 keep_en 铁律一致）。
_PREPOST_LINK_RE = re.compile(
    r"(?i)\b(Post|Pre)\s*-?\s*(\[\[([^\[\]|]+)(?:\|[^\[\]]*)?\]\])")


def translate_prepost_links(wikitext: str, glossary: dict):
    """把 `Post/Pre [[X]]` 时代前缀转成 `[[中文X|中文X后/前]]`（确定性，LLM 前）。

    返回 (新wikitext, 替换统计 [(原文→新文), ...])。
    - 链接目标 X 按译名表取 zh；X 无译名→原样保留整段。
    - 带管道 [[X|disp]]：目标按 X 译，disp 丢弃（Catacendric 等形容词形态的显示文本
      本就不独立成词，统一为「中文X后/前」）。
    - 幂等：已转换的 [[中文|中文后/前]] 不再匹配（中文不满足 [^\[\]|]+ 的英文构词，
      且 Post/Pre 前缀已消失）。
    """
    def repl(m):
        prefix = m.group(1)
        inner = m.group(2)
        target = m.group(3).strip()
        # 目标已是非 ASCII（中文：infobox 已先行译完目标）→ 直接以目标为基础加前后缀。
        # 否则按译名表查 zh；查不到 → 保留原样（不自造译名）。
        if re.search(r"[^\x00-\x7F]", target):
            zh = target
        else:
            zh = _lookup_glossary_zh(glossary, target)
        if not zh:
            return m.group(0)  # 无可靠译名 → 保留（不自造）
        suffix = "后" if prefix.lower() == "post" else "前"
        return "[[" + zh + "|" + zh + suffix + "]]"

    out = _PREPOST_LINK_RE.sub(repl, wikitext)
    stats = []
    if out != wikitext:
        # 统计：逐处提取已转换的 [[zh|zh后/前]]
        import re as _re
        for mm in _re.finditer(r"\[\[([^\[\]|]+)\|([^\[\]]+?后|前)\]\]", out):
            stats.append(("Post/Pre 时代前缀", mm.group(0)))
    return out, stats


def translate_wikilink_targets(wikitext: str, glossary: dict):
    """把 [[Parent/Subpage|display]] 这类子页链接的目标翻译成 [[父译名/子译名|display]]。

    背景：[[The Hero of Ages/Statistical analysis|225,372]] 这类词条数据统计子页链接，
    目标含 '/'。仅当「父段+所有后缀段」都能从译名表（主表 + common.json 合并）取到 zh
    时才重写，避免部分/臆测翻译；display（如数字 225,372）保持原样。返回 (新wikitext, stats)。
    """
    stats = []
    def repl(m):
        inner = m.group(1)
        disp = None
        target = inner
        if "|" in inner:
            target, disp = inner.split("|", 1)
        if "/" not in target:
            return m.group(0)
        parts = [p.strip() for p in target.split("/")]
        zhs = [_lookup_glossary_zh(glossary, p) for p in parts]
        if any(z is None for z in zhs):
            return m.group(0)
        new_target = "/".join(zhs)
        stats.append((target, new_target))
        link = "[[" + new_target
        if disp is not None and disp.strip():
            link += "|" + disp
        return link + "]]"
    out = re.sub(r"\[\[([^\[\]{}]+?)\]\]", repl, wikitext)
    return out, stats


# 普通内链目标翻译（LLM 前确定性替换）。背景：{{columns|...}} 等模板参数内的普通
# [[城市名]] 链接属于「模板参数」按规则 1 原样保留，LLM 不译、translate_wikilink_targets
# 只处理含 '/' 的子页目标 → Elendel Basin 的外城列表 18 个城市名全留英文。此处把
# [[X]] / [[X|disp]]（X 无 '/'、无命名空间前缀、非 interwiki/语言链接）按译名表译目标；
# 目标有 variants（多义词，如 Demoux 人物/城市）时**跳过**——宁保英文不误译（城市
# Demoux 若按默认 zh=德穆 会被错译成人物名）。disp 无独立译名时保留原样。
_NS_PREFIX_RE = re.compile(r"^(file|image|category|template|module|user|user talk|talk|portal|draft|summary|mediawiki|help)\s*:", re.I)


def translate_plain_links(wikitext: str, glossary: dict):
    """把普通内链 [[X]] / [[X|disp]] 的目标按译名表确定性译成中文。

    返回 (新wikitext, stats)。规则：
    - 目标含 '/'（子页）、':'-命名空间前缀（file/category/wob 等 interwiki 或语言链接）、
      variants 多义词（如 Demoux 人物/城市，城市译名待定）→ 跳过；
    - 目标命中译名表非空 zh → [[中文]]；带 disp 且 disp 也有译名 → [[中文|中文]]，
      disp 无译名 → [[中文|原disp]]；
    - 目标无译名 → 原样保留。
    调用时机：LLM 之前（与 translate_wikilink_targets 同级），让 {{columns}} 等模板参数
    内的普通链接也确定性译出（这些参数内的内链 LLM 按规则 1 不会动）。
    """
    def repl(m):
        inner = m.group(1)
        disp = None
        target = inner
        if "|" in inner:
            target, disp = inner.split("|", 1)
        target = target.strip()
        if not target or "/" in target:
            return m.group(0)
        if ":" in target and _NS_PREFIX_RE.match(target):
            return m.group(0)  # 命名空间/文件/category 链接不动
        ent = glossary.get(target)
        if isinstance(ent, dict) and ent.get("variants"):
            # 多义词（人物/城市等）：默认 zh 可能只对应其中一义，宁保英文不误译
            return m.group(0)
        zh = _lookup_glossary_zh(glossary, target)
        if not zh:
            return m.group(0)
        stats.append((target, zh))
        link = "[[" + zh
        if disp is not None and disp.strip():
            dzh = _lookup_glossary_zh(glossary, disp.strip())
            if not dzh:
                # disp 是目标去掉消歧后缀的根名（如 [[Doriel (city)|Doriel]]：disp 与
                # 目标同城）→ 复用目标译名，避免 [[多瑞尔|Doriel]] 半英半中。
                target_root = re.sub(r"\s*\([^)]*\)\s*$", "", target).strip()
                if disp.strip().lower() == target_root.lower():
                    dzh = zh
            if dzh:
                link += "|" + dzh
            else:
                link += "|" + disp
        return link + "]]"
    stats = []
    out = re.sub(r"\[\[([^\[\]{}]+?)\]\]", repl, wikitext)
    return out, stats


# 常见章节标题 EN→ZH 预翻译表（由本批 20 页实际译法归纳，取多数口径：
# Notes→注释 16x、History→历史 10x、Appearance and Personality→外貌与性格 6x…；
# 个别页的少数派译法如 Notes→备注、Relationships→关系 以多数为准归一）。
_SECTION_HEADING_MAP = {
    "notes": "注释",
    "references": "参考资料",
    "setting": "背景设定",
    "main characters": "主要角色",
    "views on religion": "宗教观",
    "history": "历史",
    "appearance and personality": "外貌与性格",
    "relationships": "人际关系",
    "trivia": "趣闻",
    "attributes and abilities": "属性与能力",
    "metallic arts": "金属技艺",
    "feruchemy": "藏金术",
    "allomancy": "镕金术",
    "hemalurgy": "血金术",
    "quotes": "语录",
    "early life": "早年生活",
    "awards": "奖项",
    "structure": "结构",
    "economy": "经济",
    "culture": "文化",
    "geography": "地理",
    "politics": "政治",
    "family": "家庭",
    "appearance": "外貌",
    "personality": "性格",
    "formation": "组建",
    "publication": "出版",
    "development": "创作",
    "summary": "剧情",
    "synopsis": "概要",
    "resources": "资源",
    "fighting": "战斗",
    "religions": "宗教",
    "currency": "货币",
    "calendar": "历法",
    "education": "教育",
    "fashion": "时尚",
    "architecture": "建筑",
    "government and politics": "政府与政治",
    # 2026-10-20 批次补（口径取自既有译文语料：封面画廊2x/脚注1x/统计分析1x/村庄1x）
    "cover gallery": "封面画廊",
    "footnotes": "脚注",
    "statistical analysis": "统计分析",
    "the village": "村庄",
    # 2026-10-22 长尾②批次补：豆包 100 页评测 25 处 [章节] 漏译标题中 19 处有语料源。
    # 口径：17 处取 DeepSeek 基线同页产物（同页同位置对齐，DS 该批全通过）；radiant
    # 取词表 Radiant(s)→光辉骑士（同页兄弟标题 Scholar and Radiant→学者与光辉骑士 同源）；
    # village 承 520ad8f「the village→村庄」同页同指称（豆包把预译标题改回英文，见 assemble
    # 再断言）。另 5 处全语料无源——Zeenid-daughter-Beth、Molli 状态 wait_book（待 sa5 中译本），
    # The Child、Formless、Vaporspren 各模型正文均按专名保留英文——宁保英文不录，留门禁重跑
    # 或用户裁定（勿凭字面造译名）。
    "village": "村庄",
    "vessel": "容器",
    "the roost": "栖木",
    "main assembly": "全体议会",
    "type i": "一类",
    "universal stamps": "通用印",
    "soulstamps": "魂印",
    "soulforging": "塑魂术",
    "resealing": "封印修复",
    "remembering": "忆塑",
    "the breakaway": "裂口市场",
    "kata": "剑式",
    "canton of orthodoxy": "正统教区",
    "contest of champions": "冠军对决",
    "contest of champions (1175)": "冠军对决 (1175)",
    "gray remnant": "灰色残部",
    "lifelight": "生命之光",
    "champion": "冠军",
    "radiant": "光辉骑士",
    # 2026-10-23 表修复增补 4 条（方向1 后仍败页的未映射 ASCII 标题；全部取同页基线产物）：
    # vessels→容器（DS Odium「== 容器 ==」）；primeval spren→原始灵（DS Spren「==== 原始灵 ====」）；
    # enlightened→启蒙（DS Order of Lightweavers「=== 启蒙 ===」子项位对位）；
    # the contest→较量（旧豆包 Shallan 同父级第 8 子项「较量」）。
    "vessels": "容器",
    "primeval spren": "原始灵",
    "enlightened": "启蒙",
    "the contest": "较量",
}

# ============ 全字典表驱动的章节标题兜底（2026-10-20 用户裁定：所有字典表全量进）============
# 来源（_sub 内优先级）：精选表（最高） > 下面合并出的字典表（中文站别名 < 中文站标题 < 译名表）。
# 仅收纯 ASCII 键与非空 zh；按 casefold 精确匹配（标题正则保证纯 ASCII）。
_HEADING_DICT_MAP = None


def _heading_dict_map() -> dict:
    global _HEADING_DICT_MAP
    if _HEADING_DICT_MAP is not None:
        return _HEADING_DICT_MAP
    out = {}

    def put(k, zh):
        if k and zh and str(k).isascii():
            out.setdefault(str(k).casefold(), str(zh))

    try:  # 低优先先放（setdefault 保先到者）：别名 < 标题反查 < 译名表
        for en, zh in load_zhwiki_aliases().items():
            put(en, zh)
    except Exception:
        pass
    try:
        for zh, en in load_zhwiki_titles().items():
            put(en, zh)
    except Exception:
        pass
    try:
        merged = load_merged_glossary(DEFAULT_GLOSSARY, DEFAULT_COMMON)
        terms = merged.get("terms", merged) if isinstance(merged, dict) else merged
        for en, v in terms.items():
            if isinstance(v, dict):
                put(en, v.get("zh"))
    except Exception:
        pass
    _HEADING_DICT_MAP = out
    return out


# 标题内允许的字符与门禁 3a 的 fullmatch 类对齐（含 &；2026-10-22 长尾②补——
# 否则 `Arts & Games` 类标题查表阶段永不匹配，门禁却会拦，两头不一致）。
_SECTION_HEAD_RE = re.compile(
    r"^(={2,6})[ \t]*([A-Za-z][A-Za-z0-9 ,:'&\-()]*?)[ \t]*(={2,6})[ \t]*$", re.M)


def _heading_plural_candidates(raw: str) -> list:
    """标题复数回退（2026-10-20）：词表只有单数（soulstamp）、标题写复数（Soulstamps）
    时差一个 s 就漏过全字典表。仅在标题精确查询未中后尝试：ies→y / es / 去 s。"""
    w = raw.casefold()
    out = []
    if w.endswith("ies") and len(w) > 4:
        out.append(w[:-3] + "y")
    if w.endswith("es") and len(w) > 3:
        out.append(w[:-2])
    if w.endswith("s") and len(w) > 3:
        out.append(w[:-1])
    return out


def translate_section_headings(wikitext: str):
    """常见章节标题确定性预翻译（LLM 前）。只匹配纯 ASCII 标题 → 表内映射为中文；
    长尾标题不在此表，漏译由 verify 3a ASCII 标题门禁拦截。返回 (新文本, 统计)。"""
    stats = []

    def _sub(m):
        raw = m.group(2).strip()
        dmap = _heading_dict_map()
        zh = (_SECTION_HEADING_MAP.get(raw.lower())
              or dmap.get(raw.casefold())
              or next((dmap[c] for c in _heading_plural_candidates(raw) if c in dmap), None))
        if not zh:
            return m.group(0)
        stats.append(f"{m.group(2)} -> {zh}")
        return f"{m.group(1)} {zh} {m.group(3)}"

    return _SECTION_HEAD_RE.sub(_sub, wikitext), stats


def translate_for_template(wikitext: str, glossary: dict):
    """把 {{for|目标|描述|pre=导语}} 模板的参数值按译名表做确定性替换。

    中文站 Template:For 渲染：`{{pre}}。欲寻{{{2}}}，请见：[[{{{1}}}|{{{3}}}]]`。
    参数 1（目标页名）/2（描述）/3（显示文本）多为专名，可确定性译；`pre=` 为导语文案，
    可译的专名（如 Brandon Sanderson）在此替换，整句剩余留给 LLM（见提示词 rule 2.2）。
    返回 (新wikitext, 替换统计)。
    """
    code = mwparserfromhell.parse(wikitext)
    stats = []
    for node in code.filter_templates(recursive=False):
        if str(node.name).strip().lower() != "for":
            continue
        changed = False
        # 只处理现有参数：位置参数（名 1/2/3）与命名参数（pre）。
        for pp in list(node.params):
            key = str(pp.name).strip()
            if key not in ("1", "2", "3", "pre"):
                continue
            pv = str(pp.value)
            nv = _sub_glossary_in_string(pv, glossary)
            if nv != pv:
                pp.value = nv
                if not changed:
                    stats.append({str(x.name).strip(): str(x.value) for x in node.params})
                    changed = True
    return str(code), stats


def ensure_infobox_original_name(wikitext: str, en_title: str) -> tuple[str, bool]:
    """给 {{Infobox ...}} 缺『原名』字段时补 `| 原名 = <en_title>`。

    背景：中文站多数 Infobox（book/character/location/nation/settlement/item/magic/...）
    标题行用 `'''{{{Xxx|{{PAGENAME}}}}}'''<br>'''{{{原名|{{#var_final:en}}}}}'''`。
    若页面未写『原名』，模板回退到 {{#var_final:en}}；而设置 en 变量的 {{en}} 位于
    infobox 之后，MediaWiki 源顺序展开时 #var_final:en 在 en 未定义时求值 → 渲染泄漏
    UNIQ--finalizedvar-* 占位符（页面出现怪串）。真实页惯例是显式写『原名 = 英文名』。
    此处对任意缺『原名』的 Infobox 补上（MediaWiki 忽略模板未使用的参数，故对没有
    『原名』槽的模板注入也无害；对有该槽的模板则正好绕开 #var_final 占位符）。
    返回 (新wikitext, 是否补了)。只处理首个缺失的 Infobox。
    """
    m = re.search(r"\{\{\s*Infobox\b", wikitext, re.IGNORECASE)
    if not m:
        return wikitext, False
    start = m.start()
    end = _find_infobox_block(wikitext, start)
    if end < 0:
        return wikitext, False
    block = wikitext[start:end]
    if re.search(r"(?m)^\|\s*原名\s*=", block):
        return wikitext, False  # 已设原名，不动
    line_end = wikitext.find("\n", start)
    if line_end < 0 or line_end > end:
        return wikitext, False
    insert = f"| 原名    = {en_title}\n"
    return wikitext[:line_end + 1] + insert + wikitext[line_end + 1:], True


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
# 引用模板占位（确定性防「引用编号幻觉」）
# --------------------------------------------------------------------------- #
# 实测（Spook 重跑）：LLM 在翻译中含 {{book ref|mb1|24}} 等引用模板时，会把编号改掉
# （mb1|24→mb1|22、mb2|25→mb2|6、mb3|16→mb3|53…），Ghostbloods 重跑同样幻 觉过
# （§4.8 教训）。这是「写回前必须人工核引用」的根本原因。根治：LLM 前把这些
# 引用模板整段替换为 %%REF_N%% 占位符，LLM 接触不到编号无从幻觉（规则只要求
# 占位符原样保留），assemble 时按英文源顺序确定性填回 → 引用编号 100% 与英文源一致。
_REF_TMPL_RE = re.compile(
    r"\{\{\s*(?:book ref|msh ref|Rpg ref|date|tes ref|epigraph ref)\b[^{}]*\}\}", re.I)


def mask_ref_templates(wikitext: str):
    """把 {{book ref|X|Y}}/{{msh ref|X|Y}}/{{Rpg ref|X|Y}}/{{date|X|Y}}/{{tes ref|N}}/
    {{epigraph ref|X|Y}} 替换为 %%REF_N%%。

    返回 (masked, refs)；refs 为按出现顺序记录的英文源模板原文。
    应在 mask_protected_blocks 之后调用（Quote/columns 整块已占位，其内部 ref
    随之保护，不会出现在这里）。wob ref 已在 convert 阶段转 <ref>（非模板），不涉及。

    注意：占位符必须是**真正的双百分号** %%REF_N%%（f-string 生成，不能用 %-格式化——
    `"%%REF_%d%%" % i` 的 %% 会被转义成单 %，得到 %REF_0%：形态太弱，LLM 会把
    单 % 当普通标点改写（实测输出 %{{date|1021|fe}}% 残留），且参照 unmask 的双 %
    无法匹配，引用填回静默失败）。
    """
    refs = []

    def repl(m):
        refs.append(m.group(0))
        return f"%%REF_{len(refs) - 1}%%"

    return _REF_TMPL_RE.sub(repl, wikitext), refs


def unmask_ref_templates(translated_body: str, refs: list[str]):
    """把译文里的 %%REF_N%% 填回英文源 ref 模板原文。

    返回 (body, missing_tokens)。2026-10-18 起确定性修复两类模型占位符损伤
    （qwen3.8-27b 实测均出现过）：

    A) **顶替型**：恰缺 1 个序号 i、占位符总数恰好等于 refs 数、恰有 1 个序号 d
       被连续抄了两次（模型把 %%REF_i%% 抄成 %%REF_d%%，如 mb5|24→mb5|epilogue）。
       英文源顺序保证 i 落在 (前驱 p, d) 之间 → 重复段的**首个**占位即 i 的槽位，
       按位置重映射为 refs[i]，两处各归其位。
    B) **丢失型**：模型删掉占位符文本，但其余占位符保持相对顺序 → 在邻居
       （前驱/后继占位符）之间回插（邻居位置即英文源位置）。

    两种修复都要求「保守可证」的条件；条件不满足（乱序/多缺/全缺）原样列出
    missing 交门禁把关，不做无谓干预。占位符替换改为**单遍位置化**（含修复
    事件合并），杜绝全局 replace 的重复命中歧义。
    """
    out = translated_body
    found = [(m.start(), m.end(), int(m.group(1)))
             for m in re.finditer(r"%%REF_(\d+)%%", out)]
    counts: dict = {}
    for _, _, n in found:
        counts[n] = counts.get(n, 0) + 1
    missing = [i for i in range(len(refs)) if counts.get(i, 0) == 0]
    remap: dict = {}        # found 下标 → 实际应填的 refs 下标（情形A 重映射）
    reinsertions: list = []  # (pos, text) 回插事件（情形B）

    # 情形A：单缺失 + 单序号连续重复（且占位符总数与 refs 相等 → 重复即顶替）
    if len(missing) == 1 and len(found) == len(refs):
        i = missing[0]
        dups = [n for n, c in counts.items() if c > 1]
        if len(dups) == 1 and counts[dups[0]] == 2:
            d = dups[0]
            ks = [k for k, (_, _, n) in enumerate(found) if n == d]
            if len(ks) == 2 and ks[1] == ks[0] + 1:
                p_prev = found[ks[0] - 1][2] if ks[0] > 0 else None
                if (p_prev is None or p_prev < i) and i < d:
                    remap[ks[0]] = i   # 重复段首占位 = 缺失序号的槽位
                    missing.remove(i)

    # 情形B：仍有缺失 + 序列（含重映射后）单调 + 缺得少 → 邻居间回插
    seq_ns = [remap.get(k, n) for k, (_, _, n) in enumerate(found)]
    seq_ok = all(seq_ns[k] < seq_ns[k + 1] for k in range(len(seq_ns) - 1))
    if missing and found and seq_ok and len(found) >= max(1, len(refs) - 3):
        for i in list(missing):
            prev_ns = [n for n in seq_ns if n < i]
            next_ns = [n for n in seq_ns if n > i]
            if next_ns:
                q = next_ns[0]
                k = next(idx for idx, n in enumerate(seq_ns) if n == q)
                pos = found[k][0]           # 后继占位起点（插在其前）
            elif prev_ns:
                q = prev_ns[-1]
                k = next(idx for idx, n in enumerate(seq_ns) if n == q)
                pos = found[k][1]           # 前驱占位终点（插在其后）
            else:
                continue                    # 无邻居（全缺等）→ 留给 missing
            reinsertions.append((pos, refs[i]))
            missing.remove(i)

    # 单遍位置化应用：token 替换 + 回插事件合并（同位置时回插在前）
    events = []
    for k, (s, e, n) in enumerate(found):
        events.append((s, 1, e, "tok", remap.get(k, n)))
    for pos, text in reinsertions:
        events.append((pos, 0, pos, "ins", text))
    events.sort(key=lambda x: (x[0], x[1]))
    pieces = []
    last = 0
    for pos, _rank, end, kind, payload in events:
        pieces.append(out[last:pos])
        if kind == "tok":
            pieces.append(refs[payload] if 0 <= payload < len(refs)
                          else f"%%REF_{payload}%%")
        else:
            pieces.append(payload)
        last = end
    pieces.append(out[last:])
    out = "".join(pieces)
    still_missing = [f"%%REF_{i}%%" for i in missing]
    return out, still_missing


# --------------------------------------------------------------------------- #
# infobox「原名」占位（防 LLM 把英文原名翻译掉）
# --------------------------------------------------------------------------- #
# infobox 的「| 原名 = Spook」语义上是英文原名（{{CmPermission}}/{{en}} 依赖它定义
# #var_final:en），LLM 却偶发把它译成中文（Spook→鬼影），破坏渲染。LLM 前占位、
# assemble 填回英文标题，确定性保证原名恒为英文。
_ORIGINAL_NAME_TOKEN = "%%ORIGINAL_NAME%%"
_INFOBOX_ORIG_NAME_RE = re.compile(r"^(\|\s*原名\s*=\s*)(.*)$", re.M)


def mask_infobox_original_name(wikitext: str, title_en: str):
    """把 infobox 的「| 原名 = X」值替换为占位符。

    返回 (masked, title_en)；无原名行则原样返回。assemble 时用
    unmask_infobox_original_name 填回英文标题。
    """
    if _INFOBOX_ORIG_NAME_RE.search(wikitext):
        return _INFOBOX_ORIG_NAME_RE.sub(lambda mm: mm.group(1) + _ORIGINAL_NAME_TOKEN, wikitext, count=1), title_en
    return wikitext, title_en


def unmask_infobox_original_name(translated_body: str, title_en: str) -> str:
    if _ORIGINAL_NAME_TOKEN in translated_body and title_en:
        return translated_body.replace(_ORIGINAL_NAME_TOKEN, title_en)
    return translated_body


# --------------------------------------------------------------------------- #
# infobox「纯内链列表」值占位（对所有页面/模型自动生效）。
# 背景：qwen3.8-27b 对 `|children=[[A|B]], [[C|D]]` 这类字段 3 连败——合并成
# `[[A|B[[C|D]]` 断链（Wax/Marasi 两页同型）。值为「仅内链 + 分隔符」的字段
# 此时已过 translate_plain_links（译名表能译的目标已译），LLM 对纯链接值没有
# 合理改写空间 → 占位直通，assemble 填回；漏保占位符交 verify 结构检查把关。
# --------------------------------------------------------------------------- #
_LINKLIST_LINE_RE = re.compile(
    # 2026-10-19 修：字段名放开为任意非 '=‘ 字符——convert 层已把 Infobox 参数名译成
    # 中文（children→子嗣），原 ASCII 限定导致掩码不命中、纯链接值漏给 LLM。
    # 值形态仍严格限定「仅 [[..]] + 分隔符」，不会波及其他字段行。
    # '=' 后的空白收进组一，占位与回填逐字还原（原 \s* 在组外会吞掉该空格）。
    r"^(\|[^\n=]*?=\s*)"
    r"(\[\[[^\[\]{}]+\]\](?:\s*[,;，、]\s*\[\[[^\[\]{}]+\]\])*)\s*$",
    re.M)


def mask_infobox_link_lists(wikitext: str):
    """纯内链列表型 infobox 字段（children/relatives/image…）→ %%LINKLIST_n%%。

    返回 (masked, registry)；registry[i] = 原值，assemble 时原样填回。
    """
    registry: list[str] = []

    def _sub(m):
        registry.append(m.group(2))
        return f"{m.group(1)}%%LINKLIST_{len(registry) - 1}%%"

    return _LINKLIST_LINE_RE.sub(_sub, wikitext), registry


def unmask_infobox_link_lists(translated_body: str, registry: list[str] | None) -> str:
    if not registry:
        return translated_body
    for i, val in enumerate(registry):
        tok = f"%%LINKLIST_{i}%%"
        if tok in translated_body:
            translated_body = translated_body.replace(tok, val)
        else:
            sys.stderr.write(f"[提醒] LINKLIST 占位符被改写未保留（LLM 动了不该动的字段）: {tok} —— "
                             f"verify [占位符] 会拦截\n")
    return translated_body


# --------------------------------------------------------------------------- #
# 分块（超长词条支持）。按 == 章节 == / === 小节 === 边界切，Infobox+导语固定 chunk0。
# --------------------------------------------------------------------------- #
@dataclass
class Chunk:
    index: int
    text: str
    title: str = ""          # 该块的首个标题（纯文本，用于提示词定位）
    char_count: int = 0
    seg_start: int = -1      # 对应 split_sections 段区间 [seg_start, seg_end)（2026-10-23 分块重试定位）
    seg_end: int = -1


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
      - 头部（Infobox+导语，首个无标题段）固定为 chunk0，且**独立成块**
        （不再把后续章节并入 chunk0）。实测（Spook rerun3）：chunk0 若同时含
        导语+整个章节（6509 字符），LLM 偶发「只译标题、导语正文留英文」——
        把导语孤立成小块后翻译成功率显著更高，也让「导语校验」可独立重试。
      - 按段累加；加入下一段会超过 max_chars 时开新块（块边界必在章节边界）。
      - 单段自身超过 max_chars 时独成一块并告警（不硬切，避免破坏模板/语义）。
      - 块内字符数按原始文本计（近似 token 量）。
    """
    segments = split_sections(wikitext)
    chunks: list[Chunk] = []
    cur_parts: list[str] = []
    cur_chars = 0
    cur_title = ""
    cur_seg_start = -1
    seg_idx = 0
    warning_oversized: list[str] = []

    def flush():
        nonlocal cur_parts, cur_chars, cur_title, cur_seg_start
        if cur_parts:
            text = "\n".join(cur_parts)
            chunks.append(Chunk(index=len(chunks), text=text, title=cur_title, char_count=cur_chars,
                                seg_start=cur_seg_start, seg_end=seg_idx))
            cur_parts, cur_chars, cur_title, cur_seg_start = [], 0, "", -1

    first = True
    for head_line, level, text, body in segments:
        # 重建段原文（连标题行）
        seg_text = (head_line + "\n" + body) if head_line else body
        seg_chars = len(seg_text)
        if first:
            # 头部固定 chunk0 且独立成块（导语专注翻译，见 docstring）
            chunks.append(Chunk(index=0, text=seg_text, title=text, char_count=seg_chars,
                                seg_start=seg_idx, seg_end=seg_idx + 1))
            first = False
            seg_idx += 1
            continue
        if seg_chars > max_chars:
            flush()
            chunks.append(Chunk(index=len(chunks), text=seg_text, title=text, char_count=seg_chars,
                                seg_start=seg_idx, seg_end=seg_idx + 1))
            warning_oversized.append(text or "（无标题超长段）")
            seg_idx += 1
            continue
        if cur_chars + seg_chars > max_chars:
            flush()
        if not cur_parts:
            cur_seg_start = seg_idx
        cur_parts.append(seg_text)
        cur_chars += seg_chars
        cur_title = text
        seg_idx += 1
    flush()

    return chunks, warning_oversized


def compute_chunk_line_starts(final_body: str, chunks: list, segments=None) -> list | None:
    """产物终文按块求起始行号（2026-10-23 分块门禁重试定位用）。

    - 块边界必在章节边界（chunk_wikitext 契约）→ 终文标题行序列须与源「有标题段」
      一一对应（结构保持）；对不上（LLM 增删标题=结构漂移）返回 None，调用方回退整页重跑。
    - 返回 [chunk0起始行, chunk1起始行, …, 总行数+1]（1-based，末哨兵，供二分映射）。"""
    if segments is None:
        return None
    lines = final_body.split("\n")
    head_lines = [i + 1 for i, ln in enumerate(lines) if _HEADING_RE.match(ln)]
    exp = [i for i, s in enumerate(segments) if s[0] is not None]  # 源有标题段号
    if len(head_lines) != len(exp):
        return None
    seg_lines = {si: head_lines[k] for k, si in enumerate(exp)}
    seg_lines.setdefault(0, 1)   # 头部段（无标题）从第 1 行起
    starts = []
    for c in chunks:
        if c.seg_start < 0 or c.seg_start not in seg_lines:
            return None
        starts.append(seg_lines[c.seg_start])
    starts.append(len(lines) + 1)
    for a, b in zip(starts, starts[1:]):
        if a >= b:
            return None
    return starts


# --------------------------------------------------------------------------- #
# OpenAI 兼容 chat completions（与 DSH 的 openai-completions 一致）
# --------------------------------------------------------------------------- #
def llm_chat(cfg: LLMConfig, messages, max_output_tokens=8000, temperature=0.2):
    """调用 OpenAI 兼容 /chat/completions。失败按指数退避重试。

    25-10-18 修复：默认发送 thinking={"type":"disabled"}，绕开 deepseek-v4-flash-0731
    对长 wikitext 翻译块的无限推理（reasoning 吃光 max_tokens→content 空→JSON 解析失败）。
    设 LLM_THINKING=enabled 可恢复推理。
    """
    url = cfg.base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": cfg.model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_output_tokens,
    }
    if cfg.thinking != "enabled":
        payload["thinking"] = {"type": "disabled"}
    if cfg.effort:
        payload["reasoning_effort"] = cfg.effort
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
2. 【专名按译名表】专有名词一律按「译名表」翻译（含正文与 {{Infobox}} 里 `字段 = 值` 的值）；译名表没有的疑似专名**保留英文**，并列入 untranslated_terms。图片文件名、ISBN、日期数字、书目代号等非译文内容的**值**原样保留不译。**重要**：凡「译名表」切片中明确给出的 `英文 = 中文`，就**必须原样使用该中文**，禁止另造译名/音译（如切片给 `Mr. Suit = 西装先生` 就用 西装先生，不要写成 苏特先生）。只有在切片里**没有**对应条目时，才允许按常见做法自行判断或保留英文。
2.2【{{for}} 模板参数要译】页首的消歧模板 `{{for|目标|描述|pre=导语}}` 的参数是**需翻译的导语文案**：`pre=` 值、第 1/2 参数（目标页名、描述、显示文本）都要译成简体中文；**不得在任一参数内残留整段英文**——描述参数第 2 参数是完整英文短语（如 `the kind of Allomancer`），必须整句译成对应中文（如 `熔金术师这一类`），而不是只换掉里面的专名；`pre=` 导语同理整句翻译。但模板名 `for` 与 `<...>` 结构、参数顺序原样保留。已译的表内专名不要重复改。其它模板的参数仍按第 1 条保留原样。
2.3【notice 模板参数要译】页首的提示框 `{{notice|style=...|b=引言|正文}}` 是**需翻译的自然语言**：`b=` 值（页面引言，多为 Brandon 语录）与无名字位置参数（剧透警告正文）都要整句译成简体中文，**不得残留整段英文**；`style=` 参数与模板名 `notice`、参数顺序原样保留。内链目标按译名表（如 [[Rosharan]]→[[柔刹]]、[[cosmere]]→[[三界宙]]）。若 notice 与其它模板嵌套（如 Hoid 页 `{{notice}}` 后紧跟 `{{theory}}`），各自独立处理。
2.4【脚注说明要译】`<references>` 与 `<ref name="X">说明文字</ref>` 里的**脚注说明文字**属于需翻译的正文（引文/书证说明），要译成简体中文；但 `<ref>/<references>` 标签本身、`name=` 属性、`<ref name="X"/>` 自闭合用法一律原样保留（自闭合占位引用不展开、不译）。
2.5【Infobox 值中普通英文要译】{{Infobox}} 的 `字段 = 值` 里，除模板 {{...}}、链接 [[...]]、引用、数字、图片文件名之外的自然语言——包括**普通英文短语**（如 `Several post-[[Catacendre]] noble houses` 里的 Several/noble houses 应译为 数个/贵族家族）——都必须译成简体中文，不得残留整段或半段英文。只有「译名表未收录的疑似专名」才保留英文并列入 untranslated_terms。
3. 【原文引用不译】(决议#13)：文中可能出现形如 %%ORIGINAL_BLOCK_1%% 的占位符，它们是**小说原著引文**（台词/称号列表）的替身。**必须原样保留、不翻译、不增删、不改动**（管道自会填回英文原文）。除此之外，正常叙述正文照常翻译。
3b.【引用占位符保留】文中可能出现形如 %%REF_0%% / %%REF_12%% / %%LINKLIST_0%% 的占位符，它们是**引用模板**（{{book ref|...}}/{{msh ref|...}}/{{Rpg ref|...}}/{{date|...}}）与 **infobox 纯内链字段**（children/relatives 等的 `[[A|B]], [[C|D]]` 链接列表）的替身（编号由管道自动填回，你接触不到原编号，也不要臆测内容）。**必须原样保留、不翻译、不增删、不改写**——包括 %%ORIGINAL_NAME%%（infobox 原名占位符）也一样原样保留。
4. 【章节标题】== 章节 == / === 小节 === 标题翻译成简体中文；标题行顶格的等号数目与格式必须原样保留。
5. 【首行(仅块0)】第一条正文行='''中文译名'''，并在其后紧跟 {{en|英文词条名}}。只有块0需要，其余块不得重复加。
5b.【导语必翻(仅块0)】块0 除 Infobox 与首行标题外，通常还有**导语/首段正文**（Infobox 之后、首个 `== 章节 ==` 之前的全部叙述文字）。这些导语正文**必须逐句翻译成简体中文**；**严禁只把标题翻成中文、却把导语正文保留成英文**。除 %%ORIGINAL_BLOCK_*%% 占位符和译名表未收录的专名外，块0 中不得残留任何英文句子。
6. 【输出格式】只输出一个 JSON 对象，不要 markdown 代码围栏、不要任何额外文字：
   {"translation": "<翻译后的完整本块 wikitext，换行转义为\\n，禁止截断/省略>", "untranslated_terms": [{"en": "<保留英文的专名>", "reason": "<原因>", "zh": "<已定译名则填，否则省略>"}]}
   translation 必须包含你收到的**整块**全部内容（含所有模板、占位符、参考文献/分类），不得丢失。
"""


def build_user_prompt(chunk: Chunk, glossary_slice: dict, en_title: str, is_first: bool,
                      glossary: dict | None = None) -> str:
    gloss_lines = "\n".join(f"- {en} = {data['zh']}" for en, data in glossary_slice.items()) if glossary_slice else "（（本文无命中译名表））"
    parts = []
    parts.append("译名表（仅与本词条相关的子集，优先采用）:\n" + gloss_lines)
    # 保留英文名单：静态 dict/keep_en.json（已确认词）+ 动态识别（本块自动判定的
    # 未收录专名）。两者合并提示，机制对任意页面自动生效，不依赖逐页人工 review。
    keep_en = [t for t in load_keep_en() if t in chunk.text]
    zhwiki_refs: list[tuple[str, str]] = []
    if glossary is not None:
        try:
            zhwiki_rev = build_zhwiki_reverse(load_zhwiki_titles(), load_zhwiki_aliases())
            keep_en = _dedup_keep_en(keep_en + detect_keep_en_terms(chunk.text, glossary, zhwiki_rev))
            zhwiki_refs = detect_zhwiki_refs(chunk.text, glossary, zhwiki_rev)
        except Exception:
            pass
    if keep_en:
        parts.append(
            "**以下专名必须保留英文、禁止翻译或改译**（译名表未收录、无官方中文译名，"
            "中文站也无对应页面，不要因为它们像书名/作品名就自造译名）：" + "、".join(keep_en) +
            "。保留原文即可，并把它们列入 untranslated_terms（reason=保留英文）。"
        )
    if zhwiki_refs:
        refs_str = "；".join(f"{en} → {zh}" for en, zh in zhwiki_refs)
        parts.append(
            "**以下专名中文站已有对应页面，请采用其页面标题作为译名参考**（若与译名表冲突"
            "以译名表为准）：" + refs_str + "。"
        )
    if is_first:
        parts.append(
            "这是**第 1 块**（含 Infobox + 导语）。英文词条名 = " + en_title +
            "。请把条目标题译成简体中文，并在首行的 '''中文译名''' 之后紧跟 {{en|" + en_title + "}}。"
            "本块的**导语/首段正文**（Infobox 之后、首个 == 章节 == 之前的叙述文字）也必须一并完整译成中文，"
            "不得只翻标题而把导语正文留成英文。"
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
                    gloss: dict | None = None, max_output_tokens: int = 8000,
                    feedback: str | None = None):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(chunk, glossary_slice, en_title, is_first, gloss)},
    ]
    if feedback:
        # 纠错反馈重试：把上一次失败的具体问题回喂给 LLM（如导语残留英文句子），
        # 并要求基于同一块原文整段重译，而不是凭空重来（凭空重来会重复同样错误）。
        messages.append(
            {"role": "user", "content": "注意：你上一次的译文违反了硬规则（见下），"
             "请基于「原始 wikitext」重新完整翻译本块，其余规则不变。\n\n上次问题：\n" + feedback})
    reply = llm_chat(cfg, messages, max_output_tokens=max_output_tokens)
    data = parse_chunk_reply(reply)
    translation = str(data.get("translation", "")).strip()
    untranslated = data.get("untranslated_terms") or []
    if not translation:
        raise ValueError("LLM 返回的 translation 为空")
    return translation, untranslated


def translate_chunk_with_retry(cfg: LLMConfig, chunk: Chunk, glossary_slice: dict, en_title: str,
                               is_first: bool, gloss: dict | None = None,
                               max_output_tokens: int = 8000, max_retries: int = 2):
    """翻译一块；对 chunk0（导语）做「导语英文残留」校验，命中则带反馈重试。

    实测偶发 LLM 只翻标题+加 {{en}}、却把导语正文保留英文（Spook 重跑连续 3 次
    都如此）。新逻辑：重试时把上一次残留的英文句子片段回喂给 LLM（feedback），
    明确要求整段翻译——而非让 LLM 凭空重来。重试仍失败则保留并告警（写回前门禁
    verify_translation.py 会再次拦截）。
    """
    last_translation, last_untranslated = None, []
    last_feedback = None
    body_retried = False
    for attempt in range(max_retries + 1):
        translation, untranslated = translate_chunk(cfg, chunk, glossary_slice, en_title,
                                                    is_first, gloss, max_output_tokens,
                                                    feedback=last_feedback)
        last_translation, last_untranslated = translation, untranslated
        if not is_first or chunk.index != 0:
            # 正文块半译校验（2026-10-20 用户裁定：导语 → 所有块；复用 feedback 通道，限 1 次）
            if not body_retried:
                fb = body_english_feedback(translation)
                if fb:
                    body_retried = True
                    last_feedback = fb
                    sys.stderr.write(f"[半译校验] 正文块疑似残留成句英文（本轮第 {attempt + 1} 次调用），"
                                     "带反馈重试（限 1 次）…\n")
                    continue
            return translation, untranslated
        if not untranslated_lead_english(chunk.text, translation):
            return translation, untranslated
        last_feedback = lead_english_feedback(chunk.text, translation)
        sys.stderr.write(
            f"[导语校验] chunk0 导语疑似残留英文（本次=第{attempt + 1}次），"
            f"带反馈重试…残留片段：{last_feedback[:80]}\n")
    sys.stderr.write("[导语校验] 重试上限已用尽，导语仍疑似含英文，保留当前译文（写回前由质量门禁拦截）。\n")
    return last_translation, last_untranslated


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


_UNTRANSLATED_STOPWORDS = {
    "a", "an", "in", "of", "to", "and", "is", "was", "the", "for", "on", "it", "its",
    "at", "that", "with", "this", "from", "by", "are", "be", "as", "his", "her", "their",
    "read", "about", "during", "after", "before", "they", "who", "which", "not", "only",
    "when", "one", "some", "more", "has", "have", "had", "called", "known", "located",
    "south", "north", "near", "between", "celebrating", "released", "wedding", "city",
}


def untranslated_lead_english(src_text: str, translation: str) -> bool:
    """检测 chunk0 译文中，导语（Infobox 后、首个章节/分节标题前的正文）是否残留英文句子。

    背景：实测偶发 LLM「只把标题译成中文 + 加 {{en}}，却把导语正文原样保留英文」。
    返回 True 表示疑似导语仍含未翻译英文（应重试/告警）。

    判定（源/译对比 + 专名白名单，避免误伤合法的原文保留）：
    1. 对源、译文导语各自剥离噪音（%%ORIGINAL_BLOCK%% 占位符、{{模板}}、[[内链]]取显示文本、URL）。
    2. 只统计「叙述性英文词」：# 全小写或在停用词表里 的词才算（这类是需译的英文句子成分）；
       全大写/首字母大写的专名串（Waxillium Ladrian / Scadrial）不算，天然不进白名单却也不判残留。
    3. 源里确有叙述性英文（≥4 词）且译文里仍残留相当叙述性英文（≥4 词）→ 判为「该翻的英文没翻成中文」。
    """
    def lead_region(text: str) -> str:
        # 截到首个章节/分节/分号标题
        seg = re.split(r"\n==|\n;", text)[0]
        # 去掉 Infobox 及头部 CmPermission：定位到最后一个 }}\n\n 之后
        i = seg.rfind("}}\n\n")
        lead = seg[i + 4:] if i >= 0 else seg
        return lead

    def strip_noise(text: str) -> str:
        s = re.sub(r"%%ORIGINAL_BLOCK_\d+%%", " ", text)
        s = re.sub(r"</?ref[^>]*>", " ", s)             # <ref> 标签
        s = re.sub(r"<references\b[^>]*>", " ", s, flags=re.I)
        s = re.sub(r"\[\[wob:\d+\|wob:\d+\]\]", " ", s)  # wob 引用标记（非叙述性英文）
        s = re.sub(r"\{\{[^{}]*\}\}", " ", s)          # 模板
        s = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1 ", s)  # 内链取显示文本
        s = re.sub(r"\[\[[^\]]*\]\]", " ", s)
        s = re.sub(r"https?://\S+", " ", s)            # URL
        s = re.sub(r"[^\w\s.a-zA-Z\u4e00-\u9fff]", " ", s)
        return s

    def prose_word_count(text: str) -> int:
        """统计叙述性英文词数：全小写或命中停用词表的词（需译为中文的句子成分）。"""
        tokens = re.findall(r"[A-Za-z]+", strip_noise(text))
        n = 0
        for tok in tokens:
            low = tok.lower()
            if low in _UNTRANSLATED_STOPWORDS or tok == low:
                n += 1
        return n

    src_lead = lead_region(src_text)
    tr_lead = lead_region(translation)
    if not src_lead.strip() or not tr_lead.strip():
        return False
    src_prose = prose_word_count(src_lead)
    if src_prose < 4:
        # 源导语本身没有成句英文（如只有专名/引用），无需检查
        return False
    dst_prose = prose_word_count(tr_lead)
    return dst_prose >= 4


def lead_english_feedback(src_text: str, translation: str) -> str:
    """生成导语残留英文的纠错反馈（供带反馈重试）。

    取译文中导语区里「连续 ≥3 个叙述性英文词」的句子片段，最多给 3 段；
    并附上对应英文原文片段与中文对照示例，让 LLM 明确「这些英文句子
    必须译成中文而不是保留」。若提取不到则给通用提示。
    """
    def lead_region(text: str) -> str:
        seg = re.split(r"\n==|\n;", text)[0]
        i = seg.rfind("}}\n\n")
        return seg[i + 4:] if i >= 0 else seg

    en_lead = lead_region(src_text)
    tr_lead = lead_region(translation)
    fragments = []
    for m in re.finditer(r"([A-Za-z][A-Za-z'\- ]{8,})", tr_lead):
        frag = m.group(1).strip()
        words = [w for w in re.findall(r"[A-Za-z]+", frag)
                 if w.lower() in _UNTRANSLATED_STOPWORDS or w != w.upper()]
        if len(words) >= 3 and frag not in fragments:
            fragments.append(frag[:120])
        if len(fragments) >= 3:
            break
    if fragments:
        # 英文原文中找对应片段（截断前缀匹配首词），给中文译法对照
        pairs = []
        for f in fragments:
            first = re.findall(r"[A-Za-z]+", f)
            head = first[0] if first else ""
            i = en_lead.find(head)
            if i >= 0:
                en_snip = en_lead[i:i + 90].replace("\n", " ")
                pairs.append(f"“{f}” → 译成中文（如“{en_snip}”对应整句中的 {f} 需译成中文句子）")
            else:
                pairs.append(f"“{f}” → 译成中文")
        return ("导语正文仍是英文（未译成中文）。请把以下英文片段所在句子**整句**译成简体中文"
                "（不是只换专名，是整句翻译；专名按译名表，其余自然语言全译）：\n"
                + "\n".join(pairs)
                + "\n\n参考：英文原文导语是 “" + en_lead[:200].replace("\n", " ") + "…”"
                  "，这些内容都必须出现在中文译文里。")
    return "导语正文整段仍是英文（未译成中文）。请把 Infobox 之后、首个章节之前的全部叙述文字逐句译成简体中文，严禁只翻标题、正文留英文。"


def _template_spans(body: str):
    # 全文 {{...}}（配平嵌套）区间——导语加粗锚点必须跳过这些区段
    spans, i, n = [], 0, len(body)
    while i < n - 1:
        j = body.find("{{", i)
        if j < 0:
            break
        depth, k, end = 0, j, -1
        while k < n:
            two = body[k:k + 2]
            if two == "{{":
                depth += 1; k += 2; continue
            if two == "}}":
                depth -= 1; k += 2
                if depth == 0:
                    end = k; break
                continue
            k += 1
        if end < 0:
            spans.append((j, n)); break
        spans.append((j, end)); i = end
    return spans


def _first_bold_outside_templates(body: str, lo: int = 0, hi=None):
    # 导语锚点：第一个不在 {{...}} 模板内的 '''粗体'''（含捕获组的标题形态）。
    # 2026-10-20 修复（Ghostbloods 跨 mimo/deepseek 复现）：notice 位于导语之前，其
    # 内部粗体（'''extensive spoilers'''）曾被 ensure_en_tag / ensure_lead_title 当作
    # 导语标题——tag 插错位、正文粗体被误改成页名。锚点跳过模板区后两处同修。
    spans = _template_spans(body)
    hi = len(body) if hi is None else hi
    for m in re.finditer(r"'''\s*([^'\n]{1,80}?)\s*'''", body):
        if m.start() < lo or m.start() >= hi:
            continue
        if any(sm <= m.start() < em for sm, em in spans):
            continue
        return m
    return None


def body_english_feedback(translation: str):
    """生成正文块「半译残留」的纠错反馈（2026-10-20 用户裁定：从导语扩到所有块）。

    判定与 verify 门禁 3c **完全同源**（同一 mask_nonprose 掩码、同一「叙述词」口径），
    因此天然回答「AI 觉得不该翻怎么办」：
      - 引用/模板/URL/斜体书名/括号原名/keep_en/引号内原词 → 掩码后贡献 0 词，豁免；
      - 首字母大写的专名串不计（只数小写叙述词或停用词），表外词「宁保英文」不误伤；
      - 掩码后单行仍 ≥6 个叙述性英文词 = 按全部管线规则都该翻 → 回喂该行。
    只回喂一次；仍失败保留现译，由写回前门禁终裁（最坏维持现状，不会误写站）。
    返回 None 表示无需重试。
    """
    try:
        masked = mask_nonprose(translation)
        snippets = []
        for orig_ln, mask_ln in zip(translation.split("\n"), masked.split("\n")):
            if not orig_ln or orig_ln[0] in "|={" or orig_ln.startswith("[[category"):
                continue
            l = re.sub(r"<ref[^>]*>.*?</ref>", " ", mask_ln)
            l = re.sub(r"</?ref[^>]*>", " ", l)
            l = re.sub(r"\[\[[^\[\]]*\]\]", " ", l)
            words = re.findall(r"[A-Za-z]+", l)
            prose = [w for w in words
                     if w.lower() in _UNTRANSLATED_STOPWORDS or w == w.lower()]
            if len(prose) >= 6:
                snip = orig_ln.strip()[:160]
                if snip and snip not in snippets:
                    snippets.append(snip)
            if len(snippets) >= 4:
                break
        if not snippets:
            return None
        lines = "\n".join(f"  {i + 1}. {sn}" for i, sn in enumerate(snippets))
        return ("译文残留整段英文（下行已掩掉引用/模板/URL/斜体书名等按规则保留英文的"
                "部分，主体仍是英文叙述句）——这些句子必须整句翻译成简体中文：专名按"
                "译名表；引用原文、URL、模板名、书名斜体、括号原名标注保持原样即可，"
                "其余叙述文字全部翻译。残留行：\n" + lines)
    except Exception:
        return None


def ensure_aitranslation(body: str) -> str:
    """页首 {{AITranslation}} 标记（2026-10-23 用户指示：每个词条最顶部）。

    样例 Bot测试(豆包Seed):陆沙德 —— 第 1 行裸 {{AITranslation}}（无参），
    压在 {{CmPermission}} 之上。幂等：已含则原样返回。
    调用序（assemble 包装分支）：CmPermission → ensure_en_tag → ensure_lead_title
    → ensync → 本函数——必须后置，因为前两者依赖 body 以 CmPermission 起头的
    置顶假设。write.py 有同语义独立实现（其仅依赖 stdlib，不 import translate），
    tests_aitranslation.py 逐输入对等断言防两处漂移。
    """
    if "{{AITranslation}}" in body:
        return body
    return "{{AITranslation}}\n" + body


def ensure_en_tag(body: str, title_en: str) -> str:
    """决议#10 兜底：确保 {{en|title}} 恰好一处、且位于导语首行粗体标题之后。

    2026-10-18 增强：qwen3.8-27b 实测把 {{en|Ghostbloods}} 安放进 notice 模板
    （LLM 自己「放」的也可能错位）。现改为：先移除全部 {{en|...}}（错位/重复的
    一并清除），再按规范位置确定性插入——idempotent，正确位置的原有 tag
    移除后会在同一位重插，结果与原样一致。
    """
    # 1. 清除所有形态的 {{en|...}} / {{en}}（含错位进 notice 的）
    body = re.sub(r"\{\{\s*en\s*(?:\|[^}]*)?\}\}", "", body, flags=re.I)
    # 2. 规范位置插入：首个**模板区之外**的加粗标题之后（跳过 notice 等模板内粗体）
    tag = "{{en|" + title_en + "}}"
    m = _first_bold_outside_templates(body)
    if m:
        return body[:m.end()] + tag + body[m.end():]
    if body.startswith("{{CmPermission"):
        # 紧跟 CmPermission 模板闭合后插入，保持 CmPermission 置顶
        close = body.find("}}")
        if close != -1:
            return body[: close + 2] + tag + body[close + 2:]
    return tag + "\n" + body


def ensure_lead_title(body: str, title_en: str) -> str:
    """导语首行粗体标题的确定性兜底（R5/R2）：

    若译名表有该页英文标题的官方译名 zh，且首行 `'''X'''` 不含 zh → 强制纠正为 zh。
    覆盖两类实测违规（2026-10-18 qwen3.8-27b 批次）：
      a) 首行仍是英文（LLM 只动导语正文没动标题）→ 直接换成官方译名；
      b) 首行是自造中文译名（如 Shadows of Self 页译成「自影」，官方为「旧影森森」）。
    保守条件（防误伤）：仅当标题**不含**官方译名时才纠正（`鬼影（锡眼）` 这类
    含官方译名的扩展写法保留）；译名表无该标题条目时一律不动（宁保留不自造）。
    返回 (body, 纠正标记)。
    """
    global _GLOS_FINISH_CACHE
    if _GLOS_FINISH_CACHE is None:
        _GLOS_FINISH_CACHE = load_merged_glossary(DEFAULT_GLOSSARY, DEFAULT_COMMON)
    zh = _lookup_glossary_zh(_GLOS_FINISH_CACHE, title_en)
    if not zh:
        return body, False
    # 仅在导语区搜索（首个 === 级/== 级章节标题之前，上限 800 字符）——
    # 防止正文中部的粗体强调（如 '''卡西尔'''）被误当导语标题纠正。
    _hpos = len(body)
    for _hm in re.finditer(r"\n={2,4} ", body):
        _hpos = _hm.start()
        break
    m = _first_bold_outside_templates(body, hi=min(_hpos, 800))
    if not m:
        return body, False
    lead = m.group(1).strip()
    if not lead or zh in lead:
        return body, False  # 已含官方译名（正确或扩展写法）→ 不动
    return body[:m.start(1)] + zh + body[m.end(1):], True


# --------------------------------------------------------------------------- #
# 非正文掩码 + 确定性译名收尾（R2「表内必译」的机制化兜底）
#
# 2026-10-18 qwen3.8-27b 批次实测：LLM 大面积漏译正文表内词（MeLaan/Kelsier/
# Aradel 裸留英文），门禁只能拦截、不能修复。此掩码是 verify_translation 的
# 单一来源（tr.mask_nonprose），_glossary_finish_pass 在 assemble 内、LLM 之后
# 确定性执行——对所有页面/所有模型自动生效，使 R2 不依赖 LLM 自觉。
#
# 掩掉（等长空格替换，位置与 verify 完全同源）：
#   1. {{...}} 模板整体（map ref 数据键 / file ref 文件名 / for 目标 /
#      CmPermission / 分类模板参数 / Quote 原文块——非需译正文）；
#   2. 方括号外链 [url 显示]（interwiki，URL 与显示保留英文合法）；
#   3. 斜体 ''..''（书名/刊名保留区；'''粗体'''不掩——页内标题属正文）；
#   4. 括号英文原名标注 （English Name） / (English Name)；
#   5. <ref name="..." 属性（引用 id 键，动了会错位同名引用）；
#   6. keep_en 静态名单词组整体出现处（词组内的子词不被误替换）；
#   7. 配对引号内引用原词（ASCII + 中文弯引号；双关语/标题引述保留英文合法）。
# --------------------------------------------------------------------------- #

def _mask_span_spans(body: str, pattern: str, flags=0):
    """把匹配 pattern 的区段替换为空格，返回 (掩码文本, 原始 spans)。等长替换；
    换行符保留（行结构不塌——verify 3c 等按行 zip 的检查依赖行数一致）。"""
    out = []
    spans = []
    last = 0
    for m in re.finditer(pattern, body, flags):
        out.append(body[last:m.start()])
        out.append("".join("\n" if c == "\n" else " " for c in m.group(0)))
        spans.append((m.start(), m.end()))
        last = m.end()
    out.append(body[last:])
    return "".join(out), spans


_KEEP_EN_CACHE: list | None = None


def _keep_en_terms() -> list:
    global _KEEP_EN_CACHE
    if _KEEP_EN_CACHE is None:
        try:
            _KEEP_EN_CACHE = load_keep_en()
        except Exception:
            _KEEP_EN_CACHE = []
    return _KEEP_EN_CACHE


def mask_nonprose(body: str) -> str:
    """掩码「非需译正文」区段（等长空格替换），供裸词扫描与译名收尾替换共用。"""
    out = body
    # 1. 模板（括号平衡；Quote/sidequote/columns 原文块整体也在此掩掉）
    res = []
    i = 0
    n = len(out)
    while i < n:
        if out.startswith("{{", i):
            depth = 0
            j = i
            while j < n:
                if out.startswith("{{", j):
                    depth += 1
                    j += 2
                elif out.startswith("}}", j):
                    depth -= 1
                    j += 2
                    if depth <= 0:
                        break
                else:
                    j += 1
            res.append("".join("\n" if c == "\n" else " "
                                       for c in out[i:min(j, n)]))
            i = j
        else:
            res.append(out[i])
            i += 1
    out = "".join(res)
    # 2. 方括号外链 [url ...]
    out, _ = _mask_span_spans(out, r"\[(?:https?://|//)[^\[\]]+\]")
    # 3. 斜体（非粗体）''text'' —— 先保护粗体
    bolds = []
    def _save_bold(m):
        bolds.append(m.group(0))
        return f"\x00{len(bolds) - 1}\x00"
    out = re.sub(r"'''.+?'''", _save_bold, out, flags=re.S)
    out, _ = _mask_span_spans(out, r"''[^'\n]+''")
    out = re.sub(r"\x00(\d+)\x00", lambda m: bolds[int(m.group(1))], out)
    # 4. 括号英文原名标注
    out, _ = _mask_span_spans(out, r"[（(]\s*[A-Za-z][A-Za-z0-9 .,'&:\-]{2,80}\s*[）)]")
    # 5. ref 的 name 属性（自闭合与开标签同模式：动了会拆散同名引用对）
    out, _ = _mask_span_spans(out, r'<ref\s+name="[^"]*"', re.I)
    # 6. keep_en 静态名单词组整体出现处
    try:
        _ke = [t for t in _keep_en_terms() if len(t) >= 3]
        if _ke:
            _ke.sort(key=len, reverse=True)
            for t in _ke:
                pre = r"(?<![A-Za-z])" if t[0].isalpha() else ""
                suf = r"(?![A-Za-z])" if t[-1].isalpha() else ""
                out, _ = _mask_span_spans(out, pre + re.escape(t) + suf)
    except Exception:
        pass
    # 7. 配对引号内的引用原词（ASCII 与中文弯引号）
    out, _ = _mask_span_spans(out, r'"([A-Za-z][^"\n]{1,70})"')
    out, _ = _mask_span_spans(out, r"“([A-Za-z][^”\n]{1,70})”")
    out, _ = _mask_span_spans(out, r"'([A-Z][^'\n]{1,70})'")
    out, _ = _mask_span_spans(out, r"‘([A-Z][^’\n]{1,70})’")
    return out


_WIKILINK_BLOCK_RE = re.compile(r"\[\[[^\[\]]*\]\]")


def _finish_exempt_spans(body: str) -> list:
    """收尾替换的豁免区间：wikilink 整体（目标与显示文本）+ 原名行（+80 容忍，
    与 verify 的 is_in_struct 同源）。"""
    spans = [m.span() for m in _WIKILINK_BLOCK_RE.finditer(body)]
    for m in re.finditer(r"\| 原名\s*=", body):
        spans.append((m.start(), min(m.end() + 80, len(body))))
    return spans


def glossary_finish_terms(glossary: dict | None = None) -> list:
    """收尾替换/裸词扫描共用的词表：全译名表有 zh、长度≥3、非 keep_en、
    不含链接/占位符特殊字符的 (en, zh)，按 en 长度降序（长词优先）。"""
    if glossary is None:
        glossary = load_merged_glossary(DEFAULT_GLOSSARY, DEFAULT_COMMON)
    keep = set(_keep_en_terms())
    terms = []
    for en, v in glossary.items():
        if not isinstance(v, dict):
            continue
        zh = v.get("zh")
        if not zh or len(en) < 3 or en in keep:
            continue
        if any(c in en for c in "[{|%/\\"):
            continue
        terms.append((en, zh))
    terms.sort(key=lambda x: -len(x[0]))
    return terms


_GLOS_FINISH_CACHE: dict | None = None


def _glossary_finish_pass(body: str):
    """确定性译名收尾：LLM 之后按译名表把正文残留的表内英文词替换为官方译名。

    豁免与 verify 完全同源（mask_nonprose 掩码区 + wikilink 整体 + 原名行）——
    凡 verify 会判为 [裸词] 的位置，这里都会被替换；反之不替换 verify 已豁免的位置。
    返回 (body, 替换处数, 明细列表)。
    """
    global _GLOS_FINISH_CACHE
    if _GLOS_FINISH_CACHE is None:
        _GLOS_FINISH_CACHE = load_merged_glossary(DEFAULT_GLOSSARY, DEFAULT_COMMON)
    # 0) 中英杂交所有格反向修复：LLM 把英文词组头部译了、's 尾巴留着
    #    （实测 qwen3.8-27b 连续两跑把 keep_en 的 Harmony's Sword 写成 和谐's Sword，
    #    keep_en 提示也拦不住）。`中文词's + 英文词` 形态在正常中文里不存在 →
    #    按译名表反向还原为英文原词组（keep_en 整词保留是铁律）。
    n_hybrid = 0
    for _en, _v in _GLOS_FINISH_CACHE.items():
        if not isinstance(_v, dict):
            continue
        _zh = _v.get("zh")
        if not _zh or len(_zh) < 2:
            continue
        try:
            _hp = re.compile(r"(?<![A-Za-z])" + re.escape(_zh) + r"'s(?=\s+[A-Za-z])")
        except re.error:
            continue
        if _hp.search(body):
            body = _hp.sub(_en + "'s", body)
            n_hybrid += 1
    terms = glossary_finish_terms(_GLOS_FINISH_CACHE)
    masked = mask_nonprose(body)
    exempt = _finish_exempt_spans(body)

    def _exempted(start: int, end: int) -> bool:
        # 与 verify 同源：整段落在掩码区 → 不碰；起点落在 wikilink/原名行 → 不碰
        if masked[start:end].strip() == "":
            return True
        return any(a <= start < b for a, b in exempt)

    # 收集替换区间（长词优先、跨度去重），与 verify 裸词扫描同一套匹配
    replacements = []  # (start, end, zh)
    for en, zh in terms:
        if en not in body:
            continue
        try:
            pat = re.compile(r"(?<![A-Za-z])" + re.escape(en) + r"(?:'s)?(?![A-Za-z])")
        except re.error:
            continue
        for m in pat.finditer(body):
            if any(m.start() < b and m.end() > a for a, b, _z in replacements):
                continue
            if _exempted(m.start(), m.end()):
                continue
            replacements.append((m.start(), m.end(), zh))
    if not replacements:
        return body, n_hybrid, ([f"杂交所有格反向修复 x{n_hybrid}"] if n_hybrid else [])
    replacements.sort(key=lambda x: x[0])
    out = []
    last = 0
    details = [f"杂交所有格反向修复 x{n_hybrid}"] if n_hybrid else []
    for s, e, zh in replacements:
        out.append(body[last:s])
        # 所有格形态 `Kelsier's` → `卡西尔的`：'s 按中文「的」落位，避免 卡西尔's
        seg = body[s:e]
        if seg.endswith("'s"):
            out.append(zh + "的")
        else:
            out.append(zh)
        details.append(f"{seg} -> {zh if not seg.endswith(chr(39) + 's') else zh + '的'}")
        last = e
    out.append(body[last:])
    return "".join(out), len(replacements) + n_hybrid, details


def assemble(title_en: str, revid, chunk_results, no_wrap: bool, target_wiki: str,
             registry: list[dict] | None = None, refs: list[str] | None = None,
             orig_title: str | None = None, linklist_reg: list[str] | None = None):
    """把各块译文拼成完整 wikitext，填回决议#13 的英文原文占位符，并插入页面级包装（决议#10-12）。"""
    body = "\n".join(t for t, _ in chunk_results).strip("\n") + "\n"
    # 兜底：LLM 偶发把 <ref name="X"/> 变回模板形态 {{ref name="X"}}（无管道/带引号），
    # 中文站 Template:Ref 会 #invoke:Ref 报「函数{{{1}}}不存在」。用最新转换器的
    # _scan_refs 幂等归一一次（标准 <ref> 不受影响，残留模板形态被转回占位引用）。
    try:
        import importlib.util as _ilu2
        _sp = _ilu2.spec_from_file_location("ct_scanrefs", HERE / "convert_templates.py")
        _cm = _ilu2.module_from_spec(_sp)
        sys.modules[_sp.name] = _cm
        _sp.loader.exec_module(_cm)
        body = _cm._scan_refs(body)
        # 同名 ref 模板（file/bws/tor/reddit ref）文本可能被 LLM 分块翻译得不一致
        # （一处译中一处留英）→ 中文站报「name 属性 X 使用不同内容定义了多次」。
        # 统一同名多次调用的文本参数为首次非空值（同一来源，显示一致性优先）。
        body = _cm._normalize_dup_ref_texts(body)
    except Exception:
        pass  # 兜底失败不影响主流程（原文即标准形态时无需归一）
    # 决议#13：把 %%ORIGINAL_BLOCK_N%% 填回英文原文（若模型翻掉/漏了一并汇报）
    if registry:
        body, missing_tokens = unmask_protected_blocks(body, registry)
        if missing_tokens:
            sys.stderr.write("[提醒] 以下原文占位符未在译文中保留（模型漏掉，人工复核）：" + ", ".join(missing_tokens) + "\n")
    # 引用模板占位填回：%%REF_N%% → 英文源 ref 模板原文（编号 100% 与英文源一致）。
    # 顺序：引用填回要在原文块填回之后？——不，ref 占位在 mask_protected_blocks 之后产生，
    # 原文块（Quote/columns）内部的 ref 已随整块保护、不在 refs 里；正文 ref 的占位符
    # 独立存在，与此处顺序无关。这里先填回 ref（正文 ref 不依赖任何原文块结构）。
    if refs:
        body, missing_refs = unmask_ref_templates(body, refs)
        if missing_refs:
            sys.stderr.write("[提醒] 以下引用占位符未在译文中保留（模型漏掉，写回前必须补）：" + ", ".join(missing_refs) + "\n")
    # infobox「原名」占位填回英文标题
    if orig_title:
        body = unmask_infobox_original_name(body, orig_title)
    # infobox 纯内链列表占位填回（children/relatives/image 等）
    if linklist_reg:
        body = unmask_infobox_link_lists(body, linklist_reg)
    # 确定性译名收尾：LLM 之后按译名表替换正文残留表内词（掩码保护区不碰）。
    # R2「表内必译」的机制化兜底——2026-10-18 起对所有页面/所有模型自动生效。
    n_finish = 0
    try:
        body, n_finish, _fin_details = _glossary_finish_pass(body)
        if n_finish:
            sys.stderr.write(f"[译名收尾] 确定性替换 {n_finish} 处表内残留英文：" +
                             "、".join(_fin_details[:8]) + ("…" if len(_fin_details) > 8 else "") + "\n")
    except Exception as _fin_err:
        n_finish = 0
        sys.stderr.write(f"[提醒] 译名收尾替换失败（不影响主流程）: {_fin_err}\n")
    # 章节标题再断言（LLM 后，2026-10-22 长尾②）：LLM 可能把预译标题改回英文
    # （豆包实测 The Village：预译村庄→输出 Village，且其正文也把该词当专名保留），
    # 也可能漏译表内长尾标题。与 LLM 前同一查表：仅动纯 ASCII 标题，表内已知→译中文，
    # 表内未知→原样留待门禁 3a 拦截重跑；中文标题/非标题行不匹配正则，零接触。
    body, head_stats2 = translate_section_headings(body)
    if head_stats2:
        sys.stderr.write(f"[章节再断言] LLM 后修复标题 {len(head_stats2)} 处：" +
                         "、".join(head_stats2[:6]) + ("…" if len(head_stats2) > 6 else "") + "\n")
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
    # 收尾替换后，纯英文条目若已不在正文（被确定性替换掉了），「保留英文」不再成立 → 移除。
    # 引用原文条目（含全角括号/占位符字样）不会被 plain-ASCII 判定误删。
    if untranslated:
        _plain_en = re.compile(r"[A-Za-z0-9][A-Za-z0-9 .,'&:\-()]*")
        _kept = []
        for u in untranslated:
            en = u.get("en") if isinstance(u, dict) else None
            if (en and _plain_en.fullmatch(en)
                    and not re.search(r"(?<![A-Za-z])" + re.escape(en) + r"(?![A-Za-z])", body)):
                continue  # 已被收尾替换，条目作废
            _kept.append(u)
        untranslated = _kept

    _lead_fixed = False
    if no_wrap:
        meta_note = "纯正文翻译（--no-wrap，未加页面级包装）"
    else:
        body = "{{CmPermission|" + title_en + "}}\n" + body
        # 决议#10 兜底：{{en}} 本应由块0 LLM 安放（导语 '''中文名''' 之后），偶发丢失；
        # 此处确定性兜底，保证 CmPermission/ensync 依赖的 #var:en 一定被定义。
        body = ensure_en_tag(body, title_en)
        # 导语首行标题确定性兜底：未译英文标题/自造译名 → 官方译名（含 zh 才纠正）
        body, _lead_fixed = ensure_lead_title(body, title_en)
        if _lead_fixed:
            sys.stderr.write(f"[导语标题兜底] 首行粗体标题已纠正为译名表官方译名（{title_en}）\n")
        if "{{ensync|" not in body:
            body = body.rstrip("\n") + "\n{{ensync|" + str(revid) + "}}\n"
        # 页首 AI翻译标记（2026-10-23 用户指示：每词条最顶部，样例 Bot测试(豆包Seed):陆沙德）。
        # 置于 ensure_en_tag/ensure_lead_title 之后（二者依赖 CmPermission 置顶假设）。
        body = ensure_aitranslation(body)
        meta_note = "已加页面级包装 {{AITranslation}}（首行）/{{CmPermission}}（顶）/{{en}}（首行自动兜底）/{{ensync}}（尾，revid=" + str(revid) + "）"
    if n_finish:
        meta_note += f"；确定性译名收尾替换 {n_finish} 处（LLM 后按译名表兜底）"

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
# 决议#13 增强：{{Quote}}/{{columns}} 原文块按「中译本书证」采证中文（接入 glossary_assist.py）
# - 书证：块内 {{book ref|书码|章}} / {{epigraph ref|书|章}} / {{tes ref|天}} 定位 → 英书上下文 +
#   中书章节全文；**同章多条合并成一次 LLM 请求**（编号子条 + 共享中译本章节文本），每条返回
#   必须通过「官方中译本原文逐字子串（空白归一）」校验，失败回退单条请求，再失败保留英文
#   （正确性优先于省 token——用户裁定 2026-10-20）。
# - 出处行（attribution）页面级批量翻译：{{...}}/[[...]]/HTML 先占位后还原，专名按译名表校验；
#   半自动/全自动都替换（出处行是页面文字，不属决议#13 的英文原文保护对象）。
# - 找不到（意译/不在书中/无 ref/该书无中译/校验不过）→ 保留英文（诚实，不硬翻）。
# - 两档：自动（默认，2026-10-21 用户裁定，采证到的正文直接替换为中文）；半自动（--no-auto-quote-cn
#   quote 正文不动，proposed_cn 供 review）。
# --------------------------------------------------------------------------- #
_REF_TMPL_ANY_RE = re.compile(r"\{\{\s*([A-Za-z][A-Za-z0-9 ]*?(?:ref|date))\s*[|}]", re.I)
_SUPPORTED_REF_RES = (
    ("book", re.compile(r"\{\{\s*book\s+ref\s*\|([^}]*)\}\}", re.I)),
    ("epigraph", re.compile(r"\{\{\s*epigraph\s+ref\s*\|([^}]*)\}\}", re.I)),
    ("tes", re.compile(r"\{\{\s*tes\s+ref\s*\|([^}]*)\}\}", re.I)),
)


def has_ref_any(source: str) -> bool:
    """块内是否存在任何 ref/日期类模板（book/tes/msh/rpg/au/wob/file/map/…/date）。"""
    return bool(_REF_TMPL_ANY_RE.search(source))


def _ref_chapter(params):
    """ref 的章节参数 → '12' | 'prologue'/'epilogue'/'postscript' | 'i-4'（插曲）；解析不了 None。"""
    if not params:
        return None
    p0 = params[0].strip()
    low = p0.lower()
    if p0.isdigit():
        return p0
    if low in ("prologue", "epilogue", "postscript"):
        return low
    if re.fullmatch(r"[ivxl]+", low) and len(params) > 1 and params[1].strip().isdigit():
        return f"{low}-{params[1].strip()}"
    return None


def extract_book_ref(source: str):
    """块内支持的书证 ref → (书码, 章)，取出现位置最靠前的一个；解析不了 → None。

    支持 {{book ref|code|ch}}（含 epilogue/prologue 段、插曲 i|N、滤除 review=yes 类命名参数
    与空参数）、{{epigraph ref|code|ch}}、{{tes ref|N|labels}}（书码固定 'tes'）。
    msh/rpg/au/wob/file/map 等其它 ref、单参整书 ref、无法解析的章参 → None（调用方用
    has_ref_any 区分 no-ref / unsupported-ref，均保留英文）。
    """
    best = None
    for kind, pat in _SUPPORTED_REF_RES:
        for m in pat.finditer(source):
            if best is None or m.start() < best[0]:
                best = (m.start(), kind, m.group(1))
    if best is None:
        return None
    _, kind, raw = best
    params = [p.strip() for p in raw.split("|")]
    params = [p for p in params if p and not re.match(r"^[A-Za-z_][A-Za-z0-9_ ]*=", p)]
    if not params:
        return None
    if kind == "tes":
        ch = _ref_chapter(params)
        return ("tes", ch) if ch else None
    ch = _ref_chapter(params[1:])
    return (params[0].lower(), ch) if ch else None


# ---------------------------- quote 块参数拆分/重建 ---------------------------- #
_SIDE_VAL_RE = re.compile(r"^\s*(?:left|right|center|centre|clear|both|none)\s*$", re.I)
_SIZE_VAL_RE = re.compile(
    r"^\s*[\d.]+\s*(?:px|%|em|ex|pt)?\s*;?\s*(?:\{\{.*?\}\}|\[\[.*?\]\])?\s*$", re.S)


def split_quote_block(source: str):
    """解析 {{quote|text|attr…|…}} → 参数结构 dict（mwparserfromhell，保原格式）。

    返回 {"tpl", "text_i", "text_val", "attrs_i", "attr_vals"]}（下标 = tpl.params 序号）：
    - 正文 = 第一个位置参数（无位置参数则命名 1=）；
    - 出处行 = 其余非结构位置参数 + 命名 2=（跳过空参数；`right`/`400px;` 等 side/size 形态的
      **位置**参数视为结构参数，其后不再当出处行）；
    - 其它命名参数（side=/size=/Size=/width=/multiline=…）由 rebuild 原样保留。
    解析不出模板 → None。
    """
    code = mwparserfromhell.parse(source)
    tpl = None
    for n in code.nodes:
        if isinstance(n, mwparserfromhell.nodes.Template):
            tpl = n
            break
    if tpl is None:
        return None
    positional, named = [], {}
    for i, pr in enumerate(tpl.params):
        if pr.showkey:
            named[str(pr.name).strip()] = i
        else:
            positional.append(i)
    text_i = positional[0] if positional else named.get("1")
    attrs_i = []
    struct = False
    for i in positional[1:]:
        v = str(tpl.params[i].value)
        if not struct and (_SIDE_VAL_RE.match(v) or _SIZE_VAL_RE.match(v)):
            struct = True
        if struct or not v.strip():
            continue
        attrs_i.append(i)
    if "2" in named and named["2"] not in attrs_i:
        attrs_i.append(named["2"])
    return {
        "tpl": tpl,
        "text_i": text_i,
        "text_val": str(tpl.params[text_i].value) if text_i is not None else "",
        "attrs_i": attrs_i,
        "attr_vals": [str(tpl.params[i].value) for i in attrs_i],
    }


# ---------------------------- 定位用文本清洗 ---------------------------- #
_TPL_NAME_RE = re.compile(r"(?i)(?:\bref\b|\bdate\b|\btes\b|\bepigraph\b)")


def _clean_locate_text(text: str, reverse=None) -> str:
    """正文参数值 → 用于英书定位的纯文本。

    - 引用/日期/tes/epigraph 模板与 {{b|…}} 速记 → 删除；
    - small caps 等「有位置参数的包裹模板」→ 解包取其正文（旧实现整段正则删除会把
      `{{small caps|句子}}` 的句子整个丢掉，导致定位必失）；
    - [[链接]] 取显示名；无显示名时若目标已被 translate_plain_links 先行译中（如 [[高图纳]]），
      用 reverse={中文:英文} 反查回英文（否则英书定位不到）；
    - HTML 标签删、HTML 实体还原。
    """
    s = text or ""

    def _sub_tpl(m):
        name, rest = m.group(1), m.group(2) or ""
        if name.strip().lower() == "b" or _TPL_NAME_RE.search(name):
            return ""
        parts = [p for p in rest.lstrip("|").split("|") if p.strip()]
        return parts[0] if parts else ""

    for _ in range(6):
        s2 = re.sub(r"\{\{\s*([^|{}]+)(\|[^{}]*)?\}\}", _sub_tpl, s)
        if s2 == s:
            break
        s = s2

    def _sub_link(m):
        parts = m.group(1).split("|")
        if len(parts) > 1 and parts[-1].strip():
            return parts[-1]
        tgt = parts[0].strip()
        if reverse and tgt in reverse:
            return reverse[tgt]
        return tgt

    s = re.sub(r"\[\[([^\[\]]+)\]\]", _sub_link, s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return s.strip()


def quote_locate_text(source: str, reverse=None) -> str:
    """{{quote|TEXT|attr}} 的 TEXT → 英书定位用纯文本（不含出处行）。"""
    p = split_quote_block(source)
    if not p or p["text_i"] is None:
        inner = source.split("|", 1)[1] if "|" in source else source
        return _clean_locate_text(inner, reverse)
    return _clean_locate_text(p["text_val"], reverse)


def quote_inner_text(source: str, reverse=None) -> str:
    """从 {{Quote|TEXT|attr...}} 提取正文（旧实现把出处行也算进正文，已修：只取正文参数）。"""
    return quote_locate_text(source, reverse)


def _reverse_glossary(glossary):
    """{中文译名: 英文键}（按键序优先，冲突取先者）——供 _clean_locate_text 反查译中的链接。"""
    rev = {}
    if not glossary:
        return rev
    for k in sorted(glossary):
        e = glossary.get(k)
        zh = e.get("zh") if isinstance(e, dict) else None
        if isinstance(zh, str) and zh and zh not in rev:
            rev[zh] = k
    return rev


def distinctive_phrases(text: str, max_n: int = 5) -> list[str]:
    """从一段文字里取若干『有分辨性的子句』作对齐锚点（≥3 词、去模板）。"""
    text = re.sub(r"\{\{.*?\}\}", "", text)
    sents = re.split(r"(?<=[.!?])\s+", text)
    out = []
    for s in sents:
        words = re.findall(r"[A-Za-z][A-Za-z'’\-]*", s)
        if len(words) >= 3:
            out.append(s.strip())
        if len(out) >= max_n:
            break
    return out


def _ga():
    import importlib.util
    spec = importlib.util.spec_from_file_location("ga_mod", HERE / "glossary_assist.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


def locate_verbatim(term: str, ref, ctx: int, full_zh: bool = True,
                    fallback_whole_book: bool = True):
    """在 (书码,章) 里定位 term，返回 glossary_assist 的 locate 结果 dict。

    - full_zh：回填 zh_full/zh_pos（中书该章全文+命中位置，供 verify_zh_official 逐字校验）。
    - fallback_whole_book：该章无文件/章内无命中时在同一本书内整书搜（如皇帝魂 41/52/57 天
      无独立章节文件），命中记 fallback="whole-book"。
    - 该书无中译版 → None（调用方记 no-cn-edition，无从校验 → 保留英文）。
    """
    if not ref:
        return None
    ga = _ga()
    code, ch = ref
    if code not in ga.BOOKS:
        return None
    if ga.BOOKS[code][1] is None:
        return None
    return ga.locate(term, code, ch, ctx=ctx, full_zh=full_zh,
                     fallback_whole_book=fallback_whole_book)


# ---------------------------- 中译本逐字校验 ---------------------------- #
def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def _candidate_zh(zh: str):
    """模型返回值的候选形态：去围栏/首尾空白的原样，及去包装引号的变体。"""
    s = (zh or "").strip()
    s = re.sub(r"^```[A-Za-z]*\s*|\s*```$", "", s).strip()
    if not s:
        return []
    out = [s]
    stripped = s.strip("\"'“”‘’")
    if stripped and stripped != s:
        out.append(stripped)
    return out


def _stitch_cover(z: str, full: str, expect_pos, tol) -> bool:
    """z（已归一）能否作为「full 中若干相邻片段的拼接」被覆盖——每段≥4字且逐字在 full 中。

    用于验收英文引文省略了书中旁白的场合（如 "...We don't...Rememberers."）：LLM 可按英文
    省略方式拼接中译本相邻片段，但每段必须逐字来自中译本。首段还须落在 expect_pos 允差内。
    """
    n = len(z)
    i = 0
    while i < n:
        remain = n - i
        seg = min(4, remain)
        if z[i:i + seg] not in full:
            return False
        if remain <= seg:
            seg_len = remain
        else:
            # 前缀单调（在原文 → 其前缀必在原文）：二分找最长可命中前缀
            lo, hi, best = seg, remain, seg
            while lo <= hi:
                mid = (lo + hi) // 2
                if z[i:i + mid] in full:
                    best = mid
                    lo = mid + 1
                else:
                    hi = mid - 1
            seg_len = best
        pos = full.find(z[i:i + seg_len])
        if i == 0 and expect_pos is not None and abs(pos - expect_pos) > tol:
            return False
        i += seg_len
    return True


def verify_zh_official(zh, zh_full, expect_pos=None, tol=None):
    """校验 zh 是官方中译本章节的逐字原文（空白归一；允许按省略拼接的多段覆盖）。

    通过 → 返回**应采用**的候选形态（可能已去包装引号）；不通过 → None（保留英文）。
    expect_pos（zh_full 归一化坐标，由 locate 的 zh_pos 换算）给定时要求首段命中在其附近
    （默认允差 max(1000, len/3)），防同章错句。正确性优先：宁可不译，不放行改写/幻觉译文。
    """
    n_full = _norm_ws(zh_full)
    if not n_full:
        return None
    if tol is None:
        tol = max(1000, len(n_full) // 3)
    for cand in _candidate_zh(zh):
        if "__NONE__" in cand:
            return None
        n_zh = _norm_ws(cand)
        if len(n_zh) < 2:
            continue
        start = n_full.find(n_zh)
        while start >= 0:
            if expect_pos is None or abs(start - expect_pos) <= tol:
                return cand
            start = n_full.find(n_zh, start + 1)
        if _stitch_cover(n_zh, n_full, expect_pos, tol):
            return cand
    return None


def _zh_expect_pos(loc, zh_full):
    """locate 记录的 zh_pos（原文坐标）→ zh_full 归一化坐标。"""
    zp = (loc or {}).get("zh_pos")
    if zp is None or not zh_full:
        return None
    return len(_norm_ws(zh_full[:zp]))


def ask_zh_from_region(en_text: str, en_ctx: str, zh_region: str, cfg) -> str:
    """单条回退：让 LLM 从中文对照区摘出 en_text 的官方中译。原样返回（校验交给
    verify_zh_official），找不到返回 ''。"""
    sys_prompt = (
        "你是官方中译本的核对器。给出这句英文在官方中译本里的确切中文译文。只输出译文本身，"
        "不要解释、不要夹杂英文、不要在译文外加引号或标注。若英文是书中原文的节选或拼接"
        "（省略了中间文句），可把片断里相邻的对应片段按英文的省略方式拼接，但每段必须逐字取自"
        "中译本、且不得加入英文里没有的文句。片断里找不到对应译文时，只输出 __NONE__。"
    )
    user = (
        "英文原文：\n" + en_text +
        "\n\n英文上下文（供定位）：\n" + (en_ctx or "")[:400] +
        "\n\n中译本章节文本片断（可能含无关文句，请找到与英文对应的部分）：\n" +
        (zh_region or "")[:1200]
    )
    try:
        reply = llm_chat(cfg, [{"role": "system", "content": sys_prompt},
                               {"role": "user", "content": user}],
                         max_output_tokens=500, temperature=0)
    except Exception as e:
        sys.stderr.write(f"[quote-zh] LLM 采证失败：{e}\n")
        return ""
    out = (reply or "").strip()
    if not out or "__NONE__" in out:
        return ""
    return out


def ask_zh_batch(items, zh_shared, cfg) -> str:
    """同章多条一次请求（省 token；用户裁定：正确性优先，同章合并）。

    items: [{'id', 'en', 'en_ctx', 'win'}]；zh_shared 非空 → 中书章节全文一次下发
    （由调用方限长），否则每条自带对照区窗口 win。返回原始 reply，解析交给 parse_batch_reply。
    """
    sys_prompt = (
        "你是官方中译本的核对器（收到的是按章节提供的中译本原文）。逐条给出英文在官方中译本里"
        "对应的中文译文。规则：1) 只逐字摘录中译本原文，不改写、不增删标点、不夹杂英文、不解释；"
        "2) 若英文是书中原文的节选或拼接（省略了中间文句），可将中译本中相邻的对应片段按英文的"
        "省略方式拼接，但每个片段必须逐字取自中译本，且不得加入英文里没有的文句；"
        "3) 找不到对应译文的条目，值写 __NONE__；"
        '4) 只输出一个 JSON 对象，键为条目编号字符串（"1"、"2"…），值为译文或 __NONE__，'
        "不要输出其它任何文字。"
    )
    parts = []
    if zh_shared:
        parts.append("中译本章节文本（可能含无关文句）：\n" + zh_shared)
    parts.append("英文条目：")
    for it in items:
        parts.append(f"[{it['id']}] {it['en']}")
        parts.append("    英文上下文（供定位）：" + (it.get("en_ctx") or "")[:400])
        if not zh_shared:
            parts.append("    对应中译本片段：" + (it.get("win") or "")[:1200])
    user = "\n".join(parts)
    return llm_chat(cfg, [{"role": "system", "content": sys_prompt},
                          {"role": "user", "content": user}],
                    max_output_tokens=max(600, 300 * len(items)), temperature=0)


def parse_batch_reply(reply):
    """批量采证回复 → {str(id): zh}；解析失败返回 None。容忍 ```json 围栏与数组形态。"""
    s = (reply or "").strip()
    s = re.sub(r"^```[A-Za-z]*\s*|\s*```$", "", s).strip()
    m = re.search(r"[\[{].*[\]}]", s, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except Exception:
        return None
    out = {}
    if isinstance(data, dict):
        for k, v in data.items():
            out[str(k).strip()] = (v or "") if isinstance(v, (str, type(None))) else str(v)
    elif isinstance(data, list):
        for e in data:
            if isinstance(e, dict) and "id" in e:
                v = e.get("zh", e.get("text", ""))
                out[str(e["id"]).strip()] = v if isinstance(v, str) else str(v)
    else:
        return None
    return out


# ---------------------------- 单位定位与分组采证 ---------------------------- #
def _ctx_for(text: str, ctx: int) -> int:
    """窗口随引文长度放大（ctx 是下限），防长引文的中书对照区被截断。"""
    return max(ctx, min(2400, len(text) * 2 + 200))


def _locate_units(units, ctx: int):
    """确定性定位（无 LLM）：整段直查 → 特征子句。填充 u['book'/'chapter'/'loc'/'matched'/'reason']。"""
    ga = _ga()
    for u in units:
        text = u.get("en") or ""
        if not u.get("ref"):
            u["reason"] = "unsupported-ref" if u.get("has_ref") else "no-ref"
            continue
        code, ch = u["ref"]
        u["book"], u["chapter"] = code, ch
        if not text:
            u["reason"] = "no-text"
            continue
        if code not in ga.BOOKS:
            u["reason"] = "bad-book"
            continue
        if ga.BOOKS[code][1] is None:
            u["reason"] = "no-cn-edition"  # 该书无中译版 → 无从校验 → 保留英文（诚实）
            continue
        loc = locate_verbatim(text, u["ref"], _ctx_for(text, ctx))
        matched = text
        if loc and not loc.get("found"):
            for frag in distinctive_phrases(text):
                l2 = locate_verbatim(frag, u["ref"], _ctx_for(text, ctx))
                if l2 and l2.get("found"):
                    loc, matched = l2, frag
                    break
        if loc is None:
            u["reason"] = "bad-book"
            continue
        u["loc"], u["matched"] = loc, matched
        if not loc.get("found"):
            err = loc.get("error") or ""
            u["reason"] = "no-chapter" if "无该章" in err else "not-in-book"
            continue
        if not (loc.get("zh_full") or ""):
            u["reason"] = "no-zh-chapter"  # 中书章节对照缺失 → 无法逐字校验 → 保留英文
            continue
        u["reason"] = None  # 待采证


def _resolve_text_units(units, cfg, ctx: int):
    """按 (书码, 章, 中书文件) 分组 → 同章一次 LLM 请求 → 逐条 verify；失败回退单条。"""
    groups = {}
    for u in units:
        if u.get("reason") is None and (u.get("loc") or {}).get("found"):
            key = (u["ref"][0], str(u["ref"][1]), u["loc"].get("zh_file"))
            groups.setdefault(key, []).append(u)
    for key, us in groups.items():
        sys.stderr.write(f"[原文块采证] 同章合并 {key[0]}|{key[1]}"
                         f"（{len(us)} 条，中书 {key[2] or '?'}）\n")
        zh_full0 = (us[0].get("loc") or {}).get("zh_full") or ""
        shared = zh_full0 if 0 < len(zh_full0) <= 12000 else None  # 超长章节退回窗口模式
        for start in range(0, len(us), 10):  # 单请求上限 10 条
            chunk = us[start:start + 10]
            items = [{"id": i + 1, "en": u["en"],
                      "en_ctx": (u["loc"].get("en_contexts") or [""])[0],
                      "win": u["loc"].get("zh_region") or ""}
                     for i, u in enumerate(chunk)]
            got = None
            try:
                got = parse_batch_reply(ask_zh_batch(items, shared, cfg))
            except Exception as e:
                sys.stderr.write(f"[原文块采证] 批量请求失败（回退单条）：{e}\n")
            for it, u in zip(items, chunk):
                zh_full_u = u["loc"].get("zh_full") or ""
                exp = _zh_expect_pos(u["loc"], zh_full_u)
                zh = None
                if got is not None:
                    zh = verify_zh_official(got.get(str(it["id"]), ""), zh_full_u, exp)
                if zh:
                    u.update(found=True, zh=zh, reason="ok", via="batch")
                    continue
                raw2 = ask_zh_from_region(it["en"], it["en_ctx"], it["win"], cfg)
                zh2 = verify_zh_official(raw2, zh_full_u, exp)
                if zh2:
                    u.update(found=True, zh=zh2, reason="ok", via="single")
                else:
                    u.update(found=False, zh=None,
                             reason="llm-no-match" if not raw2 else "verify-fail")


# ---------------------------- 出处行（attribution）批量翻译 ---------------------------- #
_ATTR_ATOM_RE = re.compile(r"\{\{.*?\}\}|\[\[.*?\]\]|<[^>]+>", re.S)


def mask_attr_atoms(piece: str):
    """出处行里的引用模板/内链/HTML 标签 → ⟦n⟧ 占位（LLM 动不到，还原时原样回填）。"""
    atoms = []

    def repl(m):
        atoms.append(m.group(0))
        return f"⟦{len(atoms) - 1}⟧"
    return _ATTR_ATOM_RE.sub(repl, piece), atoms


def unmask_attr_atoms(text: str, atoms) -> str:
    for i, a in enumerate(atoms):
        text = text.replace(f"⟦{i}⟧", a)
    return text


def attr_placeholders_ok(text: str, atoms) -> bool:
    """占位符各出现一次、相对顺序与原出处行完全一致。"""
    return re.findall(r"⟦(\d+)⟧", text or "") == [str(i) for i in range(len(atoms))]


def _attr_gloss_ok(zh_out, gloss_terms, raw) -> bool:
    """出处行译文必须用上译名表里该行出现过的专名（用户规则：Shai/Forgery/Gaotona 查表）。"""
    for t, e in (gloss_terms or {}).items():
        if re.search(r"(?<![A-Za-z])" + re.escape(t) + r"(?![A-Za-z])", raw, re.I):
            if (e.get("zh") or "") not in (zh_out or ""):
                return False
    return True


def _attr_prompt(items, gloss_pairs):
    gloss_txt = "；".join(gloss_pairs) if gloss_pairs else "（本页出处行无表内专名）"
    sys_prompt = (
        "你是 wiki 中英词条「引文出处行」（quote 模板的第二参数，格式：`原文|出处行`）的翻译器。"
        "逐条把英文出处行译成简体中文。规则：1) ⟦n⟧ 是引用模板/内链/HTML 标签的占位符，必须原样"
        "保留在译文里，且相对顺序不能变；2) 专名优先按下方译名表翻译；译名表未收录的英文专名"
        "保留英文原文；3) 只输出一个 JSON 对象，键为条目编号字符串，值为该条译文；不要解释、"
        "不要整体加引号、不要输出其它任何文字。"
    )
    parts = ["译名表（本页出处行出现的词）：" + gloss_txt, "出处行："]
    for it in items:
        parts.append(f"[{it['id']}] {it['masked']}")
    return [{"role": "system", "content": sys_prompt},
            {"role": "user", "content": "\n".join(parts)}]


def _attr_valid(zh_raw, job):
    """出处行译文校验：有中文、占位符齐且序对、译名表专名用上。通过返回可用形态，否则 None。"""
    for c in _candidate_zh(zh_raw):
        if not re.search(r"[一-鿿]", c):
            continue
        if not attr_placeholders_ok(c, job["atoms"]):
            continue
        if not _attr_gloss_ok(c, job["gloss"], job["raw"]):
            continue
        return c
    return None


def _resolve_attributions(units, cfg, glossary):
    """出处行页面级批量翻译（半自动/全自动都做：出处行是页面文字，不属决议#13 保护对象）。

    失败（LLM 无输出/占位符丢失/译名表专名缺失）→ 保留英文并记 attr_reason 供 review。
    """
    jobs = []
    for u in units:
        p = u.get("parsed")
        if not p:
            continue
        if not p.get("attrs_i"):
            u["attr_reason"] = "no-attr"
            continue
        raw = ""
        for v in p["attr_vals"]:
            s = v.strip()
            if not s:
                continue
            if not raw:
                raw = s
            elif s.startswith(("{{", "[[", "<")):
                raw += s
            else:
                raw += " " + s
        masked, atoms = mask_attr_atoms(raw)
        u["attr_en"] = raw
        if not re.search(r"[A-Za-z]{2,}", masked):
            u["attr_reason"] = "no-translatable-text"
            continue
        jobs.append({"u": u, "raw": raw, "masked": masked, "atoms": atoms,
                     "terms": extract_en_terms(raw), "gloss": {}})
    if not jobs:
        return
    glossary = glossary or {}
    all_terms = set()
    for j in jobs:
        all_terms |= j["terms"]
    slice_all = slice_glossary(glossary, all_terms)
    for j in jobs:
        j["gloss"] = {t: slice_all[t] for t in j["terms"] if t in slice_all}
    gloss_pairs = sorted(f"{t} → {e['zh']}" for t, e in slice_all.items() if e.get("zh"))
    items = [{"id": i + 1, "masked": j["masked"]} for i, j in enumerate(jobs)]
    got = None
    try:
        reply = llm_chat(cfg, _attr_prompt(items, gloss_pairs),
                         max_output_tokens=max(600, 300 * len(items)), temperature=0)
        got = parse_batch_reply(reply)
    except Exception as e:
        sys.stderr.write(f"[出处行采证] 批量请求失败（回退单条）：{e}\n")
    for it, j in zip(items, jobs):
        u = j["u"]
        zh_masked = None
        saw = False
        via = "batch"
        if got is not None and str(it["id"]) in got:
            saw = True
            zh_masked = _attr_valid(got.get(str(it["id"]), ""), j)
        if not zh_masked:
            via = "single"
            try:
                one = parse_batch_reply(llm_chat(
                    cfg, _attr_prompt([it], gloss_pairs),
                    max_output_tokens=300, temperature=0))
                if one and str(it["id"]) in one:
                    saw = True
                    zh_masked = _attr_valid(one.get(str(it["id"]), ""), j)
            except Exception:
                zh_masked = None
        if zh_masked:
            u["attr_zh"] = unmask_attr_atoms(zh_masked, j["atoms"])
            u["attr_reason"] = "ok"
            u["attr_via"] = via
        else:
            u["attr_reason"] = "verify-fail" if saw else "llm-fail"


# ---------------------------- 重建与编排 ---------------------------- #
def rebuild_quote_block(source, zh_text=None, zh_attr=None) -> str:
    """按采证结果重建原文块（保模板名/参数结构：side/size/width/multiline/命名参数均不动）。

    - zh_text（仅自动档默认给；--no-auto-quote-cn 半自动时不给）→ 替换正文参数；正文参数里罕见的引用模板
      （如 {{book ref}}）保留在译文后，参数尾随换行保留（多行排版）。
    - zh_attr（半自动/全自动都给）→ 替换首个出处参数，其余出处参数置空（其中的 ref 经
      占位还原不丢，渲染位置不变）。
    """
    p = split_quote_block(source)
    if not p:
        return source
    tpl = p["tpl"]
    if zh_text is not None and p["text_i"] is not None:
        val = zh_text
        refs = []
        for m in re.finditer(r"\{\{([^|{}]+)(\|[^{}]*)?\}\}", p["text_val"]):
            if re.search(r"(?i)(?:\bref\b|\bdate\b)", m.group(1)):
                refs.append(m.group(0))
        if refs:
            val += "".join(refs)
        val += re.search(r"\s*$", p["text_val"]).group(0)
        tpl.params[p["text_i"]].value = val
    if zh_attr is not None and p["attrs_i"]:
        first = p["attrs_i"][0]
        trail = re.search(r"\s*$", p["attr_vals"][0]).group(0)
        tpl.params[first].value = zh_attr + trail
        for i in p["attrs_i"][1:]:
            tpl.params[i].value = ""
    return str(tpl)


def resolve_blocks(registry, body: str, cfg, auto: bool, ctx: int = 160, glossary=None):
    """对 registry 各受保护块按书证采证中文（同章批量 + 逐条校验 + 单条回退 + 出处行批量翻译）。

    返回 (new_body, quote_resolutions)：
    - quote/sidequote：{token, type, en_preview, book, chapter, found, proposed_cn, reason,
      via?, en_file?, fallback?, attr_en, attr_zh, attr_reason, attr_via?}
    - columns：另加 resolved_lines/total_lines/lines[]（行级走同一套批量机制）
    - auto=True：found 的正文替换为中文；半自动不替换正文。出处行两档都替换。
    """
    resolutions = []
    new_body = body
    if not registry:
        return new_body, resolutions
    reverse = _reverse_glossary(glossary) if glossary else {}
    units, blk_units = [], {}
    for bi, blk in enumerate(registry):
        src = blk["source"]
        if blk["type"] in ("quote", "sidequote"):
            u = {"blk": bi, "kind": "quote", "src": src, "type": blk["type"]}
            u["parsed"] = split_quote_block(src)
            u["en"] = quote_inner_text(src, reverse)
            u["ref"] = extract_book_ref(src)
            u["has_ref"] = has_ref_any(src)
        elif blk["type"] == "columns":
            for li, ln in enumerate(src.splitlines()):
                s = ln.strip()
                if not s.startswith("*"):
                    continue
                title = re.sub(r"\{\{.*?\}\}", "", s).strip().lstrip("*").strip()
                title = re.sub(r"^\[\[(.*?)\]\]$", r"\1", title).strip()
                u = {"blk": bi, "kind": "column", "line_i": li, "line": ln, "src": src,
                     "type": "columns", "title": title,
                     "en": _clean_locate_text(title, reverse),
                     "ref": extract_book_ref(s), "has_ref": has_ref_any(s)}
        else:
            continue
        units.append(u)
        blk_units.setdefault(bi, []).append(u)
    _locate_units(units, ctx)               # 1) 确定性定位（无 LLM）
    _resolve_text_units(units, cfg, ctx)    # 2) 同章批量采证 + 单条回退（LLM）
    _resolve_attributions(units, cfg, glossary)  # 3) 出处行页面级批量翻译（LLM）

    for bi, blk in enumerate(registry):
        us = blk_units.get(bi, [])
        src = blk["source"]
        if blk["type"] == "columns":
            rebuilt = list(src.splitlines())
            found_n = 0
            line_entries = []
            for u in us:
                line_entries.append({"line": (u.get("line") or "").strip(),
                                     "title": u.get("title"), "ref": u.get("ref"),
                                     "found": bool(u.get("found")),
                                     "proposed_cn": u.get("zh"),
                                     "reason": u.get("reason")})
                if u.get("found"):
                    found_n += 1
                    rebuilt[u["line_i"]] = "*" + u["zh"]
            rebuilt_text = "\n".join(rebuilt) if found_n else None
            refu = next((u for u in us if u.get("ref")), None)
            entry = {
                "token": blk["token"], "type": "columns",
                "en_preview": (us[0].get("title", "") if us else "")[:80],
                "book": refu["ref"][0] if refu else None,
                "chapter": refu["ref"][1] if refu else None,
                "found": found_n > 0,
                "proposed_cn": rebuilt_text,
                "reason": "columns",
                "resolved_lines": found_n, "total_lines": len(us),
                "lines": line_entries,
            }
            if auto and rebuilt_text and src in new_body:
                new_body = new_body.replace(src, rebuilt_text)
        else:
            u = us[0] if us else {"type": blk["type"], "reason": "no-ref"}
            attr_zh = u.get("attr_zh")
            text_zh = u.get("zh") if auto else None
            if (text_zh or attr_zh) and src in new_body:
                new_body = new_body.replace(
                    src, rebuild_quote_block(src, zh_text=text_zh, zh_attr=attr_zh))
            entry = {
                "token": blk["token"], "type": blk["type"],
                "en_preview": (u.get("en") or "")[:80],
                "book": u.get("book"), "chapter": u.get("chapter"),
                "found": bool(u.get("found")),
                "proposed_cn": u.get("zh"),
                "reason": u.get("reason") or ("ok" if u.get("found") else "no-ref"),
                "attr_en": u.get("attr_en"),
                "attr_zh": u.get("attr_zh"),
                "attr_reason": u.get("attr_reason"),
            }
            for k in ("via", "attr_via"):
                if u.get(k):
                    entry[k] = u[k]
            loc = u.get("loc") or {}
            if loc.get("en_file"):
                entry["en_file"] = loc["en_file"]
            if loc.get("fallback"):
                entry["fallback"] = loc["fallback"]
        resolutions.append(entry)
    return new_body, resolutions


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="英文 converted wikitext → 中文 wikitext，产出 translation.json 契约")
    ap.add_argument("--title", required=True, help="快照标题（读取 en_snapshot/<标题>/wikitext.txt，内存里转成转换后形态）")
    ap.add_argument("--glossary", default=str(DEFAULT_GLOSSARY))
    ap.add_argument("--max-chars", type=int, default=7000, help="每块最大字符数（超长词条按此切块）")
    ap.add_argument("--redo-chunks", default=None,
                    help="逗号分隔块号（0基）：只对这些块重新 LLM 采样，其余块复用现有 "
                         "translation.json 的 chunk_results（分块门禁重试，2026-10-23）。"
                         "要求产物含 chunk_results 且块数一致，否则报错（调用方回退整页重跑）")
    ap.add_argument("--concurrency", type=int, default=1, help="并发翻译块数（默认 1）")
    ap.add_argument("--dry-run", action="store_true", help="只做分块+提示词预演，不调用 LLM")
    ap.add_argument("--no-wrap", action="store_true", help="不插入页面级包装，只输出纯正文")
    ap.add_argument("--llm-base-url", default=os.environ.get("LLM_BASE_URL"))
    ap.add_argument("--llm-model", default=os.environ.get("LLM_MODEL"))
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--timeout", type=int, default=None,
                    help="单次 LLM 请求超时秒（默认读 LLM_TIMEOUT，否则 300）")
    ap.add_argument("--max-retries", type=int, default=3)
    ap.add_argument("--max-output-tokens", type=int, default=8000, help="单块 LLM 最大输出 token（长块可调大）")
    ap.add_argument("--target-wiki", default=DEFAULT_WIKI)
    ap.add_argument("--no-resolve-quotes", action="store_true",
                    help="关闭原文块书证采证（默认开启：对 {{Quote}}/{{columns}} 按 book ref 采证中文）")
    ap.add_argument("--auto-quote-cn", action=argparse.BooleanOptionalAction, default=True,
                    help="quote/columns 书证采证到官方中译即直接替换为中文（2026-10-21 用户裁定默认开启；"
                         "--no-auto-quote-cn 退回半自动：仅产出 proposed_cn 供 review 不替换）")
    ap.add_argument("--quote-ctx", type=int, default=160, help="原文块采证的中英对照区窗口字符数")
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

    # 译名表裁切：主表 mistborn.json + 辅表 common.json（跨站通用词，如子页后缀 Statistical analysis）
    glossary = load_merged_glossary(Path(args.glossary), DEFAULT_COMMON)
    en_terms = extract_en_terms(wikitext)
    gloss_slice = slice_glossary(glossary, en_terms)

    # Infobox「字段 = 值」确定性翻译（决议#4）：把文首 {{Infobox X}} 的专名值按译名表替换，
    # 让结构化短字段不依赖 LLM 是否记得翻值。仅改 Infobox，不动正文。
    wikitext, infobox_stats = translate_infobox_values(wikitext, glossary)
    if infobox_stats:
        sys.stderr.write("[Infobox 值替换]（按译名表确定性替换，正文翻译仍交给 LLM）:\n")
        for k, (old, new) in infobox_stats.items():
            sys.stderr.write(f"  {k}: {old} -> {new}\n")

    # Post/Pre 时代前缀（历史/事件/时代词条广泛出现）：`Post [[Catacendre]]` →
    # `[[灰烬灾变|灰烬灾变后]]`。必须在 LLM 前确定性转换（LLM 常只译内链目标、留 Post/Pre
    # 英文前缀）；目标无可靠译名则原样保留。
    wikitext, prepost_stats = translate_prepost_links(wikitext, glossary)
    if prepost_stats:
        sys.stderr.write(f"[Post/Pre 时代前缀] 转换 {len(prepost_stats)} 处：\n")
        for s in prepost_stats:
            sys.stderr.write(f"  {s[1]}\n")

    # 页首 {{for|目标|描述|pre=导语}} 模板：参数值确定性替换（目标/描述/显示 + 可译专名）。
    wikitext, for_stats = translate_for_template(wikitext, glossary)
    if for_stats:
        sys.stderr.write(f"[{{{{for}}}} 模板参数翻译] {len(for_stats)} 处：\n")
        for s in for_stats:
            sys.stderr.write(f"  {{for|...| {s} }}\n")

    # 子页链接 [[父/子页|display]] 目标翻译（如 [[The Hero of Ages/Statistical analysis|225,372]]
    # -> [[永世英雄/数据分析|225,372]]，父段与后缀段均需有译名才重写）。
    wikitext, link_stats = translate_wikilink_targets(wikitext, glossary)
    if link_stats:
        sys.stderr.write("[子页链接目标翻译]（父+后缀均有译名才重写）:\n")
        for old, new in link_stats:
            sys.stderr.write(f"  {old} -> {new}\n")

    # 普通内链 [[X]] / [[X|disp]] 目标翻译（LLM 前确定性）：{{columns}} 等模板参数内的
    # 普通链接按规则 1 原样保留、LLM 不译 → 外城列表等 18 个城市名全留英文。此处对
    # 目标按译名表译中；variants 多义词（Demoux 人物/城市）跳过宁保英文不误译。
    wikitext, plain_stats = translate_plain_links(wikitext, glossary)
    if plain_stats:
        sys.stderr.write("[普通内链目标翻译]（译名表命中，LLM 前确定性）:\n")
        for old, new in plain_stats:
            sys.stderr.write(f"  {old} -> {new}\n")

    # 常见章节标题确定性预翻译（LLM 前）：qwen3.8-27b 实测把 `== Notes ==` 等
    # 高频标题原样留英（全批 5 处）。映射表由本批 20 页「EN→实际 ZH」数据归纳
    # （Notes→注释 16x、History→历史 10x…），保证跨页一致；长尾标题由 2026-10-22
    # 批次补入表 + assemble 内 LLM 后再断言兜底，仍漏的由 verify 3a「ASCII 标题」
    # 门禁拦截重跑。
    wikitext, head_stats = translate_section_headings(wikitext)
    if head_stats:
        sys.stderr.write(f"[章节标题预翻译] {len(head_stats)} 处（常见标题，LLM 前确定性）:\n")
        for s in head_stats:
            sys.stderr.write(f"  {s}\n")

    # 决议：给依赖 {{#var_final:en}} 的 {{Infobox ...}} 缺『原名』时补英文名，绕开
    # 模板回退到 #var_final:en 导致的 UNIQ--finalizedvar-* 渲染占位符（en 变量在
    # {{en}}（位于 infobox 之后）才定义）。book/character/location/... 均适用。
    wikitext, _en_added = ensure_infobox_original_name(wikitext, args.title)

    # 决议#13：把 {{Quote}}/{{columns}} 等原文块换成唯一占位符，模型原样保留，翻完再填回英文原文
    wikitext, registry = mask_protected_blocks(wikitext)
    if registry:
        sys.stderr.write(f"[原文块保护]（决议#13，占位符替换后填回英文原文）: {len(registry)} 处\n")

    # 引用模板占位（防引用编号幻觉，见 mask_ref_templates docstring）：把
    # {{book ref|...}}/{{msh ref|...}}/{{Rpg ref|...}}/{{date|...}} 换成 %%REF_N%%，
    # LLM 接触不到编号，assemble 时按英文源顺序确定性填回。
    wikitext, refs = mask_ref_templates(wikitext)
    if refs:
        sys.stderr.write(f"[引用占位]（防引用编号幻觉，LLM 后按英文源填回）: {len(refs)} 处\n")

    # infobox「原名」占位：LLM 偶发把英文原名译掉（Spook→鬼影），占位后 assemble 填回英文标题
    wikitext, _orig_title = mask_infobox_original_name(wikitext, args.title)

    # infobox 纯内链列表值占位（children/relatives/image…）：LLM 对纯链接值无改写
    # 空间，且实测会把多链接合并成断链 → 占位直通，assemble 填回（见函数注释）。
    wikitext, _linklist_reg = mask_infobox_link_lists(wikitext)
    if _linklist_reg:
        sys.stderr.write(f"[infobox 内链列表占位]（纯链接字段直通，LLM 后填回）: {len(_linklist_reg)} 处\n")

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
            prompt = build_user_prompt(c, gloss_slice, args.title, is_first=(c.index == 0), glossary=glossary)
            sys.stderr.write(f"\n--- 提示词 chunk{c.index}（{len(prompt)} 字符）一句预览 ---\n")
            sys.stderr.write(prompt[:300].replace("\n", " ") + "\n")
        sys.stderr.write("[dry-run] 预演完成，未调用 LLM，未写文件。\n")
        return 0

    cfg = load_llm_config(args)

    # 分块门禁重试（2026-10-23）：--redo-chunks 只重采样失败块，其余复用现有产物。
    redo_set: set | None = None
    prev_results = None
    if args.redo_chunks:
        redo_set = {int(x) for x in str(args.redo_chunks).split(",") if x.strip()}
        _tj = d / "translation.json"
        if not _tj.exists():
            raise SystemExit("[分块重试] 现有 translation.json 不存在，无法复用——请整页重跑")
        _prev = json.loads(_tj.read_text(encoding="utf-8"))
        prev_results = _prev.get("chunk_results")
        if not prev_results:
            raise SystemExit("[分块重试] 产物缺 chunk_results（旧产物），无法复用——请整页重跑")
        if len(prev_results) != len(chunks):
            raise SystemExit(f"[分块重试] 块数不一致（产物 {len(prev_results)} vs 当前 "
                             f"{len(chunks)}）——请整页重跑")
        if not redo_set or not redo_set <= set(range(len(chunks))):
            raise SystemExit(f"[分块重试] --redo-chunks 无效: {args.redo_chunks!r}（共 {len(chunks)} 块）")
        sys.stderr.write(f"[分块重试] 重采样块 {sorted(redo_set)}，"
                         f"复用 {len(chunks) - len(redo_set)} 块现有译文\n")

    # 逐块翻译（支持并发，默认串行）。分块重试：不在 redo_set 的块直接复用
    # 现有产物的 chunk_results——fresh sampling 只发生在门禁失败块。
    chunk_results = [None] * len(chunks)
    errs = []
    todo = chunks
    if redo_set is not None:
        for c in chunks:
            if c.index in redo_set:
                continue
            _t, _u = prev_results[c.index]
            chunk_results[c.index] = (_t, _u)
            sys.stderr.write(f"[复用] chunk{c.index}（沿用现有产物，不重采样）\n")
        todo = [c for c in chunks if c.index in redo_set]
    if args.concurrency > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
            futs = {
                ex.submit(translate_chunk_with_retry, cfg, c, gloss_slice, args.title, c.index == 0,
                          glossary, args.max_output_tokens): c.index
                for c in todo
            }
            ordered = sorted(futs, key=lambda f: futs[f])
            for f in ordered:
                try:
                    chunk_results[futs[f]] = f.result()
                except Exception as e:
                    errs.append((futs[f], str(e)))
    else:
        for c in todo:
            sys.stderr.write(f"[翻译] chunk{c.index}/{len(chunks)-1}（{c.title or '头部'}）…\n")
            try:
                chunk_results[c.index] = translate_chunk_with_retry(cfg, c, gloss_slice, args.title,
                                                                    c.index == 0, glossary,
                                                                    args.max_output_tokens)
            except Exception as e:
                errs.append((c.index, str(e)))

    if errs:
        sys.stderr.write("[失败] 以下块翻译失败：\n")
        for idx, e in errs:
            sys.stderr.write(f"  chunk{idx}: {e}\n")
        raise SystemExit(f"共 {len(errs)} 块失败，未写 translation.json。可用 --dry-run 预演排障。")

    # 组装
    contract = assemble(args.title, revid, chunk_results, args.no_wrap, args.target_wiki, registry,
                        refs=refs, orig_title=_orig_title, linklist_reg=_linklist_reg)

    # 决议#13 增强：原文块按中译本书证采证中文（quote/columns）。
    # - 半自动（--no-auto-quote-cn）：产出 quote_resolutions（proposed_cn 供 review），不替换，英文保留。
    # - 自动（默认，2026-10-21 用户裁定）：采证到的直接替换为中文（英文不留）；找不到保留英文。
    if registry and not args.no_resolve_quotes:
        sys.stderr.write("[原文块采证] 按书证（book/epigraph/tes ref）用中译本书证解析 "
                         "{{Quote}}/{{columns}}，同章合并批量采证 …\n")
        cfg = load_llm_config(args)
        new_body, resolutions = resolve_blocks(registry, contract["translation"], cfg,
                                               auto=args.auto_quote_cn, ctx=args.quote_ctx,
                                               glossary=glossary)
        contract["translation"] = new_body
        contract["quote_resolutions"] = resolutions
        n_found = sum(1 for r in resolutions if r["found"])
        n_batch = sum(1 for r in resolutions if r.get("via") == "batch")
        reasons = {}
        for r in resolutions:
            k = r.get("reason")
            reasons[k] = reasons.get(k, 0) + 1
        n_attr = sum(1 for r in resolutions if r.get("attr_reason") == "ok")
        n_attr_tot = sum(1 for r in resolutions if r.get("attr_reason"))
        mode_desc = "已自动替换为中文" if args.auto_quote_cn else "半自动产出 proposed_cn 供 review"
        sys.stderr.write(
            f"[原文块采证] 正文 {n_found}/{len(resolutions)} 采到官方中译（同章批量 {n_batch}，{mode_desc}）；"
            f"出处行译出 {n_attr}/{n_attr_tot}；"
            f"reason={reasons}\n")
        # 全自动已替换的块，从「需查中译本」清单里移除（保留未找到的）
        if args.auto_quote_cn and "untranslated_terms" in contract:
            resolved_tokens = {r["token"] for r in resolutions if r["found"]}
            contract["untranslated_terms"] = [
                u for u in contract["untranslated_terms"]
                if not (isinstance(u, dict) and any(tk in str(u.get("en", "")) for tk in resolved_tokens))
            ]

    out_json = d / "translation.json"
    out_txt = d / "translation.txt"
    # 分块门禁重试所需字段（2026-10-23）：chunk_results=逐块译文（复用源，先于 assemble）；
    # chunk_line_starts=终文各块起始行（门禁失败行→块映射；结构漂移时缺省=回退整页重跑）。
    contract["chunk_results"] = [[t, u] for (t, u) in chunk_results]
    _starts = compute_chunk_line_starts(contract["translation"], chunks, split_sections(wikitext))
    if _starts:
        contract["chunk_line_starts"] = _starts
    if redo_set:
        _m = contract.get("meta") or {}
        # contract.meta 每轮由 assemble 重建，须从上一版产品 meta 接续计数（否则恒为 1）
        _m["redo_count"] = int(((_prev or {}).get("meta") or {}).get("redo_count", 0)) + 1
        _m["last_redo_chunks"] = sorted(redo_set)
        contract["meta"] = _m
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
