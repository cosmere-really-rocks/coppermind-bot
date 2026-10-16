# HANDOFF：epub 解压 / 章节重构（Trilogy + 中文 1-6）

> 生成：2025-10-16（本次会话）
> 用途：本会话已完成 5 本干净英文书的章节提取；**Trilogy（3 本合集）与中文 1-6（partNNNN 流）需要内容驱动重构，建议在新会话处理**。

## 背景（为什么做这个）
为补全译名表缺失的全名译名（如 `Allik Neverfar`），方案是「中英 epub 章节对齐」：英文版定位关键词所在章+位置 → 中文版同章找官方译名。
系列构成与中文书名的完整说明已记入 `readme.md`「系列构成（Mistborn）」一节。

## 文件与目录（均不提交，已 gitignore）
- `dict/epub/`：7 个原始 epub（z-lib/BookZZ 来源，受版权保护，本地处理）
- `dict/epub_out/`：**本会话已产出**的英文分章节 HTML（gitignore）
- `scripts/epub_prep.py`：epub 探针（--list / --find / --dump / --zh 同章对照）
- `scripts/extract_books.py`：把「一文件一章节」的英文书拆成分章节 HTML

## ✅ 本会话已完成：5 本干净英文书 → dict/epub_out/<book>/NNN_<chapter>.html
| book | 章节数 | 说明 |
|---|---|---|
| the_alloy_of_law | 26 | prologue+20+epilogue + 4 篇报章插页（978…_ch0N，独立保留） |
| shadows_of_self | 28 | prologue+26+epilogue |
| the_bands_of_mourning | 34 | prologue+31+epilogue+postscript |
| the_lost_metal | 75 | prologue+chapter1..74（split 片段已归并） |
| secret_history | 33 | Part-1..6 + N-M 小节 + Epilogue + Postscript |

提取规则要点（`extract_books.py`）：
- 正文章节 = `prologue`/`chapterN`/`epilogue`/`postscript`/`Part-N`/`N-M`；`chapter2_split_000/_001` 等 `_split_` 归并为同一章。
- 跳过 front/back matter（cover/title/dedication/acknowledgments/maps/contents/copyright/ads/newsletter/arcanum/torad…）。
- 输出为保留结构的干净 HTML（段落/标题/强调；图片降为 `[图:alt]` 文本；链接保留文本）。

## ⬜ 待处理（建议新会话）：2 本合集，需内容驱动重构
### A. The Mistborn Trilogy —— 3 本合集
- 文件：`dict/epub/[Sanderson_Brandon]_The_Mistborn_Trilogy_(Boxed_se(BookZZ.org).epub`
- spine：236 个 `CR!…_split_NNN.html`，**书/章边界不在文件名里**，需从正文识别。
- 任务：先按内容识别 3 本书的边界与每章的 `Chapter N` 标题，再重排为 3 个 `dict/epub_out/...`book 目录的分章 HTML。
- 参考：这 3 本是 Mistborn 1-3（The Final Empire / The Well of Ascension / The Hero of Ages）。

### B. 中文 1-6 —— 6 本合集（partNNNN 流，重点难点）
- 文件：`dict/epub/mistborn_chs_1_6.epub`
- spine：315 个 `OEBPS/Text/partNNNN.xhtml`，**书名/章节全靠正文识别**（正是"epub 不按章节整理"的典型）。
- 已探明结构：
  - `part0000` = 总目录（列出 6 本书：最后的帝国 / 升华之井 / 永世英雄 / 执法镕金 / 旧影森森 / 悲悼护腕）。
  - `part0003` = 每本 Contents（致谢/楔子/第一章…）。
  - 正文章：`part0005`楔子、`part0006`第一章、之后是连续编号小节（"1 1"、"2 2"…，即章内编号段落，**不是章**）。
  - 章节边界 = 形如「第一章 XXX」的标题文件/标题行；书边界 = 卷首书名页 + 内容里的书名。
- 任务：解析 315 个 part 文件 → 按内容识别 6 本书边界 + 每本内章边界 → 把编号小节归并入所属章 → 产 `dict/epub_out/<书名>/` 分章 HTML。
- 中文书名（用于子目录名）：迷雾之子卷一最后的帝国 / 卷二升华之井 / 卷三永世英雄 / 外传卷一执法镕金 / 外传卷二旧影森森 / 外传卷三悲悼护腕。

## 新会话开工建议
1. 先跑 `scripts/epub_prep.py <file> --list/--dump` 探查，再写按内容的分章重构脚本（可扩展 `extract_books.py`，或新写 `reconstruct_*.py`）。
2. 用 `part0000`/各书 Contents 站稳书/章锚点，再处理编号小节归并。
3. 产出都放 `dict/epub_out/`（已 gitignore）；不要提交任何 epub/正文。
4. 完成后即可做中英对齐：英文 `--find 'Allik Neverfar'` 定位，中文同章找官方译名，回填 `dict/mistborn.json`（Marsh=沼泽、Cosmere=三界宙 为已定稿口径）。
