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
| `books` | 6 | 中站无同名；书页底部导航 | 可改用 `Template:Navbox mistborn` 或删除，待定（低频） |
| `summaries` | 4 | 中站无同名 | 维护页脚，drop 或不搬 |
| `notice` | 1 | 中站无同名（候选 Theory/Exemplary/Complete/Fmbox） | 横幅，drop 或手工改中文横幅 |
| `dialogue` | 1 | 中站无同名 | 对话横幅，drop 或承接（中文站如有对话模板另议） |

### C. 系统性魔法字 / 不该上站 → drop（翻译时删除）
| 英文 `{{…}}` | 用量 | 说明 |
|---|---|---|
| `FULLPAGENAME` | 9 | MediaWiki 系统魔法字（`{{Special:PrefixIndex/{{FULLPAGENAME}}/}}`），非模板，drop |
| `update` | 34 | 站务标记「需更新」，drop |
| `expand` | 25 | 站务标记「待扩充」，drop |
| `demoted` | 3 | 站务「已降级」，drop |
| `nosnippet` | 2 | 站务「不进入摘要」，drop |
| `small caps` | 1 | 排版「小型大写」，drop |
| `cite note` | 1 | 排版/脚注辅助，drop |
| `edit note` | 1 | 站务「编辑说明」，drop |
| `meta/done` | 6 | meta 编辑状态模板，drop |
| `meta/partial` | 5 | meta 编辑状态模板，drop |
| `meta/stub` | 1 | meta 编辑状态模板，drop |
| `rpg-canon` | 1 | 站务「rpg 是否正典」标记，drop |
| `CoverToC` | 2 | 封面目录导航，drop |
| `user:fbstj/mb/writing` | 1 | 用户子页模板，drop |
| `sots ref` | 2 | 引用「State of the Sanderson」站外参考，drop（或转 url ref 处理） |
| `wp ref` | 1 | 引用维基百科站外参考，drop（或转 url ref 处理） |
| `tress` | 1 | 单书维基导航隐藏项，drop |

### D. 其他系列/低频 → 按需人工
| 英文 `{{…}}` | 用量 | 处置 |
|---|---|---|
| `Rosharan date` | 41 | 风暴光历（Stormlight）专用日期模板，中站只有通用 `Date`。Mistborn 用不到（出现在快照里的 Stormlight 词条），建议**保留英文站源不动**、或通用化转 `Date`；风暴光词条不在当前 Mistborn 搬运范围，先标 pending |
| `rosharan date` | 3 | 同上（小写别名） |
| `shard info` | 1 | 神瑛信息模板（Stormlight），Mistborn 无此概念；drop 或风暴光词条人工处理 |

> 说明：`Rosharan date`/`shard info` 属于风暴光（Stormlight）世界观，而本项目范围按 readme 是 Mistborn 系列。快照里含一批风暴光词条（Adolin/Shallan/Kaladin 等），这部分模板能否照搬需与用户确认是否纳入当前搬运，故标 pending。

## 四、落地状态

- ✅ `noble house` 已接入 `rules/template_map.json`，转换器实测 `House Demoux` 正常出 `{{Infobox noble house}}`。
- ✅ 探测工具 `scripts/probe_template.py` 已修一个排序 bug（`missing.sort` 的 key 应为 dict 的 `"count"`，原误写成 `x[1]`），`--audit` 全流程可跑。
- ⬜ `metal` 等候单独承载决策（见 readme §6 / template_diff_audit §二）。
- ⬜ B/C/D 类处置需在 `convert_templates.py`/`translate.py` 的 drop/改挂逻辑落地（本轮先给决议，落地可后续做）。

## 五、给后续 AI 的提示（易踩坑）
1. **判存在性用 pageid**，别用 `missing`（灰机返回空串）别用 `allpages`（不完整）。
2. **模板名首字母不敏感**：英文 `for` 查 `模板:For`；大小写混写（`Date`/`date`、`Book ref`/`book ref`）在 MediaWiki 同名。
3. **加新 infobox 映射只需在 `template_map.json` 加一条**（src/dst/field_map），转换器与翻译器都是映射表驱动、自动生效，无需改代码；`drop_always` 与 `missing_cn_fields` 可选。
4. **探测工具会登录中文站**（复用 write.HuijiClient），批量 audit 有请求间隔；遵守 readme 决议 #14 限速。
