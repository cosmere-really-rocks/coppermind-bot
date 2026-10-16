# HANDOFF：epub 解压 / 章节重构（Trilogy + 中文 1-6 → 已全部落地）

> 更新：2025-10-16（本会话，第二次）
> 前一版（第一次会话）遗留的「Trilogy（3 本合集）与中文 1-6（partNNNN 流）需内容驱动重构」——**本次会话已用用户新传的**更清晰**分章版替代并全部完成**。

## 背景（为什么做这个）
为补全译名表缺失的全名译名（如 `Allik Neverfar`），方案是「中英 epub 章节对齐」：英文版定位关键词所在章+位置 → 中文版同章找官方译名。
系列构成与中文书名的完整说明已记入 `readme.md`「系列构成（Mistborn）」一节。

## 文件与目录（均不提交，已 gitignore）
- `dict/epub/`：原始 epub（z-lib/BookZZ 来源，受版权保护，本地处理）
- `dict/epub_out/`：**产出**的分章节 HTML（gitignore）
- `scripts/epub_prep.py`：epub 探针（--list / --find / --dump / --zh 同章对照）
- `scripts/extract_books.py`：把「一文件一章节」的英文书拆成分章节 HTML（第一批）
- `scripts/reconstruct_epub.py`：**本会话新增**的内容驱动重构（EN split 流 + 中文 cpNN/txtNNN/partNNN 合订）

## ✅ 全部已产出（dict/epub_out/）

### 第一批（第一次会话）：5 本干净英文书
| book | 章节数 | 说明 |
|---|---|---|
| the_alloy_of_law | 26 | 执法镕金（EN，时代二卷一） |
| shadows_of_self | 28 | 旧影森森（EN,时代二卷二） |
| the_bands_of_mourning | 34 | 悲悼护腕（EN,时代二卷三，含 postscript） |
| the_lost_metal | 75 | 失落金属（EN,时代二卷四） |
| secret_history | 33 | 秘史（EN,时代1.5） |

### 本会话新增（EN era1 三本 —— 之前只能从 Trilogy 合订处理，现已用 1.1~1.3 单行本）
| book（EN） | 章节数 | 结构 |
|---|---|---|
| the_final_empire | 40 | prologue + 1..38 + epilogue（split 流，bold 章节号） |
| the_well_of_ascension | 60 | 1..59 + epilogue（无 prologue；split 流） |
| the_hero_of_ages | 84 | prologue + 1..82 + epilogue（split 流） |

### 本会话新增（ZH 中文六本：era1 三本 + era2 三本，与上表 EN 一一对齐）
| book（ZH） | 章节数 | 与 EN 对齐 | 来源 | 说明 |
|---|---|---|---|---|
| zh_最后帝国 | 40 | = the_final_empire | 迷雾之子·01 单行本 | 楔子+1..38+尾声 |
| zh_升华之井 | **60** | = the_well_of_ascension | **mistborn_chs_1_6 合订→书二** | 1..59+尾声；**含第3章**（单行本缺第3章，故改从合订本取） |
| zh_永世英雄 | 84 | = the_hero_of_ages | 迷雾之子·03 单行本 | 序章/序曲+1..82+终曲 |
| zh_执法镕金 | 22 | = the_alloy_of_law | 迷雾之子外传（全三卷）合订 → 卷一 | **时代二卷一中译终于补上**（用户所说唯一缺单行本的一本） |
| zh_旧影森森 | 28 | = shadows_of_self | 外传 卷二 单行本 | 序言+1..26+尾声 |
| zh_悲悼护腕 | 34 | = the_bands_of_mourning | 外传 卷三 单行本 | 序言+1..31+尾声+后记 |

> 至此 era1 1-3 与 era2 1-3 共 6 本，**英文 + 中文均已分章 HTML 就绪**，可做中英章节对齐补全译名。
> - `[Sanderson]_The_Mistborn_Trilogy*.epub`（Trilogy 合订）已无需再处理——EN era1 改用 1.1/1.2/1.3 单行本。
> - `mistborn_chs_1_6.epub`（中文1-6 合订）**仍用于一处**：**升华之井**（书二）因单行本缺第3章，改从本合订取；其余书改从各单行本/外传全三卷取。

## 重构方法（reconstruct_epub.py）
- 按 spine 顺序扫描每个文件，用「标题锚点分类器」判断是否开启新章：
  - **开新章**：`PROLOGUE/EPILOGUE`、`楔子/序言`(prologue)、`尾声/终章/终曲`(epilogue)、`后记`(postscript)、裸数字章节号、`第X章`。
  - **非锚点**：front matter（第一个锚点前）整页丢弃；锚点后的 PART 页 / epigraph / 插图占位 / 空页 → 挂入缓冲，归属「下一个」新章。
  - **DROP 集合**：`目录/版权信息/前言/导读/鸣谢/致谢/作者简介/译者简介/镕金秘典/ARS ARCANUM` 等，无论位置一律整页丢弃（避免目录混入第一章）。
  - **内嵌 `###` 标题拆分**：合订本 part 文件常在一个文件里内嵌多章（如 `###尾声`），`inline_sections` 会据此把一个文件拆成多章（升华之井的 epilogue 即由此从 part0120 拆出）。
- 输出 `dict/epub_out/<book>/NNN_<chapter>.html`，编号从 0 起、与第一批命名一致。

## ⚠️ 已知源缺陷 / 采源决策
- **升华之井**：单行本 `迷雾之子·02*.epub` 缺第 3 章（chapter003 内容实为第 4 章）。**已改从 `mistborn_chs_1_6` 合订本（书二）提取完整版**（含第3章 + ###尾声 拆出的 epilogue），共 60 章与英文对齐。单行本仍保留在 `dict/epub/` 作备份，不再用于分章。
- **zh_旧影森森 序言**：序言正文存在（fow004，约 9.8k 字）。
- **zh_执法镕金** 取自「迷雾之子外传（全三卷）」合订的卷一部分（spine 2..29：版权页/目录/前言/鸣谢/序言/第1-20章/尾声/封面），分章干净。

## 下一步（建议）
1. 需补全译名时，用 `epub_prep.py` 对单本（不再对合订）：英文 `--find '<term>'` 定位所在章 → 中文同章找官方译名 → 回填 `dict/mistborn.json`（Marsh=沼泽、Cosmere=三界宙 为已定稿口径）。
2. 时代二四部曲名已入译名表：执法镕金/旧影森森/悲悼护腕/失落金属；各书分章 EN↔ZH 已可按同名 chapter 对齐。
