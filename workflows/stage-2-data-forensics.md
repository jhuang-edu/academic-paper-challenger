# Stage 2：全链路数据校验与统计法医挑战工作流（Data Forensics）

本工作流站在苛刻统计审稿人与盲审评委视角，对论文中的实测台账、实验日志、问卷数据或对比表格执行**“计算复算 + 统计法医扫描”**双层审计，并给出合伦理的破局处置路径。

---

## 1. 触发条件与快速豁免分支

- **常规触发**：论文包含定量表格、实验记录台账（`.csv` / `.tsv` / `.xlsx`）、分组描述统计量、混淆矩阵或跨期折算指标；
- **纯理论 / 纯质性论文快速豁免（N/A 分支）**：若论文属于纯数学推导、规范法学、纯文献综述或无量化统计的纯定性研究，请在审计报告 Stage 2 栏注明“本研究不含定量实验台账与统计汇总表，经核验适用 `N/A` 豁免”，随后直接进入 [`workflows/stage-3-authenticity-recovery.md`](stage-3-authenticity-recovery.md)。实证类论文严禁使用此豁免。

## 2. 输入参数与前置准备

- **`DATA_FILES`**：原始实验或调研数据文件（`.csv` / `.tsv` / `.xlsx`，多工作表需明确 `--sheet`）；
- **`SCHEMA_MAP`**：编号列 `--id-col`、分组列 `--group-col`、核心数值列 `--num-cols`、人工真值与系统预测对照列 `--ref-col` & `--pred-col`；
- **`MANUSCRIPT_DOCS`**：正文与附录文稿（用于跨表比对和复算结果对齐）；
- **`RECONCILE_RULES`**（可选）：自定义跨表逻辑断言 JSON。

## 3. 自动化脚本命令

```bash
# 1. 台账全量描述统计、双口径 IQR、共线性、游程、末位数字、Benford 与混淆矩阵法医扫描
python scripts/data_forensics.py \
  --input <ledger.csv|tsv|xlsx> \
  [--sheet <sheet_name>] \
  [--id-col <id_column>] \
  [--group-col <group_column>] \
  [--num-cols <col1,col2,...>] \
  [--ref-col <truth_col> --pred-col <pred_col>] \
  --corr-threshold 0.90 --alpha 0.05 --format json

# 2. 正文二维表算术加总与自定义跨表公式断言核查
python scripts/cross_table_reconciler.py --docs <manuscript_docs...> [--rules <reconcile.json>] --tol 0.05 --format json
```

## 4. 人工深挖与合伦理破局步骤

结合 [`references/statistical-forensics-guide.md`](../references/statistical-forensics-guide.md) 与 [`checklists/data-reconciliation-checklist.md`](../checklists/data-reconciliation-checklist.md) 依次推进三层核查：

### 第一层：复算精度与分母守恒核对
1. **双口径四分位距核验**：比对脚本输出的 `q1_inc / q3_inc / iqr_inc`（对应线性插值 `PERCENTILE.INC`）与 `q1_exc / q3_exc / iqr_exc`（互斥法 `PERCENTILE.EXC`），确认正文表格与哪种口径一致，并在表注或方法节明确写明所选四分位数算法口径；
2. **衍生统计与检验一致性**：复核均值、标准差（`ddof=1`）、中位数、分层样本加总是否严格等于总体 $N$，复核混淆矩阵 `TP/FP/TN/FN`、一致率、Cohen's $\kappa$ 与 McNemar 检验（小样本不均衡格 $b+c < 25$ 应优先采信精确二项检验 $p_{\text{exact}}$）；
3. **跨期折算与取整尾差**：若存在由长周期折算为年化均值导致的分项加和与总计差 `0.1`，须核实原始精确总值并在表注写明“分项按四舍五入列示，合计按精确值计算”。

### 第二层：统计法医红旗成因鉴别（多学科视角）
针对 `data_forensics.py` 检出的告警，严禁简单粗暴判定“作假”，必须先鉴别真实物理/测量成因与人为合成痕迹：
- **高共线性（$|r| \ge 0.90$ 或 $|\rho| \ge 0.90$）**：
  - *工科/理科*：是否源自同一传感通道、同一物理量纲线性换算或共同样本复杂度基线；
  - *社科/经管/医学*：是否源自同一被试完成前后两项任务的共同阅读/作答基线，抑或人为按公式 $y = ax + b + \epsilon$ 构造。
- **游程检验异常（$p < 0.05$）**：区分“按分组编号交替归档台账（未记录实际随机呈现序）”与“人为分段拼接/刻意排序数据”。
- **末位数字偏态与固定小数步长**：核查界面计时精度（如以 `0.1` 或 `0.5` 单位取整）或仪器分辨率是否天然造成末位聚集。
- **Benford 检验适用边界**：仅当正值样本 $n \ge 30$ 且跨越至少 1 个数量级（`max / min >= 10`）时才具参考意义，窄区间耗时或 1–5 分量表不得滥用 Benford 判伪。

### 第三层：合伦理破局决策（严禁篡改真值）
1. **发现计算错误或口径笔误**：立即修正正文与附表数值，统一标明统计口径；
2. **确认数据系拼凑或无原始依据**：冻结提交，退回重新采集真实数据或删除不可信试验分支；
3. **属真实测量机制引发的表观规律（如共同基线高相关、归档序游程聚簇）**：**严禁手动改写实测值去迎合检验**；必须在方法论章节如实补充测量过程说明（如随机打乱呈现序、取整粒度、共同基线效应）及稳健性补充指标（如中位数/IQR、去极值敏感性均值、分亚组统计）。

## 5. 输出产物

- 完成勾选并带实测证据摘要的 [`checklists/data-reconciliation-checklist.md`](../checklists/data-reconciliation-checklist.md)；
- 将各数值列复算比对结果、红旗处置定论及需补充的方法论段落建议填入 [`templates/audit-report-template.md`](../templates/audit-report-template.md) 与 [`templates/remediation-matrix.md`](../templates/remediation-matrix.md)。

## 6. 退出门禁

1. 所有正文中出现的数据表跨行、跨列及跨文件算术偏差均在声明容差范围内（默认 `<= 0.05` 或已注记四舍五入说明）；
2. 分位数计算口径、样本量分母守恒与检验方法已在方法论或表注中显式交代；
3. `data_forensics.py` 检出的每一项红旗均已形成明确归因与闭环处置动作，无悬而未决的“疑似合成”隐患。
