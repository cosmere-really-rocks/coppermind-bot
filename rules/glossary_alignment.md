# 译名表「中英章节对齐」验证方法与发现（glossary alignment）

> 生成：2025-10-16（本会话第二轮）
> 用途：用中英电子书章节对齐，为 `dict/mistborn.json` 补官方中译（以官方中译本为准，而非中文站 wiki 译名）。
> 术语表源文件：`dict/mistborn.json`（`terms: {英文: {zh, aliases?, note?}}`）；词条快照：`en_snapshot/<页面名>/`（含 `wikitext.txt`/`meta.json`）。

## 0. 参考模板确认
- 词条里的引用模板是 **`{{book ref|书码|章}}`**（不是 `ref`）。
- 书码映射（复用到 `readme.md` 系列构成）：`mb1`=最后帝国 … `mb6`=悲悼护腕、`mb7`/`tlm`=The Lost Metal（失落金属）。
- 另有 `{{map ref|...}}`（地图引用，名字多出现在地图/插页而非正文）、`{{file ref|...}}`（插页/报纸图）。

### 0.1 中英章节对齐规则（★批量处理必须遵守）
- **mb5/mb6 与 era1（mb1-3）**：EN 目录与 ZH 目录**按相同文件序号**一一对应（如 EN `shadows_of_self/005_chapter5.html` ↔ ZH `zh_旧影森森/005_chapter5.html`）。
- **mb4/aol（执法镕金）要按【章节号】对齐，不能按文件序号**：EN 目录比 ZH 多 4 个报章插页文件（形如 `003_9781429994897_chNN.html`，即 broadsheet 非正文），导致文件序号整体右移。正确映射为「EN 的 chapterN ↔ ZH 的 chapterN」（如 EN `005_chapter4.html` ↔ ZH `004_chapter4.html`；EN `016_chapter13.html` ↔ ZH `013_chapter13.html`）。EN 里文件名含 `9781429994897` 的都是报章插页，跳过不用。

## 1. 工作流（每词条 6 步）
1. **读词条**：`en_snapshot/<词条>/wikitext.txt` → 判断实际英文名（去掉括号消歧，如 `Demoux (city)`→`Demoux`、`Red (Scadrial)`→`Red`）。
2. **取 ref**：找 `{{book ref|书码|章}}`，定位「出现在哪本哪一章」。
3. **英文原文**：在 `dict/epub_out/<en书>/<章>.html` 找到该词条位置，理解上下文/词性（人名/地名/专名）。
4. **中文对照**：在 `dict/epub_out/<zh书>/<同章>.html` 同上下文找官方中译。
5. **核对一致性**：在多本/多章重复出现的，确认译名稳定（如 Irongate→铁门河在两本书一致）。
6. **记入译名表**：`dict/mistborn.json` 的 `terms`，必要时加 `note` 说明词义/出处，消歧的词条靠 `note` 避免歧义。

### 1.1 已脚本化：`scripts/glossary_assist.py`
上面的 6 步已脚本化为 **`scripts/glossary_assist.py`**（可复用于自动翻译 `{{quote}}` 的定位阶段）。它自动：
- 解析词条基础名（去括号消歧，如 `Chip (constable)`→`Chip`）；
- 从页面 `{{book ref|书码|章}}` 取出处（`map/file ref` 标为非正文，见 Finding D/E）；或纯词条模式跨书全书搜（Finding A 人物全名首现）；
- 在英书该章定位并显示高亮上下文；
- 按中英章节对齐（mb5/mb6/era1 同文件序号；mb4/aol 按章节号且跳过报章插页）映射到中书同章，给出「中文对照区」供人工/LLM 采证官方中译；
- 输出 JSON（`--json`）供后续自动补录/quote 翻译。

用法：
```bash
.venv/bin/python scripts/glossary_assist.py --page "Irongate River"        # 取页面 book ref 定位
.venv/bin/python scripts/glossary_assist.py --term "Allik Neverfar" --book mb6 --chapter 21
.venv/bin/python scripts/glossary_assist.py --term "Mycondwel" --all-hits  # 跨书/跨章搜
.venv/bin/python scripts/glossary_assist.py --term "X" --json              # 机器可读输出
```
验证样例（本轮）：`Irongate River→铁门河`（官方中译现于中文对照区内）、`Allik Neverfar`（全书扫证明仅 mb6 ch21 首现）、`Survivorism→幸存者教义`（悲悼护腕 mb6 ch12）、`Channerel Range/Mycondwel/Sea of Yomend→正文无命中`（地图/清单 only，如实报告待补）。

### 1.2 补全原则（用户定稿）
- **所有英文词条（含词条名本身）都应入译名表**：词条标题也是专名，写入 `terms`（如 `Sea of Yomend` 若可采证则入表；仅地图/无中译书则标 pending，见 Finding D）。
- **消歧词条→基础名为 key，一词多义用 `note`/`variants` 区分**：如 `Chip (constable)` 释义并到 `Chip`（`variants[kind=constable]` 或在 `note` 说明），不另起 `Chip (constable)` key；`Red (Scadrial)`→`Red`。查找时先 `base_name()` 去括号。
- 词条名缺官方中译但正文可采证（如 `Survivorism→幸存者教义`）→ 依 `glossary_assist.py` 定位的书证补入并加 `note`。


## 2. 已落地的验证样例（能力已跑通）
| 词条（快照） | 实际英文名 | 类别 | 出处（ref） | 官方中译（书证） | 备注 |
|---|---|---|---|---|---|
| Allik Neverfar | Allik Neverfar | 人物 | mb6（悲悼护腕）ch21 | **亚历克·奈弗法** | 全名首现于 ch21：「你叫什么名字？」→「高个子亚历克·奈弗法」。单名 Allik=亚历克 |
| Red (Scadrial) | Red | 人物（依蓝德运河船夫）| mb5（旧影森森）ch5 | **雷德** | 「朝名叫雷德的船夫挥手告别」 |
| Irongate River | Irongate River | 地理（依蓝德盆地主河）| mb5 ch18 / mb6 ch4 | **铁门河** | ch18「横跨铁门河」、ch4「沿着铁门河往东」，两书一致 |

## 3. 关键发现（★需在后续批量处理中处理）
### 发现 A：人名「全名」不保证出现在引用的那一章
- 例：`Allik Neverfar` 词条引到 mb6 ch19（角色被救出/登场），但**全名**首现其实在 ch21（韦恩/瓦克斯问名字那段）。ch19 只提到「the short masked man」等或单个 Allik。
- **处理规划**：对「人物全名」词条，不能只查引用的那一章。策略按优先级：
  1. 先在**该人物的英文书中全文搜全名**（`grep "Full Name"` 跨全书章节），定位其正式全名首现处。
  2. 找不到全名时，**拆分姓/名单独搜**（如搜 Allik 与 Neverfar），在各章分别找对应的中文名/姓，再拼回全名。
  3. 仍找不到（如地图/人名册才出现）→ 标 `note: 未见正文全名，推测为 …` 或 `untranslated`。
- 好处：同一人物只做一次，译名可复用（全名+单名+姓）。

### 发现 B：「名字+敬称/称号」整句扎堆出现 → 应记录整段可渲染短语
- 例：英文 **"Allik Neverfar, Tall One"** → 中文**「高个子亚历克·奈弗法」**（高个子对应敬称 Tall One，紧贴全名）。
- 该词条另有称号表（见 `rules/allik_terms.md` 原来按中文站译未知音，但**官方书里 Tall One=高个子**，与旧研究的「高个之君」不一致——以官方书为准）。
- **处理规划**：把这种「名+紧邻敬称」的完整中文短语记入词条的 `note`（或专门字段 `renderings`）。这样 AI 翻译时遇到 "Allik Neverfar, Tall One" 这类**整体语块**能直接套用整句译法，而不会拆成「亚历克·奈弗法+高个之君」拼错。
  - 数据模型建议：`terms["Allik Neverfar"] = {"zh":"亚历克·奈弗法", "renderings":[{"en":"Allik Neverfar, Tall One","zh":"高个子亚历克·奈弗法"}]}`（或把 rendering 并入 `aliases`/`note`）。**待定，倾向新增 `renderings` 列表字段**，便于机器替换长语块。

### 发现 C：消歧词条 → 实际名=基础词，需靠 note 区分词义
- `Red (Scadrial)` 实际名是 `Red`（依蓝德船夫，非史马锐其他 Red）；`Demoux (city)` 实际名是 `Demoux`（城，以人物 Demoux 命名），而 `Demoux`（人物）已在译名表=德穆。
- **处理规划**：消歧词条统一以「基础词」为 key；用 `note` 注明是哪个义项（城市/人物/船夫）。查询时若基础词已存在≠此义项，则并入该 key 的 `aliases` 或新增带 `note` 的义项——**但目前译名表是「一 key 一 zh」**，同名多义需扩展为「一 key 多义项」：
  - 倾向方案：`terms["Demoux"] = {"zh":"德穆","variants":[{"kind":"person","zh":"德穆"},{"kind":"city","zh":"…"},...]}`——**待定**。本轮先验证能力，暂不做大改。

### 发现 D：某些词条只出现在「无中译的书」（The Lost Metal）
- `Demoux (city)`、`The Two Seasons`（报纸名）等 ref 全指向 mb7/tlm（失落金属，**至今无官方中译**），中英对齐无处可采。
- **处理规划**：此类词条**无法**走章节对齐。只能：
  1. 若其名字部分在已译书中出现（如 Demoux 城虽只在 tlm，但人物 Demoux 在已译书中有名）→ 用「人名=德穆」推断城市名（合理：同名城市通常沿用人物名，但**需标注“推断，未经书证”**）。
  2. 全词只出现在无中译书 → 标 `untranslated` / `pending_tlm_translation`，等失落金属中译后再补。

### 发现 E：地理/地图类词条，ref 常是 `{{map ref}}`，正文不一定出现
- `Irongate River` 词条多处 `map ref`；book ref 的事件章（如 mb5|24 东桥战斗）正文**没写**「Irongate」字样，只有「the river」。名字真正落在正文的章是 mb5|10、mb5|18、mb6|4。
- **处理规划**：`map ref`/`file ref` 不能用于正文定位；应在**该地域所在书**里全文搜名字，锁定正文首现的章再做中英对照。

### 发现 F：官方中译可能「合并」英文相近/区分的多个词条
- 例：英文区分 **Trelagism**（时代一旧宗教）与 **Trellism**（时代二新宗教，源自 Trellismism 的 rename）；但官方中译**两者都叫「特雷教」**（最后帝国 ch9=特雷教；执法镕金 ch11=特雷教），而神名 **Trell=特雷**。
- **处理规划**：遇到英文「一神多名/一宗教多名」或「旧称/新称」，不能假设中译也区分。按书证逐一核对，若中译合并则多 key 标同一 zh + `note` 注明「官方未区分」。神名 Trell=特雷、宗教 Trellism/Trelagism=特雷教、民族 Nelazan=奈拉禅。

### 发现 G：英文「报章插页/broadsheet」内容在中文译本中可能被省略/改写
- 部分词条的**唯一**出处是英文书里的报纸/小报插页（Elendel Daily、broadsheet 等），而中文译本**省略或未逐字对应**该段。
- 实例：`Dorise Chevalle`（旧影森森 ch10 内的 Elendel Daily 段被中译省略）；`Corbeau`（旧影森森 ch5 的「水坝」报道段中译无对应）。
- **处理规划**：对「仅出现在报章插页」的词条，中英章节对齐常无证可采 → 标 `found:false, reason: broadsheet-omitted`，归入待补（与 tlm 类不同：书已译，但该段未被译）。

### 已落地批次（摘要；明细在 `dict/mistborn.json`，勿在此重录）

| 轮次 | 日期 | 结果 |
|---|---|---|
| pilot（§2 样例）+ 地理批 + 人物/非人物批 A-G（subagent） | 2025-10-16 | era2 可采证词条基本并入；全表 819（232 条带书证 note）；不可采证者按 Finding D/E/G 归 pending |
| 批 H 全系列 caizheng 采证 | 2026-10-18 | `Category:Mistborn` 1116 页 → 327 候选 → **168 ok 并入**（796→961）、159 pending 归档 `state/glossary_caizheng/pending_archive.md`（勿重跑） |
| 20 页 review + 采证补强 | 2026-10-18 | 961→970；keep_en 升级为机制（动态判定 + zhwiki ref，见 readme「当前实现状态」） |
| 译者 6 份 xlsx 并入 + 拆名 208 | 2026-10-19 | 3932→**4140**（= 三界宙全系列）；冲突 36 / 勘误 10 / 拆名冲突 12 → `state/glossary_xlsx_import/conflicts.md` 空列待填 |
| 三分类缺译名排查（伊岚翠/皇帝魂/飓光志） | 2026-10-19 | 2554 页中缺译 559：**80 行官方中译待裁定入表**、缺中译本 171 等 → `state/missing_translation_report.md` |

- 代表书证样例：Allik Neverfar=亚历克·奈弗法、Red=雷德、Irongate River=铁门河、Trell/Trellism/Trelagism=特雷教、Elendel=依蓝戴（146 处一致）等。
- **不可采证者勿重跑**（仅 tlm/密史无中译、报章插页被中译省略、意译未成专名、正文无书证）：总清单 `state/glossary_caizheng/pending_archive.md` + 文末复核注记。
## 4. 与既有规则的关系 / 需更正的旧决定
- `rules/allik_terms.md` 旧「用户裁决」称 **Allik Neverfar 专名不翻译、保留英文**——**本轮用户改向**：
  - 现在**以官方中译本为准**，Allik Neverfar=**亚历克·奈弗法**（不是中文站「阿利克·纳法尔」、也不是旧表「阿里克」）。`rules/allik_terms.md` 需按此更正。
  - 「原文引用不翻译」决议（#4/#13）**仍有效**：`{{quote}}` 台词/称号列表等仍不硬翻；但「名+敬称」这类**正文叙述短语**（非台词quote，是 prose）可用于书证。

## 5. 下一步（原建议，已全部完成）

1. ✅ 本文件即批量补全作业规范，已按此铺开（批次见 §3 摘要）。
2. ✅ 数据模型扩展已定稿（见下「数据模型（定稿）」），由 `scripts/glossary_migrate.py` 落地。
3. ✅ 「仅 tlm 出现」清单已单列（§7）。
### 数据模型（定稿，2025-10-16）
现状：`terms[en] = {zh, aliases?, note?}`。
新增三个**可选**字段（向后兼容，不影响既有条目）：
```jsonc
"Allik": {                        // 长语块整句替换（Finding B）
  "zh": "亚历克",
  "aliases": ["阿里克"],
  "renderings": [
    {"en": "Allik Neverfar, Tall One", "zh": "高个子亚历克·奈弗法", "note": "名+敬称"}
  ]
},
"Demoux": {                       // 同名多义（Finding C）
  "zh": "德穆",                   // 默认义项=人物
  "variants": [
    {"kind": "person", "zh": "德穆"},
    {"kind": "city", "zh": null, "pending": "tlm-untranslated"}
  ]
},
"The Village": {                  // 无固定专名（中译随上下文变）
  "zh": null,
  "zh_variable": true,
  "renders_note": "村/村里/村子（旧影森森）；村寨（悲悼护腕 prologue）"
}
```
- **`renderings`**：`{en,zh,note?}`，用于「名+敬称/称号/惯用整句」，替换优先级高于单名。
- **`variants[]`**：`{kind,zh,pending?}`，同名多义义项；`kind` 用短枚举（person/city/god/religion/item/…）；未译义项 `zh:null` + `pending:"tlm-untranslated"` 等。
- **`zh_variable`+`renders_note`**：官方无固定专名，中译随上下文变化时标记。

**迁移策略**：既有条目不动；仅对需要多义/长语块/变译的词条补上述字段。已录入的 55 条书证译名保留 `zh`+`note`，无需重跑。

## 6. 待办（与 readme「下一步/译名表补全」同步）
- ✅ 定夺数据模型扩展：`renderings` + `variants`（已定稿并落地，见 §5；迁移脚本 `scripts/glossary_migrate.py`）。
- ✅ 批量补全：人物 → 地理/地点/建筑 → 企业/团体/事件/文化/家族/物品/刊物/交通工具/疾病 → 歧义词条，E2 可采证条目已完成；不可采证者归 pending。
- ✅ 整理「仅 tlm 出现」词条清单（94 条 + mixed 58，见 §7）。
- ✅ 补全后回填 `rules/*.md` 并提交译名表（本轮已提交）。
- ✅ **2026-10-27 译者三项裁定**（后续 AI 勿回退，字典 note 已固化）：
  - `Shu-Dereth/Shu-Korath/Shu-Keseg` = **德雷西道宗/珂拉西道宗/珂西格道宗**（shu- = path of）。**10-26 的书证裁决「德雷西教宗」已被译者意见取代**；书内旧译「xxx教宗」作废，勿再用。人名 `Dereth (Derethi)` = 德雷西 不变，Derethi 派生词（德雷西祭司/信徒等）不动，教会**职衔**义「教宗」（如 现任教宗=信纳兰）照旧。
  - Aon 重名拆分：`Dao`（稳定、保障）= **多奥**、`Dio`（坚贞、稳固）= **戴奥**；同名侍灵 Seon Dao 同改 **多奥**（Seon Dio 维持戴奥）。人物 Daora/Daorn = 朵奥拉/戴奥恩 **未获裁定，不动**。
  - `Lyndel` = **林德尔**、`Ledder` = **莱德尔**（中文名不再相同 → 词条去 `(士兵)`/`(亚马兰士兵)` 消歧义）。

> 已落地书证译名（滚动更新）：见上文 §3「已落地批次（摘要）」与 §2 样例表；全量在 `dict/mistborn.json`。

## 7. 「仅出现于失落金属（tlm，无官方中译）」待补清单（Finding D）
> 这些词条所有 `{{book ref}}` 都指向 mb7/tlm，中英章节对齐暂无法采证；待《失落金属》官方中译后再补。部分可依据「同名已译书术语」推断但须标「推断未经书证」（如 Demoux 城 ← 人物 Demoux=德穆；Hammondar Bay 可能=哈蒙德湾）。
- tlm-only（94）：Abrem、Adawathwyn、Admiral Daal、Alicago、Basin Tires、Bastion (Scadrial)、Ben Oldson、Blantach、Blinker、Cali Hatthew、Call、Call and Son and Daughters…、Cassileux、Dao、Darkwater、Darlin Cett、Demmy、Demoux (city)、Dip、Drenya、Drunken Spur、Dug、Dulouis Building、Dumad、Dupon Melstrom、Elendel Supremacy Bill、Embrier、Fialia、Fion、Franis、Gabria、Garisel Daring、Gemdwyn、Getruda、Ghostbloods、Gord、Gorglen、Granks、Gregr、Hammondar Bay、Handerwym、Host、House of Proceedings、Icy Ben Oldson、Independence Tower、Jammi Walls、Jamms、Jaxy、Jeffy、Jonnes、Jub Hending、Kath、Kellen、Kelsier's seon、Kessi、Kyndlip Ternavyl、Lady Faula、Lady Gardre、LeeMar、Lily、Logshine、Macil、Maraga Dulcet、Maraya、Mari Hammondess、Mathingdaw、Mrs. Nock、Nomad Gang、Noseball、Pielle Fromed、Prasanva、Senator Vindel、Sentinel of Truth、Silajana、Silver House、Sir Squeekins、Steel Survivor、Tark Vestingdow、Tenny、Three-Tooth Dag、Tinweight Settlement、Tobal Copper、Varlance、Vennis Hasting、Versuli、Victori、Wan ShaiLu、Wayfarer、Wayne's mother、Wellid、West's Haven、Wilhelmette、Yancey Yaceczko、Yulip
- 说明：另有 58 条「mixed」（同时有已译书与 tlm ref），**可对齐**，不在本清单。

> **2025-10-16 补全轮复核确认的 pending（found=false，暂无法采证，勿再重跑）**：
> - 仅 tlm / 未译书无中译：Durkel、Maxillium Ladrian（Wax-Steris 之子，仅 mb7）、Ulaam（仅 mb7/tress）、Maxillium、Human (River)（mb7 prologue；mb3 该章未命名）、Paclo the Dusty 之外见 above。
> - 正文匿名 / 代号（中译无固定名）：Pull、Push（隐匪两名，正文仅以动作代号出现，wiki 为导航名）。
> - 报章插页被中译省略（Finding G）：Bastien Severington（名 Bastien）、Dorise Chevalle、Inis Julien、Terri（仅「警帽」道具引用，中译未具名）。
> - 现场编造的假名：Thomton Delacour（韦恩 mb6 ch4 临场虚构的时装设计师）。
