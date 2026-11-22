#!/usr/bin/env python3
"""End-to-end CLI tests for academic-paper-challenger scripts (Python 3.8+ stdlib only)."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Dict, List
import unittest
import zipfile

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"
FIXTURES_DIR = ROOT / "tests" / "fixtures"


def _run_cli(script_name: str, args: List[str]) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(SCRIPTS_DIR / script_name)] + args
    return subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def build_synthetic_docx(
    dest_path: Path,
    *,
    include_leaks: bool = False,
    include_comments: bool = False,
    include_revisions: bool = False,
    broken_table_sum: bool = False,
) -> None:
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>
  <Override PartName="/word/comments.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>
</Types>"""

    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

    leak_paras = ""
    if include_leaks:
        leak_paras = """
    <w:p><w:r><w:t>本段存在**未渲染加粗**与`反引号`残留。</w:t></w:r></w:p>
    <w:p><w:r><w:t>&gt; 未解析的块引用前缀</w:t></w:r></w:p>
    <w:p><w:r><w:t>```text</w:t></w:r></w:p>
    <w:p><w:r><w:t>换行符残留&lt;br&gt;示例</w:t></w:r></w:p>"""

    rev_para = ""
    if include_revisions:
        rev_para = """
    <w:p>
      <w:ins w:id="1" w:author="Editor"><w:r><w:t>未接受修订文本</w:t></w:r></w:ins>
      <w:del w:id="2" w:author="Editor"><w:r><w:delText>已删除文字</w:delText></w:r></w:del>
    </w:p>"""

    total_val = "99" if broken_table_sum else "30"

    document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>第一章 合成测试文档</w:t></w:r></w:p>
    <w:p><w:r><w:t>正文引用表 1-1 展示分组实验统计结果，且段落内容保持规范表达。</w:t></w:r></w:p>
    <w:p>
      <w:pPr><w:pStyle w:val="Code"/></w:pPr>
      <w:r><w:rPr><w:rFonts w:ascii="Consolas"/></w:rPr><w:t>batch_var_name = 123 # **code**</w:t></w:r>
    </w:p>
    {leak_paras}
    {rev_para}
    <w:p><w:r><w:t>表 1-1 纵向合并单元格统计测试表</w:t></w:r></w:p>
    <w:tbl>
      <w:tr>
        <w:tc><w:tcPr><w:gridSpan w:val="2"/></w:tcPr><w:p><w:r><w:t>分组标识</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>数量</w:t></w:r></w:p></w:tc>
      </w:tr>
      <w:tr>
        <w:tc><w:tcPr><w:vMerge w:val="restart"/></w:tcPr><w:p><w:r><w:t>大类甲</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>子类一</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>12</w:t></w:r></w:p></w:tc>
      </w:tr>
      <w:tr>
        <w:tc><w:tcPr><w:vMerge/></w:tcPr><w:p><w:r><w:t/></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>子类二</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>18</w:t></w:r></w:p></w:tc>
      </w:tr>
      <w:tr>
        <w:tc><w:p><w:r><w:t>合计</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>-</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>{total_val}</w:t></w:r></w:p></w:tc>
      </w:tr>
    </w:tbl>
  </w:body>
</w:document>""".format(
        leak_paras=leak_paras, rev_para=rev_para, total_val=total_val
    )

    header_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:p><w:r><w:t>通用学术论文页眉</w:t></w:r></w:p>
</w:hdr>"""

    comments_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  {body}
</w:comments>""".format(
        body=(
            '<w:comment w:id="0" w:author="Reviewer"><w:p><w:r><w:t>此处数据需核实</w:t></w:r></w:p></w:comment>'
            if include_comments
            else ""
        )
    )

    with zipfile.ZipFile(str(dest_path), "w") as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/header1.xml", header_xml)
        if include_comments:
            zf.writestr("word/comments.xml", comments_xml)


def build_synthetic_xlsx(dest_path: Path) -> None:
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
</Types>"""

    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

    wb_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="CoatingLog" sheetId="1" r:id="rId1"/>
    <sheet name="SparseSheet" sheetId="2" r:id="rId2"/>
  </sheets>
</workbook>"""

    wb_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>
</Relationships>"""

    shared_strings = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="4" uniqueCount="4">
  <si><t>sample_id</t></si>
  <si><t>speed</t></si>
  <si><t>yield_pct</t></si>
  <si><t>double_speed</t></si>
</sst>"""

    sheet1 = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1">
      <c r="A1" t="s"><v>0</v></c>
      <c r="B1" t="s"><v>1</v></c>
      <c r="C1" t="s"><v>2</v></c>
      <c r="D1" t="s"><v>3</v></c>
    </row>
    <row r="2">
      <c r="A2" t="inlineStr"><is><t>X01</t></is></c>
      <c r="B2"><v>21.4</v></c>
      <c r="C2"><v>91.2</v></c>
      <c r="D2"><f>B2*2</f><v>42.8</v></c>
    </row>
    <row r="3">
      <c r="A3" t="inlineStr"><is><t>X02</t></is></c>
      <c r="B3"><v>28.7</v></c>
      <c r="C3"><v>88.5</v></c>
      <c r="D3"><f>B3*2</f><v>57.4</v></c>
    </row>
    <row r="4">
      <c r="A4" t="inlineStr"><is><t>X03</t></is></c>
      <c r="B4"><v>35.1</v></c>
      <c r="C4"><v>93.6</v></c>
      <c r="D4"><f>B4*2</f><v>70.2</v></c>
    </row>
  </sheetData>
</worksheet>"""

    sheet2 = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1">
      <c r="A1" t="inlineStr"><is><t>id</t></is></c>
      <c r="C1" t="inlineStr"><is><t>metric_c</t></is></c>
    </row>
    <row r="2">
      <c r="A2" t="inlineStr"><is><t>P1</t></is></c>
      <c r="C2"><f>10+5</f></c>
    </row>
    <row r="3">
      <c r="A3" t="inlineStr"><is><t>P2</t></is></c>
      <c r="C3"><v>19.5</v></c>
    </row>
    <row r="4">
      <c r="A4" t="inlineStr"><is><t>P3</t></is></c>
      <c r="C4"><v>24.1</v></c>
    </row>
  </sheetData>
</worksheet>"""

    with zipfile.ZipFile(str(dest_path), "w") as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("xl/workbook.xml", wb_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        zf.writestr("xl/sharedStrings.xml", shared_strings)
        zf.writestr("xl/worksheets/sheet1.xml", sheet1)
        zf.writestr("xl/worksheets/sheet2.xml", sheet2)


class TestAcademicPaperChallengerScripts(unittest.TestCase):
    def test_doc_leak_scanner_md_and_negation(self) -> None:
        # Clean file passes
        res_clean = _run_cli(
            "doc_leak_scanner.py",
            ["--inputs", str(FIXTURES_DIR / "sample_clean.md"), "--format", "json"],
        )
        self.assertEqual(res_clean.returncode, 0, res_clean.stderr)
        data_clean = json.loads(res_clean.stdout)
        self.assertEqual(data_clean["status"], "PASS")

        # Leaky file detects leaks, enforces contrast break, exempts valid negations, skips code block
        res_leaky = _run_cli(
            "doc_leak_scanner.py",
            ["--inputs", str(FIXTURES_DIR / "sample_leaky.md"), "--format", "json"],
        )
        self.assertEqual(res_leaky.returncode, 1)
        data_leaky = json.loads(res_leaky.stdout)
        findings = data_leaky["findings"]
        rule_ids = {f["rule_id"] for f in findings}
        for expected in (
            "PLACEHOLDER_LEAK",
            "DRAFT_LINE_REF",
            "RANDOM_SEED_LEAK",
            "BARE_SNAKE_CASE",
            "AI_SURGERY_THREAD",
            "RAW_HTML_BR",
            "HTML_COMMENT_LEAK",
        ):
            self.assertIn(expected, rule_ids)

        # Code block variable must NOT appear
        evidences = " | ".join(f["evidence"] for f in findings)
        self.assertNotIn("train_step_idx", evidences)

        # seed=99 is exempted via left negation -> severity INFO
        seed99 = [f for f in findings if "seed=99" in f["evidence"]]
        self.assertTrue(seed99 and all(f["exempted"] and f["severity"] == "INFO" for f in seed99))

        # Contrast break "虽不涉及...但实测使用了 seed=17" must NOT be exempted
        seed17_break = [f for f in findings if "实测使用了 seed=17" in f["evidence"]]
        self.assertTrue(seed17_break and all((not f["exempted"]) and f["severity"] == "FAIL" for f in seed17_break))

        # External custom_rules.json disables BARE_SNAKE_CASE & catches custom term
        with tempfile.TemporaryDirectory() as tmp:
            custom_md = Path(tmp) / "custom.md"
            custom_md.write_text("中文测试 legacy_internal_flag 与 f1_score。\n", encoding="utf-8")
            res_rules = _run_cli(
                "doc_leak_scanner.py",
                [
                    "--inputs",
                    str(custom_md),
                    "--rules",
                    str(FIXTURES_DIR / "custom_rules.json"),
                    "--format",
                    "json",
                ],
            )
            self.assertEqual(res_rules.returncode, 1)
            r_ids = [f["rule_id"] for f in json.loads(res_rules.stdout)["findings"]]
            self.assertIn("CUSTOM_TERM", r_ids)
            self.assertNotIn("BARE_SNAKE_CASE", r_ids)

    def test_doc_leak_scanner_docx_and_compare(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            clean_docx = tmp_dir / "clean.docx"
            leaky_docx = tmp_dir / "leaky.docx"
            build_synthetic_docx(clean_docx, include_leaks=False, include_comments=False, include_revisions=False)
            build_synthetic_docx(leaky_docx, include_leaks=True, include_comments=True, include_revisions=True)

            res_c = _run_cli("doc_leak_scanner.py", ["--inputs", str(clean_docx), "--format", "json"])
            self.assertEqual(res_c.returncode, 0, res_c.stderr)
            self.assertEqual(json.loads(res_c.stdout)["status"], "PASS")

            res_l = _run_cli("doc_leak_scanner.py", ["--inputs", str(leaky_docx), "--format", "json"])
            self.assertEqual(res_l.returncode, 1)
            l_data = json.loads(res_l.stdout)
            l_rules = {f["rule_id"] for f in l_data["findings"]}
            for expected in (
                "DOCX_UNRENDERED_BOLD",
                "DOCX_UNRENDERED_BACKTICK",
                "DOCX_UNRENDERED_QUOTE",
                "DOCX_RAW_FENCE",
                "RAW_HTML_BR",
                "DOCX_COMMENTS_PRESENT",
                "DOCX_TRACKED_CHANGES",
            ):
                self.assertIn(expected, l_rules)
            # Code-styled paragraph must not leak BARE_SNAKE_CASE or BOLD
            self.assertNotIn("batch_var_name", " ".join(f["evidence"] for f in l_data["findings"]))

            # Compare drift test
            res_cmp = _run_cli(
                "doc_leak_scanner.py",
                [
                    "--compare",
                    str(FIXTURES_DIR / "compare_merged.md"),
                    str(FIXTURES_DIR / "compare_ch1.md"),
                    str(FIXTURES_DIR / "compare_ch2.md"),
                    "--format",
                    "json",
                ],
            )
            self.assertEqual(res_cmp.returncode, 1)
            cmp_data = json.loads(res_cmp.stdout)
            self.assertTrue(any(f["rule_id"] == "COMPARE_SYNC_DRIFT" for f in cmp_data["findings"]))

            # Perfect sync compare
            m_ok = tmp_dir / "m_ok.md"
            p1_ok = tmp_dir / "p1.md"
            p2_ok = tmp_dir / "p2.md"
            p1_ok.write_text("# 第一章\n\n第一段测试文本。\n", encoding="utf-8")
            p2_ok.write_text("# 第二章\n\n第二段测试文本。\n", encoding="utf-8")
            m_ok.write_text(p1_ok.read_text(encoding="utf-8") + "\n---\n\n" + p2_ok.read_text(encoding="utf-8"), encoding="utf-8")
            res_ok = _run_cli(
                "doc_leak_scanner.py",
                ["--compare", str(m_ok), str(p1_ok), str(p2_ok), "--format", "json"],
            )
            self.assertEqual(res_ok.returncode, 0, res_ok.stderr)
            self.assertEqual(json.loads(res_ok.stdout)["status"], "PASS")

    def test_cross_table_reconciler_md_docx_and_rules(self) -> None:
        # Clean markdown document
        res_clean = _run_cli(
            "cross_table_reconciler.py",
            ["--docs", str(FIXTURES_DIR / "sample_clean.md"), "--format", "json"],
        )
        self.assertEqual(res_clean.returncode, 0, res_clean.stderr)
        self.assertEqual(json.loads(res_clean.stdout)["status"], "PASS")

        # Anomalous tables & rules
        res_bad = _run_cli(
            "cross_table_reconciler.py",
            [
                "--docs",
                str(FIXTURES_DIR / "reconcile_tables.md"),
                "--rules",
                str(FIXTURES_DIR / "reconcile_rules.json"),
                "--format",
                "json",
            ],
        )
        self.assertEqual(res_bad.returncode, 1)
        bad_rules = {f["rule_id"] for f in json.loads(res_bad.stdout)["findings"]}
        for expected in (
            "TABLE_ROW_SUM_MISMATCH",
            "TABLE_COL_SUM_MISMATCH",
            "LIST_MISSING_CAPTION",
            "ORPHAN_CAPTION_REF",
            "RULE_WRONG_TOTAL_CHECK",
        ):
            self.assertIn(expected, bad_rules)
        self.assertNotIn("RULE_SUBTOTAL_MATCH", bad_rules)

        # Minimal demo with currency prefixes (¥, $) and rule reconciliation
        demo_md = Path(__file__).resolve().parent.parent / "examples" / "minimal-audit-demo" / "sample_paper.md"
        demo_rules = Path(__file__).resolve().parent.parent / "examples" / "minimal-audit-demo" / "audit_rules.json"
        res_demo = _run_cli(
            "cross_table_reconciler.py",
            ["--docs", str(demo_md), "--rules", str(demo_rules), "--format", "json"],
        )
        self.assertEqual(res_demo.returncode, 0, res_demo.stderr)
        self.assertEqual(json.loads(res_demo.stdout)["status"], "PASS")

        # Synthetic DOCX with vMerge and gridSpan
        with tempfile.TemporaryDirectory() as tmp:
            ok_docx = Path(tmp) / "ok.docx"
            bad_docx = Path(tmp) / "bad.docx"
            build_synthetic_docx(ok_docx, broken_table_sum=False)
            build_synthetic_docx(bad_docx, broken_table_sum=True)

            r_ok = _run_cli("cross_table_reconciler.py", ["--docs", str(ok_docx), "--format", "json"])
            self.assertEqual(r_ok.returncode, 0, r_ok.stderr)
            self.assertEqual(json.loads(r_ok.stdout)["status"], "PASS")

            r_bad = _run_cli("cross_table_reconciler.py", ["--docs", str(bad_docx), "--format", "json"])
            self.assertEqual(r_bad.returncode, 1)
            self.assertIn("TABLE_COL_SUM_MISMATCH", {f["rule_id"] for f in json.loads(r_bad.stdout)["findings"]})

    def test_data_forensics_csv_tsv_xlsx(self) -> None:
        # Clean CSV
        res_clean = _run_cli(
            "data_forensics.py",
            [
                "--input",
                str(FIXTURES_DIR / "forensics_clean.csv"),
                "--id-col",
                "sample_id",
                "--group-col",
                "line_group",
                "--format",
                "json",
            ],
        )
        self.assertEqual(res_clean.returncode, 0, res_clean.stderr)
        c_data = json.loads(res_clean.stdout)
        self.assertEqual(c_data["status"], "PASS")
        self.assertEqual(c_data["summary"]["row_count"], 36)

        # Anomalous TSV with confusion matrix & dual IQR
        res_anom = _run_cli(
            "data_forensics.py",
            [
                "--input",
                str(FIXTURES_DIR / "forensics_anomalous.tsv"),
                "--id-col",
                "sample_id",
                "--group-col",
                "batch_group",
                "--num-cols",
                "col_a,col_b",
                "--ref-col",
                "ref_grade",
                "--pred-col",
                "pred_grade",
                "--pos-label",
                "pass",
                "--strict",
                "--format",
                "json",
            ],
        )
        self.assertEqual(res_anom.returncode, 1)
        a_data = json.loads(res_anom.stdout)
        a_rules = {f["rule_id"] for f in a_data["findings"]}
        for expected in (
            "HIGH_COLLINEARITY",
            "RUNS_NON_RANDOM",
            "LAST_DIGIT_BIAS",
            "DUPLICATE_FEATURE_ROW",
            "EXTREME_3IQR_OUTLIER",
        ):
            self.assertIn(expected, a_rules)

        # Verify Benford narrow-range protection did NOT falsely fire on col_a
        self.assertFalse(a_data["summary"]["columns"]["col_a"]["benford_test"]["applicable"])
        self.assertNotIn("BENFORD_DEVIATION", a_rules)

        # Verify dual IQR values are present and distinct
        desc_a = a_data["summary"]["columns"]["col_a"]["descriptive"]
        self.assertIsNotNone(desc_a["iqr_inc"])
        self.assertIsNotNone(desc_a["iqr_exc"])

        # Verify McNemar & Kappa
        cm = a_data["summary"]["confusion_agreement"]
        self.assertEqual(cm["n_pairs"], 36)
        self.assertIn("kappa", cm)
        self.assertIn("mcnemar", cm["binary"])

        # GB18030 fallback + XLSX sparse sheet test
        with tempfile.TemporaryDirectory() as tmp:
            gbk_csv = Path(tmp) / "gbk.csv"
            gbk_csv.write_bytes("编号,数值\nA1,10.5\nA2,12.3\nA3,11.1\n".encode("gb18030"))
            r_gbk = _run_cli("data_forensics.py", ["--input", str(gbk_csv), "--id-col", "编号", "--format", "json"])
            self.assertEqual(r_gbk.returncode, 0, r_gbk.stderr)
            self.assertEqual(json.loads(r_gbk.stdout)["summary"]["row_count"], 3)

            xlsx_p = Path(tmp) / "synth.xlsx"
            build_synthetic_xlsx(xlsx_p)
            r_x1 = _run_cli(
                "data_forensics.py",
                ["--input", str(xlsx_p), "--sheet", "CoatingLog", "--id-col", "sample_id", "--format", "json"],
            )
            self.assertEqual(r_x1.returncode, 0, r_x1.stderr)
            x1_data = json.loads(r_x1.stdout)
            self.assertEqual(x1_data["summary"]["xlsx_meta"]["formula_cell_count"], 3)
            self.assertEqual(x1_data["summary"]["xlsx_meta"]["uncached_formula_count"], 0)
            self.assertEqual(x1_data["summary"]["columns"]["double_speed"]["descriptive"]["mean"], 56.8)

            r_x2 = _run_cli(
                "data_forensics.py",
                ["--input", str(xlsx_p), "--sheet", "SparseSheet", "--id-col", "id", "--format", "json"],
            )
            self.assertEqual(r_x2.returncode, 0, r_x2.stderr)
            x2_data = json.loads(r_x2.stdout)
            self.assertIn("metric_c", x2_data["summary"]["headers"])
            self.assertEqual(x2_data["summary"]["xlsx_meta"]["uncached_formula_count"], 1)
            self.assertIn("XLSX_UNCACHED_FORMULAS", {f["rule_id"] for f in x2_data["findings"]})

    def test_prose_rhythm_audit_zh_en_mixed(self) -> None:
        res_clean = _run_cli(
            "prose_rhythm_audit.py",
            ["--inputs", str(FIXTURES_DIR / "sample_clean.md"), "--format", "json"],
        )
        self.assertEqual(res_clean.returncode, 0, res_clean.stderr)
        c_data = json.loads(res_clean.stdout)
        self.assertEqual(c_data["status"], "PASS")
        self.assertGreaterEqual(c_data["summary"]["cv"], 0.35)

        res_choppy = _run_cli(
            "prose_rhythm_audit.py",
            ["--inputs", str(FIXTURES_DIR / "prose_choppy_ai.md"), "--format", "json"],
        )
        self.assertEqual(res_choppy.returncode, 1)
        ch_data = json.loads(res_choppy.stdout)
        ch_rules = {f["rule_id"] for f in ch_data["findings"]}
        self.assertIn("FRAGMENT_STANDALONE_CONN", ch_rules)
        self.assertIn("FRAGMENT_DANGLING_VERB", ch_rules)
        self.assertIn("PARAGRAPH_CONNECTOR_TRIPLE", ch_rules)
        self.assertIn("HIGH_DASH_DENSITY", ch_rules)
        # Mixed sentence "涂布均匀性提升 1.5 倍（见 Fig. 1 与 Smith et al., 2024）。" must NOT split prematurely
        self.assertEqual(ch_data["summary"]["sentence_count"], 9)

    def test_validate_skill_self_check(self) -> None:
        res = _run_cli("validate_skill.py", ["--format", "json"])
        self.assertEqual(res.returncode, 0, res.stdout + "\n" + res.stderr)
        data = json.loads(res.stdout)
        self.assertEqual(data["status"], "PASS")
        self.assertEqual(data["fail_count"], 0)


if __name__ == "__main__":
    unittest.main()
