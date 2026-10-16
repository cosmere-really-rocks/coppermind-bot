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
        if p.showkey is None:
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


def convert_wikitext(wikitext, rules):
    """返回 (converted_wikitext, report)。

    按 rules 里的 src_template 驱动：凡英文 infobox 模板名匹配即转换为对应
    中文 {{Infobox X}}（字段映射见 field_map）。其它模板保留原样。
    """
    code = mwparserfromhell.parse(wikitext)
    infobox = _collect_infobox_rules(rules)
    report = {
        "converted": {},
        "unmapped": [],
        "missing_cn": [],
        "collisions": {},
        "renamed": [],
    }

    new_nodes = []
    for node in code.nodes:
        if isinstance(node, mwparserfromhell.nodes.Template):
            # 注意：不能用 lstrip("Template:") —— lstrip 参数是字符集，会误剥开头的 l 等字符。
            name = re.sub(r'^(?:Template|模板)\s*:', '', str(node.name).strip(), flags=re.IGNORECASE)
            name = name.lstrip(":").strip()
            cfg = infobox.get(name.lower())
            if cfg is not None:
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
    converted = str(code)

    return converted, report


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
