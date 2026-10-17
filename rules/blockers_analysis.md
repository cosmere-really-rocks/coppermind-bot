# 已下载英文词条（568）转中文的卡点排查（2025-10-17 批量实测）

> 方法：对 `en_snapshot/` 全部 568 个词条做 convert（`convert_templates.py --json`，无 LLM）全量扫描 + 对中国站模板存在性探测 + 抽查已译词条。
> 目的：回答「已下载英文词条转中文，还有哪些卡点」。

## 进度基线
568 下载 → 26 已 convert → 6 已 translate/写站。管线 `fetch→convert→translate→write` 各环节**均已跑通**。

## ✅ 已确认非卡点
| 环节 | 结论 | 依据 |
|---|---|---|
| 模板转换 | **无硬堵**。542 篇未转换词条 convert 全部成功，无进程错误、无 missing_cn。 | 全量扫描 |
| 所谓「unmapped」 | 只是**有意不映射的字段**，非卡点：`noble house` 的 era/universe/home（中文 Infobox 无对应）、`shard info` 的 books、`settlement` 的 name、`character` 的 positional 参数——均按设计留给翻译阶段处理。 | template_map 注释 + 抽查 |
| translate 阶段 | 可用。dry-run 正常（分块 + 译名表命中 + 提示词）。 | `Abrem` dry-run |
| 模板口径 | 非 meta 模板已建站（migrate_templates.py 11 个）；缺失的 meta 类已决议「drop」。 | probe_resolution.md |

## 🔴 真实卡点

### 卡点 1（管线级 · 最大）：meta/维护模板未 drop，穿透进输出 —— ✅ 已修复
- **805 处**穿透：`{{complete}}`×473、`{{partial}}`×74、`{{update}}`×34、`{{expand}}`×27、`{{meta/*}}`×12、`{{demoted}}`×3、`{{stub}}`×2、`{{nosnippet}}`×2、`{{dialogue}}`×1、`{{edit note}}`×1、`{{user:*}}`×1。
- 实测：`Abrem` 转换保留 `{{complete}}`；已译 `Allik Neverfar` 翻译保留 `{{partial}}`。
- **已修**（2025-10-17）：用户决议 `complete`/`partial`/`stub` **保留**（中文站同名 Complete/Partial/Stub 语义等价，473/74/2 处原样保留）；`update`/`expand`/`meta:*/demoted/nosnippet/dialogue/edit note/user:*` **drop**；`nosnippet` 为内容包装、drop 时 unwrap 保留内文。落地在 `convert_templates.py` 递归 `_apply_drop`（处理嵌套模板），`translate.py` 在内存重转自动继承。**全量 568 词条节点级验证：0 残留、保留项精确对齐。**（见 readme 待办 13）

### 卡点 2（依赖当前任务）：metal 术语未定
- 只影响英文快照里的 `Harmonium`/`Trellium` 2 篇（用 `{{metal}}`）+ 中文站 ~20 个金属词条更新。**不影响其余 566 篇的批量管线**。
- 待翻译姐姐确认 Spiritual/Cognitive/Mental·Enhancement 中译 + type-a 呈现后落地（当前任务）。

### 卡点 3（治理级）：批量写站前需定白名单/黑名单/redirect/图片 review
- 568 篇里 ~80% 中文站**尚不存在**（样本 40：8 存在 / 32 缺失 ≈ 需新建 ~450 页）。
- readme 待办 7-8：正式批量写真实内容**前**需先定白名单范围、黑名单（File 不自动上传图、Template 已按 #16 例外处理）、redirect 搬运、图片校验与人工 review——避免覆盖真实内容。

## 建议推进顺序
1. ✅ **卡点 1（meta drop）已修复**（2025-10-17，`convert_templates.py` 递归 `_apply_drop`，568 词条节点级验证通过）。
2. 等**翻译姐姐**敲定 metal 术语（卡点 2 解除）→ 改金属模板/词条。
3. 确定**批量写站范围**（卡点 3，白名单/治理）后再大规模 write；否则 ~450 页全量写站有覆盖/无序风险。
