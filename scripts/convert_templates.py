#!/usr/bin/env python3
"""
模板转换器（决策第6条，逐步积累）。
输入：英文站 wikitext（或 snapshot 标题）
输出：
  - 转换后的 wikitext（受支持的模板按 rules/template_map.json 改写/重命名）
  - 转换报告：mapped / unmapped 参数、占位待译字段

当前支持：character -> Infobox character（字段名映射），quote 重命名为 Quote。
其余模板保留原样（先不动，逐步接入映射）。

默认只输出到 stdout / 存 <snapshot>/converted.txt，不改站。
"""
import argparse
import json
import re
import sys
from pathlib import Path

import mwparserfromhell

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RULES = ROOT / "rules" / "template_map.json"
EN_SNAPSHOT = ROOT / "en_snapshot"


def load_rules():
    return json.loads(RULES.read_text(encoding="utf-8"))


# 英文站维护/站务模板 → 翻译/写站时 drop（不搬进中文词条）。
# 用户 2025-10-17 决议：complete/partial/stub 保留（中文站同名 Complete/Partial/Stub 语义等价），
# 其余（update/expand/demoted/nosnippet/dialogue/edit note/meta:*/user:*）纯英文站编辑/维护标记，drop。
#   - nosnippet 是「对搜索引擎隐藏某段内容」的包装模板：drop 其包装但**保留内文**（unwrap）。
#   - 其余 drop 模板整删。
# meta/* 与 user:* 是前缀匹配（子模板）；其余精确名匹配（模板名首字母不敏感，统一小写）。
DROP_TEMPLATES = {
    "update", "expand", "demoted", "dialogue", "edit note",
    # stub/partial/complete 保留（中文站有同名且语义等价）——不在 drop 集
    # nosnippet 单独处理（unwrap 保内文）
}
DROP_TEMPLATE_PREFIXES = ("meta/", "user:")
UNWRAP_TEMPLATES = {"nosnippet"}


def _norm_tpl_name(name):
    """剥掉 Template:/模板: 前缀与内部空白后的小写模板名。"""
    n = re.sub(r'^(?:Template|模板)\s*:', '', name, flags=re.IGNORECASE)
    return n.lstrip(":").strip().lower()


# --------------------------------------------------------------------------- #
# 图片槽：把裸文件名包成 [[File:<名>|<宽>px]]（决议：中文站 Infobox 不自动加 [[file:]]，
# 图槽保持自由，由 bot 在写页时给出可直接渲染的 [[File:...]]）。只包裹"裸文件名"，
# 已含 [[File:...]] / 模板 {{image|...}} / <gallery> 等富内容的原样保留，不误伤。
# --------------------------------------------------------------------------- #
IMG_SRC_KEYS = {"image", "img", "cover", "map", "logo", "symbol", "mapfile", "file",
                "emblem", "flag", "picture", "photo"}
IMG_DST_PAT = re.compile(r"(图|像|地圖|地图|标志|徽|封面|封面图)")


def _looks_like_bare_filename(val: str) -> bool:
    """是否像"裸文件名"（可包成 [[File:...]]）：无 [[ / {{ / < / 换行，且以图片扩展名结尾。"""
    if not val or "[" in val or "{" in val or "<" in val or "\n" in val:
        return False
    return bool(re.search(r"(?i)\.(?:jpe?g|png|gif|svg|webp|tif{1,2}|avif|bmp)$", val))


def wrap_image_value(en_key: str, cn_key: str, val: str, width: int = 300) -> str:
    """若该字段是图片槽且值为裸文件名，则包成 [[File:<名>|<宽>px]]；否则原样返回。"""
    enl = en_key.lower()
    if enl not in IMG_SRC_KEYS and not IMG_DST_PAT.search(cn_key):
        return val
    if not _looks_like_bare_filename(val):
        return val
    return f"[[File:{val}|{width}px]]"


# --------------------------------------------------------------------------- #
# 词条名引用字段：如上`上一本/下一本`之类的字段天然指向另一词条页，中文站 Infobox
# 不自动加 [[ ]]，由写页方给全量链接。这里对"裸词条名"包成 [[<名>]]（值内已有
# [[ / {{ / < / 换行 则视为已是富内容，原样保留）。注意：只对明确是"指向别的词条页"
# 的字段白名单包裹，避免误包纯文本/日期/数字字段。
# --------------------------------------------------------------------------- #
LINK_DST_KEYS = {"上一本", "下一本"}


def wrap_link_value(en_key: str, cn_key: str, val: str) -> str:
    """若该字段是词条名引用（白名单）且值为裸词条名，则包成 [[<名>]]；否则原样返回。"""
    if cn_key not in LINK_DST_KEYS:
        return val
    if not val or any(ch in val for ch in ("[[", "{{", "<", "\n")):
        return val
    return f"[[{val}]]"


def is_drop_template(name):
    """该模板是否应 drop（整删）。"""
    n = _norm_tpl_name(name)
    if n in DROP_TEMPLATES:
        return True
    if n.startswith(DROP_TEMPLATE_PREFIXES):
        return True
    return False


def is_unwrap_template(name):
    """该模板是否应 unwrap（drop 包装、保留内文）——如 nosnippet。"""
    return _norm_tpl_name(name) in UNWRAP_TEMPLATES


def _apply_drop(code, report):
    """递归移除 drop 模板（update/expand/meta:*/demoted/dialogue/edit note/user:*），
    并 unwrap 内容包装模板（nosnippet 保留内文）。可处理嵌套在 infobox 参数值 / Tag 内容里的模板。"""
    to_process = []
    to_unwrap = []
    for node in list(code.nodes):
        if isinstance(node, mwparserfromhell.nodes.Template):
            nm = _norm_tpl_name(str(node.name))
            if is_unwrap_template(nm):
                to_unwrap.append(node)
            elif is_drop_template(nm):
                to_process.append(node)
            else:
                # 该模板会被保留：递归进它的参数值，清理嵌套的 drop/unwrap 模板
                for p in node.params:
                    _apply_drop(p.value, report)
        elif isinstance(node, mwparserfromhell.nodes.Tag):
            if node.contents is not None:
                _apply_drop(node.contents, report)
        elif isinstance(node, mwparserfromhell.nodes.Wikilink):
            if node.text is not None:
                _apply_drop(node.text, report)
    for node in to_process:
        name = _norm_tpl_name(str(node.name))
        report.setdefault("dropped", []).append(name)
        code.remove(node)
    for node in to_unwrap:
        inner = " ".join(str(p.value).strip() for p in node.params if not p.showkey and str(p.value).strip())
        report.setdefault("dropped", []).append("nosnippet(unwrap)")
        if inner:
            code.replace(node, inner)
        else:
            code.remove(node)


def build_dst_template(name_map, tpl):
    """把英文 {{character}} 调用改写成中文 {{Infobox character 调用}}。

    - 参数名查找不区分大小写（MediaWiki 参数区分大小写，但实际词条常混用，如 Spouse/spouse）。
    - 输出采用中文站约定：每个参数一行 `| 中文名 = 值`。
    - 返回 (新wikitext, mapped{英文键:中文键}, unmapped[(键,值)], collisions, missing_cn[(键,值)])。
    - missing_cn：中文站该模板**缺这些字段**（`missing_cn_fields`），属于需在中文站补字段的待办，单独报告、不静默丢弃。
    """
    dst_name = name_map["dst_template"]
    field_map = name_map["field_map"]
    drop = set(name_map.get("drop_always", []))
    drop_low = {k.lower() for k in drop}
    missing_cn_fields = set(x.lower() for x in name_map.get("missing_cn_fields", []))
    # 大小写不敏感查找表：lower(英文键) -> 中文键
    lookup = {}
    for enk, cnk in field_map.items():
        lookup.setdefault(enk.lower(), cnk)

    mapped_ordered = []   # (英文键, 中文键, 值)
    unmapped = []
    missing_cn = []   # 中文站缺字段，待办（见 missing_cn_fields）
    # 目标->源 碰撞检测（两个不同英文键映射到同一中文键）
    cn_key_src = {}

    for p in tpl.params:
        # 位置参数 showkey is False（命名参数是 True）；用 not 兼容 None
        if not p.showkey:
            v = str(p.value).strip()
            if v:
                unmapped.append(("__positional__", v))
            continue
        key = str(p.name).strip()
        # 英文模板有前导撇号别名（如 'residence / 'world），与无撇号版同义，去掉撇号再查。
        lookup_key = key[1:] if key.startswith("'") else key
        val = str(p.value).strip()
        # 空值参数不产出（英文模板常见 type=/name= 空占位，无信息量）
        if not val:
            continue
        keyl = lookup_key.lower()
        if keyl in drop_low:
            continue
        dst_key = lookup.get(keyl)
        if dst_key:
            mapped_ordered.append((key, dst_key, val))
            cn_key_src.setdefault(dst_key, []).append(key)
        elif keyl in missing_cn_fields:
            missing_cn.append((key, val))
        else:
            unmapped.append((key, val))

    # 碰撞：目标中文键被多个英文键占用（如 民族/国家 语义不同需人工定）
    collisions = {cnk: srcs for cnk, srcs in cn_key_src.items() if len(set(srcs)) > 1}

    # 输出：一个参数一行，中文站风格
    out = ["{{" + dst_name]
    for enk, cnk, val in mapped_ordered:
        val = wrap_image_value(enk, cnk, val)
        val = wrap_link_value(enk, cnk, val)
        out.append(f"| {cnk}    = {val}")
    out.append("}}")
    raw = "\n".join(out) + "\n"

    return raw, mapped_ordered, unmapped, collisions, missing_cn


def _collect_infobox_rules(rules):
    """从 rules 收集所有 infobox 转换配置：{英文模板名(小写): config}。"""
    by_name = {}
    for key, cfg in rules.items():
        if not isinstance(cfg, dict):
            continue
        src = cfg.get("src_template")
        if src and cfg.get("dst_template"):
            by_name[src.strip().lower()] = cfg
    return by_name


def _find_bal(text, start):
    """从 start（'{{'）起找匹配的 '}}'，返回其后的下标。处理脚注 text 内嵌套模板。"""
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return len(text)


def _split_top_params(body):
    """把 {{ref|...}} 的参数段按顶级 '|' 拆开（忽略嵌套 {{...}} 内的 |）。
    返回 [(key, value), ...]（无 '=' 的段=位置参数，忽略）。"""
    if not body.startswith("|"):
        body = "|" + body
    out, depth, cur = [], 0, ""
    for ch in body:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        if ch == "|" and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return [(p.split("=", 1)[0], p.split("=", 1)[1]) for p in out if "=" in p]


def _scan_refs(text):
    """把一串文本里的 {{ref|...}} 转成标准 <ref>，其余原样保留。

    - group=fn：英文站脚注组（<references group="fn"> 体系）→ 标准 <ref name=X>text</ref>
      或 <ref name=X/>（方案 A，各处定义保留原位）。
    - 无 group + name + 无 text：英文站「占位引用」{{ref|name=X}}（如 {{ref|name=aa}}），
      其正文实际内容由 <references> 内的 {{url ref|name=X}}/{{bws ref|name=X}} 提供。
      中文站 Template:Ref 会 #invoke:Ref 用空卷码查表报「函数{{{1}}}不存在」，
      故必须转成标准占位 <ref name="X"/>，与同名定义配对（引用前置于定义是合法用法）。
    - 其余（有卷/章参数的书目引用、{{ref|text=...}} 等）原样保留。
    """
    res, i = [], 0
    while i < len(text):
        if text[i:i + 2] == "{{":
            j = _find_bal(text, i)
            inner = text[i + 2:j - 2]
            m = re.match(r"\s*([^|{}]+)", inner)
            tname = m.group(1).strip().lower() if m else ""
            # LLM 可能把 <ref name="X"/> 变回模板形态 `{{ref name="X"}}`（无管道线、
            # 属性带引号）。对这种「无管道、仅 name=」形态单独识别成占位引用。
            nm = re.match(r'^\s*ref\s+name\s*=\s*["\']?([^"\'\s|}]+)["\']?\s*$', inner, re.I)
            if nm:
                rep = '<ref name="%s"/>' % nm.group(1)
                res.append(rep)
                i = j
                continue
            if tname == "ref":
                params = {k.strip().lower(): v.strip() for k, v in _split_top_params(inner[m.end():])}
                name, fn_text = params.get("name"), params.get("text")
                group = params.get("group", "").lower()
                if group == "fn":
                    if name and fn_text is not None:
                        rep = '<ref name="%s" group="fn">%s</ref>' % (name, fn_text)
                    elif fn_text is not None:
                        rep = '<ref group="fn">%s</ref>' % fn_text
                    elif name:
                        rep = '<ref name="%s" group="fn"/>' % name
                    else:
                        rep = text[i:j]
                    res.append(rep)
                    i = j
                    continue
                if not group and name and fn_text is None:
                    # 无 group 的命名占位引用 → 标准占位 <ref name=X/>（正文引用，
                    # 定义在 <references> 内的 {{url ref|name=X}}/{{bws ref|name=X}}）
                    rep = '<ref name="%s"/>' % name
                    res.append(rep)
                    i = j
                    continue
                if not group and not name and fn_text is not None:
                    # 无 group/name 的纯 text 脚注：{{ref|text=X}}（15 页 16 处，
                    # 如 Demoux (city) 的页码旁注）。中文站 Template:Ref 是 #invoke:Ref
                    # 书目查表模板，text= 无法渲染 → “函数{{{1}}}不存在”。转标准
                    # <ref>X</ref>（默认组），语义与占位/正文引用一致。
                    rep = '<ref>%s</ref>' % fn_text
                    res.append(rep)
                    i = j
                    continue
            else:
                # 非 ref 模板（如 {{columns|...}}、{{date|...}}）：其参数值里可能嵌套
                # {{ref|name=X}}（如 Publication 段的 Film rights 行），递归归一，
                # 再按原模板重组。仅当内部确实含 ref 时才重写，否则原样返回。
                sub = _scan_refs(inner)
                if sub != inner:
                    res.append("{{" + sub + "}}")
                    i = j
                    continue
            res.append(text[i:j])
            i = j
            continue
        res.append(text[i])
        i += 1
    return "".join(res)


def _fix_single_arg_book_refs(text):
    """给纯单参 {{book ref|X}} 补空第二参数：{{book ref|X}} -> {{book ref|X|}}。

    背景：英文站合法调用 {{book ref|11m}}（引用整本书、无章节号）在中文站 Template:Book ref
    的 name 生成式里是 {{b|{{{1}}}}}-{{{part|{{{2}}}-{{{3|chapter}}}}}} —— {{{2}}} 缺默认值
    管道，单参调用渲染出字面量 {{{2}}} 进 cite id（122 处，如 Pits of Eltania/Kelsier/Wayne）。
    补一个空第二参数让 {{{2}}} 展开为空串，name 变成「执法镕金--chapter」等干净形态。
    仅处理「无管道分割的单参」：多参（AoL|2）、三参（Sa2|i|9）、带命名参数（part=）不匹配。
    """
    pat = re.compile(r"(\{\{\s*book ref\s*\|)([^|{}]+)(\}\})", re.I)
    return pat.sub(lambda m: "%s%s|%s" % (m.group(1), m.group(2).strip(), m.group(3)), text)


def _expand_wob_refs(text):
    """把 {{wob ref|N}}（单参数，最常见的 Arcanum 问答引用）展开成等价的 [[wob:N|wob:N]] 独立 <ref>。

    背景：中文站 Template:Wob ref 的链接文本写的是 {{{text|{{{2}}}|}}}（嵌套 {{{2}}} 缺默认值
    管道），对只有数字参数 1 的调用（{{wob ref|9171}}）会渲染出字面量 {{{2}}}（46 处）。
    英文站此时显示 [[wob:N|wob:N]]（interwiki 前缀显示）。这里把单参数调用展开为
    <ref>[[wob:N|wob:N]]</ref>，绕开中文站模板缺陷，且不依赖缺失的 Template:Ref/broken。
    带 text/date 等扩展参数的调用保留原样（交给中文站模板，与英文站行为一致）。
    """
    def _expand(m):
        num = m.group(1)
        return "<ref>[[wob:%s|wob:%s]]</ref>" % (num, num)

    # 单参数：{{wob ref|9171}} / {{wob_ref|9171}}（容忍下划线与大小写、两侧空白）
    pat = re.compile(r"\{\{\s*wob[_ ]?ref\s*\|\s*(\d+)\s*\}\}", re.I)
    return pat.sub(_expand, text)


def _expand_nested_refs_in_fn(text):
    """展开 fn 脚注块（<ref group="fn">…</ref>）内嵌套的引用类模板为纯链接/文本。

    背景：英文站 <references group=fn> 脚注的 text 参数里可合法嵌套引用模板
    （{{book ref|mb4|1}}/{{file ref}}/{{map ref}}/{{epigraph ref}}/{{wob ref|N}} 等），
    中文站这些模板都渲染成 <ref>（独立引用结算），嵌套在 <ref group="fn"> 里就成了
    「ref 内嵌 ref」→ MediaWiki 报“<references> 的 <ref> 标记带有冲突的组(group)属性”
    或“没有找到与 </ref> 对应的 <ref>”（10+ 页，如 Wayne/Hoid/Pewter/Steel Ministry）。
    这里把 fn 块内的引用模板展开为等效链接/文本，不产生嵌套引用结算：
      - {{book ref|X|N}}/X|prologue/…      -> [[{{b|X}}/梗概#锚点|《{{b|X}}》文本]]（与中文站模板
                                            链接目标一致，见 _expand_book_ref_link）
      - {{wob ref|N}} / {{wob_ref|N}}      -> [[wob:N|wob:N]]（interwiki 纯链接，不带 <ref>）
      - {{file ref|F|说明}}               -> [[文件:F|说明]]（文件链接）
      - {{map ref|M}}                      -> [[文件:M.png|M]]（中文站 map ref 指文件）
      - {{epigraph ref|书|章}}             -> 《{{b|书}}》题词第N章（题词页链接目标未稳定，保文本）
      - {{date|…}} / 其他非 ref 模板       -> 原样保留
    仅处理 fn 块内：普通正文里的引用模板保持原样（由中文站模板渲染成独立引用）。
    必须在 _expand_wob_refs 之前调用，否则 wob ref 已变 <ref>[[wob:N|wob:N]]</ref> 无法再识别。
    """
    def _book_link(m):
        rest = m.group(1)
        parts = [p.strip() for p in rest.split("|") if p.strip() not in ("", "=")]
        if not parts:
            return "{{book ref}}"
        book = parts[0]
        chap = parts[1] if len(parts) > 1 else ""
        if len(parts) >= 3:  # 三参：book|i|3 / book|day|5 / book|c|N
            v = {
                "i": ("插曲%s", "插曲%s"),
                "interlude": ("插曲%s", "插曲%s"),
                "day": ("第%s日", "第%s日"),
                "c": ("第%s章", "第%s章"),
            }.get(chap.lower())
            if v:
                num = parts[2]
                return "[[%s/梗概#%s|《%s》%s]]" % (
                    "{{b|%s}}" % book, v[0] % num, "{{b|%s}}" % book, v[1] % num)
            return "《{{b|%s}}》" % book
        low = chap.lower()
        special = {
            "prologue": ("序幕", "序幕"),
            "epilogue": ("尾声", "尾声"),
            "endnote": ("尾注", "尾注"),
            "ars": ("秘典", "秘典"),
            "ack": ("鸣谢", "鸣谢"),
            "end": ("附录", "附录"),
        }
        if low.startswith("part="):
            partname = low.split("=", 1)[1].strip()
            if partname in special:
                a, l = special[partname]
                return "[[%s/梗概#%s|《%s》%s]]" % ("{{b|%s}}" % book, a, "{{b|%s}}" % book, l)
            return "《{{b|%s}}》" % book
        if not chap or low == "chapterless":
            return "《{{b|%s}}》" % book
        if low in special:
            a, l = special[low]
            return "[[%s/梗概#%s|《%s》%s]]" % ("{{b|%s}}" % book, a, "{{b|%s}}" % book, l)
        if re.match(r"^\d+$", chap):
            return "[[%s/梗概#第%s章|《%s》第%s章]]" % ("{{b|%s}}" % book, chap,
                                                   "{{b|%s}}" % book, chap)
        return "《{{b|%s}}》" % book

    def _block(m):
        inner = m.group(2)
        # 1) book ref（多参形态：X|章 或 X|i|N 等）
        inner = re.sub(r"\{\{\s*book ref\s*\|([^{}]+)\}\}", _book_link, inner, flags=re.I)
        # 2) wob ref：{{wob ref|N}} -> [[wob:N|wob:N]]（纯链接，无 <ref>）
        inner = re.sub(r"\{\{\s*wob[_ ]?ref\s*\|\s*(\d+)\s*\}\}",
                       lambda mm: "[[wob:%s|wob:%s]]" % (mm.group(1), mm.group(1)),
                       inner, flags=re.I)
        # 3) file ref：{{file ref|F|说明}} -> [[文件:F|说明]]（图片引用脚注改内联文件链接）
        inner = re.sub(r"\{\{\s*file ref\s*\|([^|{}]+)(?:\|([^{}]*))?\}\}",
                       lambda mm: "[[文件:%s|%s]]" % (mm.group(1).strip(), mm.group(2).strip())
                       if mm.group(2) else "[[文件:%s]]" % mm.group(1).strip(),
                       inner, flags=re.I)
        # 4) map ref：{{map ref|M}} -> [[文件:M.png|M]]
        inner = re.sub(r"\{\{\s*map ref\s*\|([^|{}]+)\}\}",
                       lambda mm: "[[文件:%s.png|%s]]" % (mm.group(1).strip(), mm.group(1).strip()),
                       inner, flags=re.I)
        # 5) epigraph ref：{{epigraph ref|书|章}} -> 《{{b|书}}》题词第N章（保留文本，不做链接）
        inner = re.sub(r"\{\{\s*epigraph ref\s*\|([^|{}]+)(?:\|([^{}]*))?\}\}",
                       lambda mm: "《{{b|%s}}》题词第%s章" % (mm.group(1).strip(), mm.group(2).strip())
                       if mm.group(2) else "《{{b|%s}}》题词" % mm.group(1).strip(),
                       inner, flags=re.I)
        # 6) msh ref：{{msh ref|部分|章}} -> [[迷雾之子：秘史/梗概#第X部分第N章|《迷雾之子：秘史》第X部分第N章]]
        inner = re.sub(r"\{\{\s*msh ref\s*\|([^|{}]+)(?:\|([^{}]*))?\}\}",
                       lambda mm: "[[迷雾之子：秘史/梗概#第%s部分第%s章|《迷雾之子：秘史》第%s部分第%s章]]"
                       % (mm.group(1).strip(), mm.group(2).strip(), mm.group(1).strip(), mm.group(2).strip()),
                       inner, flags=re.I)
        return m.group(1) + inner + m.group(3)

    pat_block = re.compile(r"(<ref group=\"fn\">)(.*?)(</ref>)", re.S)
    return pat_block.sub(_block, text)


_CN_INTERWIKI_PREFIXES = frozenset("""
17s-news 17s-post 17s-topic 17s-user acronym advogato arxiv bws bwsp c2find cache cm
commons dictionary docbook doi drumcorpswiki dwjwiki elibre emacswiki en foldoc foxwiki
freebsdman gej gentoo-wiki google googlegroups hammondwiki hrwiki imdb jargonfile
kmwiki linuxwiki lojban lqwiki lugkr meatball mediawikiwiki mediazilla memoryalpha
metawiki metawikimedia mozillawiki mw oeis openwiki pmid ppr pythoninfo rfc s23wiki
seattlewireless senseislibrary shoutwiki sourceforge sourcewatch squeak tejo theopedia
tmbw tmnet tor twiki uea uncyclopedia unreal usemod webseitzwiki wiki wikia wikibooks
wikif1 wikihow wikimedia wikinews wikinfo wikipedia wikiquote wikisource wikispecies
wikiversity wikivoyage wikt wiktionary wob wotdb
""".split())


def _convert_lang_links(text):
    """把语言间链接 [[es: Title]]/[[uk: Title]] 转成完整外部链接。

    背景：英文站页尾的 [[es: X]]/[[uk: X]] 是 MediaWiki 语言链接，指向各语言站点
    （<lang>.coppermind.net 子域，如 es.coppermind.net/uk.coppermind.net）。中文站
    （灰机）的 interwiki 表只配了 en/cm/wob 等（87 个前缀），**没有 es/uk 语言前缀**，
    导致这些链接在中文站渲染成本地页面「Es:Mistborn (saga)」红链而非语言站外链。
    （实测：中文站全站含 [[es: 的页面都渲染成红链。）

    这里把「中文站 interwiki 表未配置的」语言前缀链接转成外部链接
    [https://<lang>.coppermind.net/wiki/<URL编码标题> <lang>: <标题>]，
    链接文本保留英文站形态（es: Mistborn (saga)）。若目标不遵循 <lang>.coppermind.net
    规律（如中文站在灰机），可由 lang->url 覆盖表补充；目前 es/uk 均符合。
    已配置前缀（en/cm/wob/wikipedia 等）原样保留。无文本的 [[xx:Title]] 也转。
    """
    # 小写语言前缀 -> 语言站基 URL（当前仅覆盖英文站使用的语言码；新语言码可在此追加）
    lang_base = {
        "es": "https://es.coppermind.net/wiki/",
        "uk": "https://uk.coppermind.net/wiki/",
        "de": "https://de.coppermind.net/wiki/",
        "fr": "https://fr.coppermind.net/wiki/",
        "pt": "https://pt.coppermind.net/wiki/",
        "ru": "https://ru.coppermind.net/wiki/",
        "he": "https://he.coppermind.net/wiki/",
        "it": "https://it.coppermind.net/wiki/",
        "nl": "https://nl.coppermind.net/wiki/",
        "zh": "https://coppermind.huijiwiki.com/wiki/",
    }
    code = mwparserfromhell.parse(text)
    from urllib.parse import quote
    changed = False
    for node in code.filter_wikilinks():
        raw = str(node.title).strip()
        m = re.match(r"^([a-z]{2,3})\s*:\s*(.+)$", raw, flags=re.IGNORECASE)
        if not m:
            continue
        lang, target = m.group(1).lower(), m.group(2).strip()
        if lang in _CN_INTERWIKI_PREFIXES:
            continue  # 中文站已配置的前缀（en/wob/cm/wikipedia 等）原样保留
        base = lang_base.get(lang)
        if not base:
            continue  # 未知语言前缀不动（可能是有意保留的文本）
        display = ("%s: %s" % (lang, target)) if node.text is None else str(node.text)
        url = base + quote(target.replace(" ", "_"), safe="()'%:-")
        code.replace(node, "[%s %s]" % (url, display))
        changed = True
    return str(code) if changed else text


def _normalize_dup_ref_texts(text):
    """统一同名 ref 模板多次调用的文本参数，消除「同一 name 不同内容」渲染错误。

    背景：中文站 ref 类模板（{{file ref|文件|文本}}/{{bws ref|slug|文本|…}}/{{tor ref}}/
    {{reddit ref}} 等）的 cite name 由参数 1 生成、显示文本由参数 2（或 text=）生成。
    英文站多处调用同文 → 渲染多个同 name 同 text 的 <ref>，MediaWiki 不报错；但 LLM
    分块翻译后，同一模板在不同块里的 text 可能一处译成中文、一处保留英文 →
    中文站报「无效 <ref> 标签；name 属性 X 使用不同内容定义了多次」
    （Elendel 的 file ref/Shadows of Self 的 bws ref 实测）。
    这里把同名（模板名+参数1）多次调用的文本参数统一为**第一次出现的非空值**，
    语义保持（同一来源），显示一致，渲染不再报错。仅统一带文本的调用；无文本的
    调用保持原样（避免引入「无 text 版本」的模板缺陷）。转换层同文时无副作用。
    """
    # 收集：键=(模板名小写, 参数1) -> [text 样值...]（仅第一个非空值；无 text 调用不记）
    samples = {}
    code = mwparserfromhell.parse(text)
    for node in code.filter_templates():
        name = str(node.name).strip().lower()
        if not name.endswith(" ref"):
            continue
        a1 = tval = None
        for p in node.params:
            pn = str(p.name).strip().lower()
            if a1 is None and pn == "1":
                a1 = str(p.value).strip()
            elif tval is None and (pn == "2" or pn == "text"):
                tval = str(p.value).strip()
        if not a1 or not tval:
            continue
        key = (name, a1)
        samples.setdefault(key, None)
        if samples[key] is None:
            samples[key] = tval
    # 需要归一化的键：同键至少出现两次文本（第一次非空 + 后续不同）
    to_fix = set()
    counts = {}
    for node in code.filter_templates():
        name = str(node.name).strip().lower()
        if not name.endswith(" ref"):
            continue
        a1 = tval = None
        for p in node.params:
            pn = str(p.name).strip().lower()
            if a1 is None and pn == "1":
                a1 = str(p.value).strip()
            elif tval is None and (pn == "2" or pn == "text"):
                tval = str(p.value).strip()
        if not a1 or not tval:
            continue
        key = (name, a1)
        counts[key] = counts.get(key, 0) + 1
        if counts[key] >= 2 and tval != samples[key]:
            to_fix.add(key)
    if not to_fix:
        return text
    # 重写：同名键的文本参数统一为首次非空值
    fixed = set()
    for node in code.filter_templates():
        name = str(node.name).strip().lower()
        if not name.endswith(" ref"):
            continue
        a1 = None
        for p in node.params:
            pn = str(p.name).strip().lower()
            if a1 is None and pn == "1":
                a1 = str(p.value).strip()
                break
        if not a1:
            continue
        key = (name, a1)
        if key not in to_fix:
            continue
        first = samples[key]
        for p in node.params:
            pn = str(p.name).strip().lower()
            if pn == "2" or pn == "text":
                p.value = first
                fixed.add(key)
    return str(code)


def _convert_footnote_groups(wikitext):
    """把英文站 {{ref|...|group=fn}} 脚注体系转成中文站可渲染的标准 <ref>/<references>（方案 A）。

    背景：英文站 Template:Ref 支持 group=fn，输出 <ref group="fn">；中文站 Template:Ref 是书目
    引用模板，忽略 group，导致 <references group=fn> 找不到前置 group 标记而报
    “<references> 中定义的 <ref> 带有未在前文出现的组 fn”。此函数在 LLM 翻译之前把脚注归一为
    标准 <ref>，英文脚注 text 随即作为普通正文交给翻译（方案 A，用户 2026-10-17 确认）。

    覆盖四种形态：
      - 正文内联无 name：{{ref|group=fn|text=X}}         -> <ref group="fn">X</ref>
      - 正文内联有 name：{{ref|name=N|group=fn}}        -> <ref name="N" group="fn"/>
      - 定义块：<references group=fn>{{ref|group=fn|text=X|name=N}}</references>
                                                         -> <references group="fn"><ref name="N" group="fn">X</ref></references>
      - 自闭合：<references group=fn/>                  -> <references group="fn"/>

    说明 A'（2026-10-18）：不能剥掉 group="fn"。若 <references group=fn> 变成无 group 的
    <references>，fn 脚注会混入默认组，让页面出现多个无 group 的 <references> 结算点；
    跨块的默认组占位引用（如 {{ref|name=alloy}} 位于第二个 fn references 之前）会在中间那个
    references 渲染时被提前结算为「未定义」，主 references 里的 {{bws ref|name=alloy}} 便报
    “没有在先前的文字中使用”。保留 group="fn" 后 fn 脚注独立成组，默认组只剩主 <references>
    一个结算点，占位引用与结尾定义正常配对（最小页实验 6 验证 0 错误）。
    """
    def defblock(m):
        op, inner, close = m.group(1), m.group(2), m.group(3)
        # 保留 group="fn"（统一成 group="fn" 形式；op 无 group 属性时补上）
        op = re.sub(r"group\s*=\s*[\"']?fn[\"']?", 'group="fn"', op, flags=re.I)
        if not re.search(r"group\s*=", op, re.I):
            op = op.rstrip(">") + ' group="fn">'
        return op + _scan_refs(inner) + close

    # 1) 定义块整体处理（先把块内 {{ref...}} 当定义转，并保留 group="fn"）
    pat = re.compile(r"(<references\b[^>]*?group\s*=\s*[\"']?fn[\"']?[^>]*>)(.*?)(</references\s*>)", re.S | re.I)
    out = pat.sub(defblock, wikitext)

    # 2) 自闭合 <references group=fn/>
    out = re.sub(r"<references\b[^>]*?group\s*=\s*[\"']?fn[\"']?[^>]*?/>", '<references group="fn"/>', out, flags=re.I)

    # 3) 剩余的正文内联 {{ref|...group=fn...}}
    out = _scan_refs(out)

    return out


def convert_wikitext(wikitext, rules):
    """返回 (converted_wikitext, report)。

    按 rules 里的 src_template 驱动：凡英文 infobox 模板名匹配即转换为对应
    中文 {{Infobox X}}（字段映射见 field_map）。其它模板保留原样。
    """
    # 先做脚注 group 归一（方案 A'：{{ref|group=fn}}/<references group=fn> -> 标准 <ref>/<references>，
    # **保留 group="fn"**，见 _convert_footnote_groups 说明），
    # 再展开 {{wob ref|N}}（中文站 Template:Wob ref 对单参数调用会原样输出 {{{2}}} 字面量），
    # 以及给纯单参 {{book ref|X}} 补空第二参数（中文站 Template:Book ref 的 name 生成式
    # {{{2}}} 缺默认值管道，单参调用渲染 {{{2}}} 进 cite id，122 处）。
    # 必须在 parse 之前，否则 mwparserfromhell 会把 <references> 里嵌套的 {{ref}} 结构复杂化。
    wikitext = _convert_footnote_groups(wikitext)
    wikitext = _expand_nested_refs_in_fn(wikitext)
    wikitext = _fix_single_arg_book_refs(wikitext)
    wikitext = _expand_wob_refs(wikitext)
    # 语言间链接 [[es: X]]/[[uk: X]]：中文站 interwiki 表未配 es/uk 前缀，渲染成红链；
    # 转成指向各语言站 <lang>.coppermind.net 的完整外部链接（保留链接文本形态）。
    wikitext = _convert_lang_links(wikitext)

    code = mwparserfromhell.parse(wikitext)
    report = {
        "converted": {},
        "unmapped": [],
        "missing_cn": [],
        "collisions": {},
        "renamed": [],
        "quote_content": [],
        "footnote_groups": {"converted_to_ref": True, "note": "方案A：group=fn -> 标准<ref>/<references>"},
    }
    # 先递归清理英文站维护/站务模板（update/expand/meta:*/demoted/dialogue/edit note/user:* 整删，
    # nosnippet unwrap 保内文）——必须在 infobox 转换之前，否则嵌套在 infobox 参数值里的这些模板
    # 会被 build_dst_template 拍平成文本后无法再按模板节点识别。
    _apply_drop(code, report)
    infobox = _collect_infobox_rules(rules)

    new_nodes = []
    for node in code.nodes:
        if isinstance(node, mwparserfromhell.nodes.Template):
            # 注意：不能用 lstrip("Template:") —— lstrip 参数是字符集，会误剥开头的 l 等字符。
            name = re.sub(r'^(?:Template|模板)\s*:', '', str(node.name).strip(), flags=re.IGNORECASE)
            name = name.lstrip(":").strip()
            cfg = infobox.get(name.lower())
            if cfg is not None:
                if cfg.get("simple_rename"):
                    # 简单改名（如 quote）：位置参数按位置保留，仅改名。
                    # 位置参数是内容（引文/说话者），不是待映射字段，不报 unmapped。
                    # 引文不翻译、说话者可翻译——交给翻译阶段，这里只记录内容供提醒。
                    node.name = cfg["dst_template"]
                    report["renamed"].append(f"{name}->{cfg['dst_template']}")
                    pos = [str(p.value).strip() for p in node.params
                           if not p.showkey and str(p.value).strip()]
                    report.setdefault("quote_content", []).append({
                        "text_len": len(pos[0]) if pos else 0,
                        "speaker": pos[1][:80] if len(pos) > 1 else None,
                    })
                    new_nodes.append(node)
                    continue
                raw, mapped, unmapped, collisions, missing_cn = build_dst_template(cfg, node)
                src = cfg["src_template"]
                report["converted"].setdefault(src, []).extend(mapped)
                report["unmapped"].extend([(src, k, v) for k, v in unmapped])
                report["missing_cn"].extend([(src, k, v) for k, v in missing_cn])
                report["collisions"].update(collisions)
                new_nodes.append(mwparserfromhell.nodes.Text(raw))
                continue
            # 简单模板改名（参数原样保留，中文站同名模板按原参数消费）
            SIMPLE_RENAME = {
                "quote": "Quote",
                "image": "Image",
                "img": "Image",
                "rpg ref": "Rpg ref",
                "rpgref": "Rpg ref",
            }
            rename = SIMPLE_RENAME.get(name.lower())
            if rename and rename != name:
                node.name = rename
                report["renamed"].append(f"{name}->{rename}")
        new_nodes.append(node)

    code.nodes = new_nodes
    converted = _strip_bib_infobox_class(str(code))

    return converted, report


def _strip_bib_infobox_class(wikitext: str) -> str:
    """把书目表格 class='infobox bib ...' 里的 infobox 词去掉。

    背景：英文站书目表 `{| class='infobox bib mistborn cosmere' width=100%` 用 `infobox` 只是一个
    普通 class（配合 width=100% 占满宽度）；而 huijiwiki 平台全局把 `.infobox` 定义为「信息框」
    样式（窄/右浮/固定宽），导致这些宽书目表在中文站被压成信息框、布局奇怪。
    只对 class 含 `bib` 的表格顶行做剥离（保留其余 class 与 width 属性，让 width=100% 正常生效）。
    """
    pat = re.compile(r"^(\{\|\s+class\s*=\s*[\"'])([^\"']*)([\"']\s*)", re.M)

    def repl(m):
        cls = m.group(2)
        if "bib" not in cls.lower():
            return m.group(0)
        cls2 = re.sub(r"\binfobox\b\s*", "", cls, count=1, flags=re.I)
        if not cls2.strip():
            return m.group(0)
        return m.group(1) + cls2 + m.group(3)

    return pat.sub(repl, wikitext)


def main():
    ap = argparse.ArgumentParser(description="转换英文 wikitext 中的模板")
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--title", help="snapshot 标题（从 en_snapshot/<title>/wikitext.txt 读取）")
    grp.add_argument("--file", help="直接提供 wikitext 文件路径")
    grp.add_argument("--stdin", action="store_true", help="从 stdin 读 wikitext")
    ap.add_argument("--json", action="store_true", help="输出转换报告 JSON")
    ap.add_argument("--wrap", action="store_true", help="组装页面级包装模板（CmPermission/en/ensync，决议 10-12）")
    ap.add_argument("--en-title", help="--wrap 时使用的英文站词条名（默认取 --title）")
    args = ap.parse_args()

    if args.title:
        d = EN_SNAPSHOT / args.title.replace("/", "_")
        wikitext = (d / "wikitext.txt").read_text(encoding="utf-8")
        outfile = d / "converted.txt"
    elif args.file:
        wikitext = Path(args.file).read_text(encoding="utf-8")
        outfile = None
    else:
        wikitext = sys.stdin.read()
        outfile = None

    rules = load_rules()
    converted, report = convert_wikitext(wikitext, rules)

    if args.wrap:
        # 页面级包装（决议 10-12）：CmPermission 顶部 + en 首部占位 + ensync 结尾
        en_title = args.en_title or (args.title or "")
        revid = None
        if args.title:
            d = EN_SNAPSHOT / args.title.replace("/", "_")
            meta = d / "meta.json"
            if meta.exists():
                revid = json.loads(meta.read_text(encoding="utf-8")).get("revid")
        if not revid:
            revid = "CHANGE_ME_REVID"
        top_cm = "\n{{CmPermission|" + en_title + "}}\n"
        top_en_marker = "\n{{en|" + en_title + "}}"  # 翻译阶段移入首行 '''中文名'''
        end_ensync = "\n{{ensync|" + str(revid) + "}}\n"
        converted = top_cm + top_en_marker + converted
        # ensync 放最末尾（正文之后）；忽略最后已有换行
        converted = converted.rstrip("\n") + "\n" + end_ensync
        report["wrapped"] = {
            "CmPermission": en_title,
            "en": en_title,
            "ensync": revid,
            "note": "en 已置于顶部占位，翻译阶段需移到正文首行 '''中文名''' 之后",
        }

    if args.json:
        print(json.dumps({"converted": converted, "report": report}, ensure_ascii=False, indent=2))
    else:
        print(converted)
        print("=" * 50, file=sys.stderr)
        print("转换报告:", file=sys.stderr)
        print(json.dumps(report, ensure_ascii=False, indent=2), file=sys.stderr)

    if outfile and not args.json:
        outfile.write_text(converted, encoding="utf-8")
        print(f"(已存 {outfile})", file=sys.stderr)


if __name__ == "__main__":
    main()
