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
- **中文站写入（edit/创建）**：❌ **尚未打通**。当前 authkey 只给读取权限（匿名、rights=0），拿到的 CSRF token 是无效 `+\`。
  - 写操作需要**已登录用户的 CSRF token**（`action=edit` 前先 `meta=tokens&type=csrf`）。
  - 中文站 `action=login` API 可用（login token 能取到，未被拦截），需要 **bot 账号（用户+密码）** 才能登录拿有效 token。
- Cloudflare：英文站用 cloudscraper（TLS 指纹伪装）可过；中文站**必须**带 `X-authkey`，否则 API 层也被 403 拦。

## 技术方案

- 用 `cloudscraper`（python，已在环境安装）→ 实际走标准 MediaWiki API，无需额外 skill/插件。
- 已装过 `huiji-wiki-bot` skill（`/root/lianz/.agents/skills/huiji-wiki-bot`），是对同一套 API 的封装，可选用（需 env：`HUIJI_API`/`HUIJI_WIKI`、`HUIJI_API_KEY`、可选 `HUIJI_BOT_USER/PASS`）。

## 下一步（待办）

1. ✅ 英→中读取链路已通
2. ⬜ 拿到中文站 bot 账号（用户+密码）→ 登录 → 拿有效 CSRF token → `action=edit` 写入
3. ⬜ 翻译 `Allik_Neverfar` 词条并贴回中文站

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

---

# 待办状态总览（更新）

1. ✅ 英→中读取链路已通
2. ⬜ 中文站 bot 账号（用户+密码）→ 登录 → 有效 CSRF token → `action=edit` 写入
3. ⬜ 拿到初始译名表
4. ⬜ 实现/约定：英文站版本号记录（议题见第 3 条）
5. ⬜ 从 `Allik_Neverfar` 起步做样板词条：转换 + 译名表 + 映射表，用户 review 后再写站
6. ⬜ 落地竞品比对：白名单/黑名单/redirect/模板图片校验 等规则逐步构建
