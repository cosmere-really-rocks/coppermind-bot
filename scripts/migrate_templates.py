#!/usr/bin/env python3
"""
模板迁移工具（决策 #16 的例外：非 meta 级模板按用户决议迁移到中文站）。

背景：英文词条用到的模板，中文站缺同名模板 → 按 `rules/template_probe_resolution.md` 的决议
把非 meta 级模板迁移（翻译）到中文站，避免词条搬运后红链。

本脚本把 `TEMPLATES` 里定义的模板逐一写入中文站（Template 命名空间），用 write.HuijiClient 登录 + CSRF + edit。
- 已存在的模板：覆盖写（用于 Date/sa → 改成 redirect、或更新内容）。
- `--dry-run`：只打印将写入的内容不提交。
- 用法：
    .venv/bin/python scripts/migrate_templates.py --dry-run        # 预演
    .venv/bin/python scripts/migrate_templates.py --templates Rosharan date,Notice
    .venv/bin/python scripts/migrate_templates.py --all             # 全部
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import write

TEMPLATES: dict[str, str] = {}


def _reg(name: str, content: str):
    TEMPLATES[name] = content


# ============================================================
# 1. Rosharan date —— 风暴光/罗沙历（Vorin）中文模板
#    合并英文 Rosharan date（支持 named: year/month/week/day 与 positional: 1/2/3/4）
#    与中文站既有 Date/sa 的原生输出（年年/月/周/天），redirect 到本模板后旧调用仍可用。
# ============================================================
_reg("Rosharan date", """{{#if:{{{year|}}}{{{no-year|}}}|<!-- named / no-year
--><span class="date rosharan-date">{{#if:{{{text|}}}|{{{text}}}|{{#if:{{{year|}}}|{{{year|}}}年{{#if:{{{month|}}}|第{{{month}}}月}}{{#if:{{{week|}}}|第{{{week}}}周}}{{#if:{{{day|}}}|第{{{day}}}天}}|}}}}</span><!--
-->|{{#if:{{{1|}}}|<!-- positional
--><span class="date rosharan-date">{{{1|}}}年{{#if:{{{2|}}}|第{{{2}}}月}}{{#if:{{{3|}}}|第{{{3}}}周}}{{#if:{{{4|}}}|第{{{4}}}天}}{{#if:{{{missing-date|}}}{{{date-missing|}}}|<span class="error">?</span>&#32;}}</span><!--
-->|<!-- 缺年份
--><includeonly><span class="date rosharan-date"><span class="error" title="缺少日期参数">?</span></span></includeonly><!--
-->}}|}}<noinclude>
本模板按 Vorin 格式输出罗沙（风暴光）历日期。用法 {{t|Rosharan date|年份|月|周|日}}（亦可用命名参数 year/month/week/day；<code>text</code> 可整体覆盖输出，兼容原 {{t|Date/sa}} 调用）。
当只给年份时仅输出年份；给了月/周/日则转换为中文「年/月/周/天」形式。若 <code>missing-date</code> 有值而缺少月/周/日部分，会显示红色问号；若年份缺失则显示错误问号（除非传 <code>no-year</code>）。

- 参考：''[[王者之路]]'' 主要设定在 1173 年，''[[渡誓]]'' 设定在 1174 年末。

本模板同时承接原「模板:Date/sa」的输出（中文 年/月/周/天），date/sa 现为指向本模板的 redirect。
翻译自英文站 Template:Rosharan date（pageid 5747）。

[[category: date templates]]
[[category: 模板]]
</noinclude>""")


# 2. date/sa —— 从原有原生模板改为 redirect 到 Rosharan date（模板重定向自动转发转用；中文输出由 Rosharan date 承接）
_reg("Date/sa", "#REDIRECT [[Template:Rosharan date]]")


# ============================================================
# 3. Notice —— 横幅父模板（cite note / rpg-canon 等横幅类模板的底座）
# ============================================================
_reg("Notice", """<includeonly><div {{#if:{{{id|}}}|id="{{{id}}}"}} class="notice hide-for-print {{{class|curved}}}" style="{{{style}}}">{{#if:{{{b|}}}|<div class="notice-main-text" style="font-weight:bold;">{{{b}}}</div>|}}<span class="{{#if:{{{b|}}}|hide-for-multinotice|notice-main-text}}">{{{1}}}</span></div></includeonly><noinclude>
'''Notice''' 是用于搭建「横幅类模板」（如 [[:category: 横幅]]）的父模板。本模板不应直接用于词条，而是用于创建具体横幅模板。

== 参数 ==
* {{{style}}} —— 设置横幅盒的样式（如背景色）
* {{{b}}}　　—— 可选的横幅粗体标题
* {{{1}}}　　—— 横幅内的正文

== 示例 ==
<code><nowiki>
{{notice|style=background-color:#CCA;
|b=这是粗体标题！
|1=这是带更多说明的正文
}}
</nowiki></code>

[[category: 模板]]
</noinclude>""")


# 4. Cite note —— 「需要更多引用」横幅
_reg("Cite note", """{{notice|style=background-color:#CCA;
|b=本条目或章节需要更多[[Help:引用|引用]]
|1=请补充能说明这些事实的章节或来源引用
}}<includeonly>[[category: 需要引用]]</includeonly><noinclude>
本模板应加在「需要较多引用」的条目或章节顶部，自动把该条加入 [[:category: 需要引用]]。

参见：{{t|cite}}（对正文某一句要求引用的模板）。

翻译自英文站 Template:Cite note（pageid 4842）。
[[category: 模板]]
</noinclude>""")


# 5. Rpg-canon —— 「Cosmere RPG 内容正典」横幅
_reg("Rpg-canon", """{{notice|style=background-color:#FFA500;|id=rpg-canon
|b=本条目或章节包含来自 [[Cosmere 角色扮演游戏]] 冒险内容的信息。
|1=这些信息属于[[帮助:正典|正典]]，但在实际游玩中可能会变动。
}}<noinclude>
翻译自英文站 Template:Rpg-canon（pageid 25374）。
[[category: 模板]]
</noinclude>""")


# 6. Small caps —— 小型大写排版
_reg("Small caps", """<includeonly><span style='font-variant: small-caps'>{{{1}}}</span></includeonly><noinclude>
本模板把文字排版成「小型大写」形式，用于书中（如 [[风暴之父]]、[[培育]] 等说话时）的引文格式。

用法：<code><nowiki>{{small caps|文字}}</nowiki></code> → {{small caps|文字}}

翻译自英文站 Template:Small caps（pageid 21518）。
[[category: 模板]]
</noinclude>""")


# ============================================================
# 7. CoverToC —— 系列封面目录导航（mistborn 等系列各书 /Covers 子页）
# ============================================================
_reg("CoverToC", """<onlyinclude><div align=center><span class="toc" style="display:table; text-align:center;"><!--
-->{{#switch:{{lc:{{{1}}}}}<!--
-->|sa|stormlight|stormlight archive|the stormlight archive=<!--
   -->''[[The Way of Kings/Covers|The Way of Kings]]''<!--
   --> · ''[[Words of Radiance/Covers|Words of Radiance]]''<!--
   --> · ''[[Oathbringer/Covers|Oathbringer]]''<!--
   --> · ''[[Rhythm of War/Covers|Rhythm of War]]''<!--
   --> · ''[[Wind and Truth/Covers|Wind and Truth]]''<!--
-->|mbe1=<!--
   -->''[[Mistborn: The Final Empire/Covers|The Final Empire]]''<!--
   --> · ''[[The Well of Ascension/Covers|The Well of Ascension]]''<!--
   --> · ''[[The Hero of Ages/Covers|The Hero of Ages]]''<!--
   --> · (''[[Mistborn: Secret History/Covers|Mistborn: Secret History]]'')<!--
-->|mbe2=<!--
   -->''[[The Alloy of Law/Covers|The Alloy of Law]]''<!--
   --> · ''[[Shadows of Self/Covers|Shadows of Self]]''<!--
   --> · ''[[The Bands of Mourning/Covers|The Bands of Mourning]]''<!--
   --> · ''[[The Lost Metal/Covers|The Lost Metal]]''<!--
-->}}<!--
--></span></div></onlyinclude>
本模板为一个系列的所有 <code>/Covers</code>（封面）子页生成目录。传入一个不带名的参数标识系列（见表）。通常放在页面顶部。

{| class=infobox style="margin:auto"
|-
! 系列
! 代号
|-
! [[迷雾之子 时代一]]
| <code>mbe1</code>
|-
! [[迷雾之子 时代二]]
| <code>mbe2</code>
|-
! [[风暴光档案|风暴光]]
| <code>sa</code>、<code>stormlight</code>、<code>stormlight archive</code>、<code>the stormlight archive</code>
|}

翻译自英文站 Template:CoverToC（pageid 15936）。显示名为英文原样（封面子页名未中译，保持与英文一致）。
[[category: 导航]]
</noinclude>""")


# ============================================================
# 8. Sots ref —— 引用「State of the Sanderson」年度信（按中文站 bws ref 风格）
# ============================================================
_reg("Sots ref", """<includeonly>{{#tag:ref
|{{{pre|}}}
[[bws:{{{page|{{{1|}}}}}}|State of the Sanderson {{{1|}}}]]
{{{post|}}}
<br><small> &mdash; [[布兰登·山德森|森德森]]官网 - {{#switch:{{{1|}}}
|2013=2013-07-24|2014=2014-12-18|2015=2015-12-18|2016=2016-12-18|2017=2017-12-18
|2018=2018-12-18|2019=2019-12-19|2020=2020-12-18|2021=2021-12-20|2022=2022-12-22
|2023=2023-12-19|2024=2024-12-19|2025=2025-12-19|#default={{{date|}}}}}</small>
|name={{{name|sots-{{{1|}}}}}}
|group={{{group|}}}
}}</includeonly><noinclude>
本模板生成对 [[State of the Sanderson]] 年度信的引用。一般优先用 {{t|wob ref}} 链接到对应 SotS 的相应部分。

用法：{{t|sots ref|年份}}

翻译自英文站 Template:Sots ref（pageid 11716），按中文站 bws ref 风格改写。
[[category: 引用模板]]
[[category: 模板]]
</noinclude>""")


# 9. Wp ref —— 引用维基百科（按中文站 url ref 风格）
_reg("Wp ref", """<includeonly>{{#tag:ref<!--
-->|{{{pre|}}}
 -->[[Wikipedia:{{{page|{{{1|}}}}}}|{{{text|{{{2|{{{1|}}}}}}}}}]]<!--
 -->{{{post|}}}
 --><br><small> &mdash; [[Wikipedia:维基百科|维基百科]] {{#if:{{{date|}}}|- {{{date|}}}}}</small>
-->|name={{{name|wp-{{{page|{{{1|}}}}}}}}}<!--
-->|group={{{group|}}}<!--
-->}}<!--
--></includeonly><noinclude>
本模板用于引用[[Wikipedia:维基百科|维基百科]]条目。

用法：{{t|wp ref|维基百科条目名|显示文字|post|pre}}
* {{{text}}} 替换显示文字；{{{pre}}}/{{{post}}} 分别加在链接前后；{{{name}}} 覆盖引用名；{{{date}}} 为日期（yyyy-mm-dd）。

翻译自英文站 Template:Wp ref（pageid 5652），按中文站 url ref 风格改写。
[[category: 引用模板]]
[[category: 模板]]
</noinclude>""")


# ============================================================
# 10. Books —— 「布兰登·山德森已出版作品」总导航
# ============================================================
_reg("Books", """{{navbox
|title=[[布兰登·山德森]]已出版作品<br /><!--
--><small>([[书目]] · [[样章]] · [[未出版作品]] · [[版权]] · [[:category: 人物|人物]])</small><!--
-->|id=Books|

{{row/kv
| [[风暴光档案|The Stormlight Archive]]
|<!--
-->[[王者之路]] · <!--
-->[[光辉真言]] · <!--
-->[[渡誓]] · <!--
-->[[纷争之韵]] · <!--
-->[[风与真理]] <!--
--><br /><small>([[Edgedancer (novella)|Edgedancer]] · <!--
-->[[Dawnshard (novella)|Dawnshard]] · <!--
-->[[Elsecaller (short story)|Elsecaller]] · <!--
-->[[King Lopen the First of Alethkar]])</small>
}}

{{row/kv
| [[迷雾之子 (系列)|Mistborn]]
| '''[[迷雾之子 时代一|Era 1]]:''' [[最后帝国(书籍)|The Final Empire]] · [[升华之井(书籍)|The Well of Ascension]] · [[永世英雄(书籍)|The Hero of Ages]]<br /><!--
--> '''[[迷雾之子 时代二|Era 2]]:''' [[The Alloy of Law]] · [[Shadows of Self]] · [[The Bands of Mourning]] · [[The Lost Metal]]<br /><!--
--><small>([[迷雾之子：秘史|Mistborn: Secret History]] · [[The Eleventh Metal]] · [[Allomancer Jak and the Pits of Eltania]])</small>
}}

{{row/kv
| [[Hoid's Travails]]
| [[Tress of the Emerald Sea]] · [[Yumi and the Nightmare Painter]] · [[The Fires of December]]
}}

{{row/kv
| 其他[[三界宙|Cosmere]]作品
| [[Arcanum Unbounded]] · [[Elantris (book)|Elantris]] · [[Isles of the Emberdark]] · [[The Sunlit Man]] · [[Warbreaker]] · [[White Sand]]<br />
<small>([[The Hope of Elantris]] · [[The Emperor's Soul]] · [[Shadows for Silence in the Forests of Hell]])</small>
}}
}}<includeonly><!--
-->{{{cats|}}}<!--
--></includeonly><noinclude>
列出[[布兰登·山德森]]已出版的全部作品。用法：在页面底部加入 {{t|{{PAGENAME}}}}。

翻译自英文站 Template:Books（pageid 709）；有既定中译的书名用中文，其余保持英文显示。
[[category: 导航]]
</noinclude>""")


# 11. Tress —— 「翠海之诗」单书导航
_reg("Tress", """{{navbox
|title=[[Tress of the Emerald Sea]] ('''[[Lumar]]''')|id=Tress|

{{row/kv
| [[:category: Lumarans|Characters]]
| [[Tress]] · [[Charlie]] · [[Crow]] · [[Salay]] · [[Fort]] · [[Ann]] · [[Laggart]] · [[Dougs]] · [[Hoid]] · [[Ulaam]] · [[Riina|Sorceress]]
}}

{{row/kv
| [[:category: Lumar|Places]]
| [[Emerald Sea]] · [[Crimson Sea]] · [[Midnight Sea]] · [[Diggen's Point]] · [[Sorceress's island]]
}}

{{row/kv
| Magic
| [[Aether]]s · [[Aether spores]] · [[Spore eater]] · [[Sprouter]] · [[Luhel bond]]
}}

{{row/kv
| Ships
| [[Crow's Song]] · [[Oot's Dream]] · [[Two Cups]] · [[Whistlebow]]
}}
}}<includeonly><!--
-->{{{cats|}}}<!--
--></includeonly><noinclude>
本模板应用于与《[[Tress of the Emerald Sea]]》相关的页面。

翻译自英文站 Template:Tress（pageid 22736）；显示名保持英文原样。
[[category: 导航]]
</noinclude>""")


# ============================================================
# 写站
# ============================================================
def main():
    ap = argparse.ArgumentParser(description="把非 meta 模板迁移到中文站")
    ap.add_argument("--templates", default=None, help="逗号分隔的模板名（须在 TEMPLATES 内）")
    ap.add_argument("--all", action="store_true", help="全部模板")
    ap.add_argument("--dry-run", action="store_true", help="只打印不提交")
    args = ap.parse_args()

    if args.all:
        names = list(TEMPLATES)
    elif args.templates:
        names = [n.strip() for n in args.templates.split(",") if n.strip()]
        unknown = [n for n in names if n not in TEMPLATES]
        if unknown:
            print("未知模板:", unknown); sys.exit(1)
    else:
        print("请用 --all 或 --templates"); sys.exit(1)

    env = write.load_env(None)
    api = write.resolve_api_url(env)
    client = write.HuijiClient(api, env["HUIJI_API_KEY"], env["HUIJI_BOT_USER"], env["HUIJI_BOT_PASS"])
    if not args.dry_run:
        client.ensure_logged_in()

    for name in names:
        content = TEMPLATES[name]
        title = "模板:" + name
        if args.dry_run:
            print(f"===== [DRY] 模板:{name} =====")
            print(content)
            print("-----")
            continue
        r = client.edit(title, content, f"bot 迁移非 meta 模板（英→中，复制自英文站 {name}）")
        print(f"✅ 模板:{name} -> {r.get('result','?')} (newrevid={r.get('newrevid')})")


if __name__ == "__main__":
    main()
