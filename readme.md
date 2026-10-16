# Coppermind 中文维基搬运项目

目标：从英文 Coppermind 站抓取 wikitext → 翻译成中文 → 通过 MediaWiki API 写回同名的中文站（红铜智库）。

## 两个站点

| 站 | 域 | API 端点 | 鉴权 |
|---|---|---|---|
| 英文站 | https://coppermind.net | `https://coppermind.net/w/api.php` | 无需 key（用 cloudscraper 绕 Cloudflare） |
| 中文站 | https://coppermind.huijiwiki.com | `https://coppermind.huijiwiki.com/api.php` | 需 `X-authkey` 头（值在 `.env`） |

站点名：中文站 = 「红铜智库中文维基」，MediaWiki 1.38.4；英文站 = The Coppermind Wiki。
中文站首页 wiki 名：`首页`（mainpage），revid 16588。

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
- 逐步积累「格式转换的 tool 或 skill」来解决模板差异（⬜ 待积累）。

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

## 15. 图片一律进黑名单，不搬运（画师授权）
- **所有图片默认不允许搬运**（进入黑名单）。
- 理由：图片需**逐个获取画师授权**，未经授权不得搬运。
- 未来做法：建立**画师白名单**——只有白名单内画师的作品才允许搬运。
- 落地：图片检测/上传流程默认跳过所有图片；仅在画师白名单确认后才放行对应图片。

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
  1. `{{character}}` → `{{Infobox character}}`，字段名按 `rules/template_map.json` 映射（**大小写不敏感**；一行一参数中文站风格）
  2. `{{quote}}` → `{{Quote}}`
  3. 其余模板（`book ref`/`date`/`image`/`for`/`columns`/`partial`/`Mistborn`…）**中文站同名且参数兼容，直接复用不动**
  4. `--wrap`：组装页面级包装 `{{CmPermission|英文名}}`（顶）+ `{{en|英文名}}`（首部占位，翻译阶段移位）+ `{{ensync|revid}}`（结尾，revid 取自快照）——决议 10-12
  5. 报告 mapped/unmapped/collisions/wrapped

用法：
```bash
.venv/bin/python scripts/convert_templates.py --title <标题> [--wrap] [--json]
```

- **验证结论**：`Allik Neverfar` 全页 10 种模板，仅 `character`/`quote` 需转换，其余 8 种（占 54+ 处引用）中文站直接复用。真正需写转换规则的模板很少。

---

# 待办状态总览（更新）

1. ✅ 英→中读取链路已通
2. ✅ 中文站 bot 账号（水蛭一号，`verified` 认证用户）→ 登录 → 有效 CSRF token → `action=edit` 写入（2025-10-16 首次写入 `Allik Neverfar` 成功）
3. ⬜ 拿到初始译名表（放 `dict/`）
4. ✅ 版本号记录方案已定（`state/en_index.json` + 快照）→ ✅ 已实现（`fetch_en.py`）
5. ✅ 开发语言已定 Python；✅ 快照/索引方案已定 → ✅ 抓取落盘已实现（`fetch_en.py`）
6. ⬜ 从 `Allik_Neverfar` 起步做样板词条：转换 + 译名表 + 映射表，用户 review 后再写站（⚠️ 已测试写入，待 review 图片黑名单/包装等）
7. ⬜ 落地并实现：白名单/黑名单/redirect 批量/模板图片校验 等规则
