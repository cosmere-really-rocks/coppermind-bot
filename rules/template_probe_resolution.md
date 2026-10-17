# 模板探测与中站对应决议（live 全量核对 · 2025-10-17）

> 目的：回答「英文词条用到的每个模板，中文站有没有对应、该怎么办」。
> 用 `scripts/probe_template.py --audit` 对 **en_snapshot/ 全部 568 个英文词条**做 live 核对（登录中文站，`action=query&titles=模板:<名>` 判存在性），结果落在 `probe_report.json` / `probe_report.txt`。
>
> 判存在性基准：`pageid != null` 才算存在（灰机 API 对不存在页返回 `missing:""` 空串，`!missing` 恒真，不能用）。见 `template_diff_audit.md` §基准。

## 一、探测工具用法（供后续 AI 复用）

```bash
.venv/bin/python scripts/probe_template.py --template for            # 单查一个英文模板在中站是否有同名
.venv/bin/python scripts/probe_template.py --template 'book ref' --verbose
.venv/bin/python scripts/probe_template.py --audit                   # 全量核对 → 写 probe_report.json/.txt
.venv/bin/python scripts/probe_template.py --audit --summary         # 只打汇总不写文件
```

- 判定规则：① 中站有同名 → OK；② 英文模板名在 `rules/template_map.json` 的 `src_template` 集里（被映射为中文 infobox）→ 归 `infobox_mapped`，不算缺失；③ 其余查不到 → 归 `missing`，并顺带在中站搜近名候选，辅助判断「换名 or 真缺」。
- 命名空间/大小写：按 MediaWiki 模板名首字母不敏感规则，以 `模板:<首字母大写名>` 查询；`Template:`/`模板:` 前缀已剥。
- 依赖：复用 `write.py` 的 `HuijiClient`（需 `.env` 里 HUIJI_API_KEY/BOT_USER/BOT_PASS，已登录才可查）。
- ⚠️ 用 `action=query` 的 `pageid` 判存在，**不要用 `missing` 字段**，也别用 `allpages`（不完整）。详见 `template_diff_audit.md`。

## 二、全量结果一览（101 个模板 / 11531 处使用）

| 分桶 | 数量 | 说明 |
|---|---|---|
| 同名存在（OK） | 50 | 中站有同名模板，`{{x}}` 可直接渲染；含 Navbox（`Mistborn`/`mistborn`→Navbox mistborn、`Stormlight`→Navbox stormlight 等） |
| infobox 已映射 | 22 | 已进 `template_map.json`（character/quote/group/location/culture/item/literature/lifeform/food/magic/disease/business/book/settlement/architecture/geography/nation/vehicle/**noble house**…） |
| 缺失/待确认 | 29 | 见 §三，逐条给了处置建议 |
| **合计** | **101** | 50+22+29=101 个唯一模板，共 11531 处使用 |

> 与早期 `template_diff_audit.md`（96 个）的差异来自：新建的 settlement/architecture/geography/nation/vehicle 五个模板、以及 live 探测扫出的低频/魔法字模板。

## 三、缺失模板的处置决议

探测最初报「缺失 30 个」；其中 `noble house` 中站有对应 Infobox 且已接入映射，故**当前剩 29 个**待确认。逐条处置如下，按性质分四类。**凡标「drop（不搬运）」的**，都是英文站编辑/维护/参考类，中文站没有也**不该有**，翻译阶段应删掉或保留为注释，不搬进正式词条。

### A. 中站已有同名 Infobox → 接入映射（可直用）
| 英文 `{{…}}` | 用量 | 中站对应 | pageid | 处置 |
|---|---|---|---|---|
| `noble house` | 7 | `Template:Infobox noble house` | 440 | ✅ **已接入** conversion map（name→家族名/world→世界/books→涉及书目；home/era/universe 无对应字段，未映射） |
| `metal` | 2 | `Template:Infobox metal` | 133 | ⬜ **待决策**：EN `{{metal}}` 是「神金/金属学」语义（hemalurgy/type/properties/books，如 Trellium），中站 `Infobox metal` 是「镕金金属技艺」语义（推拉/内外/分类/对应金属/镕金术师）。**字段语义不对应，强行映射会成为错法 infobox**，建议单独定承载方式（见 readme §6 待办）后人工处理，不要自动映射。 |

### B. 中站有对应 Navbox / 横幅 → 翻译时改挂中站 Navbox 或删
| 英文 `{{…}}` | 用量 | 中站对应 | 处置 |
|---|---|---|---|
| `Mistborn Era 2` | 22 | `Template:Navbox mistborn Era 2` ✅ | 改挂中站 Navbox mistborn Era 2 |
| `Mistborn Era 1` | 1 | `Template:Navbox mistborn Era 1` ✅ | 改挂中站 Navbox mistborn Era 1 |
| `cosmere`/`Cosmere` | 4 | `Template:Navbox cosmere` ✅ | 改挂中站 Navbox cosmere（三界宙导航） |

### C. 非 meta 级模板 → 按用户决议「都需要搬」（2025-10-17 已建站）
> 用户决议：**只要不是 meta 级（编辑维护）的 Template，都需要搬**。下列英文模板已由 `scripts/migrate_templates.py --all` 迁移（翻译）到中文站，`模板:` 均已建（revid 见后）：
| 已建模板 | 英文 pageid | 用途 | 说明 |
|---|---|---|---|
| `Rosharan date`（含 `Date/sa` redirect）| 5747 | 罗沙/风暴光历（Vorin）中文输出 | 承接原中文 Date/sa 的 年/月/周/天，date/sa→redirect 到本模板（实测 `{{date/sa|1174|2}}`→`1174年第2月`） |
| `Notice` | （父模板）| 横幅类父模板 | cite note / rpg-canon 的底座，一并建 |
| `Cite note` | 4842 | 「需更多引用」横幅 | 依赖 Notice |
| `Rpg-canon` | 25374 | 「Cosmere RPG 内容正典」横幅 | 依赖 Notice |
| `Small caps` | 21518 | 小型大写排版 | 风暴之父等说话引文格式 |
| `CoverToC` | 15936 | 系列封面目录导航 | mbe1/mbe2 等代号 |
| `Sots ref` | 11716 | 引用 State of the Sanderson 年度信 | 按中文站 bws ref 风格改写 |
| `Wp ref` | 5652 | 引用维基百科 | 按中文站 url ref 风格改写 |
| `Books` | 709 | 桑德森全部作品导航 | 有既定中译的书名用中文，其余保留英文 |
| `Tress` | 22736 | 单书导航 | 显示名保留英文 |

> 已建 revid 16708–16718（`Rosharan date`/`Date/sa`/`Notice`/`Cite note`/`Rpg-canon`/`Small caps`/`CoverToC`/`Sots ref`/`Wp ref`/`Books`/`Tress`）。

### C'. 仍属 meta 级（编辑维护）→ drop，不搬
| 英文 `{{…}}` | 用量 | 说明 |
|---|---|---|
| `update` | 34 | 站务「需更新」，meta，不搬 |
| `expand` | 25 | 站务「待扩充」，meta，不搬 |
| `demoted` | 3 | 站务「已降级」，meta，不搬 |
| `nosnippet` | 2 | 站务「不进入摘要」，meta，不搬 |
| `small caps`（已迁，见上）| 1 | —— |
| `cite note`（已迁）| 1 | —— |
| `edit note` | 1 | 站务「编辑说明」，meta，不搬 |
| `meta/done`/`meta/partial`/`meta/stub` | 12 | meta 编辑状态机，不搬 |
| `rpg-canon`（已迁）| 1 | —— |
| `user:fbstj/mb/writing` | 1 | 用户子页模板，不搬 |
| `CoverToC`（已迁）| 2 | —— |
| `sots ref`（已迁）| 2 | —— |
| `wp ref`（已迁）| 1 | —— |
| `tress`（已迁）| 1 | —— |
| `FULLPAGENAME` | 9 | MediaWiki 系统魔术字，非模板，drop |
| `dialogue` | 1 | 对话横幅，待定（未在搬运清单，暂不建） |
| `notice`（直接使用的那 1 次）| 1 | 与本项目已建的 `Notice` 是同一模板名（大小写不敏感），已建 |

### D. shard info → 对应中站 Infobox shard（映射，已接入）
- **确认**：英文 `{{shard info}}` 对应中文「模板:Infobox shard」（vessel→化身/holder、status→现状/status、perpendicularity→神潭/shardpool、magic→魔法、slivers/splinters 同名、residence→世界/world；universe 无对应字段丢弃）。
- 属于「映射」而非「新建」——中文站早已有 `Infobox shard`。已接入 `rules/template_map.json`，转换器实测 `Harmony` 出 `{{Infobox shard}}`。

> 说明：`Rosharan date`/`shard info` 属风暴光（Stormlight）/神瑛概念；快照里有对应风暴光词条时按上述方案承接，纳入搬运范围。

## 四、落地状态

- ✅ `noble house` 已接入 `rules/template_map.json`（`House Demoux` 实测转换）。
- ✅ 探测工具 `scripts/probe_template.py` 全流程可跑（修过排序 bug）。
- ✅ **非 meta 模板已迁移到中文站**：`scripts/migrate_templates.py --all` 建了 11 个模板（Rosharan date/Date/sa/Notice/Cite note/Rpg-canon/Small caps/CoverToC/Sots ref/Wp ref/Books/Tress），revid 16708–16718；`Date/sa`→redirect→`Rosharan date`，实测 `{{date/sa|1174|2}}` 正常展开。
- ✅ `shard info`→`Infobox shard` 已接入转换映射（实测 `Harmony`）。
- ⬜ `metal` 等候单独承载决策（见 readme §6 / template_diff_audit §二）。
- ⬜ meta 级模板（update/expand/demoted/nosnippet/meta:* /edit note/user:...）的 drop 逻辑需在 `convert_templates.py`/`translate.py` 落地。

## 五、给后续 AI 的提示（易踩坑）
1. **判存在性用 pageid**，别用 `missing`（灰机返回空串）别用 `allpages`（不完整）。
2. **模板名首字母不敏感**：英文 `for` 查 `模板:For`；大小写混写（`Date`/`date`、`Book ref`/`book ref`）在 MediaWiki 同名。
3. **加新 infobox 映射只需在 `template_map.json` 加一条**（src/dst/field_map），转换器与翻译器都是映射表驱动、自动生效，无需改代码；`drop_always` 与 `missing_cn_fields` 可选。
4. **探测工具会登录中文站**（复用 write.HuijiClient），批量 audit 有请求间隔；遵守 readme 决议 #14 限速。
