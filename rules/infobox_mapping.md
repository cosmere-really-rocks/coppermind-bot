# Infobox 映射逐类型确认（EN {{X}} → CN {{Infobox X}}）2025-10-16

> 基于：中文站 14 个 `Template:Infobox X` 的**实际参数名**（读其 wikitext）＋ en_snapshot 里各类英文词条的**真实 infobox 调用参数**逐字段比对。
> 判据：中文站模板存在性 = `pageid`（含 character 在内 14 个目标模板全部存在，见 `rules/template_diff_audit.md` §二）。
>
> 通用规律（对几乎所有类型成立）：
> - `world` → `世界`；`universe` → `分类`（值 `[[Cosmere]]` 译三界宙）；`books` → `涉及书目`；`image` → `图像`；`type` → `类型`/各类型专名。
> - 英文 infobox 实际大多只填 `world/universe/books` + 个别专有字段，其余参数留空 → 转换时只映射"有值"字段即可，工作量大减。
> - CN 模板大量专有字段英文无来源 → 留空、翻译阶段/人工填充。

---

## 1. business（EN 15 → CN 16）

**可映射**
| EN | CN | 备注 |
|---|---|---|
| image | 图像 | |
| name | 行业名 | 原名=英文名保留 |
| owner / founder | 业主 | ⚠️ 两词碰撞同归「业主」 |
| leader | 业主 | 负责人归业主 |
| city | 城市 | |
| region | 地址 | 或 所属区域 |
| world | 世界 | |
| universe | 分类 | |
| books | 涉及书目 | |

**丢弃/需人工**：`era`（CN 无系列）、`logo`（并入图像或丢弃）、`products`/`services`（并入 类型/行业名，或丢弃）、`members`（CN 无）。CN 的 发音/别名/其他译名/地址/国家 由翻译阶段补。

## 2. group（EN 10 → CN 16）

**可映射**：image→图像、world→世界、universe→分类、books→涉及书目、type→类型、founders→组建者、leader/leaders→领袖、hq→总部、era→时代（CN 模板已加「时代」字段）。
**待人工**：CN 的 别名/其他译名/成员/发音/团体名(取标题)。

## 3. location（EN 6 → CN 45，CN 极细→大多留空）

EN 实际只有 `world/universe/books/city/region/map`：
- world→世界、universe→分类、books→涉及书目
- city→所属市县、region→所属区域
- `map`→地图（CN 模板已加「地图」字段，值为地图图片文件名；注意别与 `map ref` 混）
**待人工**：CN 45 参数里绝大多数（神瑛/神能/政体/统治者/历代执法者/物产资源/气候…）EN 无来源，留空。

## 4. culture（EN 7 → CN 13）

name→文化名、world→世界、universe→分类、books→涉及书目、type→类型、related→关联、era→时代、origin→起源（CN 模板已加「时代」「起源」字段）。

## 5. item（EN 10 → CN 15）

image→图像、name→物品名、world→世界、universe→分类、books→涉及书目、type→类型、creator/creators→创造者、owner/owners→所有者、function→用途。

## 6. literature（EN 7 → CN 14）

image→图像、world→世界、universe→分类、books→涉及书目、type→类型、author→作者、era→时期、name→文献名。

## 7. noble house（EN 6 → CN 16）

image→图像、name→家族名、world→世界、universe→分类、books→涉及书目、home→（CN 无"所在地"，丢弃或并入类型）、era→丢弃。
**待人工**：爵位/祖先/族长/前任族长/继承人/原名。

## 8. book（EN 15 → CN 25）

name→书名、cover→封面、released/date→发行日期（两源碰撞同归）、series→系列、prequel→上一本、sequel→下一本、setting→设定、publisher→出版社、ISBN→ISBN、page-count→页数。
**丢弃/需人工**：`annotations` `subpages` `word-count` `part`（CN 无）；CN 的 作者/译者/国家/语言/出版社/开本/页数等 部分英文 book 词条无 → 留空/人工。

## 9. lifeform（EN 5 → CN 17）

image→图像、world→世界、universe→分类、books→涉及书目、type→种类。CN 的 本领/用途/分布/习性/是否具备智慧 留空人工。

## 10. food（EN 4 → CN 20）

world→世界、universe→分类、books→涉及书目、type→类型。其余（产地/外观/气味/口味/原料/烹饪方法…）留空人工。

## 11. metal（EN 4 → CN 15，特殊：CN 为「金属技艺」模板）

EN metal 实参 `type`（如 God Metal）、`properties`、`hemalurgy`、`books`。CN metal 是金属技艺专用模板（推拉/内外/镕金术师/藏金术师/血金术师…）：
- type→类型（或 金属名）
- properties→?（CN 无"特性"字段，可并入 镕金术能力/藏金术能力 或丢弃）
- hemalurgy→血金术能力
- books→?（CN metal 无"涉及书目"）
> ⚠️ **metal 需要重点人工**：中文该模板专为「镕金术四类金属技艺」设计，与英文 god-metal/化合物条目不匹配。建议 god-metal（Harmonium/Trellium）用 `Infobox metal` 的改型，或单独建模板。

## 12. magic（EN 4 → CN 15）

world→世界、universe→分类、books→涉及书目、related→related（CN 保留英文参数 `related`/`focus`/`prereq`/`type`）。⚠️ CN magic 模板部分参数仍是英文（related/focus/prereq/type），需确认中文站是否已中文化，否则需手工。

## 13. disease（EN 3 → CN 12）

world→世界、universe→分类、books→涉及书目。CN 的 症状/治疗/类型 留空人工。EN disease 词条实际参数极少（books/universe/world）。

## 14. character（已完成，见 `rules/character_template_mapping.md`）

---

## 建议

1. 以上 13 类里，**9 类的映射是"通用字段 + 少量专有"**（group/location/culture/item/literature/lifeform/food/magic/disease），实现容易。
2. **business / book** 需处理「多源碰撞同归」（owner&founder→业主；released&date→发行日期）——这与 character 已处理过的 collision 机制一致。
3. **metal** 最特殊，需单独决定（god-metal 承载方式），建议作为人工 review 项。
4. 落地方式：把以上映射填进 `rules/template_map.json`（新增各 type 的 field_map/drop/collision），`convert_templates.py` 由"只支持 character"改为"按模板名查映射表"驱动。
