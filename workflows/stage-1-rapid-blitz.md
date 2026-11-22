# Stage 1（Pass 1）：收稿定基线 + 半小时地毯式五维找茬工作流（Rapid 5-Dim Blitz & First Pass）

本工作流融合了**全格式收稿定基线（Format-Aware Intake & MD5 Re-baselining）**与**“自动化扫描 + 五维人工突击 + 评分标准（Rubric）逐档核对”**，在送审、预答辩或投稿前 30 分钟内，系统定位 50–100 个内部穿帮、跨载体分裂、时序悖论、算术错账、机械残句与学科合规硬伤，形成带精确锚点与严重度定级的首轮问题台账（First-Pass Issue List）。

---

## 1. 收稿与定基线规程（Intake & Baseline Protocol）

在开始找问题前，先完成以下 6 项基线动作：
1. **索要双文档与状态门确认**：向用户确认待审论文文件及管辖该论文的**要求文档/排版模板/评分标准（Rubric）**；确认当前是**草稿（Draft）还是终稿（Final）**（如未签名的独创性声明、缺失的导师指导记录在终稿中属阻断级问题）；记录截稿日；确认**问题目标数**（默认 `50` 或 `100` 条；**铁律：绝不拿琐碎弱问题凑数，也绝不把同一问题换个编号重复报；若论文在达到目标数前已无真问题，直接如实告知**）。
2. **按文件类型分流收稿**：
   - **Word (`.docx`) / Markdown (`.md`) / 纯文本 (`.txt`)**：直接传入 `doc_leak_scanner.py`、`cross_table_reconciler.py` 与 `prose_rhythm_audit.py` 原生解析；
   - **PDF (`.pdf`)**：用 `pdftotext` 提取文本底本，并用 `pdfinfo` 检查元数据（记录作者、Creator 生成工具、CreationDate 创建时间作为 Stage 3 取证信号，不单独作为定罪结论）；
   - **LaTeX (`.tex`)**：直接对源码做静态审计（注明本地无编译器时无法核验物理渲染页数）。
3. **多口径字数矩阵（Multi-Rule Word Count Matrix）**：
   - 按**每一种可能的学校/期刊口径**各算一遍字数并全部记录在报告开头（① 仅正文［第 1 章至结论］、② 正文+中英文摘要、③ 全书含参考文献与附录、④ 纯汉字+英文词元 vs 含标点字符数），确保任何字数上限/下限争议只需指着矩阵中的某一行即可定夺。
4. **MD5 哈希与增量重定基线（MD5 Hash & Incremental Diff Re-baseline）**：
   - 记录文件 `MD5` 哈希与修改时间戳；
   - 若在复查周期内收到作者修改后的新版本，记录新 `MD5` 与时间戳，将新提取文本与旧底本做 `diff`，仅复核改动过的段落及其下游依赖项（如汇总表、摘要、结论），并将重定基线记录写入轮次日志。

---

## 2. 自动化脚本命令（纯 Python 3.8+ 标准库）

按以下顺序执行三项零依赖脚本，并将 JSON 输出留存供锚点核查：

```bash
# 1. 内部指令、符号残留与合稿/分章指纹同步扫描
python scripts/doc_leak_scanner.py --inputs <main_doc_or_dir> [--compare <merged> <part1> <part2>...] [--rules <rules.json>] [--mode prose|cs] --format json

# 2. 跨表纵向/横向算术、图表编号连续性与目录清单一致性对账
python scripts/cross_table_reconciler.py --docs <doc1> [<doc2>...] [--rules <reconcile.json>] --tol 0.05 --format json

# 3. 句长节奏 CV、机械断句残句与高频连接词/破折号初筛
python scripts/prose_rhythm_audit.py --inputs <doc_or_dir> --lang auto --min-cv 0.35 --max-sent 160 [--exclude-headings 参考文献,致谢] --format json
```

---

## 3. 人工深挖步骤（30 分钟五维时间盒 + Rubric 逐档核查）

按 [`references/five-dimension-taxonomy.md`](../references/five-dimension-taxonomy.md) 定义的 D1–D5 顺序逐一突击，并对照 [`checklists/rapid-audit-50pt-template.md`](../checklists/rapid-audit-50pt-template.md) 与学校评分标准（Rubric band-by-band）逐项标记：

1. **D1 内部产物与指令穿帮（5 分钟）**
   - 核查标题、三级目录与摘要中是否残留“防越界指令”（如“仅锁定某两项问题”）、“本版本/V3”自指词、顶部未删替换批注；
   - 核查正文与表格是否印出调试随机种子（如 `seed=42`）、旧草稿行号（如 `L197`）、内部辅助文件名（如 `对应 07 P2 防线`）或未渲染代码变量名（如 `trace=0`、`dept_decision`）。
2. **D2 跨载体分裂与排版残留（6 分钟）**
   - 直接打开最终渲染交付件（Word `.docx` / PDF），抽检表格与正文段落是否存在未解析的 `**`、`` ` ``、`<br>`、行首 `>` 或代码围栏 ```` ```text ````；
   - 逐条核对“图清单 / 表清单”与正文实际图题注、表题注及页码是否同步，重点检查**附录样本描述、抽样数量、学历/结局、双盲协议是否与正文第 3–5 章及结论正面打架**。
3. **D3 时序穿越、规则—数据冲突与学科自适应深挖（7 分钟）**
   - 画出“研究时间轴”与“方案/字典版本演进线”（例如初版 `v1.0` vs 复盘版 `v1.2`），严查是否把事后复盘才发现的规则倒填进事前实验；
   - **学科自适应核查焦点（Discipline-Matched Checks）**：
     - *法学（Law）*：核查法条条号与内容是否张冠李戴（如把跨境评估/侵权责任条文当成去标识化条文）、指导性案例/裁判文书号、司法解释生效与废止期；
     - *计算机/AI（Computing & AI）*：核查代码库与出版方记录、重算分类/回归指标、核查消融基线版本、索要并核对模型版本/温度参数/System Prompt 与测试集隔离；
     - *经管/MBA（Business & Management）*：核查历史业务台账与抽样框配额、跨表工时与财务 ROI 账本（防范“为了省 8 小时花 40 小时维护”的负 ROI 伪需求）、访谈受访者编码与企业化名脱敏一致性；
     - *理科/医学（Science & Medicine）*：核查实验原始记录、物理单位与量纲、入排标准修订时点、伦理审批号与临床试验注册号。
4. **D4 跨表算术、量纲与逻辑闭环（7 分钟）**
   - 核查投入产出表或对比表的左右分项合计、上下小计/总计是否精确相等；
   - 核查是否存在跨期总量（如 18 个月累计数）与年化指标（12 个月折算数）混写在同一对比行，核查组织分工表（RACI）角色名称是否在后文悬空。
5. **D5 机械残句、时间线与引证错配（5 分钟）**
   - 抽检连词短句（如“然而。”“第二。”）和悬空主语+引述动词句（如“……强调。”“……研究表明。”）；
   - 逐项核对所引法规、国家标准在论文调研与完稿时点的**生效状态**（并检查是否有引用文献发表日期晚于论文完稿日），复核核心外文文献观点与正文场景的迁移逻辑。

---

## 4. 严重度定级铁律（Severity Tiering Rule）

每条问题必须赋予明确严重级别，**当级别拿不准时，一律往高定一级并写明风险理由（Unclear severity goes up, with reasons）**，让作者看清最高风险而非被软化后的标签：
- **`S0 / Blocker`（致命阻断）**：导致无法提交、格式/字数硬线不达标、暴露 AI 提示词/旧行号穿帮、正文与附录事实 180 度反转、法条/核心数据严重造假；
- **`S1 / Major`（重大缺陷）**：直接影响盲审评分档次或答辩通过（如跨表算术不等、时序穿越、负 ROI 商业逻辑漏洞、机械切句残句簇）；
- **`S2–S3 / Minor`（一般瑕疵与润色）**：影响版面观感、审稿人阅读体验或局部稳健性说明。

---

## 5. 输出产物与退出门禁

- 按 [`templates/audit-report-template.md`](../templates/audit-report-template.md) 生成 Stage 1（First Pass）连续编号问题清单（每条含唯一连续编号、维度 `D1–D5`、严重度 `S0/Blocker`–`S3/Minor`、精确锚点、现场证据与具体改法），并录入 [`templates/remediation-matrix.md`](../templates/remediation-matrix.md)。
- **退出门禁**：三大自动化脚本执行完毕、D1–D5 及 50 点清单完成核验、首轮问题清单已锁定（进入 Stage 2 核验时保持首轮清单原样不动，以便逐行对照）。
