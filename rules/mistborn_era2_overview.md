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

## 3. 关键结论：中文站与英文站共享模板生态
对全部 20 种 infobox 模板做中文站核对，**中文站同名模板全部存在**：

character、settlement、business、architecture、group、culture、location、item、geography、noble house、vehicle、book、event、lifeform、food、nation、metal、magic、shard info、books —— 中文站 `Template:XXX` 均存在。

说明英文站的整套模板（含 101 种里绝大多数）在中文站**同名兼容、直接复用**，只有少数（如 `character`→`Infobox character`）中文站用不同名/结构。**与 character 不同，处地点/事件/物品等的 infobox 大概率直接复用，无需改名**（待逐模板参数校验）。

## 4. 权威 infobox 映射表（revision 用）
EN `character` → CN `Infobox character`（已验证，需字段映射）
EN `quote` → CN `Quote`（已验证）
其余 infobox（settlement/business/...）→ **中文站同名直接复用**（待逐模板参数核对，作为下一步工作）

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
