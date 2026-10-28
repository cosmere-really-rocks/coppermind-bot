# Metal 模板映射方案（用户确认 metal↔中文 Infobox metal 对应后，先方案后动工）

> 状态：**仅方案，未动工**。用户要求先看怎么改再落地（2025-10-17）。
> 目标：把英文 `{{metal}}` 接入 `rules/template_map.json` 转换映射；中文 `Template:Infobox metal` 若有缺失字段则补齐。

## 一、双方字段现状

### 英文 `Template:Metal`（模板定义 + 实际使用）
文档化的参数：`name / allomancy / type-a / misting / feruchemy / type-f / ferring / hemalurgy / type-h / type / properties`。
实际词条还会用 `books`（如 Pewter、Harmonium 都有 `books=[[Mistborn Era 2]]`）。
- 神金场景（快照里的 Harmonium/Trellium）只用了：`type`（God Metal）、`properties`、`books`、`hemalurgy`。
- 普通金属场景（Pewter/Atium）用到 `type-a/type-f/type-h` 三元组 + 各能力字段。

### 中文 `Template:Infobox metal`（现有）
`金属名 / 原名 / 图像 / 图像信息 / 推拉 / 内外 / 分类 / 对应金属 / 其他译名 / 镕金术师 / 镕金术能力 / 藏金术师 / 藏金术能力 / 血金术师 / 血金术能力`（另有自动派生的 `metal/number`、`metal/letter`、`icon`）。

## 二、对应关系结论

### ✅ 安全的一一映射（可直接进 field_map）
| 英文 | → 中文 | 说明 |
|---|---|---|
| `name` | `金属名` | 金属名 |
| `allomancy` | `镕金术能力` | 镕金术能力 |
| `misting` | `镕金术师` | 镕金术师名 |
| `feruchemy` | `藏金术能力` | 藏金术能力 |
| `ferring` | `藏金术师` | 藏金术师名 |
| `hemalurgy` | `血金术能力` | 血金术能力 |

### ⚠️ 不能自动拆值、需人工/翻译阶段填（type 位置三元组）
| 英文 | 中文对应 | 为什么不自动映射 |
|---|---|---|
| `type-a` | 拆到 `推拉/内外/分类` | **语义不对应**：英文值如 Pewter=`Internal, Pushing, Physical`，但中文白镴填的是 `推拉=推 / 内外=外 / 分类=肢体力量`（Internal 对应到内外=外？）。中文站自有一套「推拉/内外/分类」语义，**无法从英文三元组可靠推导**，硬拆会错 |
| `type-f` | 中文藏金术无「位置」字段 | 中文只显示 藏金术能力/藏金术师，无 type 位置段 |
| `type-h` | 中文血金术无「位置」字段 | 同上 |

> 建议：`type-a/type-f/type-h` 在转换器里标 **unmapped**，交给翻译阶段按中文站既有语义人工/LLM 填写，不自动拆。

### 中文缺失、需补的字段（神金场景正是缺这几个）
| 英文 | 建议中文名 | 说明 |
|---|---|---|
| `type` | `类型`（或 `金属类型`）| **神金核心字段**（如 "God Metal (Harmony)"），中文目前完全没有，必补 |
| `properties` | `属性` | 神金常用（如 "Explode when mixed with water"），缺，需补 |
| `books` | `涉及书目` | 词条实际在用（`books=[[Mistborn Era 2]]`），中文无对应，需补 |

## 三、准备怎么改（落地步骤，未执行）

### 步骤 1：给中文 `Template:Infobox metal` 补 3 个字段
在现有模板尾部（below 之前）加一段：
```
|header40   ={{#if:{{{类型|}}}{{{属性|}}}{{{涉及书目|}}}|其他信息}}
|  label41  = 类型
|  data41   = {{{类型|}}}
|  label42  = 属性
|  data42   = {{{属性|}}}
|  label43  = 涉及书目
|  data43   = {{{涉及书目|}}}
```
（放在血金术块之后、`below` 之前；`涉及书目` 与其它 infobox 的 `涉及书目` 字段名一致。）

### 步骤 2：在 `rules/template_map.json` 加 `metal` 映射
```json
"metal": {
  "src_template": "metal",
  "dst_template": "Infobox metal",
  "field_map": {
    "name": "金属名", "allomancy": "镕金术能力", "misting": "镕金术师",
    "feruchemy": "藏金术能力", "ferring": "藏金术师", "hemalurgy": "血金术能力",
    "type": "类型", "properties": "属性", "books": "涉及书目"
  },
  "drop_always": [],
  "missing_cn_fields": ["type-a", "type-f", "type-h"]
}
```
- `type-a/type-f/type-h` 放进 `missing_cn_fields`，转换器会单独报告为「需人工补」，不会静默丢，也不会瞎拆。
- 中文站模板补字段后，转换器自动产出 `| 类型 = ...` `| 属性 = ...` `| 涉及书目 = ...`。

### 步骤 3：验证
- 用 `convert_templates.py --title Harmonium`（或 Trellium）确认 `{{metal}}` 正常转成 `{{Infobox metal}}`，输出 类型/属性/涉及书目。
- 用 `parse` API 确认渲染正确、三个新字段显示正常。

## 四、需要你拍板的点
1. **新字段名**：`type→类型`、`properties→属性`、`books→涉及书目` 这三个名字 OK 吗？还是用别的（如 `金属类型`/`特性`）？
2. **`type-a/type-f/type-h`**：确认按「不自动拆、交翻译阶段人工填」处理？（我强烈不建议自动拆，中文推拉/内外/分类语义和英文三元组对不上，硬拆会像 Pewter 那样内外=外错位。）
   - 或者：你希望我在中文模板里**再加**「镕金术位置 / 藏金术位置 / 血金术位置」字段来承接这三个原值？这样信息不丢但需补 3 个字段。
3. 是否要我在**中文 Infobox metal** 里把「对应金属」等字段如何从 `type-a` 系信息区分/填充也定下来（普通金属词条已有很多，需保证新字段不破坏现有填写）。

> 注：现有普通金属词条（白镴/锡/天金…）已用 Infobox metal，只加新字段、不动现有字段，不破坏它们。

---
## 五、落地状态（2025-10-17 已执行）
用户已拍板，模板已改：
1. 中文 `Template:Infobox metal` 已更新（revid 16719）：**删除 推拉/内外/分类**，新增 `类型`(type)/`属性`(properties)/`涉及书目`(books)，并在镕金/藏金/血金三块各加 `表位`（对应英文 `type-a/type-f/type-h`，值照英文原文）。
   - 渲染已验证：`类型/属性/涉及书目/表位` 均正常显示，旧的 `推拉/内外/分类` 不再显示。
2. `rules/template_map.json` 已加 `metal` 映射（9 个安全字段 + type-a/f/h 直通）。
3. ✅ **词条改造与验收（2026-10-28 终态）**：普查 23 词条**旧参数清零、六新字段与 EN 无缺、能力六字段 0 缺**（结构迁移早于本日已完成；本日验收轮修复残留渲染缺陷）：
   - `模板:icon` 第 4/5 位参无默认 → Symbol 缺文件的 6 页（和谐金/特雷金/雷瑟金/脉天金/银）显 `{{{4}}}|{{{5}}}` 字面 → 加空缺省（探针 5/5，回滚档 `state/rollback_20261028/icon_before_fix.wikitext`）；
   - 天金脚注裸 `<ref group="fn">` 套 wob/rpg 模板 → 孤 `</ref>` 错，改 EN 同款 `{{ref|group=fn|text=}}` 形；同类 神瑛×3/优弥/Nikaro/叶宁（裸 fn 套 `{{url ref}}`/`{{au ref}}` → 「冲突的组属性""」错）同修；
   - `模板:ref` text= 支 `group={{{group|}}}` 无条件发射空组 → 条件化（探针 4/4；根因：#12 四分支重写埋坑；`group=""` 平铺无害、**触发条件=裸 fn 内嵌套**，28 族模板经探针 U2 裁定免动）；
   - `[[飓光 Archive]]` 混血坏链 7 页 → `[[飓光志]]`（源级修复 5 页，柔刹/风与真理系搜索索引陈旧、源已净）；
   - 终验：23/23 页 `泄0 括0 错0 链0`、icon 非金属 4 用点 0 字面、表位渲染视检 ✓。普查/差距档：`state/metal_survey_20261028.json`、`state/metal_gaps_20261028.json`。
