# Stage 3：AI 撰写与编造真实性质询、双向称重破局、修正账与可选短轮查工作流（Authenticity Interrogation, Remediation & Optional Follow-up Rounds）

本工作流聚焦“盲审评委为什么一直怀疑文章是 AI 写的或数据是编造的”，通过“**三对真实性判断分离 + 取证信号与反证双向天平 + 五大破绽去伪存真重构 + 单一事实源三端同步 + 争议修正账（Correction Ledger）+ 可选旋转角度短轮查**”，完成终稿放行。

---

## 1. 真实性质询的三大铁律与分级结论（Graded Authenticity Verdict）

1. **三对判断在任何时候都必须严格分开**：
   - **查不到 $\neq$ 编造（Not found is not fabricated**）；
   - **高度疑似 AI 辅助 $\neq$ 纯 AI 生成（Highly suspected AI assistance is not pure AI generation**）；
   - **引用马虎 $\neq$ 引用造假（A sloppy citation is not a fake citation**）。
2. **取证信号（Forensic Signals） vs. 反证（Counter-Evidence）双向称重**：
   在下结论前，必须把两边的证据放在天平上一起称：
   - **取证信号（指向 AI 撰写或后期拼凑**）：
     - 异常元数据（程序生成 Creator、凌晨创建时间）、未拆净的“AI 手术线头”（内部文件名 `07 内部风控代号`、旧草稿行号 `L197`、默认随机种子 `seed=42`、裸露代码变量名 `trace=0`、Word 表格残留 `**` 与 `<br>`）；
     - 为过检测器强行切句留下的机械断句残句（`然而。`、`第二。`、`…强调。`）；
     - 零阻力的“真空实验室案例”（全员无条件配合、零摩擦、零成本）；
     - “未卜先知”的规则字典（把试运行失败后才打的补丁提前写进试运行前的基准表）；
     - 脚注与参考文献表对不上、互不相关的网络引用访问日期完全雷同、完稿前几天突击塞入的文献、法条条号张冠李戴（法条幻觉）。
   - **反证（指向作者真实投入与专业把控**）：
     - 作者在文中确实做出的精准专业区分（例如准确辨析某部法规的新旧换版过渡期条款、准确区分两个极易混淆的工艺或学说边界、真实存在的负面失败样本复盘）。
3. **输出分级结论与定稿前补证清单**：
   - 真实性结论必须写成分级评估（例如：“核心业务框架与问题意识具备行业真实底座，但文本呈现高度疑似 AI 辅助扩写特征，且存在 3 处事后规则倒填与附录跨文件合成冲突”），绝不下证据撑不住的极端定论；
   - **开具定稿前补证清单（Extra Proof to Settle Authenticity**）：明确列出作者在答辩或提交前准备哪些材料可一锤定音消除评委怀疑（如：**早期修改草稿版本记录、导师历次指导纪要、原始脱敏台账/审阅时间戳截图、学校官方查重/AIGC 检测报告**）。

---

## 2. 自动化脚本命令

```bash
# 1. 全稿句长 CV 节奏、机械断句残句类型与 AI 腔特征量化审计
python scripts/prose_rhythm_audit.py --inputs <docs_or_dir> --lang auto --min-cv 0.35 --max-sent 160 [--exclude-headings 参考文献,致谢] [--buzzwords <json>] --format json

# 2. 终局零符号泄漏与跨载体段落指纹全量复核（务必同时包含最终 .docx）
python scripts/doc_leak_scanner.py --inputs <final_docx> <source_docs...> [--compare <merged> <part1> <part2>...] --format json
```

---

## 3. 五大破绽去伪存真重构与“单一事实源”三端同步

对照 [`references/ai-and-fabrication-tells.md`](../references/ai-and-fabrication-tells.md) 执行闭环修复：
1. **彻底剪除“AI 手术线头”与排版符号泄漏**：清除所有内部指令、旧稿行号、随机种子、裸露变量名，升级 Word 渲染脚本消除表格与正文中的 `**`、`` ` ``、`<br>`、`>` 与代码围栏；
2. **打破“无摩擦真空案例**”：补充真实的组织协调阻力、落地折中设计（如将手写退回原因改为 10 秒勾选卡片）、跨部门复核沟通成本以及软预警被忽视的反面失败教训；
3. **理顺“未卜先知规则字典”的演进时序**：严格区分“试运行初版基线（`v1.0`）”与“复盘迭代定稿版（`v1.2`）”，化时空穿越漏洞为行动研究迭代亮点；
4. **修复机械断句残句与公文三连排比**：将 `然而。`、`第二。`、`…强调。` 等被脚本暴力切碎的病句恢复为语法完整、长短交错的自然学术散文（保持 `CV >= 0.35` 且单句 $\le 160$ 字）；
5. **单一事实源三端同步**：严格按“**修改分章/附录/数据源码 → 重新合成全文合稿 → 重新渲染 `.docx` 并刷新目录与图表清单页码 → 全量重跑脚本复验**”执行，严禁只在最终 Word 上手改。

---

## 4. 争议重核与《修正账（Correction Ledger）》机制

- 若作者/用户对某条核查发现提出异议，或后续轮次发现了推翻早期结论的新证据：
  1. 立即回一手来源重新核实；
  2. 将重核结果记入 [`templates/remediation-matrix.md`](../templates/remediation-matrix.md) 的《**修正账（Correction Ledger**）》专表：
     - 若原指控确系误判，立即正式撤回（标记 `Retracted`，写明轮次号与推翻原结论的一手来源）；
     - 若一手来源支持原指控，则维持原判（标记 `Upheld`，附上精确的一手来源引文或条款原文）。

---

## 5. 可选的后续旋转角度短轮查（Optional Rotating Follow-up Rounds）

- **不默认开启**：仅当用户明确要求继续多轮巡查，或论文正处于答辩/终审前高频修改期时才运行；已定稿论文完成 Pass 1 + Pass 2 + 闭环验证即可收官。
- **旋转角度（One Rotating Angle per Round**）：每轮控制在 30 分钟内，只锁定一个专项角度——**① 法条与规章 / ② 引文与文献归属 / ③ 案例与样本属性 / ④ 数字与跨表算术 / ⑤ 语言与残句 / ⑥ 逻辑与时序 / ⑦ 日期与时间线 / ⑧ 结构与图表清单**，并将当前角度记入轮次日志。
- **增量基线与去重**：每轮开始前先校验文件 `MD5` 与修改时间；编新号前先检索旧问题清单，**只报告真正的新发现**。
- **空轮即停铁律（Stop at the First Empty Round**）：**一旦某一轮查出 0 条新发现，立即停止后续轮查**（无需连跑多轮空轮），向用户简短汇报空轮结果并交付最终总结。

---

## 6. 退出门禁（Gates G1–G8）

1. [`checklists/defense-and-blind-review-gate.md`](../checklists/defense-and-blind-review-gate.md) 的 **G1–G8 全部达到 PASS（0 FAIL**）；
2. [`templates/remediation-matrix.md`](../templates/remediation-matrix.md) 中所有问题均已从 `Open → Fixed → Verified` 闭环，争议项已在《修正账》结清。
