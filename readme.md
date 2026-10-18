# Coppermind 中文维基搬运项目

目标：从英文 Coppermind 站抓取 wikitext → 翻译成中文 → 通过 MediaWiki API 写回同名的中文站（红铜智库）。

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

分章脚本：`scripts/extract_books.py`（一文件一章节的英文书）、`scripts/reconstruct_epub.py`（EN split 流 + 中文合订，含内嵌 `###` 标题拆分）；探针/中英同章对照用 `scripts/epub_prep.py`。

**译名表**：`dict/mistborn.json` 为**全系列**（era1+era2）译名表；源文件在本地 `dict/raw/`（不提交）。补全方法见 `rules/glossary_alignment.md`（中英章节对齐，以官方中译本），数据模型含 `renderings`（长语块）/`variants`（同名多义）/`zh_variable`（无固定译名）三可选字段（迁移脚本 `scripts/glossary_migrate.py`）。2025-10-16 已落地约 60 条书证译名（人物/地理/地点/定居点/宗教，见 rules doc）。


## 关键结论（截至现在）

- **读取英文站 wikitext**：已跑通。例：`Allik_Neverfar` 用
  `GET /w/api.php?action=query&prop=revisions&rvprop=content&titles=<标题>` 拿到 7830 字符完整 wikitext（含 `{{character}}`/`{{quote}}`/`{{date}}`/`{{book ref}}`/`[[内链]]`）。
- **读取中文站**：已跑通，需 `X-authkey` 头走 `api.php`（否则 Cloudflare 403）。
- **中文站写入（edit/创建）**：✅ **已打通**（2025-10-16 首次写入 `Allik Neverfar` 成功，newrevid 16679）。
  - 写操作需要**已登录 bot 账号的有效 CSRF token**（`action=edit` 前先 `meta=tokens&type=csrf`）。
  - 关键门槛：即使登录拿到的 CSRF 有效，**账号还必须属于「认证用户」(`verified`) 或「职员」(`staff`) 群组**才拥有 `edit` 权，否则 `action=edit` 会报 `permissiondenied`（仅限认证用户/职员）。`水蛭一号` 认证手机号后进入 `verified` 群组，才获得 `edit` 权。
  - 判断是否认证：登录会话（`userinfo&uiprop=groups`）里 `groups` 含 `verified` 即有编辑权；匿名/未登录 `allusers` 列表不显示该平台级群组。
- Cloudflare：英文站用 cloudscraper（TLS 指纹伪装）可过；中文站**必须**带 `X-authkey`，否则 API 层也被 403 拦。

## 技术方案

- 用 `cloudscraper`（python，已在环境安装）→ 实际走标准 MediaWiki API，无需额外 skill/插件。
- 已装过 `huiji-wiki-bot` skill（`/root/lianz/.agents/skills/huiji-wiki-bot`），是对同一套 API 的封装，可选用（需 env：`HUIJI_API`/`HUIJI_WIKI`、`HUIJI_API_KEY`、可选 `HUIJI_BOT_USER/PASS`）。

## 下一步（待办）

1. ✅ 英→中读取链路已通
2. ✅ 中文站 bot 账号（水蛭一号，`verified`）→ 登录 → 有效 CSRF token → `action=edit` 写入（2025-10-16 已跑通）
3. ✅ 翻译 `Allik_Neverfar` 词条并贴回中文站（测试写入成功，页面 [Allik Neverfar](https://coppermind.huijiwiki.com/wiki/Allik_Neverfar)）

### 译名表补全（glossary alignment，方法见 `rules/glossary_alignment.md`）
待办按优先级：
- ✅ 数据模型扩展已定稿并落地：`renderings`（长语块替换，如 "Allik Neverfar, Tall One"↔"高个子亚历克·奈弗法"，见 `Allik`）+ `variants`（同名多义义项，如 Demoux=人物/城市）+ `zh_variable`（无固定专名，如 The Village），迁移脚本 `scripts/glossary_migrate.py`（已跑）。
- ✅ 批量补全：人物 → 地理/地点/建筑 → **企业/团体/事件/文化/家族/物品/刊物/交通工具/疾病** → 歧义词条 已铺开并完成 E2 可采证条目（本论 769→819 条，全表共 819 条，232 条带书证 note，见 `rules/glossary_alignment.md` §2 批 G）。不可采证的（仅 tlm 无中译、报章插页被省略、正文意译未成专名、正文无书证）已归入 pending。
- ✅ 整理「仅出现于失落金属(tlm)」词条清单（94 条 + mixed 58，见 `rules/glossary_alignment.md` §7），待 tlm 中译出版后补。
- ✅ 补全后回填 `rules/*.md` 并提交译名表（本轮已提交）。

### 已落地书证译名（`dict/mistborn.json`，2025-10-16，全表 819 条，含 232 条带书证 note）
- Allik Neverfar = 亚历克·奈弗法；Allik = 亚历克（别名 阿里克）
- Red（依蓝德运河船夫）= 雷德
- Irongate River = 铁门河
- Carlo’s Bend = 卡罗湾（已有，书证核验）
- Trell（神）= 特雷；Trellism / Trelagism（宗教，官方中译合并）= 特雷教；Nelazan = 奈拉禅
- Spook=鬼影、Waxillium Ladrian=瓦克斯利姆·拉德利安、Steris Harms=史特芮丝·哈姆斯、Telsin Ladrian=苔尔辛、Marasi Colms=玛拉茜·科尔姆斯、Elendel=依蓝戴（书证146处一致，修正源表伊兰黛尔市） 等，完整批记录见 `rules/glossary_alignment.md` §2。
- ⚠️ 2026-10-17 台版清理：源文件 `dict/raw/迷雾之子第二纪元名词表.xls` 为**台版**译名（如 斯卡德利亚/寰宇/和谐之主），与大陆源 `《迷雾之子》名词表(1).xls`（司卡德瑞尔/三界宙/和谐）冲突。已比对二者（`.\`/`．`全角点→间隔号`·`判定为同词非差异）：**11 条改为大陆译名**（Scadrial→司卡德瑞尔、Harmony→和谐、Bleeder→放血者、Basin→盆地区、Jak→杰克、Saze→萨兹、Octant→8分区、Rust and Ruin→铁锈灭绝、Hammondar Bay→哈姆德海湾、God Beyond→彼界之神、Allriandre→亚莉安德；各条 src 记 `大陆(名词表(1))#台版清理:<旧台版>`），**27 条**仅台版源、无大陆对应 → 删除。全表 821→794 条。备份 `dict/mistborn.json.bak.twpurge-*`。
- 🔧 2026-10-17 Ghostblood 词条修复：`Ghostbloods`（组织=鬼血会）此前缺词条，LLM 把 `Mistborn (series)` 页第三纪元三部曲名 `Mistborn: Ghostbloods` 误译为「血影」。已新增 `Ghostbloods`→`鬼血会`；并按用户确认把单数 `Ghostblood` 也统一为`鬼血会`（二者同译）。`extract_en_terms`+切片已验证能给出 gloss。全表 795 条。
- ✅ 2026-10-17 译名表 vs 红铜智库维基核对收尾（`state/glossary_wiki_audit.txt` 54 条不一致逐条核对完毕，文件已删）：
  - 以维基为准改译名表：**Krent 科兰特→克伦特**（维基既有页，ch9 拉德利安家车夫）
  - 维基 move 到译名表名：**Mi'chelle Yomen 拆两条**——`Mi'chelle Yomen`=米歇尔·尤门（旧姓欧斯特林，婚后夫姓）、新增 `Mi'chelle Ostlin`=米歇尔·欧斯特林（旧姓），维基核心正文移动至 `米歇尔·尤门`，其余 redirect；**Yomen-Ostlin wedding dinner**=尤门-欧斯特林的婚礼晚宴（欧斯特林·斯），维基旧页 `尤门·/尤门- 尤门-欧思特林…` redirect 至连字符版正文
  - 其余不一致均在更早批次已解决或为「用户口径保留差异」（Origin/Pinnacle/Shadesmar/Valette Renoux/Wax/Mistborn 等）。全表 796 条。
- ✅ 2026-10-18 爬取 `Category:Mistborn` 全量（递归展开 **1116 页**；其中 Era_2 等 564 页已抓/跳过，本次新抓 **550 页**，0 错误）。复用 `fetch_en.fetch_one` + cloudscraper（与 Era_2 同法），慢速限速 `2.0s/页`（决议#14，防反爬，全程未触发封禁）。脚本 `scripts/fetch_mistborn_crawl.py`（按 `state/mistborn_need_fetch.json` 清单断点续跑、每 25 页存索引）；范围清单 `state/mistborn_category_list.json`。验证：1116/1116 全快照、0 缺失。
- ✅ 2026-10-18 译名表补全轮·caizheng 采证并入（`state/glossary_caizheng/` 工作目录）：对 `state/mistborn_glossary_terms.json` 的 **327 条**候选词条按批次书证采证（批次文件 `batch_*.json`/`miss_*.json` 逐条给出 zh+书证+置信），汇总 `consolidated.json`：**168 条 ok**（含人物/地理/地点/机构/物品/金属/祝福等），已并入 `dict/mistborn.json`（全表 796→**961** 条；脚本 `scripts/glossary_caizheng_merge.py`）；**159 条不可采证**（仅 tlm/密史无中译、维基子页/元信息、正文无书证、意译未成专名）已归档 `state/glossary_caizheng/pending_archive.md`（勿重跑）。并入门类一致：Venture 家族=泛图尔、Tekiel=太齐尔、Cett=塞特、Kelsier=卡西尔、硝镪病等。备份 `dict/mistborn.json.bak.caizheng-*`。
- ✅ 2026-10-18 **20 词条翻译 review 轮·方案1+2 落地**（用户定按 1+2 继续，不写站）：review 发现 Wayne/Elendel 两页缺 `{{en}}`、extract_en_terms 屈折/大小写误判致使大量「伪未收录」+英文残留。
  - **方案1**：给 `translate.py` 加 `ensure_en_tag` 确定性兜底（块0 LLM 漏安放 `{{en|title}}` 时，在首个 `'''加粗标题'''` 后自动补上；无标题页紧跟 `{{CmPermission}}` 后补）——决议#10 落地更稳，`CmPermission`/`ensync` 依赖的 `#var:en` 必被定义。已单测 + 小页实测。
  - **方案2a**：`extract_en_terms` 增捕**小写词**（kandra/metalmind/harmonium 等，原只捕大写首字母词故漏配）；`slice_glossary` 改用归一化索引（`_norm_glossary_key`：去冠词/去属格/去复数/小写），使 `Set`→`The Set`、`metalminds`→`metalmind`、`kandra's`→`Kandra` 命中规范词条；对**全小写正文词**套 `GENERIC_EN_STOPLIST` 防通用英文误翻（如小写 `red`→专名 雷德）。Effect：Elendel 命中 110→168 条，英文残留/伪未收录显著下降。
  - **方案2b**：`glossary_assist` 采证高价值真缺口并入 `dict/mistborn.json`（961→**969** 条）：`Sovereign=君主`（悲悼护腕 mb6 ch21-23，非「主权」）、`Ashmount=灰山`（永世英雄 mb3 ch34）、`Edwarn=埃德温`（全名 埃德温·拉德利安 已有）、`Mr. Suit/西装先生`、`Winsting=温斯汀`、`Breeze=微风`、`Allrianne=奥瑞安妮`（全名 奥瑞安妮·拉德利安）。无书证术语（Steinel/Mycondwel/Icy Ben Oldson/West's Haven/Channeral Range/Faleast Range/Sycamore Street Gang/Getruda/Dumad/Clubs）全书 0 命中 → 追加归档 `pending_archive.md` 勿强译。
  - **重跑验证**（`scripts/batch.py --stage translate` 全 20 页）：✅ 全 20 页均已含 `{{en|...}}`（Wayne/Elendel 补齐）；✅ Set/kandra/metalminds/skaa/harmonium/Edwarn/Sovereign/Breeze/Winsting/Ashmount 等不再「伪未收录」，正文统一 组织/坎得拉/金属意识/...；✅ stoplist 防误翻生效（小写 red/well/dug/rioting 等不再误命中专名；Set→组织 与 Cett→塞特 不撞）。剩余可接受点：MeLaan infobox `| 种族 = kandra`（未走确定性替换）、Elendel 正文「Allrianne 女士」（LLM 未用 奥瑞安妮，改自译 阿莉安）；untranslated_terms 数量因 LLM 详略不同有波动（Waxillium 本次多报到普通词，正文均已译对，属上报口径差异非质量回归）。
  - 备份 `dict/mistborn.json.bak.review-*`。
- ✅ 2026-10-18 **残点2 + Mistborn(series) 三项翻译修复**：
  - **残点2收尾**（重跑 Wayne/MeLaan/Elendel 验证）：`_sub_glossary_in_string` 加**归一化整值兜底**（infobox `| 种族 = kandra`→坎得拉、`Set`→组织、`metalminds`→金属意识，全小写套 stoplist 防误翻）；`extract_en_terms` 增捕**大写短语内单个大写词**（"Lady Allrianne Ladrian"分离出 Allrianne、"Mr. Suit"分离出 Suit）；SYSTEM_PROMPT rule 2 强化「切片给出 zh 必须原样使用、禁自造音译」。`dict/mistborn.json` 新增 `Suit=西装先生`（Mr. Suit 简写变体）969→**970**。验证：Mr. Suit→西装先生、Allrianne→奥瑞安妮、`| 种族 = 坎得拉`；`review_verify` 伪未收录清零。
  - **① `{{for}}` 模板参数翻译**：新增 `translate_for_template`（convert 后确定性替换参数 1/2/3/pre 的可译专名）+ SYSTEM_PROMPT rule 2.2（{{for}} 的 pre=/目标/描述属需翻译导语文案）。`{{for|Allomancy|the kind of Allomancer|pre=This article is about [[Brandon Sanderson]]'s series}}` → `{{for|镕金术|the kind of 熔金术师|pre=本文介绍的是[[布兰登·桑德森]]的系列作品}}`（参数1/pre 全译；参数2 虚词结构 LLM 偶留英文为已知小瑕疵）。
  - **② `<references>/<ref>` 脚注翻译**：SYSTEM_PROMPT rule 2.3（脚注说明属需翻译正文，标签/name/自闭合保留）。实测两块 7 条脚注全部译中。
  - **③ 子页链接 [[X/Statistical analysis|数字]]→[[永世英雄/数据分析|数字]]**：新增 `translate_wikilink_targets`（父+后缀均有译名才重写、display 保留）+ `load_merged_glossary`（主表 mistborn.json + 辅表 common.json 合并，次表补主表缺失）。新增 **`dict/common.json`**（跨站通用词：`Statistical analysis=数据分析`，**不塞入 mistborn.json**）。
  - **重跑验证**：`Mistborn (series)` 三项全达标，写回 `bot测试:Mistborn (series)`（newrevid 17178）；全 8 处 `/Statistical analysis` 统一译《xxx/数据分析》。提交 `ccff85c`。
  - **补强（2026-10-18 晚）**：SYSTEM_PROMPT rule 2.2 强化「描述/`pre=` 参数须**整句**译成中文，不得残留整段英文虚词」。重跑并重写（newrevid 17179）：`{{for|镕金术|熔金术师这一类|pre=本文介绍的是[[布兰登·桑德森]]的系列作品}}`——参数 2 由 `the kind of 熔金术师` 整句化 `熔金术师这一类`。提交见 `git log`。

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
  - ⬜ 待接入/待决策：`metal`（中文 `Infobox metal` 是「镕金金属技艺」语义，EN `{{metal}}` 是「神金/金属学」语义，字段不对应，**需单独定承载方式**，见 `rules/template_probe_resolution.md` §三 A）。
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
- ⬜ 待定：Python 侧写站模块实现后，与 Node skill 的行为对齐（CSRF 会话、重试、`sync` 语义）。

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
  2. `{{quote}}` → `{{Quote}}`
  3. 其余模板（`book ref`/`date`/`image`/`for`/`columns`/`partial`/`Mistborn`…）**中文站同名且参数兼容，直接复用不动**
  3b. **脚注 group 归一（方案 A，2026-10-17）**：英文站 `{{ref|...|group=fn}}` + `<references group=fn>` 是英文站 `Template:Ref` 扩展脚注体系；中文站 `Template:Ref` 是书目引用模板、**不支持 group** → 原样透传会让 `<references group=fn>` 找不到前置 group 标记而报「引用了未在前文中出现的组 fn」。`convert_templates.py` 在解析前用 `_convert_footnote_groups` 转成中文站可渲染的标准 `<ref>/<references>`：正文内联 `{{ref|group=fn|text=X}}`→`<ref>X</ref>`、内联具名→`<ref name="N"/>`、定义块 `{{ref|group=fn|text=X|name=N}}`→`<ref name="N">X</ref>`（`<references group=fn>`→`<references>`）、自闭合→`<references/>`；英文脚注 text 成为普通正文由 LLM 翻译。涉及 Wayne/Waxillium/Elendel Basin/Mistborn (series) 等 4/20 页（下轮重跑生效）。
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
  4b. **决议#13 增强·原文块书证采证**：按 `{{book ref|书码|章}}` 调 `glossary_assist` 到中译本书证采证这些原文块的中文——
      - **台词 quote**：用书证采证官方中译；不逐字匹配原书（意译）或无 book ref 的 quote **保留英文**（诚实不硬翻）
      - **称号/称呼列表 columns**（如 `Great Metallic One`）：逐行采证替换为中文，非逐字的保留英文
      - 两档：**半自动（默认）**——产出 `quote_resolutions`（`proposed_cn` 供 review）不替换；**全自动 `--auto-quote-cn`**——采证到的直接替换为中文（英文不留）
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
  .venv/bin/python scripts/translate.py --title <标题>                       # 默认半自动：原文块书证采证产出 quote_resolutions（review，不替换）
  .venv/bin/python scripts/translate.py --title <标题> --auto-quote-cn       # 全自动：采证到的 quote/称号直接替换为中文
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
  2. **下载**：英文站 `revisions` 取 **File: 页 wikitext（内容，含 {{art}} 授权/来源模板）**；`imageinfo` 取图片 bytes。**关键坑**：英文站 CDN 做内容协商，cloudscraper 的 Chrome Accept 会拿到 webp 转码版而非原始格式——脚本显式带原始格式 `Accept` 取回与扩展名一致的原始字节。
  3. **上传**：中文站 `action=upload`（bytes + `text=原始 File 内容`），图片本体与 File: 页**一次到位**。**幂等以「中文站 File 页已存在」为准**（不用 sha1 判等——实测英文站内容协商取回的字节对部分文件 ≠ 规范哈希；本脚本是唯一上传者，存在即视为已迁移）。`--force` 才对已存在文件尝试覆盖。
  4. **安全/限速**：`--include-bare` 的裸命名仅「列出待人工复核」（已实证：文件名含空格会把 `...Laurys L.jpg` 切出 `L.jpg`，且英文站恰有无关 `File:L.jpg`），需 `--confirm-bare` 才自动迁移。英文站读请求统一经 `RateLimiter` 限速 `--en-delay`（默认 1.0s，防反爬，决议 #14）；中文站写/下载间 `--delay`；失败退避重试（最多 5 次）——永久错误（`fileexists-forbidden`/`filetype-banned` 等）不重试。
  5. **中文站扩展名白名单**：原来灰机只允许 `png/jpg/jpeg/gif/webp`，`.svg` 报 `filetype-banned`；**2025-10-17 用户联系管理员开放了 `.svg` 上传**，`ZH_ALLOWED_EXT` 已加入 `.svg`（实测 3 个 svg 上传成功）。仍被拒的有 `.tif/.tiff`（需要可再找管理员开）。
  6. **上传大小上限 10 MB**：中文站 `maxuploadsize=10485760`（10 MB），服务器对超限请求回 `HTTP 413`。全 301 张实测仅 **2 张接近/超过**：`Dalinar Ambush LGD.png`（EN 规范 12MB，但 CDN 实取 9MB，未超限，已传成功）× `Harmony and Discord by Ashley Coad.png`（实取 13.5MB，超限，**无法经此路径上传**，需站长提高 `maxuploadsize` 或人工处理）。
  6. **覆盖已存在文件（`--force`）**：MediaWiki 对无 `reupload` 权限的账号，即使 `ignorewarnings=1` 也报 `fileexists-forbidden`（权限门）。`水蛭一号` 现已加入 `sysop` 组（具备 `reupload`/`delete`），`--force` 可覆盖。**注意**：`action=upload` 覆盖已存在 File 页时**只更新图片本体、不更新 File 页描述**——脚本会在成功覆盖后自动 `edit` 补写 File: 内容为英文站原样。`fileexists-no-change`（内容已一致）视为 `ok` 而非失败。
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
  实测：**真实上传已验证**（2025-10-17）：`Allik Neverfar` 4 张 + `Dao/Ghostbloods/Harmonium/Set` 的 `webp/jpg/jpeg` + `.svg`（`Aon Dao`/`Ettmetal (Alloy of Law)`/`Ghostblood`）+ `New Ascendancy` 2 张共 **13 张均落到中文站 `File:` 命名空间成功**，File 页含 `{{art}}` 授权/来源，读回 sha1/size 一致；重跑幂等 skip。**`.svg` 已由管理员开放**上传。**`Zinc (Alloy of Law).svg` 覆盖完成**（`水蛭一号` 入 `sysop` 组后 `--force` 覆盖为英文版，图片本体 + File 页 `{{art}}` 内容均已修正）。全部 13 张 + Zinc 共 14 张文件读回均 `art=True`、`missing=False`。

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

# 待办状态总览（更新）

1. ✅ 英→中读取链路已通
2. ✅ 中文站 bot 账号（水蛭一号，`verified` 认证用户）→ 登录 → 有效 CSRF token → `action=edit` 写入（2025-10-16 首次写入 `Allik Neverfar` 成功）
3. ✅ 译名表 `dict/mistborn.json`（819→821 条，书证采证中）；✅ 补全工具 `glossary_assist.py` 已可用（中英章节对齐定位，见 `rules/glossary_alignment.md` §1.1/1.2）→ 缺失专名可据此采证补入
4. ✅ 版本号记录方案已定（`state/en_index.json` + 快照）→ ✅ 已实现（`fetch_en.py`）
5. ✅ 开发语言已定 Python；✅ 快照/索引方案已定 → ✅ 抓取落盘已实现（`fetch_en.py`）
6. ✅ 样板词条 `Allik_Neverfar`：转换 + 译名表 + 映射表 + 翻译（`translate.py`）均已跑通并写入（2025-10-16 首次写入；2025-10-17 起 translate.py 自动产出，附 CmPermission/en/ensync 包装）
7. ⬜ 落地并实现：白名单/黑名单/redirect 批量/模板图片校验 等规则（Template 命名空间暂不搬运；图片引用文本照搬）。✅ 图片本体迁移已随授权放行（`scripts/migrate_images.py`，见当前实现状态）；正式批量前仍需定画像/范围治理
8. ⬜ 批量写站前的**治理/人工 review**：图片黑名单、模板图片校验、redirect 搬运（`batch.py` 已能批量串联 fetch→translate→write，但正式批量跑某个分类/清单前需先定上述规则与范围，避免覆盖真实内容）
9. ⬜ **译名表补全铺开**：用 `glossary_assist.py` 对缺失专名批量采证（优先可书证的正文词：地理/地点/宗教/货币等）；地图-only 或仅 tlm 无中译的词条标 pending 待补。本轮已示范 `Survivor→幸存者`、`Survivorism→幸存者教义`（悲悼护腕 mb6 ch12）
10. ✅ **模板存在性探测 + 中站对应决议**：`scripts/probe_template.py --audit` 全量核对 en_snapshot 全部模板（101 个 / 11531 处，同名 50、已映射 22、缺失 29），缺失项逐条给出处置，见 `rules/template_probe_resolution.md` + `probe_report.json`；并按决议**接入 `noble house→Infobox noble house`、`shard info→Infobox shard` 映射**（实测 `House Demoux`/`Harmony` 正常转换）。`metal` 因中英语义不对应，标待决策不自动映射。
11. ✅ **非 meta 模板已迁移到中文站**（决议 #16 例外，用户定「只要不是 meta 级 Template 都搬」）：`scripts/migrate_templates.py --all` 建了 11 个模板（Rosharan date/Date/sa/Notice/Cite note/Rpg-canon/Small caps/CoverToC/Sots ref/Wp ref/Books/Tress，revid 16708–16718），`Date/sa`→redirect→`Rosharan date` 并保留中文 年/月/周/天 输出。meta 级（update/expand/demoted/nosnippet/meta:* 等）不搬、drop。
12. ⬜ **更新 `Category:金属` 全部词条到新 Infobox metal**：用户 2025-10-17 决议 `metal`↔中文 `Infobox metal` 对应，模板已改（revid 16719）——删 `推拉/内外/分类`、新增 `类型/属性/涉及书目` 与 `type-a/type-f/type-h` 表位（照英文原文）；已接入 `template_map.json` 的 `metal` 映射。但因删除旧字段，**现有约 20 个金属词条（白镴/锡/电金/铁/天金/钢…）的 infobox 需逐个改为新字段**（type-a/f/h 取英文站同金属词条原文），见 `rules/metal_mapping_plan.md`。
13. ✅ **meta/维护模板已在 convert 中 drop**（2025-10-17 批量扫描 568 词条发现 → 已修复）：用户决议 `complete`/`partial`/`stub` **保留**（中文站同名 Complete/Partial/Stub 语义等价，473/74/2 处原样保留）；`update`/`expand`/`meta:*/demoted/nosnippet/dialogue/edit note/user:*` **drop**（纯英文站编辑/维护标记，~79 节点，全量节点级验证为 0 残留）。`nosnippet` 为内容包装、drop 时 **unwrap 保留内文**。`scripts/convert_templates.py` 新增递归 `_apply_drop`（可处理嵌套在 infobox 参数值/Tag 内容里的模板），`translate.py` 在内存重转时自动继承。
