---
name: academic-paper-challenger
description: >
  Universal three-stage academic thesis & paper audit and data/authenticity challenger skill
  (integrating two-layer primary-source verification with automated data forensics across Markdown, Word .docx, LaTeX, PDF, and CSV/TSV/XLSX).
  Covers Stage 1 (First Pass 50-100 issue blitz across D1-D5, rubric band checks & format-aware intake with MD5/multi-rule word count baseline),
  Stage 2 (Second Pass primary-source verification [Confirmed/Discrepancy/Unverifiable/Serious Error] & automated statistical/cross-table data challenge),
  and Stage 3 (Graded authenticity & AI-writing interrogation weighing forensic signals vs. counter-evidence, correction ledger, and optional rotating follow-up rounds).
  Triggers: thesis audit, thesis challenger, paper audit, data challenge, data forensics, 论文核查, 论文挑战, 找50个问题, 挑战数据, 真实性质询, 盲审自查.
license: MIT
metadata:
  version: "1.2.0"
  author: "jhuang-edu"
---

# Academic Paper Challenger：通用学术论文核查、数据挑战与真实性质询

本 Skill 融合了**“两层一手来源考官核查法（First Pass + Primary-Source Second Pass）”**与**“自动化跨表/统计数据法医挑战 + AI 代写与编造真实性破局”**，适用于**任意学科与载体**（`.md` / `.txt` / `.docx` / `.tex` / `.pdf` 与 `.csv` / `.tsv` / `.xlsx`）的学位论文或期刊论文送审前极限压力测试。

## 收稿与动态定基线（Format-Aware Intake & Re-baselining）

1. **收稿四问与底稿对齐**：获取论文文件与学校/期刊要求文档（或评分标准 Rubric）；确认是**草稿（Draft）还是终稿（Final）**；确认**问题目标数**（默认 `50` 或 `100` 条，绝不拿琐碎弱问题凑数，不够则实话实说）；建议作者一并提供早期草稿与导师指导记录。
2. **按格式分流提取**：Word 用原生 OpenXML / `python-docx`；PDF 用 `pdftotext` 提文本并用 `pdfinfo` 记录作者/生成器/创建时间作为取证信号；LaTeX 直接做源码静态审计；数据台账读取 `.csv/.tsv/.xlsx`。
3. **多口径字数矩阵与 MD5 哈希基线**：
   - 按**每种可能口径**各算一遍字数并并排记录（仅正文、正文+摘要、含标点全字符、中文字+英文词元），终结字数达标争议；
   - 记录文件 `MD5` 哈希与修改时间戳；复查中若收到新版本，自动重新定基线并与旧提取底本 `diff`，仅复核改动段落及其下游依赖项。

## 硬性边界与三大铁律

1. **只审计与提出修正方案，严禁编造或篡改真值**：绝不捏造实验记录、访谈原话、文献 DOI、法条号或人为篡改原始实测值以迎合统计检验；若真实机制导致高相关或特定分布，须引导补充测量学方法论说明与稳健性指标。
2. **证据锚定与一手来源铁律（Primary-Source Rule）**：
   - 首轮每条缺陷必须附带精确锚点（`file:line`、`docx:part:pX/tblY` 或 `CSV列名`）与可执行改法；**严重级别拿不准时一律往高定一级并写明风险理由**（`S0/Blocker` 阻断提交、`S1/Major` 影响评分或答辩、`S2-S3/Minor` 影响观感）；
   - 第二轮核验引用的每个一手来源（官方公布法条、出版商/DOI 索引、法院/监管通报、标准原文）**必须亲自打开核实，搜索结果摘要（Snippet）或二手转述页绝不算一手来源**；未核实的数字绝不写成“已证实”。
3. **真实性三对分离与分级结论铁律（Graded Authenticity）**：
   - 任何时候严格区分三对判断：**查不到 $\neq$ 编造**；**高度疑似 AI 辅助 $\neq$ 纯 AI 生成**；**引用马虎 $\neq$ 引用造假**；
   - 必须将**取证信号**（异常元数据、凌晨创建时间、AI 手术线头、零摩擦真空案例、未卜先知字典、脚注与文献脱节、互不相关引用访问日期雷同）与**反证**（作者确实做出的精准专业区分，如法条例外条款或相近理论辨析）放在天平两端一起称重，给出**分级结论**并列出定稿前需补充的证明材料（查重报告、早期草稿、指导记录）。

## 三阶核查与挑战路由表

| 阶段 / 核心任务 | 首选工作流 | 配套清单 / 模板 | 参考方法论与自动化脚本 |
|---|---|---|---|
| **Stage 1（Pass 1）：收稿定基线 + 半小时五维找茬**（D1–D5 + Rubric 逐档 + 学科自适应找 50/100 问） | [`workflows/stage-1-rapid-blitz.md`](workflows/stage-1-rapid-blitz.md) | [`checklists/rapid-audit-50pt-template.md`](checklists/rapid-audit-50pt-template.md) | [`references/five-dimension-taxonomy.md`](references/five-dimension-taxonomy.md) + `doc_leak_scanner.py` / `cross_table_reconciler.py` / `prose_rhythm_audit.py` |
| **Stage 2（Pass 2）：一手来源全量复核 + 数据统计法医挑战**（四大核验结论 + 跨表平账 + 合成信号挑战） | [`workflows/stage-2-data-forensics.md`](workflows/stage-2-data-forensics.md) | [`checklists/data-reconciliation-checklist.md`](checklists/data-reconciliation-checklist.md) | [`references/statistical-forensics-guide.md`](references/statistical-forensics-guide.md) + `data_forensics.py` / `cross_table_reconciler.py` |
| **Stage 3：AI 与编造真实性质询、破局、修正账与可选短轮查**（信号/反证称重 + 三端同步 + 空轮即停） | [`workflows/stage-3-authenticity-recovery.md`](workflows/stage-3-authenticity-recovery.md) | [`templates/remediation-matrix.md`](templates/remediation-matrix.md)（含**修正账 Correction Ledger**） | [`references/ai-and-fabrication-tells.md`](references/ai-and-fabrication-tells.md) + `prose_rhythm_audit.py` |
| **输出核查报告与交付门禁**（G1–G8 终极放行检查） | — | [`checklists/defense-and-blind-review-gate.md`](checklists/defense-and-blind-review-gate.md) + [`templates/audit-report-template.md`](templates/audit-report-template.md) | [`references/case-study-desensitized.md`](references/case-study-desensitized.md)（脱敏实战复盘） |

## 通用自动化脚本速查（100% 纯 Python 3.8+ 标准库，零外部依赖）

```bash
# 1. 文档泄漏、内部指令/未渲染符号扫描与合稿/分章指纹同步比对 (.md/.txt/.docx)
python scripts/doc_leak_scanner.py --inputs <doc_or_dir...> [--compare <merged> <part1> <part2>...] [--rules <rules.json>] [--mode prose|cs] --format json

# 2. 跨表纵向/横向算术、合并单元格、图表编号连续性与清单对账
python scripts/cross_table_reconciler.py --docs <doc1> [<doc2>...] [--rules <reconcile.json>] [--tol 0.05] --format json

# 3. 台账统计复算与数据法医挑战 (.csv/.tsv/.xlsx：双口径IQR、共线性 r>0.90、游程检验、末位数字、Benford、Kappa/McNemar)
python scripts/data_forensics.py --input <data.csv|tsv|xlsx> [--sheet <name>] [--id-col <col>] [--group-col <col>] [--num-cols <c1,c2>] [--ref-col <col> --pred-col <col>] --alpha 0.05 --format json

# 4. 句长节奏 CV、机械断句残句（如“然而。”）与 AI 连接词/套话审计
python scripts/prose_rhythm_audit.py --inputs <doc_or_dir...> --lang auto --min-cv 0.35 --max-sent 160 [--exclude-headings 参考文献,致谢] [--buzzwords <json>] --format json

# 5. Skill 包自身结构、YAML、链接、纯标准库与测试合规自检
python scripts/validate_skill.py --run-tests --format json
```

## 终稿放行闸门（G1–G8）

以下任一闸门为 `FAIL` 时，**禁止签发终稿交付放行**：
- **G1 零符号与指令泄漏**：无未渲染 `**`/`` ` ``/`>`/`<br>`/围栏、无旧行号/随机种子/裸变量名、无未清理批注或修订；
- **G2 跨载体单一事实源一致**：合稿、分章、附录与 `.docx` 样本属性、流程描述与结论零冲突；
- **G3 图表编号与索引同步**：图/表编号连续、正文无孤儿引用、图清单/表清单页码与正文题注一致；
- **G4 时序与状态机自洽**：无复盘规则倒填事前实验、初版（`v1.0`）与修订版（`v1.2`）区分清晰、状态枚举全稿统一；
- **G5 算术、量纲与一手来源全平**：表格分项加总=小计/合计、跨期与年化量纲明确、Pass 2 一手来源核验无 `Serious Error`；
- **G6 统计法医红旗已处置**：共线性/游程/末位数字/Benford/离群红旗已修正或补充测量学方法论与稳健性解释；
- **G7 断句残句与 AI 套话清零**：无机械拆句残句，句长 CV 与衔接自然，无空泛三连排比与零摩擦真空案例；
- **G8 法条、文献与主体锚定**：法规条款号与生效期（完稿日之前）准确、文献迁移逻辑成立、脱敏化名全稿统一、争议项已记入《修正账》。
