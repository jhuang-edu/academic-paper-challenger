# Academic Paper Challenger 极简审核体验示范 (Minimal Audit Demo)

本目录提供了一个开箱即用的微型学术论文审核用例，演示如何在 1 分钟内通过 `academic-paper-challenger` 纯 Python 标准库工具链完成快速找茬（Stage 1）、跨表加总核对（Stage 2）以及文风节奏审计（Stage 3）。

---

## 1. 包含文件

- `sample_paper.md`：包含完整图表清单、规范题注、三线表及货币符号（`¥`）的极简学术文稿样例。
- `audit_rules.json`：声明式的跨表与单元成本求和断言规则（演示将“自动化分拣组”与“人工复核组”单元总成本求和并核验是否等于“合计”）。

---

## 2. 一键体验运行命令

在仓库根目录下打开终端，依次运行以下命令体验各阶段核心功能：

### 步骤 1：Stage 1 格式规范与指令残留扫描
扫描文稿中是否存在 TODO、未解析 Markdown 标记、未闭合 HTML 标签或内部提示词泄露：
```bash
python scripts/doc_leak_scanner.py --inputs examples/minimal-audit-demo/sample_paper.md --format text
```
- **预期结果**：`STATUS: PASS`，未发现任何指令泄漏或未闭合标记。

### 步骤 2：Stage 2 跨表加总与业务规则核算
校验三线表内的行/列和是否匹配，并基于 `audit_rules.json` 自动解析前缀货币符号（如 `¥1500` 与 `¥500`）执行断言求和：
```bash
python scripts/cross_table_reconciler.py --docs examples/minimal-audit-demo/sample_paper.md --rules examples/minimal-audit-demo/audit_rules.json --format text
```
- **预期结果**：`STATUS: PASS`，跨表规则 `RULE_TOTAL_COST_SUM` 验证通过（1920 + 2400 == 4320）。

### 步骤 3：Stage 3 散文节奏与去 AI 腔调审计
评估句长分布变异系数（CV）、超长句比例以及模板化连接词密度：
```bash
python scripts/prose_rhythm_audit.py --inputs examples/minimal-audit-demo/sample_paper.md --format text
```
- **预期结果**：`STATUS: PASS`，句长变异系数自然，无超长句与机械套话。

---

## 3. 进阶使用

更多高级统计挑战（如双口径 IQR、游程检验、Benford 法则及卡方拟合）与 DOCX/XLSX 深度审查，请参考根目录 `README.md` 与 `workflows/` 详细指南。
