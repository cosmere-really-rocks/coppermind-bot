# 实现思路：英文 Coppermind → 中文红铜智库 翻译管线

> 本文档写给**后来接手该项目的 AI / 开发者**，解释本仓库的核心设计决策与实现机制。
> 代码事实优先，注释里的「决议#N」「review 修复」指开发过程中与用户逐轮确认的约定。
> 铁律：**不写正式站；写站仅到 `bot测试:` 前缀测试页**（用户明确批准的范围）。

---

## 1. 总体管线（一次翻译做了什么）

`scripts/translate.py` 是核心，`--title X` 单页流程：

```
en_snapshot/X/wikitext.txt（英文快照）
  → convert_wikitext()          # 模板/脚注/占位的确定性归一（见 §4）
  → extract_en_terms()          # 提取本页候选专名（内链目标+大写词+小写领域词）
  → slice_glossary()            # 从全译名表裁出命中本页的子集，放提示词
  → 确定性替换                 # Infobox 值 / {{for}} 参数 / 子页链接目标 按译名表替换
  → chunk_wikitext()            # 按章节切块（默认 max_chars=7000）
  → LLM 逐块翻译（提示词见 §3）
  → assemble()                  # 拼回、填回受保护原文占位符、加页面级包装
  → translation.json/txt        # 产物；write.py 再写回站
```

入口：`scripts/batch.py --titles 清单.txt --write-target-prefix "bot测试:"`（批量编排，逐页子进程调 translate.py / write.py）。

### 1.1 译名表体系（三层）

| 文件 | 内容 | 说明 |
|---|---|---|
| `dict/mistborn.json` | 主译名表（973 条） | 键=规范英文，值 `{zh, note}`，note 记书证/中文站页面证据 |
| `dict/common.json` | 跨站通用 | 子页后缀（Statistical analysis→数据分析）等 |
| `dict/keep_en.json` | 人工确认「保留英文」名单（23 词） | 见 §2，已被自动机制取代为辅助层 |
| `dict/zhwiki_titles.json` | 中文站已建中文页面 → 规范英文原名（847 条） | 由 scan_zhwiki_titles.py 生成 |
| `dict/zhwiki_aliases.json` | 英文标题重定向页 → 中文目标（723 条） | 同上，第二阶段 |

`load_merged_glossary(primary, secondary)`：主表键优先合并。`build_norm_glossary()` 建归一化索引
（去冠词/属格/复数，小写），让正文屈折形式（Kandra's/kandra/metalminds）也能命中规范词条。

### 1.2 关键决策：宁可保留英文，不可自造译名

用户最在意的错误是 LLM **自造译名**（如把《The Long Way In》译成「长路漫漫」）。规则 2：
「译名表/中文书证均未收录、又无官方中文译名的疑似专名，**保留英文**并列入 untranslated_terms，
不得自造译名」。代价是译文出现英文原词（可后续补表），收益是绝不产生错误译名。

---

## 2. keep_en：从「人工名单」到「全自动三层机制」（2026-10-18）

### 2.1 问题

最初 keep_en.json 是 review 一个页面补一批词的手工名单。但快照有 1123 页，逐页人工 review
不可行，用户质疑「其他页面咋整」。改为任何页面翻译时**自动计算**本页应保留英文的专名。

### 2.2 三层合流（都是 translate.py 里逐块实时计算的）

**第一层：动态 keep_en —— `detect_keep_en_terms(chunk_text, glossary, zhwiki_rev)`**

- 信号：`''斜体书名''` + `[[链接目标]]`（书名/作品名惯例形态），过滤命名空间前缀
  （User:/Category:/File:/wob:/bws:/interwiki es: uk: 等）。
- 排除已在译名表（精确或归一命中）的词。
- 排除**中文站已有对应页面**的词（zhwiki_rev 命中，见第二层）。
- **贪心拆译判定 `_can_split_translate()`**：把短语按词拆分，贪心用「译名表里的最长连续词条 +
  停用词」覆盖，能全覆盖则说明「由已收专名组成」，不保留英文。
  例：`Mistborn: The Final Empire` = Mistborn(在表) + The(停用) + Final Empire(在表) → 可拆译，
  不保留（正确译「迷雾之子：最后帝国」）；`The Long Way In` 有 Long/Way 拆不动 → 保留英文。
- **`'''粗体'''` 不误判为斜体**：三个引号里嵌两个引号，正则取 `''X''` 时检查前后是否还有单引号。

**第二层：zhwiki ref —— `detect_zhwiki_refs(chunk_text, glossary, zhwiki_rev)`**

- 中文站已有页面的专名（如 Brandon Sanderson、Kaladin）提示 LLM **采用中文站页面标题**作译名，
  而不是保留英文或自造。
- 数据来自 `scripts/scan_zhwiki_titles.py` 全站扫描：
  - 第一阶段：allpages 遍历主命名空间（跳过 bot测试:），只处理**含中文的标题**页，读 wikitext
    提取原名信号——`{{CmPermission|X}}`（本项目 bot 写的页必有）> `{{en|X}}` > `{{Infobox|原名=}}`。
  - 第二阶段：`apfilterredir=redirects` 列出**英文标题重定向页**（如 `Elend` → `依蓝德·泛图尔`），
    递归解析重定向链到最终中文目标，写入 aliases。这些是链接目标最常见形态（正文 `[[Elend]]`
    而非 `[[Elend Venture]]`）。
  - 反索引 `build_zhwiki_reverse(zh_map, aliases)`：en_title → [zh_title...]，两源合并。

**第三层：静态 keep_en.json**——人工确认过的词（如 Alloy of Law (rule book)）与动态结果
`_dedup_keep_en()` 保序合并，两不冲突（已复核：静态 23 词在 zhwiki 全部无对应页面）。

### 2.3 提示词形态（build_user_prompt 追加两段）

```
**以下专名必须保留英文、禁止翻译或改译**（译名表未收录、无官方中文译名，中文站也无对应
页面，不要因为它们像书名/作品名就自造译名）：Mistborn Legacy、The Long Way In、…。
保留原文即可，并把它们列入 untranslated_terms（reason=保留英文）。

**以下专名中文站已有对应页面，请采用其页面标题作为译名参考**（若与译名表冲突以译名表为准）：
Brandon Sanderson → 布兰登·桑德森。
```

注意：build_user_prompt 增加了可选参数 `glossary`（完整译名表），translate_chunk(_with_retry)
与 main 调用点都已透传。

### 2.4 效果与维护

- 任何新页面自动生效，零人工维护。
- 中文站有人建了新页 → 重跑一次 `scan_zhwiki_titles.py`（约 10 分钟）即纳入参考。
- 剩余兜底：仍无译名的专名（如 `Leras`，中文站页还是英文标题）保留英文并出现在
  untranslated_terms，确认后补进译名表即可。

---

## 3. LLM 调用细节（deepseek-v4-flash-0731）

- OpenAI 兼容接口（token.glint-mvt.com/v1），config 见 `translate.py::LLMConfig`，
  凭据在 `.env`（gitignored）。
- **`thinking={"type":"disabled"}` 必须默认发送**：该模型对长 wikitext 块会做病态无限推理
  （reasoning 吃光 max_tokens → content 空 → JSON 解析失败）。`LLM_THINKING=enabled` 可恢复。
- chunk 内、块间串行；`--concurrency` 可开并发。
- `parse_chunk_reply()` 宽松 JSON 解析：容忍 ```json 围栏与前后文字，取首 `{` 到末 `}`。
- LLM 返回 `{translation, untranslated_terms}`；untranslated_terms 会被 assemble 汇总。
- 导语校验 `untranslated_lead_english()`：chunk0 导语若残留叙述性英文（≥4 个全小写/停用词），
  重试最多 2 次。**必须剥掉 `<ref>`/`</ref>` 标签与 `[[wob:N|wob:N]]` 再计数**，否则 wob ref
  展开成的小写 `wob`/`ref` 会误判（Atium 页曾因此导语校验重试 3 次失败）。

---

## 4. 模板与引用归一（convert_templates.py，LLM 之前做确定性转换）

### 4.1 `_scan_refs`：{{ref|...}} → 标准 <ref>

英文站 `{{ref|...}}` 形态多样，中文站 `Template:Ref` 是书目引用模板（`#invoke:Ref` 用卷/章码），
纯占位引用直接传给它会报「函数{{{1}}}不存在」。统一转标准 `<ref>`：
- `group=fn` + name + text → `<ref name="N" group="fn">text</ref>`
- fn + text 无 name → `<ref group="fn">text</ref>`；fn + name 无 text → `<ref name="N" group="fn"/>`
- **无 group + name + 无 text**（占位引用，如 `{{ref|name=alloy}}`）→ `<ref name="X"/>`
  —— 定义由 `<references>` 内的 `{{url ref|name=X}}`/`{{bws ref|name=X}}` 提供。
- 非 ref 模板参数内嵌套的 `{{ref|name=X}}`（如 `{{columns|...}}` 内）也递归归一，否则外层
  模板整块被跳过。
- LLM 偶发把 `<ref name="X"/>` 变回 `{{ref name="X"}}`（无管道、带引号）也能归一：
  `assemble()` 对最终译文**幂等重跑 `_scan_refs`**。

### 4.2 `_convert_footnote_groups`：保留 group="fn"（方案 A'）

**必须保留 `group="fn"`，不能剥掉**。MediaWiki Cite 语义：每个无 group 的 `<references>` 是
默认组的一个「结算点」；若把 `<references group=fn>` 剥成无 group，fn 脚注混入默认组，页面出现
**多个默认组结算点**，位于中间 references 之前的**未定义占位引用**（如 alloy 占位在第二个 fn
references 之前）会被提前结算为「未定义」→ 主 `<references>` 里的定义再报「没有在先前的文字中
使用」。保留 group="fn" 后 fn 脚注独立成组，默认组只剩主 `<references>` 一个结算点（最小页
实验 4/5/6 精确复现与验证）。

### 4.3 `_expand_wob_refs`：{{wob ref|N}}（仅参数 1）→ `<ref>[[wob:N|wob:N]]</ref>`

中文站 `Template:Wob ref` 的链接文本写的是 `{{{text|{{{2}}}|}}}`（嵌套 `{{{2}}}` **缺默认值
管道**），单参数调用渲染出 46 处 `{{{2}}}` 字面量。展开成独立 `<ref>` 绕开模板缺陷，且不依赖
缺失的 `Template:Ref/broken`。带 text/date 等扩展参数的调用保留原样。

### 4.4 infobox 类

- Infobox「字段 = 值」按译名表确定性替换（`translate_infobox_values`），结构化短字段不依赖 LLM。
- `{{for|...|pre=}}` 参数确定性替换（`translate_for_template`）。
- 子页链接 `[[父/子页|display]]` 父段与后缀段**都有译名**才重写（`translate_wikilink_targets`）。
- 表格 bib 表头 `class=` 里的 `infobox` 词被剥离（`_strip_bib_infobox_class`），避免中文
  `wikitable infobox` 冲突布局损坏。
- 站务模板整删（update/expand/meta:*/demoted/dialogue/edit note/user:*）；nosnippet unwrap 保内文。

---

## 5. 写站与验证（write.py）

- `HuijiClient.edit(title, content, summary)` 是正确方法名（不是 edit_page）；`read_page` 只读。
- 登录：login token → CSRF token → `action=edit`（bot 标记）；会话 cookie 名 `huiji_session`。
- `--skip-if-same`：目标页 ensync revid == meta.revision_id 则跳过（增量）。
- **渲染校验**：`c._post({"action":"parse","page":...,"prop":"text"})` 取渲染 HTML，查
  `引用错误|脚本错误|class="error"|{{{2}}}` 等特征；`cite_note-*` 出现表示引用生成成功。
- 删除实验页：`action=delete` + CSRF token（`bot测试:Ref实验1..6` 用过）。

---

## 6. 常见调试手法

- **最小页实验**：在 `bot测试:` 前缀建几行 wikitext 的小页 → 渲染 → 精确复现
  MediaWiki 渲染错误（引用结算点问题就是这样定位的），验证后删除。
- **单测**：`importlib` 重载模块后直接调私有函数（`_scan_refs`/`detect_keep_en_terms` 等）比对期望串。
- **dry-run**：`translate.py --dry-run` 打印每块提示词概要与长度，不调 LLM。
- **回归对照**：重跑已知页面，核对已确认译名/keep_en/标题等关键字符串不退化。
- 未提交的 `.bak` 文件（dict/mistborn.json.bak-*）勿提交；state/*.log 是运行记录不提交。

---

## 7. 关键 git 历史锚点

| 提交 | 内容 |
|---|---|
| c8862f9 | LLM thinking disabled（绕开无限推理）；中文站模板/模块核对 |
| 9bc6fd4 | keep_en 名单机制 + 两书名入译名表（官方译名查证） |
| ea79bfb | 页面三个渲染错误修复（ref 占位归一/保留 group=fn/wob 展开） |
| ea8a140 | **keep_en 升级为全自动三层机制**（本文档 §2 的主体） |