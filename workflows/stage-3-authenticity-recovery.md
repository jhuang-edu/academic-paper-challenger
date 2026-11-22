# Stage 3：AI 撰写与编造真实性质询、破局与三端闭环工作流（Authenticity Recovery）

本工作流聚焦“脚本看似合规、文字看似工整，但内行一追问就露馅”的深层真实性风险，完成去伪存真改写与“单一事实源”多端同步闭环，并执行终局 G1–G8 闸门放行。

---

## 1. 触发条件与适用场景

- 已完成 Stage 1 与 Stage 2 问题排查，进入集中修复与终稿合成阶段；
- 论文经由多轮生成式工具改写、降重或缩写扩写后，出现腔调僵硬、案例“完美无阻力”或句法碎裂问题；
- 需要确保“源码/数据脚本 ↔ 分章与附录 ↔ 最终渲染 Word/PDF”彻底同步，避免出现局部补丁破坏全局的次生事故。

## 2. 输入参数与前置准备

- **`MANUSCRIPT_DOCS`**：全部待修与待核验文档（含源码分章、附录、合稿及渲染后的 `.docx`）；
- **`REMEDIATION_MATRIX`**：汇总自 Stage 1 与 Stage 2 的 [`templates/remediation-matrix.md`](../templates/remediation-matrix.md)；
- **`BUZZWORDS_JSON`**（可选）：针对特定学科扩充或覆盖的空洞套话/高频连接词词表。

## 3. 自动化脚本命令

```bash
# 1. 全稿句长 CV 节奏、残句类型与 AI 腔特征量化审计
python scripts/prose_rhythm_audit.py --inputs <docs_or_dir> --lang auto --min-cv 0.35 --max-sent 160 [--exclude-headings 参考文献,致谢] [--buzzwords <json>] --format json

# 2. 终局零符号泄漏与跨载体段落指纹全量复核（务必同时包含最终 .docx）
python scripts/doc_leak_scanner.py --inputs <final_docx> <source_docs...> [--compare <merged> <part1> <part2>...] --format json
```

## 4. 人工深挖与破局重构步骤

对照 [`references/ai-and-fabrication-tells.md`](../references/ai-and-fabrication-tells.md) 逐章排查五大真实性破绽，并按下列策略执行改写破局：

1. **清除“AI 手术线头”**
   - 检查是否存在修改残留元话语（如“在原有表述基础上……”“以下为润色后内容”）、版本残影（旧方案名与新方案名混杂）以及错位的跨学科术语；
   - **破局**：连带整段主干重新理顺主语与因果连接，彻底抹去拼贴感。
2. **修复“无摩擦真空案例”**
   - 若案例研究、工程落地或田野调研中呈现出“全员无条件配合、零成本消耗、零误判/零故障、边界样本全部自动完美解决”，在真实审稿人眼中极具编造嫌疑；
   - **破局**：基于真实记录补充**组织协调阻力、跨部门沟通/算力耗时成本、软性预警被人为忽视导致的真实失误样本**以及组织隐性空缺/返工收益核算。
3. **拆解“未卜先知规则字典”**
   - 检查方法设计章节是否毫无铺垫地精准写出了一套刚好命中后文全部刁钻边界样本的规则；
   - **破局**：明确区分“**试运行前初版基线（v1.0）**”与“**复盘后补充修订版（v1.2）**”，显式标注哪些规则条款或硬性锁死机制是在试运行暴露失误后才迭代固化的，恢复真实科研与工程演进时序。
4. **核实法条、标准与引文的“幻觉精确”**
   - 核验文中引用的每一条法律条文（防止用罚则/通用原则条文张冠李戴充当技术处理条文）、技术标准号与生效时间；
   - 核验英文/中文参考文献的真实研究对象与结论，若属于跨领域理论迁移，须在正文显式补出“从原领域向本文研究情境的迁移边界条件”。
5. **消除机械公文腔与“强行拆句次生灾害”**
   - 结合 `prose_rhythm_audit.py` 报告，拆解同一段落内的三连排比连接词（“此外……同时……综上所述……”）与千字空洞拔高词，削减冗余破折号；
   - 重点修复此前为满足“句长上限”或“提升句长 CV”而被机械劈断的残句（如“然而。”“按 1.5 年折算。”），通过合理重构长短交错句式，在保持语言自然完整的同时满足 `CV >= 0.35` 与单句长度上限。

### 单一事实源三端同步操作规范
- 严禁仅在最终生成的 Word 文件上手动修改正文或表格数值；
- 严格遵循“**修改源码/数据 → 重新生成合稿 → 运行排版渲染脚本导出终稿 `.docx` → 全量重跑 Stage 1/2/3 脚本复核**”闭环流水线，并在 [`templates/remediation-matrix.md`](../templates/remediation-matrix.md) 逐行更新状态。

## 5. 输出产物

- 全部问题闭环为 `Verified` 的 [`templates/remediation-matrix.md`](../templates/remediation-matrix.md)；
- 签核完成的 [`templates/audit-report-template.md`](../templates/audit-report-template.md) 与 [`checklists/defense-and-blind-review-gate.md`](../checklists/defense-and-blind-review-gate.md)。

## 6. 退出门禁

1. `checklists/defense-and-blind-review-gate.md` 的 **G1–G8 全部达到 PASS（0 FAIL）**；
2. 对最终交付文档（含 `.docx` 成品与源码）重跑 `doc_leak_scanner.py`、`cross_table_reconciler.py` 与 `prose_rhythm_audit.py` 均无阻断级告警，且无未归因的遗留异常。
