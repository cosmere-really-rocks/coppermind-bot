# 迷雾之子·第二纪元（Mistborn Era 2）分类爬取与模板分析总览

> 生成：2025-10-16
> 数据：`Category:Mistborn_Era_2` 递归展开，共 **563 页**（9 子分类）全部抓取落盘，0 错误。索引 `state/en_index.json` 共 568 页。
> 限速：爬取间隔 0.8s（决议 #14），全程 682s，未触发反爬。

## 1. 分类规模
- 子分类 9 个：Elendel、Elendel Basin、Residents of Bilming、Residents of Elendel、Residents of Tinweight Settlement、Residents of Weathering、Set、Vanishers、Mistborn_Era_2（自身）
- 顶层直采 561 页 + 递归子分类补充，去重后 563 页
- 页面清单：`state/mistborn_era2_pages.json`

## 2. 页面类型分布（按主 infobox 模板归类，555 页可分类）
| 类型 | infobox 模板 | 页数 | 典型页 |
|---|---|---|---|
| 人物 | `character` | 311 | Allik Neverfar、Waxillium Ladrian、Wayne、Marasi Colms、Steris Harms |
| 城市/定居点 | `settlement` | 37 | Elendel、Bilming、New Seran、Weathering、Roughs |
| 商业/企业 | `business` | 35 | Basin Bill's Old Time Pub、Malwish Consortium |
| 地点/设施 | `architecture` | 31 | Ahlstrom Tower、Elendel University、Feder Tower |
| 团体/组织 | `group` | 24 | Set、Vanishers、Canton of Cartography |
| 节日/文化 | `culture` | 20 | Day of Founding、Survivorday、Harmontide |
| 地点(地域) | `location` | 20 | Flint's Hollow、Dampmere Park |
| 物品 | `item` | 15 | Bands of Mourning、Wax's earring、Trellium 相关 |
| 地理 | `geography` | 12 | Seran Range、Channerel Range、Irongate River |
| 作品/文献 | `literature` | 9 | The Elendel Daily、The House Record |
| 贵族家族 | `noble house` | 7 | House Ladrian、House Lekal、House Yomen |
| 交通工具 | `vehicle` | 7 | Brunstell、Wilg、Breaknaught |
| 书目(书籍) | `book` | 6 | The Alloy of Law、The Bands of Mourning、Shadows of Self |
| 事件 | `event` | 5 | Lady ZoBell's party、Yomen-Ostlin wedding dinner |
| 生物 | `lifeform` | 4 | Ornisaur、Hemalurgic chimera |
| 食物 | `food` | 3 | Logshine、Pectin-Ade |
| 国家/民族 | `nation` | 2 | Elendel Basin、Malwish Consortium |
| 金属 | `metal` | 2 | Harmonium、Trellium |
| 魔法/能力 | `magic` | 2 | Excisor、Twinborn |
| 神格 | `shard info` | 1 | Harmony |
| 疾病 | `disease` | 1 | Chillfever |

未按 infobox 归类的 13 页：各本小说的 `/Statistical analysis`、`Summary:XX` 摘要页、Harmony（shard info）、两位大写变体 `Business`/`Architecture`（实际即 business/architecture，MediaWiki 模板名大小写不敏感）。

## 3. 关键结论（★2025-10-16 重核，推翻旧结论）：中文站 **不** 与英文站同名共享 infobox
**旧结论有误，作废**：此前声称"中文站与英文站共有模板生态、infobox 同名全部存在、直接复用"，经 API 实测（`coppermind.huijiwiki.com` Template 命名空间全量拉取）**不成立**。

- 英文站这 20 种 infobox 模板名（`character`/`settlement`/`business`/…，均已在英文站确认存在）在中文站**几乎全部不存在同名模板**；
- 中文站 infobox 采用独立的 **`Infobox *`（Infobox 家族）命名体系**（共 36 个），如 `Infobox character` / `Infobox location` / `Infobox book`；
- 因此**不能同名直用，必须逐项做 EN→CN 模板映射 + 字段映射**（除少数如 `quote`→`Quote`、`event`→`Event` 恰好同名）。

实测结论：英文站使用这些 infobox 的 555 页，**没有一个能只靠"改名"就中文站直用**，绝大部分需要模板名 + 参数双重转换。

## 4. 权威 infobox 映射表（★2025-10-16 API 实测修正版）
> 依据：`action=query&titles=Template:<名>` 逐个探测存在性 + `list=embeddedin` 确认真实页面在用。EN 名均在英文站确认存在。

| EN infobox（类型） | 中文站对应模板 | 中文站同名？ | 实测依据 |
|---|---|---|---|
| `character`（人物） | `Infobox character` | ❌ | 存在且在用（如 须空/卡拉克） |
| `settlement`（城市/定居点） | `Infobox location` ⚠️ | ❌ | 无 `Infobox settlement`；`Infobox location` 存在并在用（玛拉特/柔刹）；用户裁决：settlement→location |
| `location`（地点/地域） | `Infobox location` | ❌ | 存在并在用 |
| `architecture`（地点/设施） | `Infobox location` ⚠️（待核） | ❌ | 无 `Infobox architecture`；按语义并入 location |
| `geography`（地理） | `Infobox location` ⚠️（待核） | ❌ | 无 `Infobox geography`；按语义并入 location |
| `business`（商业/企业） | `Infobox business` | ❌ | 存在并在用（公仆牌） |
| `group`（团体/组织） | `Infobox group` | ❌ | 存在 |
| `culture`（节日/文化） | `Infobox culture` | ❌ | 存在 |
| `item`（物品） | `Infobox item` | ❌ | 存在 |
| `literature`（作品/文献） | `Infobox literature` | ❌ | 存在 |
| `noble house`（贵族家族） | `Infobox noble house` | ❌ | 存在 |
| `book`（书目/书籍） | `Infobox book` | ❌ | 存在（`books` 是笔误，无此模板） |
| `event`（事件） | `Infobox event`（或 `Event`） | ✅ 同名 `Event` 也存在 | Infobox event 在用（灭世/驱逐）；`Template:event` 亦存在 |
| `lifeform`（生物） | `Infobox lifeform` | ❌ | 存在 |
| `food`（食物） | `Infobox food` | ❌ | 存在 |
| `metal`（金属） | `Infobox metal` | ❌ | 存在 |
| `magic`（魔法/能力） | `Infobox magic` | ❌ | 存在 |
| `shard info`（神格） | `Infobox shard` | ❌ | 存在并在用（和谐/灭绝/存留） |
| `disease`（疾病） | `Infobox disease` | ❌ | 存在 |
| `vehicle`（交通工具） | `Infobox vehicle` ✅ | 已建（pageid3494）并接入 `template_map.json` |
| `nation`（国家/民族） | `Infobox nation` ✅ | 已建（pageid3493）并接入 `template_map.json` |

✅ 已有字段映射经验：`character`→`Infobox character`（33 直接映射/32 丢弃/54 CN-only，见 `rules/template_map.json`）。
✅ 大部分已解决（2026-10-27 复核）：25 条映射见 `rules/template_map.json`（settlement/architecture/geography/nation/vehicle 模板均已建）；剩余＝逐字段映射残项复核（以 character 为样板，见 `rules/template_diff_audit.md` §五）。
🔗 关联：`quote`→`Quote`、`en`/`CmPermission`/`ensync` 三个页面包装模板中文站均已存在、直接复用。

## 5. 下一步推荐翻译重点（每种类型挑几篇典型，规模适中、结构标准）
- **人物**：Waxillium Ladrian（最大最全）、Marasi Colms、Steris Harms、Wayne（已有 4 主角经验）
- **城市**：Elendel（71807 字符，最全）、Bilming、New Seran
- **地点/设施**：Elendel University、Feder Tower（`architecture`，参数简单）
- **商业**：Basin Bill's Old Time Pub（`business`）
- **团体**：Set（`group`）、Vanishers
- **事件**：Lady ZoBell's party、Yomen-Ostlin wedding dinner（`event`）
- **物品**：Bands of Mourning（`item`）
- **地理**：Seran Range（`geography`，短小）
- **书目**：The Bands of Mourning（`book`，且与 Allik 关联）
- **贵族家族**：House Yomen（`noble house`）
- **交通工具**：Brunstell、Wilg（`vehicle`，与 Allik 关联）

先从「人物」与「简单 infobox（geography/location/event）」各试一篇，验证非 character 的 infobox 是否真能中文站同名直用，再铺开。
