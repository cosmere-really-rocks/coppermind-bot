# 模板差异盘点（EN wikitext → CN 中文站）——修正版 2025-10-16

> 目的：回答「英→中还差什么」。逐条比对了 en_snapshot 的「英文词条用到的模板」与「中文站（红铜智库）实际存在哪些模板」。
>
> **判据（重要）**：判定模板是否存在，用 **`action=query&titles=` 返回的 `pageid`**（`pageid != null` = 存在）。
> ⚠️ 不能用 `missing` 字段判存在：灰机 API 对不存在的页面返回 `missing: ""`（**空字符串**），`!missing` 恒为真，会误判成"存在"；也**不能用所有页面清单(allpages)**（不完整）。`get` 命令对模板标题也有 bug（全报不存在）。
>
> 校验基准：`Template:Infobox settlement`、`Asdf` → pageid=null（**不存在**，与用户确认一致）；`Template:Infobox character`(pageid=4)、`Template:Mistborn`(2547)、`Kaladin`(845) → 存在。

## 结论速览

- 英文词条用到的模板共 **96 个**。
- 中文站**并非全覆盖**：有一批模板真的不存在（见 §四），不能直接照搬。
- 差异分四类：**可复用 / infobox 重命名（有对应）/ infobox 重命名（中文缺模板）/ 中文不存在（需建或替换）**。

---

## 一、可复用（中文站同名/大小写存在，直接照搬即可）

以下英文模板在中文站有同名（仅大小写差异）模板：

`book ref` `Mistborn`(→Navbox mistborn) `complete` `wob ref` `date` `file ref` `icon`
`quote` `columns` `sidequote` `map ref` `for` `row` `cat tag` `partial` `tag`
`tes ref` `ref` `epigraph ref` `chart` `msh ref` `cite` `bws ref` `url ref`
`mistborn`(→Navbox mistborn) `anchor` `holder` `theory` `Stormlight`(→Navbox stormlight)
`reddit ref` `uncanonical` `tor ref` `event` `chart/wrap` `tweet ref` `map`
`Date` `stub` `date/sa` `exemplary` `Sidequote` `article ref` `row/kv` `Book ref` `Quote` `Book tag`

> 注意几个看起来特殊其实可复用的：`Mistborn`/`mistborn`/`Stormlight` 在中文站对应的是 **Navbox**（导航框）；`event`/`map`/`cite`/`date`/`icon` 等英语大小写均可命中。

## 二、infobox 重命名：英文 `{{X}}` → 中文站 **有** `Template:Infobox X`（可映射）

英文正文用的是**无 Infobox 前缀**的模板名，中文站要求 `Infobox X`（中文参数）：

| 英文 `{{…}}` | 中文目标模板 | 存在性(pageid) |
|---|---|---|
| `{{character}}` | `Infobox character` | ✅(4) 映射表+转换器已做好 |
| `{{business}}` | `Infobox business` | ✅(1326) ⬜待映射 |
| `{{group}}` | `Infobox group` | ✅(371) ⬜ |
| `{{location}}` | `Infobox location` | ✅(5) ⬜ |
| `{{culture}}` | `Infobox culture` | ✅(510) ⬜ |
| `{{item}}` | `Infobox item` | ✅(2193) ⬜ |
| `{{literature}}` | `Infobox literature` | ✅(345) ⬜ |
| `{{noble house}}` | `Infobox noble house` | ✅(440) ⬜ |
| `{{book}}` | `Infobox book` | ✅(2) ⬜ |
| `{{lifeform}}` | `Infobox lifeform` | ✅(395) ⬜ |
| `{{food}}` | `Infobox food` | ✅(210) ⬜ |
| `{{metal}}` | `Infobox metal` | ✅(133) ⬜ |
| `{{magic}}` | `Infobox magic` | ✅(1341) ⬜ |
| `{{disease}}` | `Infobox disease` | ✅(2244) ⬜ |

> 中文站另有风暴光系 `Infobox fabrial/radiant/shard/war/magical entities/series/system/religion` 等（Mistborn 用不到，跳过）。

## 三、infobox 重命名：英文有这类词条，但中文站 **缺** `Template:Infobox X`（需建模板或承接）

| 英文 `{{…}}` | 使用量 | 中文站 `Infobox X` | 处置建议 |
|---|---|---|---|
| `{{settlement}}` | 37 | ✅ 已建 | 已建 `Template:Infobox settlement`（pageid3490），映射见 infobox_mapping.md |
| `{{architecture}}` | 31 | ✅ 已建 | 已建 `Template:Infobox architecture`（pageid3491） |
| `{{geography}}` | 12 | ✅ 已建 | 已建 `Template:Infobox geography`（pageid3492） |
| `{{nation}}` | 2 | ✅ 已建 | 已建 `Template:Infobox nation`（pageid3493） |
| `{{vehicle}}` | 7 | ✅ 已建 | 已建 `Template:Infobox vehicle`（pageid3494） |

> 这是最需要**决策**的一类：这些是高频类型（settlement+architecture 合计 68 条），但中文站没有对应模板，强行搬运会红链。建议先与用户定：建模板还是统一用现有的 `Infobox location` 承接。

## 四、中文站不存在、需「创建模板」或「替换/删除」

逐条 pageid 确认**不存在**：

- **高频/必须处理**：
  - `{{image}}`（246 次）——中文站无 `Template:Image`。**真实词条已出现失效的 `{{image}}` 红链**。可建的替代：`Template:Multiple image`(存在,949)、`Template:Wide image`(719)、`Template:Image link`(528) 都存在，选一承接，或新建 `Template:Image`。
  - `{{rpg ref}}`（194 次）——中文站无 `Rpg ref` 变体。高引用模板，需建或映射到其他 ref 模板（wob/msh/epigraph ref 都有）。
- **维护/特殊（建议搬运时删除，不照搬到新站）**：`update` `expand` `nosnippet` `demoted` `small caps` `cite note` `edit note` `meta/done` `meta/partial` `meta/stub` `rpg-canon` `user:fbstj/mb/writing` `wp ref` `sots ref` `tress` `coverToc` `FULLPAGENAME`(系统魔术字) —— 这些是英文站编辑维护用，不应上中文站。
- **其他系列/低频**：`Rosharan date`/`rosharan date`（风暴光历）、`cosmere`、`summaries`、`Notice`、`Dialogue`、`Mistborn Era 1`/`Mistborn Era 2` —— 中文站无，需按需相应处理（Era 1/2 或改成 Navbox，Notice/Dialogue 改其他横幅）。

## 五、字段级差异（模板名对上后仍需做）

以 character 为样板（`rules/character_template_mapping.md`、`rules/template_map.json`）：
- EN `{{character}}` 65 参数 vs CN `Infobox character` 84 参数，**非一一对应**。
- 三类处理：可直接映射(33) / 丢弃(32, 内部 ref/raw/hidden) / 待人工填充(54 CN 独有如 图二/原名/性别/文化/武器/恋人 等)。
- **其他 13 个可映射 infobox、以及承接 settlement/architecture 的方案，都要逐字段做这种映射**——这是「待积累」的核心工作量。

## 六、建议下一步（供定夺）

1. **先解决 §三 的决策**：settlement/architecture/geography/nation/vehicle 是建模板还是用 `Infobox location` 承接（需用户拍板，影响最大）。
2. **解决 §四 高频项**：建 `Template:Image` 或选 `Wide image` 承接 `{{image}}`；补 `Template:Rpg ref` 或映射到 ref 系。
3. 按使用量把 §二 的 13 个 infobox 依次接入 `convert_templates.py`（先 settlement/business/architecture——一并解决 §三）。每个先读中文站模板 wikitext，产出 character 同款字段对照。
4. §四 维护类在转换器中列为 `drop`（删除不搬运）。

> 附录：英文侧模板使用量前 20：book ref 6296、Mistborn 534、complete 473、wob ref 438、date 400、file ref 366、character 311、icon 292、quote 281、image 246、rpg ref 194、columns 192、sidequote 155、map ref 123、for 100、row 87、cat tag 84、partial 74、tag 65、tes ref 53。
