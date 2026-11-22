# Stage 1：半小时地毯式极限找茬工作流（Rapid 5-Dim Blitz）

本工作流用于在送审、预答辩或投稿前 30 分钟内，通过“自动化扫描 + 五维人工突击”，系统定位所有内部穿帮、跨载体分裂、时序悖论、算术错账与机械残句隐患，形成带精确锚点的待修台账。

---

## 1. 触发条件与适用场景

- 论文初稿/终稿已合成，准备交付盲审、外审、预答辩或期刊投稿；
- 论文已完成本地格式检查或单脚本自检且看似“全绿”，但需要以苛刻审稿人视角执行压力测试；
- 多人协作合稿或历经多轮大模型辅助润色后，怀疑存在版本分裂、残余指令或隐性逻辑打架。

## 2. 输入参数与前置准备

开始前明确以下四个输入要素：
- **`TARGET_DOCS`**：待审主文稿路径（支持 `.md` / `.txt` / `.docx`，若存在分章与附录文件请一并纳入）；
- **`MERGED_DOC` & `PART_DOCS`**（可选）：若采用“分章写作 + 合并总稿”架构，需提供总稿路径与有序分章列表，用于段落指纹同步比对；
- **`CUSTOM_RULES`**（可选）：项目自定义禁用词、白名单术语与否定窗口 JSON 配置；
- **`DISCIPLINE`**：学科类型 `engineering | science | social_science | business | medical | general`，用于切换 D3/D4/D5 人工深挖焦点。

## 3. 自动化脚本命令

按以下顺序执行三项零依赖脚本，并将 JSON 输出留存供锚点核查：

```bash
# 1. 内部指令、符号残留与合稿/分章指纹同步扫描
python scripts/doc_leak_scanner.py --inputs <main_doc_or_dir> [--compare <merged> <part1> <part2>...] [--rules <rules.json>] [--mode prose|cs] --format json

# 2. 跨表纵向/横向算术、图表编号连续性与目录清单一致性对账
python scripts/cross_table_reconciler.py --docs <doc1> [<doc2>...] [--rules <reconcile.json>] --tol 0.05 --format json

# 3. 句长节奏 CV、机械断句残句与高频连接词/破折号初筛
python scripts/prose_rhythm_audit.py --inputs <doc_or_dir> --lang auto --min-cv 0.35 --max-sent 160 [--exclude-headings 参考文献,致谢] --format json
```

> 若在纯文本环境（如 `.tex` 或导出 `.pdf` 纯文本）运行，请先转换为 `.txt` 或 `.md` 后传入 `--inputs`；对计算机/工程含大量行内代码变量的文稿，可将 `--mode` 设为 `cs`。

## 4. 人工深挖步骤（30 分钟五维时间盒）

按 [`references/five-dimension-taxonomy.md`](../references/five-dimension-taxonomy.md) 定义的 D1–D5 顺序逐一突击，并对照 [`checklists/rapid-audit-50pt-template.md`](../checklists/rapid-audit-50pt-template.md) 逐项标记：

1. **D1 内部产物与指令穿帮（5 分钟）**
   - 核查标题、三级目录与摘要中是否残留“防越界指令”（如“仅锁定某两项问题”）、“本版本/旧稿”自指词、顶部未删替换批注；
   - 核查正文与表格是否印出调试随机种子（如 `seed=42`）、旧草稿行号（如 `L204`）、内部脚本编号或未渲染代码变量名。
2. **D2 跨载体分裂与排版残留（6 分钟）**
   - 直接打开最终渲染交付件（Word `.docx` / PDF），抽检表格与正文段落是否存在未解析的 `**`、`` ` ``、`<br>`、`>` 或代码围栏；
   - 逐条核对“图清单 / 表清单”与正文实际图题注、表题注及页码是否同步，重点检查附录样本描述、抽样数量、流程叙述是否与正文结论打架。
3. **D3 时序穿越与规则—数据冲突（7 分钟）**
   - 画出“研究时间轴”与“方案/字典版本演进线”（例如初版 `v1.0` vs 复盘版 `v1.2`），严查是否把事后复盘才发现的规则倒填进事前实验；
   - **学科适配焦点**：
     - *工科/理科*：消融基线版本混淆、超参数冻结时点与测试集泄露；
     - *社科/经管*：试运行软性提示与正式上线硬性阻断混淆、双盲施测者编制与洗脱期矛盾；
     - *医学*：入排标准修订时点、回顾性病例窗口期与随访截止期冲突。
4. **D4 跨表算术、量纲与逻辑闭环（7 分钟）**
   - 核查投入产出表或消融对比表的左右分项合计、上下小计/总计是否精确相等；
   - 核查是否存在跨期总量（如 1.5 年或 18 个月累计）与年化指标混写，核查组织分工表（RACI/贡献声明）角色名称是否在预算或审计章节悬空。
5. **D5 机械残句、时间线与引证错配（5 分钟）**
   - 抽检连词短句（如“然而。”“第二。”）和悬空主语+引述动词句（如“……研究表明。”）；
   - 逐项核对所引法规、国家标准、行业指南在论文调研与完稿时点的**生效状态**（未施行/过渡期/已废止），并复核核心外文参考文献观点与正文场景的迁移逻辑是否断裂。

## 5. 输出产物

- 按 [`templates/audit-report-template.md`](../templates/audit-report-template.md) 生成 Stage 1 审计明细表，每条问题必须包含唯一 ID、维度 `D1–D5`、严重度 `S0–S3` 与精确锚点（`file:line` 或 `docx:part:pX/tblY`）；
- 将所有未关闭缺陷录入 [`templates/remediation-matrix.md`](../templates/remediation-matrix.md) 作为后续统一修复台账。

## 6. 退出门禁

1. `doc_leak_scanner.py`、`cross_table_reconciler.py` 与 `prose_rhythm_audit.py` 三个自动化脚本均无异常报错完成执行；
2. D1–D5 五大维度及 50 点清单模板全部完成一轮人工核验（不适用项须明确标记 `N/A` 并简述理由）；
3. 全部已定位缺陷均已带精确锚点写入修复矩阵，准备进入 Stage 2 数据校验。
