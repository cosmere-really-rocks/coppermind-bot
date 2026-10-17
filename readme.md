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

## 15. File 命名空间不得自动搬运；图片引用文本可搬运（画师授权）
- **`File:` 命名空间下的词条（图片本体文件）不能自动搬运**——即 bot 不自动上传图片文件。理由：图片需**逐个获取画师授权**，未经授权不得搬运。
- **注意区分「图片本体」与「图片引用文本」**：`File:` 命名空间词条（图片文件）禁止自动搬运；但**作为文本的引用** `[[File:xxx.jpg]]` / `[[Image:xxx.jpg]]`（甚至直接裸写 `xxx.jpg`、由 Template 内部包装成 `[[]]` 的形式）**可以搬运**——这些只是 wikitext 文本引用，不涉及上传图片文件。
- 未来做法：建立**画师白名单**——只有白名单内画师的作品才允许上传对应图片文件。
- 落地：**上传流程**默认跳过所有图片文件（仅在画师白名单确认后放行）；**文本中的图片引用保持不变、照搬**。

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
7. ⬜ 落地并实现：白名单/黑名单/redirect 批量/模板图片校验 等规则（黑名单含 File 命名空间不自动上传图片、Template 命名空间暂不搬运；图片引用文本照搬）
8. ⬜ 批量写站前的**治理/人工 review**：图片黑名单、模板图片校验、redirect 搬运（`batch.py` 已能批量串联 fetch→translate→write，但正式批量跑某个分类/清单前需先定上述规则与范围，避免覆盖真实内容）
9. ⬜ **译名表补全铺开**：用 `glossary_assist.py` 对缺失专名批量采证（优先可书证的正文词：地理/地点/宗教/货币等）；地图-only 或仅 tlm 无中译的词条标 pending 待补。本轮已示范 `Survivor→幸存者`、`Survivorism→幸存者教义`（悲悼护腕 mb6 ch12）
10. ✅ **模板存在性探测 + 中站对应决议**：`scripts/probe_template.py --audit` 全量核对 en_snapshot 全部模板（101 个 / 11531 处，同名 50、已映射 22、缺失 29），缺失项逐条给出处置，见 `rules/template_probe_resolution.md` + `probe_report.json`；并按决议**接入 `noble house→Infobox noble house`、`shard info→Infobox shard` 映射**（实测 `House Demoux`/`Harmony` 正常转换）。`metal` 因中英语义不对应，标待决策不自动映射。
11. ✅ **非 meta 模板已迁移到中文站**（决议 #16 例外，用户定「只要不是 meta 级 Template 都搬」）：`scripts/migrate_templates.py --all` 建了 11 个模板（Rosharan date/Date/sa/Notice/Cite note/Rpg-canon/Small caps/CoverToC/Sots ref/Wp ref/Books/Tress，revid 16708–16718），`Date/sa`→redirect→`Rosharan date` 并保留中文 年/月/周/天 输出。meta 级（update/expand/demoted/nosnippet/meta:* 等）不搬、drop。
12. ⬜ **更新 `Category:金属` 全部词条到新 Infobox metal**：用户 2025-10-17 决议 `metal`↔中文 `Infobox metal` 对应，模板已改（revid 16719）——删 `推拉/内外/分类`、新增 `类型/属性/涉及书目` 与 `type-a/type-f/type-h` 表位（照英文原文）；已接入 `template_map.json` 的 `metal` 映射。但因删除旧字段，**现有约 20 个金属词条（白镴/锡/电金/铁/天金/钢…）的 infobox 需逐个改为新字段**（type-a/f/h 取英文站同金属词条原文），见 `rules/metal_mapping_plan.md`。
13. ⬜ **meta/维护模板在 convert/translate 中 drop**（2025-10-17 批量扫描 568 词条发现的真实卡点）：`{{complete}}`×473、`{{partial}}`×74、`{{update}}`×34、`{{expand}}`×27、`{{meta/*}}`×12、`{{demoted}}`×3、`{{stub}}`×2、`{{nosnippet}}`×2、`{{dialogue}}`×1、`{{edit note}}`×1、`{{user:*}}`×1 共 **805 处**当前**原样穿透**进入 converted→translated 输出（实测 `Abrem` 保留 `{{complete}}`、`Allik Neverfar` 保留 `{{partial}}`）。按 `rules/template_probe_resolution.md` §C' 这些全是英文站维护标记、应 drop 不搬（中站同名 Complete/Partial/Stub 语义不同，不能等价复用）。**需在 `convert_templates.py`/`translate.py` 加全局 meta drop 清单**。
