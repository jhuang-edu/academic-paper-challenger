---
name: thesis-audit
description: >
  Universal three-stage audit skill for academic and degree theses (Markdown, Word .docx, and CSV/TSV/XLSX research logs).
  Covers Stage 1 five-dimension rapid defect blitz (leaks, cross-file drift, timeline paradoxes, arithmetic/unit errors, broken prose),
  Stage 2 statistical & cross-table data forensics, and Stage 3 AI-writing/fabrication authenticity diagnosis and remediation loops.
  Triggers: thesis audit, thesis check, paper audit, data forensics, 论文核查, 论文审计, 盲审自查, 终稿检查, 数据校验, 真实性质询.
license: MIT
metadata:
  version: "1.0.0"
  author: "jhuang-edu"
---

# Thesis Audit：通用学术与学位论文三阶极限审计

本 Skill 适用于**任意学科与载体**（`.md` / `.txt` / `.docx` 与 `.csv` / `.tsv` / `.xlsx`）的学位论文或期刊论文送审前压力测试，旨在通过“半小时找茬 + 全链路统计法医 + AI 与真实性破局”系统暴露隐患并建立三端同步闭环。

## 硬性边界与反误杀声明

1. **只审计与提出修正方案，严禁编造或篡改真值**：绝不捏造实验记录、访谈原话、文献 DOI、法条号或人为篡改原始实测数据以迎合统计检验；若真实机制导致高相关或特定分布，须引导补充测量学方法论说明与稳健性指标。
2. **证据锚定铁律**：每一条缺陷指控必须附带精确可复核锚点（`文件路径:行号`、`DOCX 段落/表格序号` 或 `CSV/XLSX 列名与统计量`）；无锚点指控禁止写入正式报告。
3. **单一事实源与跨载体同步**：任何修改必须按“原始数据/脚本 ↔ 分章/附录文稿 ↔ 合稿与排版终稿（DOCX/PDF）”链路同步核验，防止“修一处、裂三处”。
4. **反误杀边界（Clues, Not Blacklists）**：
   - 模式匹配、句长 CV、连接词密度与统计法医信号均属**审查线索**，不单独构成“AI 代写”或“数据造假”的定罪证据；
   - 保留学术文本必需的限定词（“可能”“初步”“在……条件下”）、否定范围、客观归因及合法平行结构，禁止为降 AI 率强行口语化或机械拆碎长句；
   - 本 Skill 旨在提升论文一致性与答辩抗压能力，**不保证**通过任何特定查重系统、AIGC 检测器或学校盲审。

## 核心原则（Non-Negotiable Principles）

1. **魔鬼代言人优先**：假设所有局部自检“全绿”均可能掩盖跨文件、表格解析或统计口径漏洞，以苛刻盲审评委视角主动质询。
2. **口径与统计零妥协**：分位数插值口径（`INC` vs `EXC`）、跨期折算基准、分母守恒与检验边界必须显式写明并可独立复算。
3. **跨学科与无数据豁免兼容**：覆盖工科、理科、社科、经管、医学论文；纯理论/纯质性无量化台账研究在 Stage 2 记录 `N/A` 豁免说明后直通 Stage 3。
4. **全链路闭环签核**：所有缺陷均须录入修复矩阵并经终稿复扫验证通过后，方可从 `Fixed` 转为 `Verified`。

## 三阶审计路由表

| 阶段 / 场景 | 首选工作流 | 配套清单 / 模板 | 参考方法论与脚本 |
|---|---|---|---|
| **Stage 1：半小时地毯式找茬**（D1–D5 全文缺陷定位） | [`workflows/stage-1-rapid-blitz.md`](workflows/stage-1-rapid-blitz.md) | [`checklists/rapid-audit-50pt-template.md`](checklists/rapid-audit-50pt-template.md) | [`references/five-dimension-taxonomy.md`](references/five-dimension-taxonomy.md) + `doc_leak_scanner.py` / `cross_table_reconciler.py` / `prose_rhythm_audit.py` |
| **Stage 2：全链路数据校验与统计挑战**（口径/复算/法医检测） | [`workflows/stage-2-data-forensics.md`](workflows/stage-2-data-forensics.md) | [`checklists/data-reconciliation-checklist.md`](checklists/data-reconciliation-checklist.md) | [`references/statistical-forensics-guide.md`](references/statistical-forensics-guide.md) + `data_forensics.py` / `cross_table_reconciler.py` |
| **Stage 3：AI 与编造真实性质询及破局**（破绽定位与闭环修复） | [`workflows/stage-3-authenticity-recovery.md`](workflows/stage-3-authenticity-recovery.md) | [`templates/remediation-matrix.md`](templates/remediation-matrix.md) | [`references/ai-and-fabrication-tells.md`](references/ai-and-fabrication-tells.md) + `prose_rhythm_audit.py` |
| **输出核查报告与交付门禁**（G1–G8 终极放行检查） | — | [`checklists/defense-and-blind-review-gate.md`](checklists/defense-and-blind-review-gate.md) + [`templates/audit-report-template.md`](templates/audit-report-template.md) | [`references/case-study-desensitized.md`](references/case-study-desensitized.md)（完全脱敏实战复盘） |

## 通用脚本速查（纯 Python 3.8+ 标准库）

```bash
# 1. 文档泄漏与合稿/分章指纹同步扫描 (.md/.txt/.docx)
python scripts/doc_leak_scanner.py --inputs <doc_or_dir...> [--compare <merged> <part1> <part2>...] [--rules <rules.json>] [--mode prose|cs] --format json

# 2. 跨表纵向/横向算术、合并单元格、图表编号连续性与清单对账
python scripts/cross_table_reconciler.py --docs <doc1> [<doc2>...] [--rules <reconcile.json>] [--tol 0.05] --format json

# 3. 台账统计复算与法医检验 (.csv/.tsv/.xlsx)
python scripts/data_forensics.py --input <data.csv|tsv|xlsx> [--sheet <name>] [--id-col <col>] [--group-col <col>] [--num-cols <c1,c2>] [--ref-col <col> --pred-col <col>] --alpha 0.05 --format json

# 4. 句长节奏 CV、机械断句残句与 AI 连接词/套话审计
python scripts/prose_rhythm_audit.py --inputs <doc_or_dir...> --lang auto --min-cv 0.35 --max-sent 160 [--exclude-headings 参考文献,致谢] [--buzzwords <json>] --format json

# 5. Skill 包自身结构、YAML、链接、纯标准库与测试合规自检
python scripts/validate_skill.py --run-tests --format json
```

## 终稿放行闸门（G1–G8）

详见 [`checklists/defense-and-blind-review-gate.md`](checklists/defense-and-blind-review-gate.md)。以下任一闸门为 `FAIL` 时，**禁止签发交付放行**：

| 闸门 | 核心要求 | 校验手段 |
|---|---|---|
| **G1 零符号与指令泄漏** | 无未渲染 `**`/`` ` ``/`>`/`<br>`/围栏、无旧行号/seed/裸变量、无未清理批注或修订 | [`scripts/doc_leak_scanner.py`](scripts/doc_leak_scanner.py) |
| **G2 跨载体内容一致** | 合稿、分章、附录与 `.docx` 样本属性、流程描述与结论无矛盾 | `doc_leak_scanner.py --compare` + 人工对照 |
| **G3 图表编号与索引同步** | 图/表编号连续、正文无孤儿引用、图清单/表清单页码与正文题注一致 | [`scripts/cross_table_reconciler.py`](scripts/cross_table_reconciler.py) |
| **G4 时序与状态机自洽** | 无复盘规则倒填事前实验、初版与修订版区分清晰、状态枚举全稿统一 | [`workflows/stage-1-rapid-blitz.md`](workflows/stage-1-rapid-blitz.md) (D3) |
| **G5 算术、量纲与口径全平** | 表格分项加总=小计/合计、跨期与年化量纲明确、样本量分母守恒 | `cross_table_reconciler.py` + [`scripts/data_forensics.py`](scripts/data_forensics.py) |
| **G6 统计法医红旗已处置** | 共线性/游程/末位数字/Benford/离群红旗已修正或补充方法论与稳健性解释 | `data_forensics.py` |
| **G7 断句残句与 AI 套话清零** | 无强行拆句残句，句长 CV 与衔接自然，无空泛三连排比与真空案例 | [`scripts/prose_rhythm_audit.py`](scripts/prose_rhythm_audit.py) |
| **G8 法条、文献与主体锚定** | 法规标准条款号与生效时态准确、文献迁移逻辑成立、脱敏化名全稿统一 | 人工核验 + `doc_leak_scanner.py` |

## 反模式（Anti-Patterns）

- 仅因单篇自检脚本输出全绿就放弃人工对照最终 Word/PDF 成品。
- 直接在最终排版 Word 手改文字或数字，却不同步回源分章文稿、合稿与渲染脚本。
- 仅凭单个高频连接词或单句长度就武断判定“AI 代写”，或为压字数/拉高 CV 把正常长句强行劈成病句。
- 为消除高相关性或游程告警而擅自篡改原始实验实测数值。
- 不加锚点（`file:line` / `tbl:rXcY`）或跳过修复后回归验证就将问题标为已解决。
