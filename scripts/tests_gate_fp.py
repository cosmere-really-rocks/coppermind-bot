# -*- coding: utf-8 -*-
"""门禁③误伤修正回归单测（_field_half_problems 直调）。

背景：门禁第 5 节（| 字段行中英夹杂）在 2026-10-22 豆包评测有 3 类误伤（FP）——
Words of Radiance 4/4 全 FP + Wind and Truth 1/1 FP，两页零真缺陷（+2 页可回）：
- 斜体 `''…''` 外语书名不剔除 → 非 ASCII 断词碎片（Stürme→rme、Câmpiile→mpiile、
  Jurâmântului→ntului）与外语虚词 des 被当英文残留；
- 模板剔除上限 150 字符 → Wind and Truth 186 字符长 {{tor ref|…}} 剔不掉，
  「tor ref」残留被当小写内容词；
- FUNC_WORDS 缺外语虚词 des。

③修法（2026-10-23，判定从 check_one 原位抽出为 _field_half_problems 便于直调）：
斜体整体剔除（镜像 mask_nonprose 第3步：粗体先占位保护、不豁免）+ 上限 150→512
（全语料 |行内最长模板 449）+ FUNC_WORDS 增 des。

覆盖：
- FP×5：评测两页的 5 行逐字原文 → 修后零问题
- 真缺陷不回吞（对照回归核心）：小写内容词残留 / 称号紧邻中文 / 引号外残留 /
  长模板+引号外残留 / 粗体英文 / 外语虚词之外的小写词 → 一律仍拦
- 结构边界：值全中文、非 | 行、{{tag}}/{{en}}/原名行、决议#13原文块内行 → 不判
- FUNC_WORDS 模块级形态：含 des、不含内容词 several
- ④（2026-10-23 口径修正·方向1，用户裁定「先修门禁」不烧 LLM）：
  无源 5 标题 3a 豁免（UNSCOURCED_HEADS）/ 干扰扫描剔裸 URL（Order 两页 quiz
  链接 %XX 配对 8 处误伤）/ 散文半译词数前剔行内 HTML 注释·标签·裸 URL（span
  样式词恰 6 词等 4 页 9 行误伤）/ 字段半译 untranslated_terms 已记录保留词豁免
  （Tor books，人审 PASS）/ 引用同集合仅顺序不同=合理重排不拦（丢失/改号仍拦）。
  全部只减少误报：真缺陷对照用例不回吞。
- ⑤（2026-10-23 深夜·导语检查误伤，WoA/Spren 实录两页 4 连败实为假阳性）：
  lead_region 锚从 "}}\n\n" 换为「最后一个单独 }} 行」（WoA infobox 收尾无空行、
  紧贴 {{for}} 行，旧锚失效把英文 Infobox 整段当导语）+ 剥噪剔 HTML 标签
 （Spren <div style=clear:right/> 属性词 div/style/clear/right 正好 4 词凑满阈值，
  且源侧同行贡献「源 ≥4」，div 自己和自己对上）。真英文导语对照用例仍拦。

用法：.venv/bin/python scripts/tests_gate_fp.py
"""
import os
import sys
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, fname))
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


tr = _load("translate_mod", "translate.py")
vr = _load("verify_mod", "verify_translation.py")

# 评测实录逐字行（state/doubao_eval_verify.txt Words of Radiance / Wind and Truth）
WOR1 = "| ''Die Stürme des Zorns''（意为“愤怒风暴”）"
WOR2 = "| ''Le Livre des Radieux''（意为“光辉骑士之书”）"
WOR3 = "| ''Câmpiile Sfârâmate''（破碎平原）"
WOR4 = "| ''Poarta Jurâmântului''（誓约之门）"
WAT = ("| 发行日期    = December 6th, 2024{{tor ref|"
       "brandon-sandersons-fifth-stormlight-archive-book-gets-publishing-date|"
       "Brandon Sanderson's Fifth Stormlight Archive Book Gets Publishing Date|"
       "date=2023-12-18|name=release-date}}")

# 造一个 >150 且 <512 的长模板（模拟长 tor ref 变体）
LONG_TOR = "{{tor ref|" + "x" * 300 + "|some title}}"

# --- ④ 口径修正（2026-10-23 方向1）实录样本行 ---
# Order of Windrunners/Lightweavers 干扰误伤原貌（percent-encoding 链接 + 100%）
QUIZ = ("* 100%风行骑士团得分，需要选择一套特定答案，详情见"
        "[https://www.reddit.com/media?url=https%3A%2F%2Fpreview.redd.it"
        "%2Fhow-the-knights-radiant-quiz-works-v0-zxess4lhspnc1.png"
        "%3Fwidth%3D400%26format%3Dpng%26s%3Dabc]")
# Sylphrena/Dalinar/Cultivation/Odium span 样式行原貌（style 属性恰 6 个英文词）
SPAN = "* 茜芙蕊娜是少数以<span style='font-variant: small-caps'>小型大写字母</span>格式说话的角色之一。"
# Szeth:471 行内说明注释原貌
INLINE_CMT = ("* 在''[[王者之路(初版)]]''中，无真奴 of Shinavar"
              "<!--This is the correct spelling per 王者之路 大帝, do not update-->"
              "，简称Jek，后来就不再适用了。")
# Roshar:57 裸链行原貌
BARE_URL = "https://www.reddit.com/r/飓光_Archive/comments/7ph9ap/no_spoilers_roshar_physics/"


# ③ 只动 | 字段行 → 问题数即判定
def nprob(body, spans=None):
    return len(vr._field_half_problems(body, [] if spans is None else spans))


CASES = [
    # --- FP×5：两页实录行，修后必须零问题 ---
    ("fp|WoR德语书名des", nprob, WOR1, 0),
    ("fp|WoR法语书名des", nprob, WOR2, 0),
    ("fp|WoR罗马尼亚语断词", nprob, WOR3, 0),
    ("fp|WoR罗马尼亚语属格ntului", nprob, WOR4, 0),
    ("fp|WaT长tor ref残留", nprob, WAT, 0),
    ("fp|长模板300字符", nprob, "| date = 中文说明 " + LONG_TOR, 0),
    # --- 真缺陷对照：一类都不许回吞 ---
    ("real|小写内容词残留", nprob,
     "| lore = 这是设定说明，several noble houses remain", 1),
    ("real|称号紧邻中文B信号", nprob, "| x = 幸存者 of the Flames", 1),
    ("real|斜体书名外残留仍拦", nprob,
     "| note = ''Die Stürme des Zorns''（意为愤怒风暴）several houses remain", 1),
    ("real|长模板+引号外残留仍拦", nprob,
     "| date = 中文 " + LONG_TOR + " several houses remain", 1),
    ("real|粗体不豁免", nprob, "| x = 中文 '''noble houses''' remain", 1),
    ("real|des之外小写词仍拦", nprob, "| y = 术语 des contes restants", 1),
    ("real|夹杂残留短语", nprob,
     "| title = 迷雾之子 lord of drifters", 1),
    # --- 结构边界：按设计不判 ---
    ("edge|值全中文", nprob, "| x = 纯中文值", 0),
    ("edge|非|行不判", nprob, "中文 several noble houses in prose", 0),
    ("edge|tag模板行跳过", nprob, "| {{tag|en}} 中文 several houses", 0),
    ("edge|en标注行跳过", nprob, "| {{en|Foo}} 中文 several houses", 0),
    ("edge|原名行跳过", nprob, "| 原名 = 中文 several houses", 0),
    ("edge|引号未成对不断词", nprob, "| x = 中文 it's several houses", 1),
    # --- ④ 口径修正（2026-10-23）helpers 直调：只少误报 ---
    ("④|无源标题Zeenid放行", lambda s: len(vr._heading_problems(s)),
     "=== Zeenid-daughter-Beth ===", 0),
    ("④|无源标题TheChild放行", lambda s: len(vr._heading_problems(s)),
     "=== The Child ===", 0),
    ("④|未译真标题仍拦", lambda s: len(vr._heading_problems(s)),
     "=== Vessels ===", 1),
    ("④|已译中文标题放行", lambda s: len(vr._heading_problems(s)),
     "=== 容器 ===", 0),
    ("④|等号不配对仍拦", lambda s: len(vr._heading_problems(s)),
     "=== Kata ==", 1),
    ("④|quiz链接噪声不报", lambda s: len(vr._interference_problems(s)), QUIZ, 0),
    ("④|真干扰占位符仍报", lambda s: len(vr._interference_problems(s)),
     "早期在%{{date|1021|fe}}%处", 1),
    # Wind and Truth 桥接回归：两个 % 被 90+ 字符的无 % 长 URL 隔开 → 间距不变不配对
    ("④|长URL两侧百分号不桥接", lambda s: len(vr._interference_problems(s)),
     "%。[ 第二次进度更新]见[https://www.reddit.com/r/x/comments/abcdefghijklmnop/"
     "abcdefghijklmnopqrstuvwxyz0123456789abcdefghijklmnopqrstuvwxyz0123456789ab] 约33%",
     0),
    ("④|span样式行不报", lambda s: len(vr._prose_half_problems(s)), SPAN, 0),
    ("④|行内注释行不报", lambda s: len(vr._prose_half_problems(s)), INLINE_CMT, 0),
    ("④|裸URL行不报", lambda s: len(vr._prose_half_problems(s)), BARE_URL, 0),
    ("④|真半译正句仍拦", lambda s: len(vr._prose_half_problems(s)),
     "It is also possible to snap from false emotions caused by soothing and rioting indeed.",
     1),
]


def main():
    failed = 0
    passed = 0

    def check(name, got, want):
        nonlocal failed, passed
        if got == want:
            passed += 1
            print("  OK  %s" % name)
        else:
            failed += 1
            print("  FAIL %s" % name)
            print("    got : %r" % (got,))
            print("    want: %r" % (want,))

    for name, fn, src, want in CASES:
        check(name, fn(src), want)

    # --- 决议#13 原文块内的字段行（含署名行）按设计不判 ---
    body = "{{Quote|\n| x = 中文 several noble houses remain\n}}"
    spans = [(0, len(body))]
    check("edge|原文块内行跳过", nprob(body, spans), 0)
    # 同行不在原文块内时必须判（证明 spans 真的生效，不是恒 0）
    check("edge|块外同行仍判", nprob(body, []), 1)

    # --- FUNC_WORDS 模块级形态 ---
    check("func|des已入", "des" in vr.FUNC_WORDS, True)
    check("func|内容词不入", "several" in vr.FUNC_WORDS, False)
    check("func|既有词保留", {"of", "the", "with"} <= vr.FUNC_WORDS, True)

    # --- 抽出等价性探针：粗体占位不残留占位符 ---
    check("edge|无占位符泄漏",
          "\\x00" in str(vr._field_half_problems("| x = 中文 '''bold''' test", []))
          or "\x00" in str(vr._field_half_problems("| x = 中文 '''bold''' test", [])),
          False)

    # --- ④ 引用比对：同集合仅顺序不同=合理重排不拦；丢失/改号仍拦 ---
    check("ref|仅顺序重排不报",
          vr._ref_mismatch_problems(["mb1|1", "mb1|2"], ["mb1|2", "mb1|1"]), [])
    check("ref|丢失仍报",
          len(vr._ref_mismatch_problems(["mb1|1", "mb1|2"], ["mb1|1"])) >= 1, True)
    check("ref|改号仍报",
          len(vr._ref_mismatch_problems(["mb1|1"], ["mb1|9"])) >= 1, True)
    check("ref|重复项换位不报",
          vr._ref_mismatch_problems(["x", "x", "y"], ["y", "x", "x"]), [])

    # --- ④ 字段半译 ut 豁免：记录保留词放行、未记录内容词照拦 ---
    ut_tor = [{"en": "Tor books", "reason": "译名表未收录，无官方中文译名"}]
    check("ut|Tor books记录放行",
          len(vr._field_half_problems("| 出版社 = Tor books", [], ut_tor)), 0)
    check("ut|无记录仍拦",
          len(vr._field_half_problems("| 出版社 = Tor books", [], [])), 1)
    check("ut|未记录内容词不放行", len(vr._field_half_problems(
        "| lore = 这是设定说明，several noble houses remain", [], ut_tor)), 1)
    check("ut|占位符条目不构成豁免", len(vr._field_half_problems(
        "| lore = 中文 quote 台词若干 words remain here",
        [], [{"en": "Quote 台词（占位符 %%ORIGINAL_BLOCK_1%%）", "reason": "决议#13"}])), 1)

    # --- ⑤ 导语检查误伤（2026-10-23 实录：WoA infobox 收尾无空行锚失效 / Spren div 属性词）---
    woa_src = ("{{Infobox book\n| 原名 = The Well of Ascension\n"
               "| 发行日期 = August 21, 2007{{ref|x}}\n}}\n\n"
               "'''The Well of Ascension''' is the second volume of the Mistborn trilogy. "
               "Three armies besiege the city while an ancient legend offers hope of finding the well.\n\n"
               "== Summary ==\nAll text.\n")
    woa_dst = ("{{AITranslation}}\n{{CmPermission|The Well of Ascension}}\n"
               "'''升华之井'''{{en|The Well of Ascension}}\n"
               "{{Infobox book\n| 原名    = The Well of Ascension\n"
               "| 出版社    = Tor Books publishing house\n"
               "| 发行日期    = August 21, 2007{{ref|x}}\n}}\n"
               "{{for|升华之井|[[存留]]的垂贯点}}\n"
               "'''''升华之井'''''是布兰登·桑德森创作的第二卷。三支军队兵临城下，古老传说带来一线希望。\n\n"
               "== 简介 ==\n中文。\n")
    check("lead|infobox紧贴for旧锚失效不报",
          tr.untranslated_lead_english(woa_src, woa_dst), False)
    div_src = ("{{Infobox lifeform\n| 原名 = Spren\n}}\n\n"
               "Spren are fragments of the almighty that gain sentience on Roshar. "
               "They range widely in form and intellect across the highstorms.\n"
               "<div style=clear:right/>\n\n== Traits ==\n")
    div_dst = ("{{AITranslation}}\n{{CmPermission|Spren}}\n"
               "{{Infobox lifeform\n| 原名    = Spren\n}}\n\n"
               "灵体是创世之力的碎片，在柔刹智慧生物影响下获得自我意识。它们的外形与智力千差万别。\n"
               "<div style=clear:right/>\n\n== 特征 ==\n")
    check("lead|div属性词不计不报", tr.untranslated_lead_english(div_src, div_dst), False)
    real_dst = ("{{AITranslation}}\n{{Infobox x\n| a = b\n}}\n\n"
                "Spren are tiny pieces of the almighty that talk to humans all the time.\n")
    check("lead|真英文导语仍拦", tr.untranslated_lead_english(div_src, real_dst), True)

    # --- ⑥ 导语检查误伤二连（2026-10-24 首个马拉松块实录 Kali'kalin / Cabine）---
    apos_src = ("{{Infobox person\n| 原名 = Kali'kalin\n}}\n\n"
                "Kali'kalin is a spirit name invoked by the Iriali to curse at misfortune "
                "in their daily speech across the highstorms of Roshar.\n\n== Notes ==\n")
    apos_dst = ("{{AITranslation}}\n{{Infobox person\n| 原名    = Kali'kalin\n}}\n\n"
                "'''Kali'kalin'''是[[柔刹]]的一名人物。吃角族相信他留有鬼魂，"
                "有时会以这只鬼魂的名字咒骂，仅称其为Kali'kalin之鬼。这可能与类似表达"
                "Kali'kalin'da有关。\n\n== 注记 ==\n")
    check("lead|撇号专名分词不报", tr.untranslated_lead_english(apos_src, apos_dst), False)
    quote_src = ("{{Quote|one of the ten fools|中文。}}\n\n"
                 "Cabine was one of the ten fools who acted like a child though he was "
                 "an adult. He remained a figure of doctrine within the Vorin church.\n\n"
                 "== History ==\n")
    quote_dst = ("{{AITranslation}}\n"
                 "{{Quote|[[卡拉丁|Kal]] felt like one of the ten fools&mdash;specifically "
                 "Cabine, who acted like a child though he was adult.|[[卡拉丁]]将他的行为相提并论。"
                 "{{book ref|sa1|37}}}}\n\n"
                 "'''卡宾'''{{en|Cabine}}是[[十蠢]]之一{{book ref|sa1|37}}，十蠢是[[沃林教]]"
                 "教义的一部分。<ref>[[wob:4157|wob:4157]]</ref>\n\n"
                 "他虽为成年人，举止却像个孩子。{{book ref|sa1|37}}\n\n== 历史 ==\n")
    check("lead|嵌套模板原文块不报", tr.untranslated_lead_english(quote_src, quote_dst), False)
    check("lead|连字符专名不报", tr.untranslated_lead_english(
        "{{Infobox person\n| 原名 = Samjae\n}}\n\nSamjae is a Torish yoki-hijo who "
        "befriended Yumi while both were still in training under Liyun's watch.\n\n== Notes ==\n",
        "{{AITranslation}}\n{{Infobox person\n| 原名    = Samjae\n}}\n\n"
        "'''Samjae'''{{en|Samjae}}是一名[[Torish]]籍的[[yoki-hijo]]，"
        "在两人尚且年幼时便与[[Yumi]]成为了朋友。{{book ref|yumi|32}}\n\n"
        "尽管遭到[[Liyun]]的禁止，Samjae仍会偷偷给Yumi讲述yoki-hijo相恋并私奔的故事。"
        "{{book ref|yumi|13}}\n\n== 注记 ==\n"), False)
    check("lead|真英文导语仍拦②", tr.untranslated_lead_english(
        quote_src, "{{AITranslation}}\n\nCabine felt like one of the ten fools "
        "though he was an adult within the Vorin church doctrine.\n\n== 历史 ==\n"), True)

    # --- ⑦ 导语 ut 豁免（2026-10-24 Stone of Ten Dawns 实录：记录保留词不计）---
    utsrc = ("{{Infobox item\n| 名称 = Stone of Ten Dawns\n}}\n\n"
             "The '''Stone of Ten Dawns''' is a legendary [[perfect gemstone]] on "
             "[[Roshar]]. According to legend it was perfect and could hold light.\n\n"
             "== Notes ==\n")
    utdst = ("{{AITranslation}}\n{{Infobox item\n| 名称    = Stone of Ten Dawns\n}}\n\n"
             "'''十晓之石'''{{en|Stone of Ten Dawns}}是[[柔刹]]上一颗传说级的"
             "[[perfect gemstone]]。根据传说它完美无瑕，能够储存光芒。他们寻找perfect gemstones"
             "来囚禁光芒，并将这些perfect gems的传说记入史册。{{book ref|sa3|99}}\n\n== 注记 ==\n")
    check("lead|记录保留词豁免", tr.untranslated_lead_english(
        utsrc, utdst, keep_terms=["perfect gemstone"]), False)
    check("lead|未记录保留词仍拦", tr.untranslated_lead_english(utsrc, utdst), True)
    check("lead|豁免不吞真英文", tr.untranslated_lead_english(
        utsrc, "{{AITranslation}}\n\nThe stone of ten dawns is a legendary perfect "
        "gemstone that sits upon the roshar continent of legend.\n\n== 注记 ==\n",
        keep_terms=["perfect gemstone"]), True)

    # --- ⑧ 图库文件名不计（2026-10-24 Inkima 实录）---
    gsrc = ("{{Infobox person\n| 名称 = Inkima\n}}\n\n"
            "Inkima is a woman living on the shattered plain. She attended the wine "
            "tasting with Adolin and other lighteyes.\n\n"
            "<gallery caption=\"images of Inkima\">\n"
            "Yakamav and inkima.jpg | Inkima with Yakamav, art by Sheep\n"
            "</gallery>\n\n== Notes ==\n")
    gdst = ("{{AITranslation}}\n{{Infobox person\n| 名称 = Inkima\n}}\n\n"
            "英姬玛是居住在破碎平原的一名女性，曾与阿多林等光眼种一同参加品酒会。{{book ref|sa1|58}}\n\n"
            "<gallery caption=\"英姬玛的相关图片\">\n"
            "雅卡马夫 and inkima.jpg | 英姬玛与雅卡马夫，绘者[[User: Sheep]]\n"
            "</gallery>\n\n== 注记 ==\n")
    check("lead|图库文件名不报", tr.untranslated_lead_english(gsrc, gdst), False)
    check("lead|真英文仍拦(含图库)", tr.untranslated_lead_english(
        gsrc, gdst.replace("英姬玛是居住在破碎平原的一名女性，曾与阿多林等光眼种一同参加品酒会。",
                           "Inkima is a woman living on the plain with the others.")), True)

    # --- ⑨ HTML 编辑批注不计（2026-10-24 Masha-daughter-Shaliv 实录）---
    csrc = ("{{Infobox person\n| 名称 = Masha-daughter-Shaliv\n}}\n\n"
            "Masha wrote the book about the journey and the order of these events "
            "as told by Szeth and Kaladin's testimony.\n\n"
            "<!--Please don't add speculation about what order this is-->\n\n"
            "== History ==\n")
    cdst = ("{{AITranslation}}\n{{Infobox person\n| 名称 = Masha-daughter-Shaliv\n}}\n\n"
            "玛莎依据泽斯与卡拉丁的证词记述了这趟旅程的始末。{{epigraph ref|sa5|133}}"
            "<!--Please don't add speculation about what order this is-->\n\n== 历史 ==\n")
    check("lead|HTML批注不报", tr.untranslated_lead_english(csrc, cdst), False)
    check("lead|真英文仍拦(含批注)", tr.untranslated_lead_english(
        csrc, cdst.replace("玛莎依据泽斯与卡拉丁的证词记述了这趟旅程的始末。",
                           "Masha wrote the book about the journey and the order.")), True)

    # --- ⑩ 章节 3a 认本页 untranslated_terms 记录（2026-10-24 Tyche/Evanotype 实录）---
    pk = vr._page_keep_heads({"untranslated_terms": [
        {"en": "Ylt", "reason": "保留英文"}, {"en": "evanoscope", "reason": "保留英文"},
        {"en": "NoReason"}, {"en": "%%ORIG%%", "reason": "%%ORIGINAL_BLOCK_1%%"}]})
    check("章节|页内记录并集", pk, {"ylt", "evanoscope"})
    base_heads = {t.lower() for t in tr.load_keep_en()}
    check("章节|记录词标题放行", len(vr._heading_problems(
        "== Ylt ==\n正文段落\n", keep_heads=base_heads | pk)), 0)
    check("章节|未记录真标题仍拦", len(vr._heading_problems(
        "== History ==\n正文段落\n", keep_heads=base_heads | pk)), 1)
    check("章节|缺理由记录不豁免", vr._page_keep_heads(
        {"untranslated_terms": [{"en": "Ghost"}]}), set())

    # --- ⑪ ut 剥除词边界/碎片过滤 + 消歧基名（2026-10-24 Shob/Aditil 实录）---
    bsrc = ("{{Infobox person\n| 名称 = Shob\n}}\n\n"
            "Shob was a former soldier and deserter who served under Vstim. He was "
            "known for talking too much about his imagined illnesses.\n\n== Appearance ==\n")
    bdst = ("{{AITranslation}}\n{{Infobox person\n| 名称 = Shob\n}}\n\n"
            "肖布是柔刹的一名前士兵兼逃兵，他因臆想疾病而话很多。{{book ref|sa3|27}}"
            "{{book ref|sa3|40}}\n\n== 外貌 ==\n")
    check("导语|碎片记录不咬模板", tr.untranslated_lead_english(
        bsrc, bdst, keep_terms=["{{b", "ends"]), False)
    check("导语|碎片记录不吞真英文", tr.untranslated_lead_english(
        bsrc, "{{AITranslation}}\n\nShob was a soldier deserter who talked too much "
             "about his imagined illnesses all day long.\n\n== 外貌 ==\n",
        keep_terms=["{{b", "ends"]), True)
    pk2 = vr._page_keep_heads({"untranslated_terms": [
        {"en": "Lodestar_(technology)", "reason": "保留英文"}]})
    check("章节|消歧基名并入", "lodestar" in pk2, True)
    check("章节|消歧标题放行", len(vr._heading_problems(
        "==== Lodestar ====\n正文\n", keep_heads=base_heads | pk2)), 0)
    check("章节|碎片记录不入豁免", vr._page_keep_heads(
        {"untranslated_terms": [{"en": "{{b", "reason": "保留英文"}]}), set())

    # --- ⑫ 正文半译认 ut 记录（2026-10-24 Dakwara's island 实录）---
    hln = ("数千年后的太空时代，玛尔维什人看到洞穴和dakwara，认为这里就是垂贯点的所在地。"
           "不久之后他们试图同时突破dakwara和所谓的死亡之洞，却以失败告终。"
           "dakwara甚至摧毁了一架MW-232，他们随后又用dakwara诱饵设下陷阱，"
           "但dakwara识破了计划，dakwara的巢穴最终也被发现。{{book ref|iote|39}}")
    hbody = "\n\n" + hln + "\n\n== 注记 ==\n"
    keep_dak = {"dakwara", "mw-232"}
    check("半译|ut记录行不报", len(vr._prose_half_problems(hbody, ut_terms=keep_dak)), 0)
    check("半译|无记录仍拦", len(vr._prose_half_problems(hbody)), 1)
    check("半译|记录不吞真英文", len(vr._prose_half_problems(
        "\n\nThey sailed across the western ocean searching for the lost city of "
        "dakwara ruins in the age of the deep and found nothing at all.\n",
        ut_terms=keep_dak)), 1)

    # --- ⑬ 章节标题单复数容差（2026-10-24 Sunheart 实录）---
    sb_body = "\n== Cinderhearts ==\n正文。\n\n== Odiums ==\n正文。\n"
    check("章节|标题复数认记录单数",
          len(vr._heading_problems(sb_body, keep_heads={"cinderheart"})), 1)  # 只剩 Odiums
    check("章节|无记录复数标题仍拦",
          len(vr._heading_problems(sb_body, keep_heads=set())), 2)
    check("章节|控制组未记录不豁免",
          len(vr._heading_problems("\n== Odiums ==\n", keep_heads={"cinderheart"})), 1)

    # --- ⑭ 章节标题消歧后缀/年份尾豁免（2026-10-24 Masaka/Navani 实录）---
    check("章节|消歧后缀认基名记录",
          len(vr._heading_problems("\n=== Nikaro (Painter) ===\n",
                                   keep_heads={"nikaro", "painter"})), 0)
    check("章节|年份尾认月份记录",
          len(vr._heading_problems("\n=== Jeseses 1174 ===\n",
                                   keep_heads={"jeseses"})), 0)
    check("章节|消歧不吞未记录基名",
          len(vr._heading_problems("\n=== Random (Stuff) ===\n",
                                   keep_heads={"nikaro", "painter"})), 1)
    check("章节|年份不吞未记录基名",
          len(vr._heading_problems("\n=== Kaladin 1174 ===\n",
                                   keep_heads={"jeseses"})), 1)
    # --- ⑮ 撇号前置键剥除（2026-10-24 Iriali |'world= 实录）---
    check("字段|撇号前置键当结构位",
          len(vr._field_half_problems("\n|'world=未知\n", [])), 0)
    # 字段半译仅判中英夹杂行（纯英文行按设计跳过）——控制组取真实杂夹形态
    check("字段|撇号键值仍照拦",
          len(vr._field_half_problems("\n|'world=未知 lands beyond here\n", [])), 1)
    check("字段|普通键控制组",
          len(vr._field_half_problems(
              "|next=战争的结束<br />Beginning of the [[终极灭世]]\n", [])), 1)

    total = passed + failed
    print("%d/%d passed" % (passed, total))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
