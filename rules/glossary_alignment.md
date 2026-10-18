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

### 已落地书证译名（第二轮 pilot，2025-10-16）
| key | zh | note | 书证章 |
|---|---|---|---|
| Allik Neverfar | 亚历克·奈弗法 | 全名 | 悲悼护腕 ch21 |
| Allik | 亚历克（别名 阿里克） | 官方书证 | 多书 |
| Red | 雷德 | 依蓝德运河船夫 | 旧影森森 ch5 |
| Irongate River | 铁门河 | 依蓝德盆地主河 | 旧影森森 ch18 / 悲悼护腕 ch4 |
| Carlo’s Bend | 卡罗湾 | 依蓝德盆地（已有，书证核验） | 执法镕金 ch15 |
| Trell | 特雷 | 神（独盟化身）；宗教=特雷教 | 执法镕金 ch11/尾声、最后帝国 ch9 |
| Trellism | 特雷教 | 时代二宗教 | 执法镕金 ch11 |
| Trelagism | 特雷教 | 时代一旧宗教（与 Trellism 中译同） | 最后帝国 ch9 |
| Nelazan | 奈拉禅 | 崇拜特雷的北方民族 | 最后帝国 ch9 |

**地理/地点批（subagent）：**
| key | zh | note | 书证章 |
|---|---|---|---|
| Seran Range | 赛朗山脉 | Seran 全系列统一=赛朗 | 悲悼护腕 ch22 |
| Seran River | 赛朗河 | | 悲悼护腕 ch7 |
| Glimmering Point | 光点 | 光点码头 | 悲悼护腕 ch4 |
| Stansel Belt | 斯坦瑟尔环路 | 词条快照误引执法镕金，实证在悲悼护腕 ch4 | 悲悼护腕 ch4 |
| Sea of Yomend | —（未得） | mb1 地图-only（灾后名），正文无；另「尤门」实为 Yomen 家族 | — |

**批量人物/定居点批（subagent，2025-10-16）：** 详见 `dict/mistborn.json`。
- 人物批 A（Dashir boys…Eriola，19 条）：18 条已录（旧影森森/悲悼护腕），1 条未得（Dorise Chevalle，报章插页被中译省略，Finding G）。
- 人物批 B（Evenstrom Tekiel…Hughes Entrone，15 条）：15 条全录；兼证 House Tekiel=太齐尔、Captain Demoux=德穆队长。
- 人物批 C（Idashwy…Jendel，8 条）：7 条全录；1 条未得（Inis Julien，New Ascendancy 报章插页被中译省略，Finding G）。
- 定居点（subagent 前段 + 剩余批 + 复核）：Elmsdel=埃尔姆斯德尔、Rashekin=拉舍金、Wiestlow=威斯特洛、Doriel (city)=多瑞尔、New Seran=新赛朗、Dulsing=道廷镇、Ironstand=铁岗镇、Thermoli=瑟莫利、Tathingdwel=塔辛德维尔 已录；Corbeau、Tarier 未得（报章插页/地图-only）；The Village 无固定专名（随上下文=村/村寨）。
- 地理/地点：见上表。

**批量人物批 D（Alernath…Chapaou，subagent，2025-10-16，继续 A/B/C 之后）：** 详见 `dict/mistborn.json`。
- 全录（执法镕金/旧影森森/悲悼护腕）：Alernath=亚勒纳斯、Allri Innate=亚莉·因内特、Allriandre Durkel=亚莉安德、Ape Manton=亚佩·曼顿、Aramine=亚拉敏（亚拉敏教授）、Arintol=亚林托尔、Augustin Tekiel=奥古斯丁·太齐尔、Aunt Gin=金姨、Aving Cett=亚凡·塞特、Bilmy=比尔米、Blome=布洛米、Boris Junior=小鲍里斯、Boris the Third=鲍里斯家的老三、Burlow=布罗、Caberel=卡贝雷尔、Chapaou=查波欧。
- 1 条部分采证：Bastien Severington——姓 Severington=瑟维灵顿（悲悼护腕 ch14/15，正文有证）；名 Bastien 仅见于第六章报章插页被中译省略 → **pending 待人工补全名**。

**批量人物批 E→F（Chip…Winsting，subagent + 直接书证，2025-10-16 续完）：** 覆盖上一批之后剩余的全部 era2 可采证人物，详见 `dict/mistborn.json`。
- 已录代表（执法镕金/旧影森森/悲悼护腕，均为官方书证）：Chip(奇普)、Claude Aradel=克劳德·亚拉戴尔、Daius=戴尤斯、Darriance=达李恩斯、Jordis=约蒂丝、Joshin Yomen=约辛·尤门、Kelesina Shores=克雷西娜、Lady ZoBell=佐贝尔夫人、Lord Barrington=巴灵顿大人、Lord Stenet=史提内特领主、Marasi Colms=玛拉茜·科尔姆斯、Marksman=神射手、Brettin=布雷廷、Murnbru=蒙布鲁、Paclo=帕克罗（尘染者）、Peret the Black=黑手佩瑞特、Rian=利恩、Rick Stranger=里克·斯特朗格、Replar Innate=雷普拉·因内特、Slink=斯灵克、Sophi Tarcsel=索菲·塔瑟尔、Spook=鬼影、Steris Harms=史特芮丝·哈姆斯、Tarson=塔森、Telsin Ladrian=苔尔辛、Tindwyl Ladrian=廷朵·拉德利安、Vwafendal=瓦范达尔、Waxillium Ladrian=瓦克斯利姆·拉德利安、Winsting Innate=温斯汀、Petrine=佩崔恩 等（共约 90 条）。
- 本轮新增 pending（found=false，无法采证）：Durkel、Maxillium Ladrian、Ulaam（仅 tlm 无中译）；Pull、Push（正文匿名代号，中译无固定名）；Terri（仅「警帽」道具引用，中译未具名）；Thomton Delacour（韦恩现场编造的假名）；+ 前批 Bastien Severington、Dorise Chevalle、Inis Julien。

**批量非人物批 G（企业/团体/事件/文化/家族/物品等，2025-10-16，把译名表从「仅人物」扩到所有 E2+E1 可采证类型）：** 详见 `dict/mistborn.json`。
- 企业/商业：Ashweather Carriage and Coach=灰侯车马场、Gavil's Carriages=加维马车行、Findley's=芬得利餐厅、Citizen Magistrates=市民公仆牌(雪茄)、Syles=塞尔斯白兰地、Immerling Arms=艾莫林(手枪)、Terringul 27=泰林格尔27型、Sterrion 36=史特里昂36型、Granger 28=格兰杰28型、Ambersair=安博萨、Rioting=莱廷枪(枪械，非煽动)、Invarian steel=因伐利安钢、Emotional Allomancy parlors=安抚之厅/煽动之厅、The Weeping Bull=牛泣酒馆、Tingmar=廷格玛雪茄、The Elendel Daily=依蓝戴日报、Barrington carriage=巴灵顿(型马车)。
- 团体：Originators=创始者、Preservers=存留者、Hidden Guard=秘卫、Nightstreet Gang=夜匪帮、Surefires=神火帮、Cobblers=光脚帮、Deniers of Masks=面具驳阻者、Men of gold and red=金红之人。
- 事件/节日/文化：Yomen-Ostlin wedding dinner=尤门·欧斯特林婚宴、Lady ZoBell's party=佐贝尔夫人的派对、Kelesina Shores's party=克雷西娜·肖尔斯的派对、Winsting Innate's auction=拍卖会、Allomantic Agreement of '94=镕金术94号公约、The Path=道(宗教，信徒=道徒)、Mareweather=迈尔、Evanotype=照片、Southern Scadrian=南方人、Jaggenmire=轧亘米尔。
- 家族（House X=族，按书证）：House Innate=因内特家族、House Ladrian=拉德利安家族、House Harms=哈姆斯家族、House Yomen=尤门家族、House Lekal=雷卡家、House Hammondess=哈姆德家族。
- 其他：Elendel Basin=依蓝戴盆地、Excisor=切除器、Chillfever=寒热病、Wilg=柳影号、Brunstell=布伦斯特尔号、Destroyer=毁灭者、Docksithium=多克森之书、The Last Breath=《最后的气息》。Elendel=依蓝戴（书证146处一致，修源表伊兰黛尔市）。
- 本轮新增 pending（found=false）：仅 tlm 无中译——Tarcsel Electric、Community、Malwish Consortium、Plank Boys、Admiral Daal's warship、Hemalurgic chimera、Human (River)、Sea of Yomend、Corbeau、Tarier；报章插页被省略——Survivor's Treasure、Linville & Lyons（House Record）；中译意译未成专名——Soonie pup、Roseweather、Wax's earring（仅作「耳环」）、Seran New District Cemetery（新赛朗墓地）、Truefast；正文无书证——Canton of Cartography、House Demoux。

**批量书证批次 H（全系列补扫，2026-10-18，`state/glossary_caizheng/`）：** 从 `Category:Mistborn` 1116 页快照提取 327 条候选词条，按 `state/mistborn_glossary_terms.json` 逐批 `batch_*.json`/`miss_*.json`（复用 `glossary_assist.py` 中英章节对齐）书证采证，汇总 `consolidated.json` = **168 ok + 159 pending**；168 条已并入 `dict/mistborn.json`（脚本 `scripts/glossary_caizheng_merge.py`，全表 796→961）。
- 已录类别代表：人物（Kelsier=卡西尔、Dockson=多克森、Redd=雷德、Kale Tekiel=凯尔·太齐尔、Straff Venture=史特拉夫·泛图尔、Zane Venture=詹·泛图尔、Themos Tresting=赛摩斯·特雷斯廷、Jess=洁丝 等）；家族（House Venture=泛图尔、House Geffenry=詹芬利家族、House Hasting=海斯丁家族、House Cett=塞特家族 等，均与既有同名家族一致）；地理/统御区（Central/Eastern/Northern/Southern/Western Dominance=各统御区、Terris Dominance=泰瑞司统御区、Luth-Davn Canal=陆沙德运河）；机构/事件（Canton of Inquisition=审判廷、Luthadel Garrison=陆沙德警备队、Battle of Luthadel=陆沙德之战、Siege of Luthadel=陆沙德围城战）；物品/文化（Mistcloak=迷雾斗篷、Spikeway=金属大道、Pek=佩币、Streetspice=迷幻药、Shakewelts=颤抖症）；金属/祝福（Aluminum=铝、Gold=金、Silver=银、Blessing of Awareness/Presence/Stability=各祝福）。
- 本轮新增 pending 159 条（found=false，勿重跑，待中译出版/新书证）：仅 tlm/密史无中译（Aledin、Audil Lekal、Kallib、Leonore、Ever-Slaying Sword、Iyatil、Axindweth、Moash、Vasher、Kabsal 等）；维基子页/元信息（各 `/Statistical analysis`、`/Epigraphs`、`Summary:...`、铁血/地盘的表格页签 etc）；正文无书证的地名/人物（Lake Luthadel、Tresting plantation、Cameron's safe house、House Penrod、Midge 等）；中译意译未成专名（Charred=焦黑形容词、Fets=「下棋」）；报章/扩展内容（Alloy of Law: Masks of the Past、Mistborn Adventure Game 等桌游）。完整清单 `state/glossary_caizheng/pending_archive.md`。

## 4. 与既有规则的关系 / 需更正的旧决定
- `rules/allik_terms.md` 旧「用户裁决」称 **Allik Neverfar 专名不翻译、保留英文**——**本轮用户改向**：
  - 现在**以官方中译本为准**，Allik Neverfar=**亚历克·奈弗法**（不是中文站「阿利克·纳法尔」、也不是旧表「阿里克」）。`rules/allik_terms.md` 需按此更正。
  - 「原文引用不翻译」决议（#4/#13）**仍有效**：`{{quote}}` 台词/称号列表等仍不硬翻；但「名+敬称」这类**正文叙述短语**（非台词quote，是 prose）可用于书证。

## 5. 下一步（建议，待用户确认方向）
1. 把 `glossary_alignment.md` 定为批量补全的作业规范；先小批量（人物/地理/歧义各若干）跑通后铺开，勿一次性全量。
2. 定夺数据模型扩展：`renderings`（长语块替换）+ `variants`（同名多义）是否落地。
3. 对「仅 tlm 出现」的词条单独列清单，供失落金属中译出版后补。

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
- ⬜ 定夺数据模型扩展：`renderings` + `variants`。
- ⬜ 批量补全：人物（全名搜全/拆姓分名）→ 地理/地点 → 歧义词条，各挑几篇跑通后铺开。
- ⬜ 整理「仅 tlm 出现」词条清单（如 Demoux (city)、The Two Seasons）。
- ⬜ 补全后回填 `rules/*.md` 并提交译名表。

> 已落地书证译名（滚动更新）：见上文「### 已落地书证译名（第二轮 pilot）」表。

## 7. 「仅出现于失落金属（tlm，无官方中译）」待补清单（Finding D）
> 这些词条所有 `{{book ref}}` 都指向 mb7/tlm，中英章节对齐暂无法采证；待《失落金属》官方中译后再补。部分可依据「同名已译书术语」推断但须标「推断未经书证」（如 Demoux 城 ← 人物 Demoux=德穆；Hammondar Bay 可能=哈蒙德湾）。
- tlm-only（94）：Abrem、Adawathwyn、Admiral Daal、Alicago、Basin Tires、Bastion (Scadrial)、Ben Oldson、Blantach、Blinker、Cali Hatthew、Call、Call and Son and Daughters…、Cassileux、Dao、Darkwater、Darlin Cett、Demmy、Demoux (city)、Dip、Drenya、Drunken Spur、Dug、Dulouis Building、Dumad、Dupon Melstrom、Elendel Supremacy Bill、Embrier、Fialia、Fion、Franis、Gabria、Garisel Daring、Gemdwyn、Getruda、Ghostbloods、Gord、Gorglen、Granks、Gregr、Hammondar Bay、Handerwym、Host、House of Proceedings、Icy Ben Oldson、Independence Tower、Jammi Walls、Jamms、Jaxy、Jeffy、Jonnes、Jub Hending、Kath、Kellen、Kelsier's seon、Kessi、Kyndlip Ternavyl、Lady Faula、Lady Gardre、LeeMar、Lily、Logshine、Macil、Maraga Dulcet、Maraya、Mari Hammondess、Mathingdaw、Mrs. Nock、Nomad Gang、Noseball、Pielle Fromed、Prasanva、Senator Vindel、Sentinel of Truth、Silajana、Silver House、Sir Squeekins、Steel Survivor、Tark Vestingdow、Tenny、Three-Tooth Dag、Tinweight Settlement、Tobal Copper、Varlance、Vennis Hasting、Versuli、Victori、Wan ShaiLu、Wayfarer、Wayne's mother、Wellid、West's Haven、Wilhelmette、Yancey Yaceczko、Yulip
- 说明：另有 58 条「mixed」（同时有已译书与 tlm ref），**可对齐**，不在本清单。

> **2025-10-16 补全轮复核确认的 pending（found=false，暂无法采证，勿再重跑）**：
> - 仅 tlm / 未译书无中译：Durkel、Maxillium Ladrian（Wax-Steris 之子，仅 mb7）、Ulaam（仅 mb7/tress）、Maxillium、Human (River)（mb7 prologue；mb3 该章未命名）、Paclo the Dusty 之外见 above。
> - 正文匿名 / 代号（中译无固定名）：Pull、Push（隐匪两名，正文仅以动作代号出现，wiki 为导航名）。
> - 报章插页被中译省略（Finding G）：Bastien Severington（名 Bastien）、Dorise Chevalle、Inis Julien、Terri（仅「警帽」道具引用，中译未具名）。
> - 现场编造的假名：Thomton Delacour（韦恩 mb6 ch4 临场虚构的时装设计师）。
