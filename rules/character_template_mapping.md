# Template:Character (EN) ↔ Template:Infobox character (CN) 字段对照

> 基于两站模板 wikitext 逐参数比对（2025-10-15）。EN 共 65 个参数，CN 共 84 个参数，**并非一一对应**。

## 一、可直接映射（EN → CN，33 项）

| EN 参数 | CN 参数 | 备注 |
|---|---|---|
| name | 人名 | |
| image | 图像 | |
| family | 家族 | |
| spouse | 配偶 | 注意实际词条可能写 `Spouse`（大小写不敏感） |
| children | 子嗣 | |
| ancestors | 祖先 | |
| descendants | 后代 | |
| relatives | 亲戚 | |
| siblings | 同辈 | 语义略宽（兄弟姐妹），惯例待确认 |
| parents | 家族 | ⚠️ CN 拆成 父亲/母亲，需按值拆 |
| born | 出生时间 | |
| died | 死亡时间 | |
| birthplace | 出生地点 | |
| residence | 村镇 | ⚠️ CN 拆 村镇/城市/国家/大陆 |
| abilities | 能力 | |
| bonded | 契约对象 | |
| skills | 能力 | |
| achievements | 其他补充 | |
| powers | 其他补充 | |
| titles | 头衔 | |
| aliases | 别名 | |
| profession | 职业 | |
| occupation | 职业 | |
| religion | 宗教 | |
| groups | 阵营 | |
| species | 种族 | |
| ethnicity | 民族 | |
| nationality | 国家 | |
| nation | 国家 | |
| world | 世界 | |
| universe | 分类 | ⚠️ 值 [[Cosmere]] 译作 三界宙 |
| era | 系列 | ⚠️ CN 无 时代，语义待确认 |
| introduced | 小说 | |

## 二、EN 参数（丢弃，32 项）

这些是模板内部 ref/raw/隐藏控制，不产出：

`unnamed` `merge-family` `hide-family` `hide-world` `image-artist` `earth`
`species-ref` `'species` `species-raw` `raw-species`
`birthplace-ref` `'birthplace` `birthplace-raw` `raw-birthplace`
`residence-ref` `'residence` `residence-raw` `raw-residence`
`ethnicity-ref` `'ethnicity` `ethnicity-raw` `raw-ethnicity`
`nation-ref` `'nation` `nationality-ref` `nation-raw` `raw-nation`
`world-ref` `'world` `world-raw` `raw-world`
`#profession` `{profession`

## 三、CN 参数（EN 无直接来源，54 项）

翻译/人工阶段填充或留空：

**图片/展示**：图二 图三 图四 图像信息 原名
**发音/名称**：发音 发音文件 其他译名 昵称 性别
**外貌**：发色 瞳色 肤色 服饰 服装 饰品
**能力/身份**：阶职 体系 死亡 死亡地点 文化 语言
**武器/随身**：武器 工具 坐骑
**关系细分**：继承人 儿子 女儿 恋人 好友 仇敌 上级 下属 师从 学徒 侍从
**地点细分**：城市 大陆
**媒体出场**：漫画 图画小说 动画 电影 电视剧 电子游戏 桌上游戏
**演员/配音**：电影演员 电视剧演员 动画配音 游戏配音
**其他**：extra1-5

## 结论 / 待办

- **机械转换只能填"第一节"里的 33 项**；其余要么留空，要么在翻译阶段由人/LLM 从正文、其他模板、站点分类推导。
- 待确认的语义点（siblings→同辈、residence 细分、era→系列、parents 拆分）→ 建议拿 1-2 个已有中文角色页（如卡拉丁）核对该站社区实际怎么填，再固化映射。
- 机器可自动产出 `unmapped` / `cn_only` 报告，供逐步积累。

## 主角页实证校验（2025-10-15，卡拉丁/沙兰·达瓦/阿多林·寇林/达力拿·寇林）

用 4 个英文主角页（Kaladin/Shallan/Adolin/Dalinar）的完整 `{{character}}` 调用与中文站对应页的信息框对照，确认/修正如下：

**已修正的 bug：**
- **前导撇号参数是真实值别名，不是 ref**：`'residence`/`'world`/`'nation`/`'species`/`'ethnicity`/`'birthplace` 带真实值（如 Kaladin `'residence={{tag|Hearthstone|...}}`）。原先误列入 drop，已改为「去掉前导撇号后按 field_map 查找」。
- `居住地` **不是 CN 模板的有效参数**（只是显示 label），阿多林页里的 `| 居住地 = ...` 是被模板忽略的多余参数 → 转换器不产出它，映射照旧用 `村镇/城市/国家/大陆`。

**对照中观察到的实际填法（供后续取值/翻译参考）：**
- `parents` 实际多值（`[[Lirin]], [[Hesina]]`）→ 中文站习惯拆成 `父亲=[[李伦]]`、`母亲=[[赫希拿]]`（转换器先并到 `家族`，翻译阶段再决定拆分）。
- `siblings` 中文主营页用 `同辈`（`同辈=[[提安]]（弟弟）`）。
- `universe=[[Cosmere]]` → 中文 `分类` 值应为 `三界宙`（属分类选项值）。
- EN 值里的日期/引用模板（`{{Rosharan date|1153}}`、`{{tag+|...}}`、`{{book ref}}`）翻译阶段需一并做 EN→CN 模板转换（决策 #6 的后续积累方向）。
- 中文主营页常在参数值里内嵌 `[[category:...]]` 与 `{{date/sa}}` 等本站专属约定，翻译后写入时参考所在页面惯例。

**下一步**：把 `{{Rosharan date}}`、`{{date}}`、`{{book ref}}` 等高频引用/日期模板纳入转换映射（这些是所有词条都用的）。

## 高频模板复用白名单（2025-10-15 确认）

多数模板中文站与英文站**共享同一套生态，同名且参数兼容，直接复用、不转换**。以 `Allik Neverfar` 全页实测：

| 模板 | 次数 | 中文站同名？ | 处理 |
|---|---|---|---|
| `book ref` | 54 | ✅ 同名，参数兼容（`{{b|书缩写|章}}`） | 直接复用 |
| `date` / `Date` | 5 | ✅ 同名，era 缩写（fe/fa/pc）兼容 | 直接复用 |
| `image` / `Image` | 3 | ✅ 同名（同一模板） | 直接复用 |
| `quote` | 2 | 中文 `Quote` | **重命名**（已实现） |
| `character` | 1 | 中文 `Infobox character` | **字段映射**（已实现） |
| `for` | 1 | ✅ 同名 | 直接复用 |
| `columns` | 1 | ✅ 同名 | 直接复用 |
| `partial` | 1 | ✅ 同名 | 直接复用 |
| `Mistborn` | 1 | ✅ 同名 | 直接复用 |

**结论**：真正需要"写转换规则"的模板很少（`character` 家族 + 个别改名）。绝大多数直接复用 → 转换器对它们保持原样即可（当前已如此：转换器只碰 character/quote）。
