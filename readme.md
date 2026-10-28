# Coppermind 中文维基搬运项目

目标：从英文 Coppermind 站抓取 wikitext → 翻译成中文 → 通过 MediaWiki API 写回同名的中文站（红铜智库）。

> **给后来的 AI / 开发者**：先读 [docs/architecture.md](docs/architecture.md)——那里记录了
> 译名表体系、keep_en 全自动三层机制（动态识别/中文站映射/静态名单）、引用与模板归一、
> LLM 调用细节、写站与验证手法等**实现思路与设计决策**。本 readme 是操作层面的流水账记录。

## 两个站点

| 站 | 域 | API 端点 | 鉴权 |
|---|---|---|---|
| 英文站 | https://coppermind.net | `https://coppermind.net/w/api.php` | 无需 key（用 cloudscraper 绕 Cloudflare） |
| 中文站 | https://coppermind.huijiwiki.com | `https://coppermind.huijiwiki.com/api.php` | 需 `X-authkey` 头（值在 `.env`） |

站点名：中文站 = 「红铜智库中文维基」，MediaWiki 1.38.4；英文站 = The Coppermind Wiki。
中文站首页 wiki 名：`首页`（mainpage），revid 16588。

## 系列构成（Mistborn）与译名表

迷雾之子（Mistborn）是大系列，可拆成两个小时代。本地 epub 与译名表覆盖面都按此理解（见 `dict/epub/`，均不提交）。

**英文版**
- **时代一（era1）/ 古代三部曲**：单行本 `dict/epub/[Mistborn 1.1..1.3]*.epub`（The Final Empire / The Well of Ascension / The Hero of Ages，分章最清晰，重构首选）；也保留合订 `The_Mistborn_Trilogy*.epub`（仅备份，不再用于分章）。
- **时代 1.5**：中间短篇，`Secret History`（`dict/epub/[Mistborn 1.5] - Secret History*.epub`）。
- **时代二（era2）四部曲**，英文顺序：
  1. The Alloy of Law（`THE_ALLOY_OF_LAW_EPUB.epub`）
  2. Shadows of Self（`SHADOWS_OF_SELF_EPUB.epub`）
  3. The Bands of Mourning（`THE_BANDS_OF_MOURNING_EPUB.epub`）
  4. The Lost Metal（`Mistborn 07 - The Lost Metal*.epub`）

**粉丝戏称 / 编号（wikitext 里两种都可能出现）**
- 全集排列 **mistborn1~7**：如 `mb7` = The Lost Metal。
- 按时代划分 **era2|N**：如 `era2|4` 也指 The Lost Metal。

**中文版（era1 1-3 + era2 1-3，六本都已分章）**
- 时代一：`迷雾之子·01·最后帝国 / 02·升华之井 / 03·永世英雄`（单行本）。**注：升华之井单行本缺第3章（源缺陷），其分章改从 `mistborn_chs_1_6` 合订（书二）提取完整版**。
- 时代二：`迷雾之子外传（全三卷）`（合订，含卷一执法镕金——此卷无中译单行本，只能从合订或 1-6 取）；另有 `外传 卷二 旧影森森 / 卷三 悲悼护腕`（单行本）。
- 早期合订 `mistborn_chs_1_6.epub`（1~6）仍用于升华之井、并保留作备份（The Lost Metal 尚无中译）。

**分章产物（`dict/epub_out/<book>/NNN_<chapter>.html`，中英按章对齐、本地不提交）**

| 书 | EN 目录 | ZH 目录 | 章节数 EN/ZH |
|---|---|---|---|
| 时代一 卷一 | the_final_empire | zh_最后帝国 | 40 / 40 |
| 时代一 卷二 | the_well_of_ascension | zh_升华之井 | 60 / 60 |
| 时代一 卷三 | the_hero_of_ages | zh_永世英雄 | 84 / 84 |
| 时代二 卷一 | the_alloy_of_law | zh_执法镕金 | 26 / 22（EN 多 4 篇报章插页）|
| 时代二 卷二 | shadows_of_self | zh_旧影森森 | 28 / 28 |
| 时代二 卷三 | the_bands_of_mourning | zh_悲悼护腕 | 34 / 34 |
| 时代二 卷四 | the_lost_metal | （尚无中译） | 75 / — |
| 时代 1.5 | secret_history | （尚无中译） | 33 / — |

分章脚本：`scripts/extract_books.py`（一文件一章节的英文书）、`scripts/reconstruct_epub.py`（EN split 流 + 中文合订，含内嵌 `###` 标题拆分）、`scripts/split_epub.py`（**第二批：TOC 驱动**，见下表）；探针/中英同章对照用 `scripts/epub_prep.py`。

**第二批分章（飓光志 / 伊岚翠 / 破战者 / 皇帝魂；`scripts/split_epub.py`，同为 `dict/epub_out/`、本地不提交）**

| 系列·书 | EN 目录 | ZH 目录 | 章节数 EN/ZH |
|---|---|---|---|
| 伊岚翠 正传 | elantris | zh_伊岚翠 | 65 / 65 |
| 伊岚翠 短篇 The Hope of Elantris | the_hope_of_elantris | （中译附在【简体版】皇帝魂 同一 epub 内，未单独提取） | 1 / — |
| 皇帝魂 | the_emperors_soul | zh_皇帝魂 | 17 / 17 |
| 破战者 | warbreaker | zh_破战者 | 60 / 60 |
| 飓光志1 王者之路 | the_way_of_kings | zh_王者之路 | 87 / 87 |
| 飓光志2 光辉真言 | words_of_radiance | zh_光辉真言 | 105 / 105 |
| 飓光志3 渡誓 | oathbringer | zh_渡誓 | 138 / 138 |
| 飓光志4 节奏之战 | rhythm_of_war | （尚无中译） | 131 / — |
| 飓光志5 风历真谛 | wind_and_truth | （尚无中译） | 168 / — |
| 飓光志 短篇 Dawnshard | dawnshard | （尚无中译） | 21 / — |
| 飓光志 短篇 Elsecaller + King Lopen | elsecaller_and_king_lopen | — | 2（一 epub 两短篇）/ — |

处理要点（`scripts/split_epub.py --dry-run` 先看分章方案，`--book <目录名>` 单跑）：
- **TOC 驱动**：以 toc.ncx/nav 为章节边界，白名单认「真章节」标签（第X章 / 第X天 / Chapter N / `1: TITLE` / `I-N` / 序章·序幕·引子·尾声·后记 / Prologue·Epilogue·Postscript…）；分部页（Part / 第X部分 / 插曲 / Interludes 标题页）、地图、彩插不自成一章，并入相邻章；末章按其后的尾注/秘典/Annotations/Ars Arcanum 条目截断，前言版权目录整段丢弃。
- **文件内锚点切分**：如 `渡誓` 一个 `part0008` 内含 1..32 章（`id="hh2-N"`），按锚点切；Oathbringer 里 `#pg_NNNN` 分页书签条目直接过滤。
- **补题**：章题是图片的书（王者之路英文版、风历真谛、节奏之战、渡誓中译）正文无标题 → 自动生成 `<h1 class="chapter-title">`；正文已有标题的不重复补。
- `飓光志3：渡誓` 只有 azw3 → 用 `mobi` 包转成同目录 `【重庆社版】飓光志3：渡誓 (azw3转epub).epub`（不提交）。
- `【简体版】皇帝魂` 同 epub 后半附赠《保卫至福净土》《长子》《第十一种金属》《军团》→ 用 `slice: [0,21]` 只取皇帝魂本体。
- `Warbreaker (Retail)` 是注解版：章首 Annotations 链接行已剔除、书末 Annotations_* 独立条目截断丢弃；第45章中英版都极短（源书如此，已核对中译同章）。
- **破战者 60/60 的来龙去脉**：中译 epub（重庆社·小龙译）打包时把 `第五十八章` 标题漏成 `part0061.xhtml` 里的普通 `<p>`、toc.ncx 也缺该条目，所以看起来只有 59 章；补传的两个源 `破战者 ([美]布兰登·桑德森) (z-lib…).epub/.mobi` 经逐字节校验与原 epub 除 `content.opf` 外完全相同，**换源解决不了**。最终用 `split` 配置按正文该标题切开（`{"label":"第五十七章","at":"第五十八章","into":"第五十八章"}`），恢复 60/60 逐章对齐——中英每章字数比的离散度 sd 从 0.069 降到 0.027。


**译名表**：`dict/mistborn.json` 为**全系列**（era1+era2）译名表；源文件在本地 `dict/raw/`（不提交）。补全方法见 `rules/glossary_alignment.md`（中英章节对齐，以官方中译本），数据模型含 `renderings`（长语块）/`variants`（同名多义）/`zh_variable`（无固定译名）三可选字段（迁移脚本 `scripts/glossary_migrate.py`）。2025-10-16 已落地约 60 条书证译名（人物/地理/地点/定居点/宗教，见 rules doc）。


## 关键结论（截至现在）

- **读英文站**：标准 MW API + cloudscraper（TLS 指纹绕 Cloudflare）已跑通；**写中文站**：`X-authkey` + bot 登录 CSRF + `action=edit` 已跑通（账号 `水蛭一号` 须属 `verified` 群组才有 edit 权——灰机平台级要求）。
- 英文站 Cloudflare 用 cloudscraper 可过；中文站 API 必须带 `X-authkey` 头否则 403。
- 各环节能力/用法见「当前实现状态」；未决项见文末「待办状态总览」。

## 技术方案

- 用 `cloudscraper`（python，已在环境安装）→ 实际走标准 MediaWiki API，无需额外 skill/插件。
- 已装过 `huiji-wiki-bot` skill（`/root/lianz/.agents/skills/huiji-wiki-bot`），是对同一套 API 的封装，可选用（需 env：`HUIJI_API`/`HUIJI_WIKI`、`HUIJI_API_KEY`、可选 `HUIJI_BOT_USER/PASS`）。

## 下一步（待办）

- 读取/转换/翻译/写站/图片/模板**全链路已跑通**（见「当前实现状态」）。
- **未决项集中见文末「待办状态总览」（更新 2026-10-28）。**

### 译名表补全（glossary alignment，方法见 `rules/glossary_alignment.md`）
- ✅ 数据模型已定稿落地：`renderings`（长语块整句替换）+ `variants`（同名多义）+ `zh_variable`（无固定专名），迁移脚本 `scripts/glossary_migrate.py`。
- ✅ 批量补全已铺开：era2 可采证条目完成（961→969）；2026-10-19 译者 6 份 xlsx 并入 + 拆名 → **全表 4140 条，实质为三界宙全系列译名表**（meta.name 已改、按书拆分不做——用户定方向）。不可采证者归 pending 归档（勿重跑）。
- ✅ tlm-only 清单（94 + mixed 58）见 `rules/glossary_alignment.md` §7，待《失落金属》中译出版后补。
- ✅ **2026-10-27 译者三项裁定**（字典 note 已固化，后续 AI 勿回退；完整版见 `rules/glossary_alignment.md` §6）：
  1. `Shu-Dereth/Shu-Korath/Shu-Keseg` = 德雷西/珂拉西/珂西格**道宗**（**shu- = path of**；书内旧译「xxx教宗」作废；人名 `Dereth`、Derethi 派生词、职衔义「教宗」均不动）。
  2. Aon `Dao`（稳定、保障）= **多奥**、`Dio`（坚贞、稳固）= **戴奥**；侍灵 Seon Dao 同改多奥；**人物朵奥拉/戴奥恩未获裁定不动**。
  3. `Lyndel` = **林德尔**、`Ledder` = **莱德尔**（去括号消歧）。
  - 维基侧落地与核验：36 页 102 处词面 + 3 标题移动 + 60 处裸 `[[德雷西]]` 补全 + `Dao/Dio` 两页移动 + `==译名变更==` 段×7；旧词全站 0、裸 `[[德雷西]]` 仅人名 7 处、`[[戴奥]]` 仅 Dio 侧 5 处。备份 `dict/mistborn.json.bak.who3rulings-*`、`dict/zhwiki_*.bak-rulings-*`。

### 译名表定案要点（`dict/mistborn.json`，现 4140 条 = 三界宙全系列）

**长期口径**
- **书证优先级**：官方中译本书证 > 红铜智库维基既有译 > 源表；消歧词并入基础名 key，义项用 `variants`/`note`；名+敬称整句用 `renderings`（如 "Allik Neverfar, Tall One"=高个子亚历克·奈弗法）。
- **台版源清理（2026-10-17）**：台版 xls 与大陆源冲突时**大陆优先**（11 条改译、27 条仅台版删除；src 留 `大陆(名词表(1))#台版清理:<旧值>` 可回滚）。
- **作品内的作品不加书名号**（A 类裁定 2026-10-19；全表清理 45 条，回滚档 `booktitle_strip.json`）。官方中译合并的义项多 key 同 zh + note（Trellism/Trelagism=特雷教）。
- **无官方译名的书名/作品名保留英文**：机制在 `translate.py`（动态 keep_en + zhwiki ref + 静态 `dict/keep_en.json`），见「当前实现状态」。
- 与维基不一致的个别词按用户口径，记录在 meta.notes / 条目 src。

**规模演进**：819（2025-10-16）→ 969（era2 书证轮 2026-10-18）→ 3932（译者 6 份 xlsx 2026-10-19）→ **4140**（拆名 +208）。

**明细/档案**：`rules/glossary_alignment.md` §2-§3（批次摘要与样例）、`state/glossary_caizheng/pending_archive.md`（159 条勿重跑）、`state/glossary_xlsx_import/conflicts.md`、`state/missing_translation_report.md`、`dict/mistborn.json.bak.*`、git log。

## 凭据

API key 在 `.env`（已 gitignore，勿提交）。账号类凭据后续也放 `.env`。

---

# Bot 搬运规则（用户决议 · 2025-10-15 确认）

> 这是 bot 行为的设计契约，实现与后续开发都应遵循。待办/待定项用 ⬜ 标注。

## 1. 搬运范围 = 白名单制
- bot 只能搬运**白名单内**的内容。
- 白名单可细到**单个页面**或**整个 category**。
- 若某 **category 进入白名单** → 允许搬运其**全部子页面**，且**允许递归**（子页面中的 category 继续展开）。

## 2. 黑名单制
- 另设黑名单。
- 进入黑名单的 **category 或页面** → bot **禁用**，**不允许自动处理**。
- 黑名单优先级高于白名单（先判黑再判白，或黑名单一票否决）。

## 3. 版本号去重（增量搬运）
- 每篇**搬运过的文档**，都要记录**英文站的版本号**（revid，待细化实现）。
  - 记得英文站 `Template:Character` 这类模板可能有"en version 标记"功能，可研究复用（⬜ 待讨论如何落地）。
- 若英文站该页**版本号未变化** → **跳过**不处理。
- 实现侧即：本地存 <英文标题 → 英文站 revid>，搬运前先 `query revisions` 比对当前 revid。

## 4. 翻译时的"专有名词"处理 + 结构化返回
- AI 须**识别文中疑似专有名词**的部分。
- **翻译时不要翻译专有名词**（保留原文/按译名表）。
- **返回格式 = 格式化 JSON**，除翻译好的文本外，还必须带一个字段：**「未在译名表中的内容」**（即文中出现但当前译名表没覆盖的疑似专名，供积累）。
- 项目初始：用户会给一份**初始译名表**；后续靠"我们"一起积累扩充。

## 5. 译名表 = 一词多义，AI 自主选择
- 同一词可能有多个可译义（例：`American` 既可能是「美国人」也可能是「美国的」）。
- AI **自主选择**最合适的释义。
- 若 AI 觉得**所有释义都不合适** → 在返回的 JSON 中**描述原因/建议**（不要硬选）。

## 6. 保持 wikitext 格式，逐步积累格式转换工具
- 翻译时**保持 wikitext 的格式**（模板、内链、引用标记等结构保留）。
- 已知两侧模板**不完全一致**（如英文 `{{character}}` ↔ 中文 `{{Infobox character}}`，参数名/字段集都不同）。
- 逐步积累「格式转换的 tool 或 skill」来解决模板差异。已接入 `rules/template_map.json`（大小写不敏感、一行一参数）：
  - ✅ 已接入：`character`（完整）、及「通用映射批」`group`/`location`/`culture`/`item`/`literature`/`lifeform`/`food`/`magic`/`disease`、`business`/`book`（含多源碰撞归一，如 owner&founder→业主）、`noble house`、`shard info`（→Infobox shard）、以及已建中文站模板的 `settlement`/`architecture`/`geography`/`nation`/`vehicle`/`quote`/`image`/`rpg ref`。
  - ✅ `metal` 已接入（commit `518613b`）：中站 `Infobox metal` 已按 EN 语义重写（revid 16719，删 推拉/内外/分类，新增 类型/属性/涉及书目 + type-a/f/h），字段映射见 `rules/template_map.json`。剩余 = 旧金属词条改造 + type 值口径（见文末待办）。
  - 模板差异盘点见 `rules/template_diff_audit.md`；全量存在性探测（101 模板）与缺失项逐条处置见 `rules/template_probe_resolution.md` + `probe_report.json`；字段映射确认见 `rules/infobox_mapping.md`。

## 7. 每篇处理后：校验用到的 template 与 image 是否存在
- bot **每处理完一个文件**，记录该文章**用到的 templates 和 images**。
- **跑完一轮后**，汇总 **distinct** 出的 templates/images，**逐一检查在中文站是否存在**。
- **不存在的 → 输出一份清单给用户**（人工处理）。
- 注意：从 wikitext 静态分析**可能无法完整识别图片**（`File:` 前缀可能藏在某个模板内部/由模板参数拼接），所以**允许 bot 自定义/手动补充**图片识别结果。
- **template 的存在性检查：无需递归查找**（只查模板本身是否存在于中文站，不查其内部引用的其他模板）。
  - 注：images 同理先尽量静态识别 + 允许手动补充。

## 8. 自动搬运 redirects（含英→中）
- 自动搬运**所有 redirects**。
- 包括**从英文到中文的 redirects**（例：能从 `china` 跳转到「瓷器」）。
- 即英文站的 redirect 页也要搬运，并建立对应中文靶向的正确跳转。

## 9. 省 token 方案（可选的效率优化）
- 给 LLM 送译名表时，**不要整表**传。
- 只送**本文可能用到的部分**（按当前文章内容裁剪出相关译名）。
  - 示例：先对原文做候选专名提取，再从大译名表里取这些词的子集送给 LLM。

## 10. 每个词条首部加 `{{en|英文词条名}}`
- 中文站本地模板 `Template:en`，**每个搬运词条翻译时都要做**。
- 用法：正文开头（如 `'''卡拉丁'''{{en|Kaladin}}`），第一参数 = 英文站词条名（如 Kaladin）。
- 第二参数 = 显示的字符串（特殊需要时与英文名不一致才用）；`nolang=true` 供特殊页（英文无歧义但中文需消歧义等）。
- 该模板用 `#var:en` / `#var:en_underscore` 存英文名，**`CmPermission` 与 `ensync` 都依赖它先定义**。

## 11. 每页最顶部加 `{{CmPermission|英文词条名}}`
- 中文站本地模板 `Template:CmPermission`，功能 = 展示"来自 The Coppermind Wiki 授权搬运"的来源说明。
- **每个页面最顶部**都要放。
- 参数 = 英文站那边的词条名；**可省略**（省略时自动读 `{{en}}` 存的英文名），显式传参则用参数。

## 12. 每篇结尾加 `{{ensync|<英文站版本号>}}`
- 中文站本地模板 `Template:ensync`，功能 = 记录"此文档最后一次与英文站同步的版本号"。
- **每篇文档结尾**都要有。
- 参数 = 英文站对应页面的版本号（revid）。
- 依赖 `{{en}}` 已在页面定义英文名（`#varexists:en`）。

## 13. 原文引用内容：不翻译，标记让人类查中译本
- **背景**：这个维基是为一个小说系列服务的。大量英文 wikitext 内容是**对官方中译本的引用**（台词、特定措辞、称号等）。
- **规则**：翻译时，遇到**明显引用了原文的英文内容**，**不要翻译**，保留英文；在返回的 `untranslated_terms` 里**注明"需人类去查中译本对应译文"**，由人工补上中译本原话（避免与中译本对不上）。
- **例证**：
  1. `{{quote}}` 模板的内容（引用的原书台词）→ 不翻译
  2. 明显需查中文版原文的列表（如「给瓦克斯的称号列表」`{{columns}}` 中那些称号）→ 不翻译
- **与译文 JSON 契约联动**：此类条目进入 `untranslated_terms`，`reason` 写「原文引用，需查中译本」。
- **边界**：区分「引用原文」（不译）与「叙述性正文」（照常翻译）。

> 注：`en` / `CmPermission` / `ensync` 三个模板**英文站没有，是中文站独有的**；搬运时要额外加到中文页，对应 - 决议第 10-12 条。`ensync` 参数即决议第 3 条记录的英文站版本号（与 `state/en_index.json` 里的 revid 对应）。

## 14. 爬取限速，避免被封
- 批量爬取分类/大量页面时，**必须控制请求间隔**，避免触发英文站（Coppermind）反爬封禁。
- 默认两次请求间隔 ≥ 1 秒（`delay_seconds`），可配置；连续大量请求时适当加大。
- 脚本内置 `time.sleep(delay)`，并对失败做退避重试。
- 中文站同理，遵循礼貌爬取，不过度并发。

## 15. File 命名空间授权后放行（图片本体可搬运）；图片引用文本照搬
- **原限制（已解除）**：`File:` 命名空间下的词条（图片本体文件）当初不自动搬运，理由是要「逐个获取画师授权」。
- **解除（2025 用户通知）**：**中文站站长已从英文站拿到包括图片的授权**——授权给英文站的画师，自动也授权给我们。因此图片本体文件 + `File:` 页内容均可搬运，不再受逐图授权限制。
- **图片引用文本**（`[[File:xxx.jpg]]` / `[[Image:xxx.jpg]]`，甚至裸写 `xxx.jpg` / 由模板包装的 `[[]]`）始终是 wikitext 文本，照搬不动。
- 落地：见 `scripts/migrate_images.py`（发现 → 下载英文站图片+File 内容 → 上传中文站）。

## 16. Template 命名空间暂时进黑名单
- 由于「英文站 Template 与中文站 Template 不同、如何处理」尚无结论，**`Template:` 命名空间下的模板词条暂时纳入黑名单**，bot 不自动搬运模板。
- 页面内对模板的**引用**（`{{xxx}}`）仍作为文本照常处理（是否同名直用/转换，另由模板映射规则决定，见决议 #4/#6 与 `rules/template_map.json`）。

---

# 技术决策（用户确认 · 2025-10-15）

## A. 开发语言：Python
- **主语言用 Python 3**（`.venv` 管理依赖）。理由：绕英文站人机验证的生态在 Python 最强——`cloudscraper`（已验证可绕过 Cloudflare，TLS 指纹伪装），必要时升级 `curl_cffi` / Playwright。
- 中文站不走人机验证（`X-authkey` 即过），但与英文站用同一套 `requests`/cloudscraper 统一处理。
- ⚠️ 已装的 `huiji-wiki-bot` **skill 是 Node.js 写的**，与 Python 主栈不一致（见下「F」节评估）。

## B. 抓取落盘（快照）+ 后处理解耦
- **先抓取落盘，后处理（翻译/写站）**。抓取是联网重活；翻译/写站可完全离线，各自重试不互阻塞。
- 落盘目录：`en_snapshot/`，每篇一个目录：`<标题>/wikitext.txt` + `<标题>/meta.json`。
- `meta.json` 里记：`标题`、`revid`（英文站版本号）、`timestamp`、`is_redirect`、`target`（redirect 目标）。
- 网络问题/中断可断点续跑：重跑自动跳过已抓页面。

## C. 同名同版本判重 = 扁平索引
- 顶部维护 `state/en_index.json`（扁平，非只靠文件夹判断）：

```json
{
  "Allik Neverfar": {"revid": 12345, "ts":"...", "has_wikitext":true, "is_redirect":false, "target":null},
  "Allik_Neverfar": {"revid": 12344, "ts":"...", "is_redirect":true, "target":"Allik Neverfar"}
}
```

- 判重逻辑：`当前英文站 revid == 索引记录的 revid` → **跳过**（决议第 3 条落地）。
- 优点：快（只对 revid）；redirect 可独立记录；`has_wikitext` 区分"抓过但空"与"没抓"。

## D. 每轮抓取流程
1. 输入标题清单（或 category → 递归展开，遵循白名单/黑名单）。
2. 每标题 `query revisions` 取当前 revid。
3. 与 `en_index.json` 比对：revid 同 → 跳过；否则抓 wikitext 落盘 + 更新索引。
4. 一轮完成后的产物（`en_index.json` + 快照目录）作为下一阶段（翻译/写站）的输入，下一阶段不再联网抓英文。

## E. 项目目录骨架
（已搭建，见下）
```
coppermind/
├── readme.md
├── .env            (gitignore, 凭据)
├── .gitignore
├── en_snapshot/    (英文站快照: <标题>/wikitext.txt + meta.json)
├── state/          (en_index.json 等运行态)
├── dict/           (译名表 glossary, 初始由用户提供)
├── scripts/        (python: fetch / translate / write / verify 等)
└── rules/          (白名单/黑名单/模板映射等配置)
```

## F. 关于 `huiji-wiki-bot`（Node.js skill）—— 是否需要 Python 版？
- **现状**：该 skill 是 Node/ESM，封装中文站 MediaWiki API（`x-authkey` + bot 登录/编辑/上传/同步）。
- **评估**：主栈定为 Python。写站逻辑本就简单（`action=login` → `csrftoken` → `action=edit`），Python 几十行即可复刻，**不必依赖一个 Node 脚本**。
- **结论**：不急着翻译成 Python。先让 Python 主栈自实现读/写 API；Node skill 可留作参考（其 `api.md`/同步策略有借鉴价值）。若日后需要批量 `sync` 目录上传（大图/模板批量），可再考虑移植。
- ✅ 已按此结论执行：`scripts/write.py`（HuijiClient：登录/CSRF/编辑/移动/删除/上传）为现役写站实现，全项目写站均用它；Node skill 仅作参考，无需再对齐。

---

# 当前实现状态

- **`scripts/fetch_en.py`**（Python，已跑通）：抓英文站单页/多页 →
  1. 查当前 revid，与 `state/en_index.json` 比对，**revid 未变则跳过**（决策 C 落地）
  2. 抓 wikitext 落盘 `en_snapshot/<标题>/wikitext.txt` + `meta.json`
  3. 用 **mwparserfromhell** 解析提取 templates / files / categories / wikilinks / redirect 目标（**不靠 AI，确定性解析**）
  4. 识别 redirect 页（`#REDIRECT`）并按自身标题记录 `is_redirect`+`target`
  5. 更新 `state/en_index.json`

用法：
```bash
.venv/bin/python scripts/fetch_en.py <标题...> [--force]
```

- **文件（images）识别说明**（决策第 7 条）：`[[File:...]]` 直接链接 + `{{image}}` 模板首参 + 任意模板中"像文件名的命名参数值"（如 `character|image=`）。已实测 `Allik Neverfar` 抓全 4 张图。静态分析仍可能漏（文件藏更深模板里），届时靠 meta.json 手动补充。
- 依赖：`.venv`（requests / cloudscraper / mwparserfromhell）。已实测。

- **`scripts/convert_templates.py`**（Python，已跑通）：模板转换器 →
  1. 按 `rules/template_map.json` 的 `src_template` 驱动，把匹配的英文 infobox 转换为 `{{Infobox X}}`，字段名按 `field_map` 映射（**大小写不敏感**；一行一参数中文站风格；空值参数自动丢弃）
     - 已支持：`character` + `group`/`location`/`culture`/`item`/`literature`/`lifeform`/`food`/`magic`/`disease`
  2. `{{quote}}` → `{{Quote}}` 重命名
  3. 其余模板（`book ref`/`date`/`image`/`for`/`columns`/`partial`/`Mistborn`…）**中文站同名且参数兼容，直接复用不动**
  3b. **脚注 group 归一（方案 A）**：英文站 `{{ref|group=fn}}` + `<references group=fn>` 中文站不支持（透传会报「引用了未在前文中出现的组 fn」）→ 解析前 `_convert_footnote_groups` 转标准 `<ref>/<references>`（英文脚注 text 作正文交 LLM 翻译；涉及 4/20 页）。
  4. `--wrap`：组装页面级包装 `{{CmPermission|英文名}}`（顶）+ `{{en|英文名}}`（首部占位，翻译阶段移位）+ `{{ensync|revid}}`（结尾，revid 取自快照）——决议 10-12
  5. 报告 mapped/unmapped/collisions/wrapped

用法：
```bash
.venv/bin/python scripts/convert_templates.py --title <标题> [--wrap] [--json]
```

- **验证结论**：`Allik Neverfar` 全页 10 种模板，仅 `character`/`quote` 需转换，其余 8 种（占 54+ 处引用）中文站直接复用。真正需写转换规则的模板很少。

- **`scripts/translate.py`**（Python，已跑通）：翻译管道，英文 converted wikitext → 中文 wikitext → `translation.json` 契约 →
  1. **在内存里用最新转换逻辑重转一次**（不依赖可能过期的 `converted.txt`，避免旧版把 `{{quote}}` 内容清空）
  2. **超长词条分块**：按 `== 章节 ==`/`=== 小节 ===` 边界切块，每块 ≤ `--max-chars`（默认 7000），Infobox+导语固定 chunk0，**绝不在一节/一模板内部硬切**（单节超限独成一块并告警）。已验证 23KB 的 `Spook` 切 5 块、197KB 的 `Kaladin` 切 35 块均无损（章节结构完全保留）
  3. **Infobox「字段 = 值」确定性翻译**（决议#4）：结构化短字段按译名表整值/最长匹配替换，不依赖 LLM 是否记得翻值
  4. **决议#13 确定性保护**：`{{Quote}}`/`{{columns}}`/`{{sidequote}}` 等原文引用块在送 LLM 前用唯一占位符替换，模型原样保留，翻译后填回英文原文，并自动列入 `untranslated_terms`（「需查中译本」）——不让 LLM 选择翻不翻
  4b. **决议#13 原文块书证采证**：按 `{{book ref|书码|章}}` 调 `glossary_assist` 采证 `{{Quote}}`/称号列表的官方中译并替换（无证/意译不硬翻、保英文）；两档：自动（默认，2026-10-21 裁定）/ `--no-auto-quote-cn`（出 `proposed_cn` 供 review）。
  5. **术语裁切**（决议#9）：仅把本文命中的译名子集送 LLM，省 token
  6. 组装页面级包装 `{{CmPermission}}`（顶）+ `{{en}}`（首行，由 LLM 在块0安放）+ `{{ensync}}`（尾，revid 取快照 meta）——决议 10-12
  7. 输出契约 `translation.json`：`{meta, translation, untranslated_terms}`，另落 `translation.txt`

  用法：
  ```bash
  # LLM 配置与 DSH 一致：默认 base_url=https://token.glint-mvt.com/v1、model=deepseek-v4-flash-0731，
  # api key 从环境变量 DEEPGLINT2_API_KEY 读取（可 --api-key / .env 的 LLM_API_KEY 覆盖）
  .venv/bin/python scripts/translate.py --title <标题>                 # 全量翻译
  .venv/bin/python scripts/translate.py --title <标题> --dry-run        # 只预演分块+提示词，不调 LLM
  .venv/bin/python scripts/translate.py --title <标题> --max-chars 6000 # 调小分块预算（更细粒度，块更多）
  .venv/bin/python scripts/translate.py --title <标题> --concurrency 2  # 并发翻译块
  .venv/bin/python scripts/translate.py --title <标题>                       # 默认自动：采证到的 quote/称号直接替换为中文（quote_resolutions 留档）
  .venv/bin/python scripts/translate.py --title <标题> --no-auto-quote-cn    # 半自动：quote 正文不动，proposed_cn 供 review
  .venv/bin/python scripts/translate.py --title <标题> --no-resolve-quotes   # 关闭原文块采证（回到纯英文占位符）
  ```
  依赖：stdlib（`urllib`/`json`/`re`/`dataclasses`）+ `mwparserfromhell`；不需要额外 LLM 客户端库。

- **`scripts/write.py`**（Python，已跑通）：写站管道，把 `translation.json` 写回中文站 →
  - 读 `.env`（`HUIJI_WIKI`/`HUIJI_API_KEY`/`HUIJI_BOT_USER`/`HUIJI_BOT_PASS`）→ `login`（logintoken）→ CSRF → `action=edit`（bot 标记）
  - 权限要求：账号须在中文站 `verified`（认证用户）或 `staff` 群组才有 edit 权，否则 `permissiondenied`
  - `--dry-run`（登录+CSRF，只打印载荷不写）/ `--skip-if-same`（目标页 ensync revid 与 meta.revision_id 相同则跳过，决议#3 增量去重）/ `--target`（指定中文页标题，默认 meta.title_en）
  - 端到端已验：真实写页成功（newrevid 返回）、读回校验内容、skip-if-same 判重生效
  ```bash
  .venv/bin/python scripts/write.py --title <标题>                 # 写回（目标=meta.title_en）
  .venv/bin/python scripts/write.py --title <标题> --dry-run        # 预演
  .venv/bin/python scripts/write.py --title <标题> --skip-if-same   # 增量：已同 revid 则跳过
  ```
  依赖：仅 stdlib（urllib/http.cookiejar/re/json）。

- **`scripts/batch.py`**（Python，已跑通）：批量管道，串联 **fetch→convert+translate→write** →
  - 编排脚本：逐页以子进程调用 `fetch_en.py`/`translate.py`/`write.py`（复用已验证逻辑，不做阶段复制）；支持并发标题
  - `--titles <清单文件>`（每行一标题）/ `--title`（可多次）/ `--all`（跑 en_snapshot 现有全部含 infobox 的标题）
  - `--stage fetch,translate,write`（默认 translate,write；快照缺失才补 fetch）/ `--dry-run` / `--concurrency N`
  - `--write-target-prefix <前缀>`：写站目标页加前缀（如 `BOT测试:`，非破坏性验证）
  - 透传 `--max-chars`/`--skip-if-same`/`--force`/`--summary` 等；末尾打印每页状态汇总（ok/FAIL/skipped/no-input）
  ```bash
  .venv/bin/python scripts/batch.py --titles 清单.txt                       # 正式跑
  .venv/bin/python scripts/batch.py --titles 清单.txt --dry-run             # 全程预演
  .venv/bin/python scripts/batch.py --all --stage translate,write --concurrency 3
  .venv/bin/python scripts/batch.py --title X --write-target-prefix "BOT测试:"  # 写临时页验证
  ```

- **`scripts/glossary_assist.py`**（Python，已跑通）：译名表补全的中英章节对齐定位工具（把「缺失专名→book ref →英书定位→中书采证」人工流程脚本化；可复用于自动翻译 `{{quote}}` 的定位阶段）→
  - 解析词条基础名（去括号消歧：`Chip (constable)`→`Chip`）
  - 出处：页面 `{{book ref|书码|章}}`（map/file ref 标为非正文，见 Finding D/E）；或纯词条模式跨书全书搜（人物全名首现，Finding A）
  - 英书该章定位并高亮上下文；按中英章节对齐映射到中书同章给出「中文对照区」，供人工/LLM 采证官方中译
  - 输出 JSON（`--json`）供后续自动补录/quote 翻译
  ```bash
  .venv/bin/python scripts/glossary_assist.py --page "Irongate River"          # 页面 book ref → 定位
  .venv/bin/python scripts/glossary_assist.py --term "X" --book mb6 --chapter 21 # 指定书章
  .venv/bin/python scripts/glossary_assist.py --term "Mycondwel" --all-hits     # 跨书/跨章搜
  .venv/bin/python scripts/glossary_assist.py --term "X" --json                 # 机器可读
  ```
  依赖：stdlib；读取本地 `dict/epub_out/`（中英电子书已解包，不提交）。

- **`scripts/probe_template.py`**（Python，已跑通）：模板存在性探测工具（决策 #7「校验用到的 template 是否存在」落地）→ 查英文站用到的 `{{模板}}` 在中站（红铜智库）有没有对应 →
  1. 单查：`--template <名>` 查中站 `模板:<首字母大写名>` 是否有同名
  2. 全量核对：`--audit` 扫描 `en_snapshot/` 全部词条，提取所用模板名 → 批量查中站存在性 → 输出三类：**同名存在** / **template_map 已映射** / **缺失（含中站近名候选）**
  3. 结果落 `probe_report.json` + `.txt`（全量 101 个模板 / 11531 处使用，其中同名 50、已映射 22、缺失 29）
  - **存在性判定用 `pageid != null`**（灰机 API 对不存在页返回 `missing:""` 空串，`!missing` 恒真，不能用 missing；也别用 allpages）；大小写不敏感。复用 `write.py` 登录。
  - 缺失项的逐条处置决议见 `rules/template_probe_resolution.md`（A 类接入映射 / B 改挂中站 Navbox / C drop 站务模板 / D 风暴光低频 pending）。
  ```bash
  .venv/bin/python scripts/probe_template.py --template for        # 单查（OK：中站有 模板:For）
  .venv/bin/python scripts/probe_template.py --audit                # 全量核对，写 probe_report.json/.txt
  .venv/bin/python scripts/probe_template.py --audit --summary      # 只打汇总
  ```
  依赖：stdlib + `write.py` 的 HuijiClient（需 `.env` 登录凭据）；不需额外库。

- **`scripts/migrate_images.py`**（Python，已跑通）：**图片迁移**（画师授权后放行，覆盖决议 #15 旧限制）→ 把英文站的**图片本体文件 + File: 页内容**搬到中文站 →
  1. **发现**：扫描英文 wikitext，用**正则**匹配图片引用（`[[File:x.jpg]]` / `[[Image:x.jpg]]` / `[[file:x.jpg|width=...]]` / 模板命名参数值，可选裸写 `x.jpg`），并**合并**各快照 `meta.json["files"]`（fetch_en.py 用 mwparserfromhell 确定性提取 `{{image}}` 首位置参 / 文件感参数，最稳妥）。两来源去重（含下划线≡空格归一）、过滤外链误报。
  2. **下载**：File: 页 wikitext（revisions）+ 图片 bytes（imageinfo）；显式带原始格式 `Accept`（英文站 CDN 内容协商会吐 webp 转码版，与扩展名不符）。
  3. **上传**：`action=upload`（bytes + `text=` 原始 File 内容）本体与 File 页一次到位；幂等以「中文站 File 页已存在」为准（sha1 不可靠：CDN 取回字节对部分文件 ≠ 规范哈希）。
  4. **安全/限速**：裸命名默认仅列清单待人工复核（`--confirm-bare` 才自动，防 `...Laurys L.jpg` 切出 `L.jpg` 类误匹配）；英文站 `--en-delay` 默认 1.0s（决议#14），失败退避重试，永久错误（banned/forbidden）不重试。
  5. **扩展名**：白名单已含 `.svg`（2025-10-17 管理员开放）；`.tif/.tiff` 仍禁。
  6. **大小与覆盖**：上限 10 MB（超限仅 1 张 `Harmony and Discord by Ashley Coad.png` 13.5MB，待站长调 `maxuploadsize`）；`--force` 覆盖需 reupload 权（水蛭一号已入 sysop），覆盖只更新本体 → 脚本自动补写 File 页描述。
  ```bash
  .venv/bin/python scripts/migrate_images.py --scan --all                          # 只发现图片清单（离线）
  .venv/bin/python scripts/migrate_images.py --title "Allik Neverfar" --report     # 看正则明细
  .venv/bin/python scripts/migrate_images.py --title X --dry-run                   # 预演：下载但不上传
  .venv/bin/python scripts/migrate_images.py --title X                             # 正式迁移该标题用到的图
  .venv/bin/python scripts/migrate_images.py --title X --en-delay 1.5              # 调英文站读限速更保守
  .venv/bin/python scripts/migrate_images.py --title X --force                     # 覆盖已存在文件（需 reupload 权限）
  .venv/bin/python scripts/migrate_images.py --all --status-file state/image_migration_status.jsonl  # 整批+进度落盘（后台长任务用）
  .venv/bin/python scripts/migrate_images.py --all                                 # 全快照（301 张）
  ```
  **长任务/断线续看**：用 `--status-file <路径>` 会把每个文件的 `ok/skip/exists/fail` 逐条追加为 JSONL，并写最终 `summary`。会话断开后，后续 AI 只需读该文件即可查看进度/失败清单，无需联网。整批跑用 `state/image_migration_status.jsonl` 作为规范状态文件。
  依赖：cloudscraper + write.py 的 HuijiClient（复用登录/CSRF）；不含额外库。
  实测：全批 301 张跑通（`.svg` 含在内）；进度/失败清单落 `state/image_migration_status.jsonl`（断点续看）。

---

- **`scripts/migrate_templates.py`**（Python，已跑通）：把**非 meta 级模板**迁移（翻译）到中文站（决议 #16 的例外，用户 2025-10-17 决议「只要不是 meta 级 Template 都需要搬」）→ 读内置 `TEMPLATES` 定义，逐一到中文站 `模板:<名>` 登录+CSRF+edit 建/覆盖 →
  1. 已建：`Rosharan date`（+ `Date/sa` redirect）、`Notice`、`Cite note`、`Rpg-canon`、`Small caps`、`CoverToC`、`Sots ref`、`Wp ref`、`Books`、`Tress`（revid 16708–16718）
  2. `Date/sa` 从原生中文模板改为 redirect → `Rosharan date`（保留中文 年/月/周/天 输出，实测 `{{date/sa|1174|2}}`→`1174年第2月`）
  3. `shard info` 属「映射」非「新建」：对应中文站已有 `Infobox shard`，已接入 `template_map.json`
  - meta 级（`update`/`expand`/`demoted`/`nosnippet`/`meta:*`/`edit note`/`user:...`/`FULLPAGENAME` 等）不搬，drop。
  ```bash
  .venv/bin/python scripts/migrate_templates.py --dry-run               # 只打印不提交
  .venv/bin/python scripts/migrate_templates.py --templates Notice,Sots ref
  .venv/bin/python scripts/migrate_templates.py --all                   # 全部
  ```
  依赖：stdlib + `write.py` 的 HuijiClient。

---

# 待办状态总览（更新 2026-10-28）

> 过程性明细已归档（`state/final_report_20261023.md`、git log、`state/` 各账目文件）；本节只留**未决项**与**已完成摘要**。

## ⬜ 未决（按优先级）

1. **批量写站治理**（原 #7/#8）：白名单/黑名单规则落地、redirect 批量搬运、模板与图片校验、图片黑名单；`batch.py` 已能串联 fetch→translate→write，但正式批量（样本推算约 450 页需新建）**前**必须先定范围与人工 review，避免覆盖真实内容。 另并入 #11 余项：5 条无目标红链待建页——dominance 行 EN 值（站内无统御区页）、`[[Painter]]s`、`[[司卡叛乱]]`、`[[塞芮]]`、`[[最后的升华]]`。
2. **`Category:金属` ~20 词条改新字段**（原 #12）：新 `Infobox metal` 已上线并接入映射（commit `518613b`，旧参数已删）→ 逐词条改 `类型/属性/涉及书目` + `type-a/f/h`（取英文站同金属原文），见 `rules/metal_mapping_plan.md` §3。
3. **金属 type 值口径**：现按英文原文直填（原 #12 口径）；`rules/metal_type_translation.md` 中译研究稿（Spiritual/Cognitive/Mental·Enhancement 等）待用户决定是否采用——影响 Harmonium/Trellium 2 篇与上条呈现。
4. **译名表未决批次**：B 类余 29 条 + `Misra` 待裁定；三分类采证 **80 行官方中译待裁定入表**（`state/missing_translation_report.md`）；xlsx 冲突 36 / 勘误 10 / 拆名冲突 12 —— `conflicts.md` 处理空列待填（填后勿重跑 report）；tlm 94 + 批 H pending 159 等中译出版（`pending_archive.md`，勿重跑）。
5. **`三界宙系列` navbox 红链 115 处**（2026-10-27 `action=parse` 复核）：补目标页或裁剪导航条目。
6. **`艾欧符文` 页 39 处 `''Examples:''` 英文残留**：属未翻译导语残留，按决议 #13/#9 处理（可译部分中文化）。
7. **`艾欧符文` 1 处畸形 `{{Quote|Fire, Warmth |Ars Arcanum{{book ref…`**：括号不闭合（pre-existing），需修复。
8. **书封 200→300px 推送**（2026-10-2x 会话）：4 个原生模板 17 个书封进 `图像` 槽并 300px（convert 侧已提交 `ea295ac`），**页面/模板侧推送待用户批准**。
9. **`Template:Character` en-version 标记复用**（决议 #3 注，⬜ 待讨论如何落地）。
10. **低频待定模板**：`dialogue`（对话横幅）建否待定；风暴光低频 pending 见 `rules/template_probe_resolution.md`。

## ✅ 已完成摘要（详见过往小节 / git log / `state/` 档案）

- **管线**（2025-10-16 起）：读取→转换→翻译→写站→批量 全通；写站/移动/删除/上传均经 `scripts/write.py` HuijiClient 实战验证。
- **图片**：301 张迁移跑通（svg 白名单已开、10MB 上限 1 张例外）；**模板**：非 meta 11 个已建、meta 级 drop（568 页节点级验证 0 残留）、存在性探测+处置决议（`rules/template_probe_resolution.md`）、映射表 25 条（含 magic system/metal）。
- **译名表**：4140 条（三界宙全系列）+ pending 归档体系；**2026-10-27 译者三裁定**落地（见「译名表补全」）。
- **`艾欧符文` gallery 图名修复**：53 节对齐 EN，站上 32 + 新搬 21 = **53/53 实存**、渲染全出图、0 文件红链（账目 `state/aon_relink_plan.json`/`aon_existence.json`/`aon_fetch_result.json`）；本页 gallery 衬底已用页级 CSS 去除（`MediaWiki:Common.css`：皮肤 `var(--modal)=#222` 压黑线稿不可读）。
- **`{{glossary ref}}` 本地化**：子页 `glossary`→`名词`、脚注改中文，132 处模板级生效（旧红链 0，`#O` 锚可解析）。
- **图片说明中文化（2026-10-27）**：528 页 /1227 个 `{{Image}}` 英文说明**复扫 0 未译**——三件套：A 提示词规则 2.6（后续翻译页图注必译）+ crew 停用词；B 门禁新增 `3d [图片说明]` 专查（回归 98/98）；C 回填 `scripts/fix_image_captions.py`（**掩码不变量**只动说明 + 写前 parse 冒烟 + 逐条旧→新账本 `state/image_caption_fix_status.jsonl` 可逐条回滚；累计 878 对（875 脚本 +1 手工 +2 例文件名误译回滚 revid 30731/30732）。6 个提取/校验真 bug 的处置详见报告档 §10.5。
- **`模板:Event` 信息框化推送（2026-10-27，用户报障「占领乌有斯麓 event 渲染不对」根修）**：根因 = 站上 模板:Event 仍是 2015 导航条（吞掉全部信息框参数 → 框从不渲染）。推送链 5 件：`模板:Event`（30091→**30752**，EN 对等：SMW `#show` 原名名条 + 照片 300px + 属于/日期/参与者/影响/城市…宇宙 19 行、空行自隐、`demonym` 缺件剔除）+ `模板:Toponym link`（→**30751**，`{{ucfirst}}` 剥壳残余 `}}` 泄漏根修）+ `模板:Toponym`（→**30753**，剥 `</includeonly>` 后尾随 `\n`——它让 `{{toponym}}` 输出带换行进 `[[ ]]` 目标位被链接解析拒绝 → 信息框世界行漏字面 `[[Roshar |Roshar ]]`，place tag 走 `{{tag}}` 路径本就不受影响，改此 1 件零外溢）+ `模板:Peoples`（→**30773**，LBL 补口标签中译）。引擎侧（`state/build_zh_templates.py`，本地档不入库）：LBL 新增 日期/参与者/影响/地点/国家/公国/`Part of the `→属于（全库词频审计仅命中 Event/Peoples/Vehicle，无 `{{{大写参}}}` 破参数风险）+ `demonym` 表达式剔除（实测旧源会把字面 `[[分类:红链模板:Demonym]]` 漏正文）。页面侧：3 个纯导航用点 `{{event|title|prev|next}}`→`{{history}}` 1:1 迁移（复仇誓约/最终升华/陆沙德围城，终审视觉不变）+ **19 页** EN 残留清（`world=[[X]]` 套娃 3、`world=Roshar/Scadrial`→柔刹/司卡德瑞尔 11、city Kholinar/T'Telir/Torio City→塔冠城/特特利尔/Torio城、region Makabak→马卡巴克、participants `[[Nightmare]]s`→[[梦魇]]、占领页 `title=The` 剔除 + `Anti-lights`→[[光能#反光|反光]]）。验收：**60/60** 反链页新框全出、0 demonym 残、0 字面 `[[]]`、0 EN 世界值；date 值与 EN 逐字同（parity 不动）；模板三重护栏与回滚档 `state/rollback_20261027/` 全程在案。同轮应用户指令追加 `模板:History` 导航条改版（29961→**30774**，引擎特例重建，全轮构建 diff 恰 = Event/Peoples/Toponym/History 四件）：默认底宽 40%→**100%** 满宽、prev/this/next 各 **33%**、沿用 2015 旧 模板:event 配色（米底 `#f5f5dc`/棕字 `#8d6b22`/深棕标题条 `#4b3c1c`/中格高亮 `#eae7cb`，不带 mw-collapsible 保持常显），标题行 `{{row/header|cols=3}}` 内联裸 `! colspan=3`（row/header 系站原生保护件、样式随原生 infobox 头，不贴旧条），`{{missing/required}}` 校验与 `事件与时代` 分类原样保留、`|width=`/`|style=` 覆写口保留（42 用点无一带覆写）；42 用点 `action=purge` 清缓存后复扫 **42/42 新版式、0 滞留、0 异常**（**经验：改模板后依赖页 parse 队列分钟级滞后，purge 前 parse 持续给旧表**）。占领页序列导航 next 三链同轮中文化（Cleansing of Shinovar/Second Battle of Narak/Battle of Azimir → 净化深国/第二次纳拉克之战/阿兹米尔之战，与 EN 三链 parity；后两条系该页漏迁、按既定移名表补）。
- **sidequote 全面根修（2026-10-27 用户报障「迦维拉尔·寇林遇刺事件 渲染泄露 padding」深挖）**：三层根因全清——(1) **尾参吃换行**：多行调用 `|left|250px\n}}` 使 `{{{4}}}`=`250px\n` → 样式属性在 `width:` 后断行 → 次行 `; padding: 10px 10px"` 被 MW 解析为定义列表（`<dl><dt>padding</dt>`）外漏——310 用页末参换行全剔；(2) **ZH 移植丢具名双形**：EN Template:Sidequote（revid 119848，fetch_en 留档）代码为 `{{{side|{{{3|}}}|}}}`/`{{{size|{{{4|}}}|}}}`——**EN 规范调用即 `|side=left|size=400px`（EN 文档示例原形）**，ZH 移植只读位置参 `{{{3}}}/{{{4}}}` 致全站具名调用浮宽失效 → 模板加双形嵌套默认（live-only：build 无此件、非保护名单、回滚档在案），三形展开验证 ✓（具名/位置=真浮宽、两参=`float: ;` 与 EN 同构=无默认 parity）；301 页具名形归位位置参 + 5 页逆序/单参变体（`|size=300px|side=right`、`|side=right`、`size=100` 无单位保值）修正；(3) **本轮自造回归修复**：具名原在调用**最前**（EN 具名不占位、正文本为 pos1/2）的 46 页/61 调用被原地换位把正文挤进 pos3（`float: 正文` 断行再漏 padding）——重排为 `正文|署名|side|width`（含 `{{sidequote\n|side=` 模板名后换行位形）。**终验 310 页全量复扫（增强残渣集：可见 padding/float/width/margin 字面、裸参数、style 断行、侧表样式体检）：303/310 全净**，余 7 = 引注族既有伤（已随 #12 修复清零）、8 = 两参 EN-parity（空浮宽，EN 同构）。**方法论教训两条**：① 复验正则必须含 **CSS 字面 token**（原验只查括号类故漏 padding）；② Cirrus `insource:/.../ ` 会**静默返 0 假阴性**（`side=(left|right)\|size=` 与 `[Rr]`/`\}\}` 类查询皆空手而站上实存数百例）——普查查询必须设阳性对照。
- **复核注记**：`#var_final:en` 站点级复核**正常**（`{{en}}` 必定义 + `ensure_en_tag` 兜底；仅「同 parse 无定义」才泄 UNIQ，源码层 UNIQ/QINU 残留=0）——历史「35 UNIQ 页」问题不复现。