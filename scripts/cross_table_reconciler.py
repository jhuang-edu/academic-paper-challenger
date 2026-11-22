#!/usr/bin/env python3
"""Universal cross-table arithmetic, caption continuity, and list reconciler (Python 3.8+ stdlib)."""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
import xml.etree.ElementTree as ET
import zipfile

VERSION = "1.0.0"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

TOTAL_ROW_RE = re.compile(
    r"^(?:合\s*计|总\s*计|总\s*和|汇\s*总|Total|Grand\s+Total|Sum)(?:[\s（(].*)?$",
    re.IGNORECASE,
)
SUBTOTAL_ROW_RE = re.compile(
    r"^(?:小\s*计|Subtotal)(?:[\s（(].*)?$",
    re.IGNORECASE,
)
TOTAL_COL_RE = re.compile(r"(?:合\s*计|总\s*计|小\s*计|Total|Sum)", re.IGNORECASE)
NON_ADDITIVE_HEADER_RE = re.compile(
    r"(?:序号|编号|No\.|占比|比例|构成比|%|率|均值|平均|Mean|SD|标准差|中位数|Median|IQR|p值|p-value|Kappa|t值|Z值)",
    re.IGNORECASE,
)

FIG_CAPTION_RE = re.compile(
    r"^\s*(?:\*{0,2}|#{1,6}\s*)?(?:图|Figure|Fig\.)\s*([A-Z]?\d+(?:[-.]\d+)*[a-zA-Z]?)\s*[:：.\s]\s*(.+?)\*{0,2}\s*$"
)
TBL_CAPTION_RE = re.compile(
    r"^\s*(?:\*{0,2}|#{1,6}\s*)?(?:表|Table)\s*([A-Z]?\d+(?:[-.]\d+)*[a-zA-Z]?)\s*[:：.\s]\s*(.+?)\*{0,2}\s*$"
)
LIST_HEADING_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:图清单|插图清单|表清单|表格清单|List\s+of\s+Figures|List\s+of\s+Tables)\b",
    re.IGNORECASE,
)
NUM_CELL_RE = re.compile(
    r"^\s*(?:[¥￥$€£]\s*)?([+-]?\d+(?:\.\d+)?)\s*(%|％|小时|人时|分钟|分|份|个|例|篇|天|元|万元|h|min|kg|mg|次)?\s*$"
)


@dataclass
class CellData:
    text: str
    is_vmerge_cont: bool = False


@dataclass
class ExtractedTable:
    doc_path: str
    table_index: int
    caption: str
    caption_id: Optional[str]
    headers: List[str]
    rows: List[List[CellData]]
    location: str


@dataclass
class CaptionItem:
    kind: str  # "fig" | "tbl"
    cap_id: str
    title: str
    location: str


@dataclass
class ListItem:
    kind: str  # "fig" | "tbl"
    cap_id: str
    title: str
    page: Optional[str]
    location: str


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _w_attr(elem: ET.Element, name: str) -> Optional[str]:
    return elem.attrib.get("{{{0}}}{1}".format(W_NS, name)) or elem.attrib.get(name)


def _read_text_with_fallback(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _clean_cell_text(raw: str) -> str:
    txt = re.sub(r"<\s*br\s*/?\s*>", " ", raw, flags=re.IGNORECASE)
    txt = txt.replace("**", "").replace("__", "").replace("`", "")
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


def _normalize_title(title: str) -> str:
    t = _clean_cell_text(title)
    t = re.sub(r"[\s\.·…\-\–—]+$", "", t)
    t = re.sub(r"\s+", "", t)
    return t.lower()


def _parse_num(text: str) -> Optional[Tuple[float, bool]]:
    s = _clean_cell_text(text)
    if not s or s in ("-", "—", "–", "N/A", "NA", "/", "null", "None"):
        return None
    s_no_comma = s.replace(",", "")
    m = NUM_CELL_RE.match(s_no_comma)
    if not m:
        return None
    val = float(m.group(1))
    unit = m.group(2) or ""
    is_pct = unit in ("%", "％")
    return val, is_pct


def _parse_list_entry(line: str, default_kind: str, location: str) -> Optional[ListItem]:
    cleaned = re.sub(r"^\s*(?:[-*+]\s+|\d+\.\s+)", "", line).strip()
    cleaned = cleaned.replace("**", "").replace("`", "")
    # Markdown table row in list section: | 表 1-1 | 标题 | 12 |
    if "|" in cleaned:
        cols = [c.strip() for c in cleaned.strip("|").split("|")]
        if len(cols) >= 2 and not re.match(r"^:?-{2,}:?$", cols[0]):
            joined = " ".join(cols)
            m_cap = re.match(
                r"^(?:(图|Figure|Fig\.)|(表|Table))\s*([A-Z]?\d+(?:[-.]\d+)*[a-zA-Z]?)\s+(.+)$",
                joined,
                re.IGNORECASE,
            )
            if m_cap:
                kind = "fig" if m_cap.group(1) else "tbl"
                cap_id = m_cap.group(3)
                rest = m_cap.group(4).strip()
                page_opt: Optional[str] = None
                m_tail_pg = re.match(r"^(.+?)\s+(\d+|[ivxlcdm]+)$", rest, re.IGNORECASE)
                if m_tail_pg and len(cols) >= 3:
                    rest = m_tail_pg.group(1).strip()
                    page_opt = m_tail_pg.group(2)
                return ListItem(kind=kind, cap_id=cap_id, title=rest, page=page_opt, location=location)
        return None

    m = re.match(
        r"^(?:(图|Figure|Fig\.)|(表|Table))\s*([A-Z]?\d+(?:[-.]\d+)*[a-zA-Z]?)\s*[:：.\s]\s*(.+)$",
        cleaned,
        re.IGNORECASE,
    )
    if not m:
        return None
    kind = "fig" if m.group(1) else ("tbl" if m.group(2) else default_kind)
    cap_id = m.group(3)
    rest = m.group(4).strip()
    page_opt = None
    # Match trailing dotted/tabbed page number like "Title ....... 12" or "Title\t12"
    m_pg = re.match(r"^(.+?)\s*(?:[\.·…\t]{2,}|\s{2,})\s*(\d+|[ivxlcdm]+)\s*$", rest, re.IGNORECASE)
    if m_pg:
        rest = m_pg.group(1).strip()
        page_opt = m_pg.group(2)
    return ListItem(kind=kind, cap_id=cap_id, title=rest, page=page_opt, location=location)


def _split_md_pipe_row(line: str) -> List[str]:
    safe = line.replace(r"\|", "\x00PIPE\x00").strip()
    if safe.startswith("|"):
        safe = safe[1:]
    if safe.endswith("|"):
        safe = safe[:-1]
    return [_clean_cell_text(c.replace("\x00PIPE\x00", "|")) for c in safe.split("|")]


def _extract_md_doc(
    path: Path,
) -> Tuple[List[ExtractedTable], List[CaptionItem], List[ListItem], bool, List[Tuple[str, str]]]:
    """Return tables, captions, list_items, has_lists, prose_lines(loc, text)."""
    content = _read_text_with_fallback(path)
    lines = content.splitlines()
    tables: List[ExtractedTable] = []
    captions: List[CaptionItem] = []
    list_items: List[ListItem] = []
    prose_lines: List[Tuple[str, str]] = []
    has_lists = False

    n = len(lines)
    idx = 0
    if n >= 3 and lines[0].strip() == "---":
        for j in range(1, n):
            if lines[j].strip() in ("---", "..."):
                idx = j + 1
                break

    in_code = False
    fence_char = ""
    fence_len = 0
    in_list_section: Optional[str] = None  # "fig" | "tbl" | None
    tbl_counter = 0

    sep_re = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$")

    while idx < n:
        line = lines[idx]
        line_no = idx + 1
        loc = "{0}:{1}".format(path.name, line_no)

        m_fence = re.match(r"^[ ]{0,3}(`{3,}|~{3,})(.*)$", line)
        if not in_code and m_fence:
            in_code = True
            fence_char = m_fence.group(1)[0]
            fence_len = len(m_fence.group(1))
            idx += 1
            continue
        if in_code:
            if m_fence and m_fence.group(1)[0] == fence_char and len(m_fence.group(1)) >= fence_len and not m_fence.group(2).strip():
                in_code = False
            idx += 1
            continue

        # Check list heading
        if LIST_HEADING_RE.match(line):
            has_lists = True
            in_list_section = "fig" if re.search(r"图|Figures", line, re.IGNORECASE) else "tbl"
            idx += 1
            continue

        if in_list_section is not None:
            if re.match(r"^\s*#{1,6}\s+\S", line) and not LIST_HEADING_RE.match(line):
                in_list_section = None
            elif re.match(r"^\s*[-*_]{3,}\s*$", line):
                in_list_section = None
            else:
                li = _parse_list_entry(line, in_list_section, loc)
                if li is not None:
                    list_items.append(li)
                idx += 1
                continue

        # Check Markdown pipe table
        if "|" in line and idx + 1 < n and sep_re.match(lines[idx + 1]):
            header_cells = _split_md_pipe_row(line)
            num_cols = len(header_cells)
            raw_rows: List[List[CellData]] = [[CellData(text=c) for c in header_cells]]
            j = idx + 2
            while j < n and "|" in lines[j] and not sep_re.match(lines[j]):
                row_vals = _split_md_pipe_row(lines[j])
                if len(row_vals) < num_cols:
                    row_vals.extend([""] * (num_cols - len(row_vals)))
                elif len(row_vals) > num_cols:
                    row_vals = row_vals[:num_cols]
                raw_rows.append([CellData(text=c) for c in row_vals])
                j += 1

            # Look back up to 3 non-empty lines for table caption
            cap_text = ""
            cap_id: Optional[str] = None
            checked = 0
            k = idx - 1
            while k >= 0 and checked < 3:
                cand = lines[k].strip()
                if cand:
                    checked += 1
                    m_tbl = TBL_CAPTION_RE.match(cand)
                    if m_tbl:
                        cap_id = m_tbl.group(1)
                        cap_text = _clean_cell_text(m_tbl.group(2))
                        break
                k -= 1

            tbl_counter += 1
            tables.append(
                ExtractedTable(
                    doc_path=str(path),
                    table_index=tbl_counter,
                    caption=cap_text,
                    caption_id=cap_id,
                    headers=header_cells,
                    rows=raw_rows,
                    location=loc,
                )
            )
            idx = j
            continue

        # Check captions outside list sections
        m_fig = FIG_CAPTION_RE.match(line)
        if m_fig:
            captions.append(
                CaptionItem(
                    kind="fig",
                    cap_id=m_fig.group(1),
                    title=_clean_cell_text(m_fig.group(2)),
                    location=loc,
                )
            )
            idx += 1
            continue

        m_tbl = TBL_CAPTION_RE.match(line)
        if m_tbl:
            captions.append(
                CaptionItem(
                    kind="tbl",
                    cap_id=m_tbl.group(1),
                    title=_clean_cell_text(m_tbl.group(2)),
                    location=loc,
                )
            )
            idx += 1
            continue

        stripped = line.strip()
        if stripped and not stripped.startswith("<!--"):
            prose_lines.append((loc, stripped))
        idx += 1

    return tables, captions, list_items, has_lists, prose_lines


def _extract_docx_para_text_and_style(p_elem: ET.Element) -> Tuple[str, str]:
    style_val = ""
    p_pr = p_elem.find("{{{0}}}pPr".format(W_NS))
    if p_pr is not None:
        p_style = p_pr.find("{{{0}}}pStyle".format(W_NS))
        if p_style is not None:
            style_val = _w_attr(p_style, "val") or ""

    parts: List[str] = []

    def walk(node: ET.Element) -> None:
        lname = _local_name(node.tag)
        if lname in ("del", "delText", "pPr", "rPr"):
            return
        if lname == "t" and node.text:
            parts.append(node.text)
            return
        if lname == "tab":
            parts.append("\t")
            return
        if lname in ("br", "cr"):
            parts.append(" ")
            return
        for child in list(node):
            walk(child)

    for child in list(p_elem):
        walk(child)
    return re.sub(r"[ ]+", " ", "".join(parts)).strip(), style_val


def _extract_docx_doc(
    path: Path,
) -> Tuple[List[ExtractedTable], List[CaptionItem], List[ListItem], bool, List[Tuple[str, str]]]:
    tables: List[ExtractedTable] = []
    captions: List[CaptionItem] = []
    list_items: List[ListItem] = []
    prose_lines: List[Tuple[str, str]] = []
    has_lists = False

    try:
        zf = zipfile.ZipFile(str(path), "r")
    except (zipfile.BadZipFile, OSError) as exc:
        raise ValueError("无法打开 DOCX 文件 {0}: {1}".format(path, exc))

    with zf:
        if "word/document.xml" not in zf.namelist():
            raise ValueError("DOCX 缺少 word/document.xml: {0}".format(path))
        root = ET.fromstring(zf.read("word/document.xml"))
        body = root.find("{{{0}}}body".format(W_NS))
        if body is None:
            body = root

        in_list_section: Optional[str] = None
        last_nonempty_paras: List[str] = []
        p_idx = 0
        t_idx = 0

        def walk_body(elem: ET.Element) -> None:
            nonlocal in_list_section, p_idx, t_idx
            for child in list(elem):
                lname = _local_name(child.tag)
                if lname == "p":
                    p_idx += 1
                    loc = "{0}:p{1}".format(path.name, p_idx)
                    txt, style_val = _extract_docx_para_text_and_style(child)
                    if not txt:
                        continue
                    if LIST_HEADING_RE.match(txt):
                        has_lists = True
                        in_list_section = "fig" if re.search(r"图|Figures", txt, re.IGNORECASE) else "tbl"
                        continue
                    if in_list_section is not None:
                        if re.match(r"(?i)heading\s*[1-6]|^[1-6]$", style_val) and not LIST_HEADING_RE.match(txt):
                            in_list_section = None
                        else:
                            li = _parse_list_entry(txt, in_list_section, loc)
                            if li is not None:
                                list_items.append(li)
                                continue
                            # If plain non-list paragraph follows after heading, exit list mode
                            if not re.match(r"^(?:图|表|Figure|Fig\.|Table)\s*", txt, re.IGNORECASE):
                                in_list_section = None

                    m_fig = FIG_CAPTION_RE.match(txt)
                    m_tbl = TBL_CAPTION_RE.match(txt)
                    if m_fig:
                        captions.append(
                            CaptionItem(
                                kind="fig",
                                cap_id=m_fig.group(1),
                                title=_clean_cell_text(m_fig.group(2)),
                                location=loc,
                            )
                        )
                    elif m_tbl:
                        captions.append(
                            CaptionItem(
                                kind="tbl",
                                cap_id=m_tbl.group(1),
                                title=_clean_cell_text(m_tbl.group(2)),
                                location=loc,
                            )
                        )
                    else:
                        prose_lines.append((loc, txt))

                    last_nonempty_paras.append(txt)
                    if len(last_nonempty_paras) > 3:
                        last_nonempty_paras.pop(0)

                elif lname == "tbl":
                    t_idx += 1
                    loc = "{0}:tbl{1}".format(path.name, t_idx)
                    vmerge_top_text: Dict[int, str] = {}
                    parsed_rows: List[List[CellData]] = []

                    for tr in list(child):
                        if _local_name(tr.tag) != "tr":
                            continue
                        row_cells: List[CellData] = []
                        col_ptr = 0
                        for tc in list(tr):
                            if _local_name(tc.tag) != "tc":
                                continue
                            grid_span = 1
                            vmerge_state = "none"
                            tc_pr = tc.find("{{{0}}}tcPr".format(W_NS))
                            if tc_pr is not None:
                                gs = tc_pr.find("{{{0}}}gridSpan".format(W_NS))
                                if gs is not None:
                                    try:
                                        grid_span = max(1, int(_w_attr(gs, "val") or "1"))
                                    except ValueError:
                                        grid_span = 1
                                vm = tc_pr.find("{{{0}}}vMerge".format(W_NS))
                                if vm is not None:
                                    vm_val = (_w_attr(vm, "val") or "").lower()
                                    vmerge_state = "restart" if vm_val == "restart" else "continue"

                            cell_parts: List[str] = []
                            for p_node in list(tc):
                                if _local_name(p_node.tag) == "p":
                                    ptxt, _ = _extract_docx_para_text_and_style(p_node)
                                    if ptxt:
                                        cell_parts.append(ptxt)
                            cell_text = _clean_cell_text(" ".join(cell_parts))

                            for k in range(grid_span):
                                c_idx = col_ptr + k
                                if vmerge_state == "continue":
                                    row_cells.append(
                                        CellData(
                                            text=vmerge_top_text.get(c_idx, ""),
                                            is_vmerge_cont=True,
                                        )
                                    )
                                else:
                                    if vmerge_state == "restart":
                                        vmerge_top_text[c_idx] = cell_text
                                    else:
                                        vmerge_top_text.pop(c_idx, None)
                                    row_cells.append(CellData(text=cell_text, is_vmerge_cont=False))
                            col_ptr += grid_span

                        if row_cells:
                            parsed_rows.append(row_cells)

                    if parsed_rows:
                        max_cols = max(len(r) for r in parsed_rows)
                        for r in parsed_rows:
                            while len(r) < max_cols:
                                r.append(CellData(text="", is_vmerge_cont=False))

                        cap_text = ""
                        cap_id: Optional[str] = None
                        for cand in reversed(last_nonempty_paras):
                            m_tbl = TBL_CAPTION_RE.match(cand)
                            if m_tbl:
                                cap_id = m_tbl.group(1)
                                cap_text = _clean_cell_text(m_tbl.group(2))
                                break

                        headers = [c.text for c in parsed_rows[0]]
                        tables.append(
                            ExtractedTable(
                                doc_path=str(path),
                                table_index=t_idx,
                                caption=cap_text,
                                caption_id=cap_id,
                                headers=headers,
                                rows=parsed_rows,
                                location=loc,
                            )
                        )
                elif lname == "sdt":
                    sdt_content = child.find("{{{0}}}sdtContent".format(W_NS))
                    if sdt_content is not None:
                        walk_body(sdt_content)

        walk_body(body)

    return tables, captions, list_items, has_lists, prose_lines


def _audit_table_arithmetic(tbl: ExtractedTable, tol: float) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    if len(tbl.rows) < 2 or not tbl.headers:
        return findings

    num_cols = len(tbl.headers)
    non_additive_cols: Set[int] = set()
    for c_idx, h in enumerate(tbl.headers):
        if NON_ADDITIVE_HEADER_RE.search(h):
            non_additive_cols.add(c_idx)

    # 1. Vertical (column) sums: subtotals & totals without double counting subtotals or vMerge continuations
    sub_acc: Dict[int, float] = {c: 0.0 for c in range(num_cols)}
    sub_has_val: Dict[int, bool] = {c: False for c in range(num_cols)}
    detail_acc: Dict[int, float] = {c: 0.0 for c in range(num_cols)}
    detail_has_val: Dict[int, bool] = {c: False for c in range(num_cols)}
    pct_detail_acc: Dict[int, float] = {c: 0.0 for c in range(num_cols)}
    pct_has_val: Dict[int, bool] = {c: False for c in range(num_cols)}

    for r_idx in range(1, len(tbl.rows)):
        row = tbl.rows[r_idx]
        first_cell = row[0].text.strip()
        is_subtotal = bool(SUBTOTAL_ROW_RE.match(first_cell))
        is_total = bool(TOTAL_ROW_RE.match(first_cell))

        if is_subtotal:
            for c_idx in range(1, num_cols):
                if c_idx in non_additive_cols or row[c_idx].is_vmerge_cont:
                    continue
                parsed = _parse_num(row[c_idx].text)
                if parsed is not None and sub_has_val[c_idx]:
                    expected = sub_acc[c_idx]
                    actual = parsed[0]
                    if abs(expected - actual) > tol:
                        findings.append(
                            {
                                "rule_id": "TABLE_SUBTOTAL_MISMATCH",
                                "severity": "FAIL",
                                "location": "{0}:r{1}c{2}".format(tbl.location, r_idx + 1, c_idx + 1),
                                "message": "表 {0} 第 '{1}' 列小计不平：明细累加 {2:.4g} vs 表中 {3:.4g}".format(
                                    tbl.caption_id or tbl.table_index,
                                    tbl.headers[c_idx],
                                    expected,
                                    actual,
                                ),
                                "evidence": "{0} | {1}".format(first_cell, row[c_idx].text),
                                "exempted": False,
                            }
                        )
            sub_acc = {c: 0.0 for c in range(num_cols)}
            sub_has_val = {c: False for c in range(num_cols)}
            continue

        if is_total:
            for c_idx in range(1, num_cols):
                if row[c_idx].is_vmerge_cont:
                    continue
                parsed = _parse_num(row[c_idx].text)
                if parsed is None:
                    continue
                actual, is_pct = parsed
                if c_idx in non_additive_cols:
                    # Special check: percentage column summing to 100.0%
                    if (is_pct or "%" in tbl.headers[c_idx] or "占比" in tbl.headers[c_idx] or "比例" in tbl.headers[c_idx]) and abs(actual - 100.0) <= tol and pct_has_val[c_idx]:
                        if abs(pct_detail_acc[c_idx] - actual) > tol:
                            findings.append(
                                {
                                    "rule_id": "TABLE_COL_SUM_MISMATCH",
                                    "severity": "FAIL",
                                    "location": "{0}:r{1}c{2}".format(tbl.location, r_idx + 1, c_idx + 1),
                                    "message": "表 {0} 百分比列 '{1}' 合计不平：明细和 {2:.4g}% vs {3:.4g}%".format(
                                        tbl.caption_id or tbl.table_index,
                                        tbl.headers[c_idx],
                                        pct_detail_acc[c_idx],
                                        actual,
                                    ),
                                    "evidence": "{0} | {1}".format(first_cell, row[c_idx].text),
                                    "exempted": False,
                                }
                            )
                    continue
                if detail_has_val[c_idx]:
                    expected = detail_acc[c_idx]
                    if abs(expected - actual) > tol:
                        findings.append(
                            {
                                "rule_id": "TABLE_COL_SUM_MISMATCH",
                                "severity": "FAIL",
                                "location": "{0}:r{1}c{2}".format(tbl.location, r_idx + 1, c_idx + 1),
                                "message": "表 {0} 第 '{1}' 列总计不平：明细累加 {2:.4g} vs 表中 {3:.4g}".format(
                                    tbl.caption_id or tbl.table_index,
                                    tbl.headers[c_idx],
                                    expected,
                                    actual,
                                ),
                                "evidence": "{0} | {1}".format(first_cell, row[c_idx].text),
                                "exempted": False,
                            }
                        )
            continue

        # Regular detail row
        for c_idx in range(1, num_cols):
            if row[c_idx].is_vmerge_cont:
                continue
            parsed = _parse_num(row[c_idx].text)
            if parsed is None:
                continue
            val, _ = parsed
            if c_idx in non_additive_cols:
                pct_detail_acc[c_idx] += val
                pct_has_val[c_idx] = True
            else:
                sub_acc[c_idx] += val
                sub_has_val[c_idx] = True
                detail_acc[c_idx] += val
                detail_has_val[c_idx] = True

    # 2. Horizontal (row) sums
    total_cols = [c for c, h in enumerate(tbl.headers) if TOTAL_COL_RE.search(h)]
    prev_tot = 0
    for c_tot in total_cols:
        addend_cols: List[int] = []
        for c in range(c_tot - 1, prev_tot, -1):
            if c in non_additive_cols:
                continue
            addend_cols.append(c)
        addend_cols.reverse()
        if len(addend_cols) >= 2:
            for r_idx in range(1, len(tbl.rows)):
                row = tbl.rows[r_idx]
                if row[c_tot].is_vmerge_cont:
                    continue
                tot_parsed = _parse_num(row[c_tot].text)
                if tot_parsed is None:
                    continue
                vals: List[float] = []
                skip_row = False
                for ac in addend_cols:
                    if row[ac].is_vmerge_cont:
                        skip_row = True
                        break
                    p = _parse_num(row[ac].text)
                    if p is None:
                        skip_row = True
                        break
                    vals.append(p[0])
                if skip_row:
                    continue
                expected = sum(vals)
                actual = tot_parsed[0]
                if abs(expected - actual) > tol:
                    findings.append(
                        {
                            "rule_id": "TABLE_ROW_SUM_MISMATCH",
                            "severity": "FAIL",
                            "location": "{0}:r{1}c{2}".format(tbl.location, r_idx + 1, c_tot + 1),
                            "message": "表 {0} 第 {1} 行横向合计不平：分项和 {2:.4g} vs 合计 {3:.4g}".format(
                                tbl.caption_id or tbl.table_index,
                                r_idx + 1,
                                expected,
                                actual,
                            ),
                            "evidence": "{0} -> {1}".format(row[0].text, row[c_tot].text),
                            "exempted": False,
                        }
                    )
        prev_tot = c_tot

    return findings


def _audit_captions_and_refs(
    captions: Sequence[CaptionItem],
    list_items: Sequence[ListItem],
    has_lists: bool,
    prose_lines: Sequence[Tuple[str, str]],
) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []

    by_kind: Dict[str, List[CaptionItem]] = {"fig": [], "tbl": []}
    cap_map: Dict[Tuple[str, str], CaptionItem] = {}

    for item in captions:
        key = (item.kind, item.cap_id)
        if key in cap_map:
            findings.append(
                {
                    "rule_id": "CAPTION_DUPLICATE",
                    "severity": "FAIL",
                    "location": item.location,
                    "message": "{0} 编号 {1} 重复定义".format(
                        "图" if item.kind == "fig" else "表", item.cap_id
                    ),
                    "evidence": item.title[:80],
                    "exempted": False,
                }
            )
        else:
            cap_map[key] = item
            by_kind[item.kind].append(item)

    # Check numbering continuity per kind and prefix (e.g., "1-" vs "2-")
    for kind, items in by_kind.items():
        prefix_groups: Dict[str, Set[int]] = {}
        for it in items:
            m = re.match(r"^(.*?)(\d+)[a-zA-Z]?$", it.cap_id)
            if m:
                prefix = m.group(1)
                num = int(m.group(2))
                prefix_groups.setdefault(prefix, set()).add(num)
        kind_label = "图" if kind == "fig" else "表"
        for prefix, nums in sorted(prefix_groups.items()):
            ordered = sorted(nums)
            if ordered and ordered[0] != 1:
                findings.append(
                    {
                        "rule_id": "CAPTION_NUMBER_GAP",
                        "severity": "FAIL",
                        "location": "captions:{0}:{1}".format(kind, prefix or "root"),
                        "message": "{0}序列（前缀 '{1}'）未从 1 开始，起始编号为 {2}".format(
                            kind_label, prefix, ordered[0]
                        ),
                        "evidence": ", ".join(str(x) for x in ordered[:5]),
                        "exempted": False,
                    }
                )
            for a, b in zip(ordered, ordered[1:]):
                if b - a > 1:
                    findings.append(
                        {
                            "rule_id": "CAPTION_NUMBER_GAP",
                            "severity": "FAIL",
                            "location": "captions:{0}:{1}".format(kind, prefix or "root"),
                            "message": "{0}编号跳跃：{1}{2} 与 {1}{3} 之间存在断号".format(
                                kind_label, prefix, a, b
                            ),
                            "evidence": "{0}{1} -> {0}{2}".format(prefix, a, b),
                            "exempted": False,
                        }
                    )

    # List of Figures / Tables reconciliation
    if has_lists:
        list_map: Dict[Tuple[str, str], ListItem] = {}
        has_any_page = any(li.page is not None for li in list_items)
        for li in list_items:
            key = (li.kind, li.cap_id)
            list_map[key] = li
            if has_any_page and li.page is None:
                findings.append(
                    {
                        "rule_id": "LIST_MISSING_PAGE_NUMBER",
                        "severity": "FAIL",
                        "location": li.location,
                        "message": "清单条目 {0} {1} 缺失页码".format(
                            "图" if li.kind == "fig" else "表", li.cap_id
                        ),
                        "evidence": li.title[:80],
                        "exempted": False,
                    }
                )
            if key not in cap_map:
                findings.append(
                    {
                        "rule_id": "LIST_PHANTOM_CAPTION",
                        "severity": "FAIL",
                        "location": li.location,
                        "message": "清单中存在正文无对应的幽灵条目：{0} {1}".format(
                            "图" if li.kind == "fig" else "表", li.cap_id
                        ),
                        "evidence": li.title[:80],
                        "exempted": False,
                    }
                )
            else:
                cap = cap_map[key]
                if _normalize_title(cap.title) != _normalize_title(li.title):
                    findings.append(
                        {
                            "rule_id": "LIST_TITLE_MISMATCH",
                            "severity": "FAIL",
                            "location": li.location,
                            "message": "清单与正文标题不一致 ({0} {1})".format(
                                "图" if li.kind == "fig" else "表", li.cap_id
                            ),
                            "evidence": "清单:'{0}' vs 正文:'{1}'".format(li.title[:40], cap.title[:40]),
                            "exempted": False,
                        }
                    )

        listed_kinds = set(li.kind for li in list_items)
        for key, cap in cap_map.items():
            if cap.kind in listed_kinds and key not in list_map:
                findings.append(
                    {
                        "rule_id": "LIST_MISSING_CAPTION",
                        "severity": "FAIL",
                        "location": cap.location,
                        "message": "正文{0} {1} 漏列于对应清单".format(
                            "图" if cap.kind == "fig" else "表", cap.cap_id
                        ),
                        "evidence": cap.title[:80],
                        "exempted": False,
                    }
                )

    # Orphan / unreferenced caption checks in prose
    referenced: Set[Tuple[str, str]] = set()
    zh_ref_re = re.compile(
        r"(?:如|见|参见|详见|参照|根据|由|在)?\s*(图|表)\s*([A-Z]?\d+(?:[-.]\d+)+[a-zA-Z]?)"
        r"|(?:如|见|参见|详见|参照|根据|由)\s*(图|表)\s*([A-Z]?\d+[a-zA-Z]?)"
        r"|(图|表)\s*([A-Z]?\d+[a-zA-Z]?)(?=\s*(?:中|所示|显示|表明|汇总|对比|统计|列出))"
    )
    en_ref_re = re.compile(r"\b(Figure|Fig\.|Table)\s+([A-Z]?\d+(?:[-.]\d+)*[a-zA-Z]?)\b")

    for loc, txt in prose_lines:
        for m in zh_ref_re.finditer(txt):
            label = m.group(1) or m.group(3) or m.group(5)
            cid = m.group(2) or m.group(4) or m.group(6)
            if not label or not cid:
                continue
            kind = "fig" if label == "图" else "tbl"
            key = (kind, cid)
            referenced.add(key)
            if cap_map and key not in cap_map:
                findings.append(
                    {
                        "rule_id": "ORPHAN_CAPTION_REF",
                        "severity": "FAIL",
                        "location": loc,
                        "message": "正文引用了不存在的{0} {1}".format(label, cid),
                        "evidence": txt[:80],
                        "exempted": False,
                    }
                )
        for m in en_ref_re.finditer(txt):
            label = m.group(1)
            cid = m.group(2)
            kind = "fig" if label.lower().startswith("fig") else "tbl"
            key = (kind, cid)
            referenced.add(key)
            if cap_map and key not in cap_map:
                findings.append(
                    {
                        "rule_id": "ORPHAN_CAPTION_REF",
                        "severity": "FAIL",
                        "location": loc,
                        "message": "正文引用了不存在的 {0} {1}".format(label, cid),
                        "evidence": txt[:80],
                        "exempted": False,
                    }
                )

    if prose_lines:
        for key, cap in cap_map.items():
            if key not in referenced:
                findings.append(
                    {
                        "rule_id": "UNREFERENCED_CAPTION",
                        "severity": "WARN",
                        "location": cap.location,
                        "message": "正文从未明确引用{0} {1}".format(
                            "图" if cap.kind == "fig" else "表", cap.cap_id
                        ),
                        "evidence": cap.title[:80],
                        "exempted": False,
                    }
                )

    return findings


def _safe_eval_ast(node: ast.AST, env: Dict[str, float]) -> float:
    if isinstance(node, ast.Expression):
        return _safe_eval_ast(node.body, env)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return float(node.value)
        raise ValueError("表达式中仅允许数值常量")
    if hasattr(ast, "Num") and isinstance(node, ast.Num):  # Python 3.8 compatibility
        return float(node.n)
    if isinstance(node, ast.Name):
        if node.id not in env:
            raise KeyError("未定义变量: {0}".format(node.id))
        return env[node.id]
    if isinstance(node, ast.UnaryOp):
        val = _safe_eval_ast(node.operand, env)
        if isinstance(node.op, ast.UAdd):
            return +val
        if isinstance(node.op, ast.USub):
            return -val
        raise ValueError("不支持的一元运算符")
    if isinstance(node, ast.BinOp):
        left = _safe_eval_ast(node.left, env)
        right = _safe_eval_ast(node.right, env)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                raise ZeroDivisionError("表达式出现除以零")
            return left / right
        raise ValueError("不支持的二元运算符")
    raise ValueError("不允许的表达式节点类型: {0}".format(type(node).__name__))


def _resolve_rule_variable(
    var_name: str, spec: Dict[str, Any], tables: Sequence[ExtractedTable]
) -> float:
    doc_match = spec.get("doc_match", "")
    table_match = spec.get("table_match", "")
    row_match = spec.get("row_match", "")
    col_match = spec.get("col_match", "")
    extract_regex = spec.get("extract_regex")
    agg = str(spec.get("agg", "first")).lower()

    for tbl in tables:
        if doc_match and not re.search(doc_match, tbl.doc_path):
            continue
        tbl_label = "{0} {1}".format(tbl.caption_id or "", tbl.caption).strip()
        if table_match and not re.search(table_match, tbl_label):
            continue

        col_indices = [
            idx for idx, h in enumerate(tbl.headers) if not col_match or re.search(col_match, h)
        ]
        if not col_indices:
            continue

        for row in tbl.rows[1:]:
            row_label = row[0].text
            if row_match and not re.search(row_match, row_label):
                continue
            for c_idx in col_indices:
                cell_txt = row[c_idx].text
                if extract_regex:
                    matches = re.findall(extract_regex, cell_txt)
                    nums = [float(m[0] if isinstance(m, tuple) else m) for m in matches]
                    if not nums:
                        continue
                    if agg == "sum":
                        return sum(nums)
                    if agg == "count":
                        return float(len(nums))
                    return nums[0]
                else:
                    parsed = _parse_num(cell_txt)
                    if parsed is not None:
                        return parsed[0]
    raise KeyError("规则变量 '{0}' 未能在文档表格中匹配到数值".format(var_name))


def _evaluate_custom_rules(
    rules_path: Path, tables: Sequence[ExtractedTable], default_tol: float
) -> List[Dict[str, Any]]:
    try:
        cfg = json.loads(_read_text_with_fallback(rules_path))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("无法解析跨表规则文件 {0}: {1}".format(rules_path, exc))

    env: Dict[str, float] = {}
    findings: List[Dict[str, Any]] = []
    for var_name, spec in (cfg.get("variables") or {}).items():
        try:
            env[var_name] = _resolve_rule_variable(var_name, spec, tables)
        except KeyError as exc:
            findings.append(
                {
                    "rule_id": "RULE_VARIABLE_MISSING",
                    "severity": "FAIL",
                    "location": str(rules_path.name),
                    "message": str(exc),
                    "evidence": var_name,
                    "exempted": False,
                }
            )

    for assertion in cfg.get("assertions", []):
        aid = str(assertion.get("id", "CUSTOM_ASSERT"))
        desc = str(assertion.get("description", aid))
        lhs_expr = str(assertion["lhs"])
        rhs_expr = str(assertion["rhs"])
        op = str(assertion.get("op", "==")).strip()
        tol = float(assertion.get("tol", default_tol))
        sev = str(assertion.get("severity", "FAIL")).upper()

        try:
            lhs_val = _safe_eval_ast(ast.parse(lhs_expr, mode="eval"), env)
            rhs_val = _safe_eval_ast(ast.parse(rhs_expr, mode="eval"), env)
        except (KeyError, ValueError, ZeroDivisionError, SyntaxError) as exc:
            findings.append(
                {
                    "rule_id": aid,
                    "severity": "FAIL",
                    "location": str(rules_path.name),
                    "message": "断言求值失败 ({0}): {1}".format(desc, exc),
                    "evidence": "{0} {1} {2}".format(lhs_expr, op, rhs_expr),
                    "exempted": False,
                }
            )
            continue

        ok = False
        if op == "==":
            ok = abs(lhs_val - rhs_val) <= tol
        elif op == "!=":
            ok = abs(lhs_val - rhs_val) > tol
        elif op == "<=":
            ok = lhs_val <= rhs_val + tol
        elif op == ">=":
            ok = lhs_val + tol >= rhs_val
        elif op == "<":
            ok = lhs_val < rhs_val
        elif op == ">":
            ok = lhs_val > rhs_val
        else:
            raise ValueError("不支持的断言运算符: {0}".format(op))

        if not ok:
            findings.append(
                {
                    "rule_id": aid,
                    "severity": sev,
                    "location": str(rules_path.name),
                    "message": "跨表断言失败：{0}（左={1:.4g} {2} 右={3:.4g}, tol={4}）".format(
                        desc, lhs_val, op, rhs_val, tol
                    ),
                    "evidence": "{0} ({1:.4g}) {2} {3} ({4:.4g})".format(
                        lhs_expr, lhs_val, op, rhs_expr, rhs_val
                    ),
                    "exempted": False,
                }
            )
    return findings


def main(argv: Optional[Sequence[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="核对 Markdown/DOCX 表格纵向横向加总、图表编号连续性、清单对齐与自定义跨表规则"
    )
    parser.add_argument("--docs", nargs="+", required=True, help="待审计的 .md/.txt/.docx 文档列表")
    parser.add_argument("--rules", help="可选声明式跨表规则 JSON 文件")
    parser.add_argument("--tol", type=float, default=0.05, help="算术容差（默认 0.05）")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="输出格式")
    parser.add_argument("--strict", action="store_true", help="将 WARN 视为退出码 1")

    args = parser.parse_args(argv)

    all_tables: List[ExtractedTable] = []
    all_captions: List[CaptionItem] = []
    all_list_items: List[ListItem] = []
    any_lists = False
    all_prose: List[Tuple[str, str]] = []

    try:
        for raw_doc in args.docs:
            p = Path(raw_doc)
            if not p.exists():
                raise FileNotFoundError("文档不存在: {0}".format(p))
            if p.suffix.lower() == ".docx":
                tbls, caps, lis, has_l, prose = _extract_docx_doc(p)
            else:
                tbls, caps, lis, has_l, prose = _extract_md_doc(p)
            all_tables.extend(tbls)
            all_captions.extend(caps)
            all_list_items.extend(lis)
            any_lists = any_lists or has_l
            all_prose.extend(prose)
    except (FileNotFoundError, ValueError, OSError) as exc:
        sys.stderr.write("文档解析错误: {0}\n".format(exc))
        return 2

    findings: List[Dict[str, Any]] = []
    for tbl in all_tables:
        findings.extend(_audit_table_arithmetic(tbl, args.tol))

    findings.extend(_audit_captions_and_refs(all_captions, all_list_items, any_lists, all_prose))

    if args.rules:
        try:
            findings.extend(_evaluate_custom_rules(Path(args.rules), all_tables, args.tol))
        except (ValueError, OSError) as exc:
            sys.stderr.write("跨表规则执行错误: {0}\n".format(exc))
            return 2

    fail_cnt = sum(1 for f in findings if f["severity"] == "FAIL")
    warn_cnt = sum(1 for f in findings if f["severity"] == "WARN")
    status = "FAIL" if fail_cnt > 0 else ("WARN" if warn_cnt > 0 else "PASS")

    payload: Dict[str, Any] = {
        "tool": "cross_table_reconciler",
        "version": VERSION,
        "status": status,
        "summary": {
            "docs_count": len(args.docs),
            "tables_extracted": len(all_tables),
            "captions_extracted": len(all_captions),
            "list_items_extracted": len(all_list_items),
            "fail_count": fail_cnt,
            "warn_count": warn_cnt,
        },
        "findings": findings,
    }

    if args.format == "json":
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    else:
        sys.stdout.write(
            "[cross_table_reconciler v{0}] status={1} tables={2} captions={3} fail={4} warn={5}\n".format(
                VERSION, status, len(all_tables), len(all_captions), fail_cnt, warn_cnt
            )
        )
        for item in findings:
            sys.stdout.write(
                "- [{0}] {1} @ {2}: {3}\n".format(
                    item["severity"], item["rule_id"], item["location"], item["message"]
                )
            )

    if fail_cnt > 0 or (args.strict and warn_cnt > 0):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
