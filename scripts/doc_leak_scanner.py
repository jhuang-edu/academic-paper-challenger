#!/usr/bin/env python3
"""Universal document leak and cross-file sync scanner (Python 3.8+ stdlib only)."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import difflib
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
import xml.etree.ElementTree as ET
import zipfile

VERSION = "1.0.0"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MONO_FONTS = {
    "consolas",
    "courier new",
    "dejavu sans mono",
    "jetbrains mono",
    "menlo",
    "monaco",
    "source code pro",
    "fira code",
}
SUPPORTED_EXTS = {".md", ".txt", ".docx"}

DEFAULT_NEGATION_LEFT = (
    r"(?:不涉及|不含|不包含|排除|未采用|未使用|未引入|并非|非|禁止|严禁|杜绝|消除|清除|无须|无需|"
    r"avoid|exclude|without|not\s+use|no\s+)"
)
DEFAULT_CONTRAST_BREAK = r"(?:但是|但|然而|不过|却|实际|however|but|yet)"
DEFAULT_NEGATION_RIGHT = r"(?:已清除|已删除|已替换|已脱敏|removed|excluded)"


@dataclass
class TextBlock:
    doc_path: str
    carrier: str  # "md" | "docx"
    location: str
    text: str
    is_code: bool = False
    line_no: Optional[int] = None


@dataclass
class RuleDef:
    rule_id: str
    applies_to: Tuple[str, ...]
    severity: str
    exemptible: bool
    pattern: str
    ignore_case: bool
    description: str


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _w_attr(elem: ET.Element, name: str) -> Optional[str]:
    return elem.attrib.get("{{{0}}}{1}".format(W_NS, name)) or elem.attrib.get(name)


def _extract_docx_para_info(p_elem: ET.Element) -> Tuple[str, bool, int, int]:
    """Extract paragraph text (excluding w:del), detect code style/font, and count revisions."""
    style_is_code = False
    p_pr = p_elem.find("{{{0}}}pPr".format(W_NS))
    if p_pr is not None:
        p_style = p_pr.find("{{{0}}}pStyle".format(W_NS))
        if p_style is not None:
            val = _w_attr(p_style, "val") or ""
            if re.search(r"(?i)(code|verbatim|source|listing)", val):
                style_is_code = True

    parts: List[str] = []
    ins_count = 0
    del_count = 0
    total_nonempty_runs = 0
    mono_runs = 0

    def walk_inline(node: ET.Element, in_del: bool = False) -> None:
        nonlocal ins_count, del_count, total_nonempty_runs, mono_runs
        lname = _local_name(node.tag)
        if lname == "del":
            del_count += 1
            return
        if lname == "delText":
            return
        if lname == "ins":
            ins_count += 1
        if lname == "r":
            r_pr = node.find("{{{0}}}rPr".format(W_NS))
            is_mono_run = False
            if r_pr is not None:
                r_fonts = r_pr.find("{{{0}}}rFonts".format(W_NS))
                if r_fonts is not None:
                    for fname_attr in ("ascii", "hAnsi", "cs"):
                        fname = (_w_attr(r_fonts, fname_attr) or "").strip().lower()
                        if fname in MONO_FONTS:
                            is_mono_run = True
                            break
            run_buf: List[str] = []
            for child in list(node):
                clname = _local_name(child.tag)
                if clname == "t" and child.text:
                    run_buf.append(child.text)
                elif clname == "tab":
                    run_buf.append("\t")
                elif clname in ("br", "cr"):
                    run_buf.append("\n")
                elif clname not in ("rPr", "delText"):
                    walk_inline(child, in_del)
            run_txt = "".join(run_buf)
            if run_txt.strip():
                total_nonempty_runs += 1
                if is_mono_run:
                    mono_runs += 1
            parts.append(run_txt)
            return
        if lname == "t" and not in_del and node.text:
            parts.append(node.text)
            return
        if lname == "tab" and not in_del:
            parts.append("\t")
            return
        if lname in ("br", "cr") and not in_del:
            parts.append("\n")
            return
        for child in list(node):
            walk_inline(child, in_del)

    for child in list(p_elem):
        if _local_name(child.tag) != "pPr":
            walk_inline(child, False)

    text = "".join(parts)
    is_code = style_is_code
    if not is_code and total_nonempty_runs > 0 and mono_runs == total_nonempty_runs:
        if re.search(r"[=(){}\[\];_]|def |class |import |SELECT ", text):
            is_code = True
    return text, is_code, ins_count, del_count


def _extract_docx_blocks(path: Path) -> Tuple[List[TextBlock], Dict[str, Any]]:
    blocks: List[TextBlock] = []
    meta: Dict[str, Any] = {
        "comments": [],
        "ins_count": 0,
        "del_count": 0,
    }
    try:
        zf = zipfile.ZipFile(str(path), "r")
    except (zipfile.BadZipFile, OSError) as exc:
        raise ValueError("无法打开 DOCX 文件 {0}: {1}".format(path, exc))

    with zf:
        names = set(zf.namelist())
        if "word/document.xml" not in names:
            raise ValueError("DOCX 缺少 word/document.xml: {0}".format(path))

        part_order: List[str] = ["word/document.xml"]
        part_order.extend(sorted(n for n in names if re.match(r"^word/header\d*\.xml$", n)))
        part_order.extend(sorted(n for n in names if re.match(r"^word/footer\d*\.xml$", n)))
        for extra in ("word/footnotes.xml", "word/endnotes.xml"):
            if extra in names:
                part_order.append(extra)

        for part_name in part_order:
            raw = zf.read(part_name)
            try:
                root = ET.fromstring(raw)
            except ET.ParseError as exc:
                raise ValueError("DOCX XML 解析失败 ({0}:{1}): {2}".format(path, part_name, exc))

            part_short = part_name.replace("word/", "").replace(".xml", "")
            container = root.find("{{{0}}}body".format(W_NS))
            if container is None:
                container = root

            p_counter = 0
            t_counter = 0

            def walk_container(elem: ET.Element) -> None:
                nonlocal p_counter, t_counter
                for child in list(elem):
                    lname = _local_name(child.tag)
                    if lname == "p":
                        p_counter += 1
                        txt, is_code, ins_c, del_c = _extract_docx_para_info(child)
                        meta["ins_count"] += ins_c
                        meta["del_count"] += del_c
                        if txt.strip():
                            blocks.append(
                                TextBlock(
                                    doc_path=str(path),
                                    carrier="docx",
                                    location="{0}:{1}:p{2}".format(path.name, part_short, p_counter),
                                    text=txt,
                                    is_code=is_code,
                                )
                            )
                    elif lname == "tbl":
                        t_counter += 1
                        rows = [tr for tr in list(child) if _local_name(tr.tag) == "tr"]
                        for r_idx, tr in enumerate(rows, start=1):
                            cells = [tc for tc in list(tr) if _local_name(tc.tag) == "tc"]
                            is_single_cell_tbl = len(rows) == 1 and len(cells) == 1
                            for c_idx, tc in enumerate(cells, start=1):
                                cell_lines: List[str] = []
                                cell_code_flags: List[bool] = []
                                for p_node in list(tc):
                                    if _local_name(p_node.tag) == "p":
                                        ptxt, pcode, ins_c, del_c = _extract_docx_para_info(p_node)
                                        meta["ins_count"] += ins_c
                                        meta["del_count"] += del_c
                                        cell_lines.append(ptxt)
                                        if ptxt.strip():
                                            cell_code_flags.append(pcode)
                                joined = "\n".join(cell_lines)
                                cell_is_code = bool(
                                    is_single_cell_tbl
                                    and cell_code_flags
                                    and all(cell_code_flags)
                                )
                                if joined.strip():
                                    blocks.append(
                                        TextBlock(
                                            doc_path=str(path),
                                            carrier="docx",
                                            location="{0}:{1}:tbl{2}:r{3}c{4}".format(
                                                path.name, part_short, t_counter, r_idx, c_idx
                                            ),
                                            text=joined,
                                            is_code=cell_is_code,
                                        )
                                    )
                    elif lname == "sdt":
                        sdt_content = child.find("{{{0}}}sdtContent".format(W_NS))
                        if sdt_content is not None:
                            walk_container(sdt_content)

            walk_container(container)

        if "word/comments.xml" in names:
            raw_c = zf.read("word/comments.xml")
            try:
                c_root = ET.fromstring(raw_c)
                for c_elem in c_root.findall(".//{{{0}}}comment".format(W_NS)):
                    cid = _w_attr(c_elem, "id") or "?"
                    author = _w_attr(c_elem, "author") or "unknown"
                    ctext = "".join(t.text or "" for t in c_elem.findall(".//{{{0}}}t".format(W_NS))).strip()
                    meta["comments"].append({"id": cid, "author": author, "text": ctext[:80]})
            except ET.ParseError:
                pass

    return blocks, meta


def _read_text_with_fallback(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _extract_md_blocks(path: Path) -> Tuple[List[TextBlock], List[Dict[str, Any]]]:
    content = _read_text_with_fallback(path)
    lines = content.splitlines()
    blocks: List[TextBlock] = []
    structural_findings: List[Dict[str, Any]] = []

    idx = 0
    n = len(lines)
    # Skip leading YAML frontmatter if present
    if n >= 3 and lines[0].strip() == "---":
        end_fm = None
        for j in range(1, n):
            if lines[j].strip() in ("---", "..."):
                end_fm = j
                break
        if end_fm is not None:
            idx = end_fm + 1

    in_code = False
    fence_char = ""
    fence_len = 0
    fence_start = 0

    while idx < n:
        line = lines[idx]
        line_no = idx + 1
        m_fence = re.match(r"^[ ]{0,3}(`{3,}|~{3,})(.*)$", line)
        if not in_code and m_fence:
            fence_seq = m_fence.group(1)
            fence_char = fence_seq[0]
            fence_len = len(fence_seq)
            in_code = True
            fence_start = line_no
            blocks.append(
                TextBlock(
                    doc_path=str(path),
                    carrier="md",
                    location="{0}:{1}".format(path.name, line_no),
                    text=line,
                    is_code=True,
                    line_no=line_no,
                )
            )
            idx += 1
            continue

        if in_code:
            if m_fence:
                seq = m_fence.group(1)
                rest = m_fence.group(2).strip()
                if seq[0] == fence_char and len(seq) >= fence_len and rest == "":
                    in_code = False
                    blocks.append(
                        TextBlock(
                            doc_path=str(path),
                            carrier="md",
                            location="{0}:{1}".format(path.name, line_no),
                            text=line,
                            is_code=True,
                            line_no=line_no,
                        )
                    )
                    idx += 1
                    continue
            blocks.append(
                TextBlock(
                    doc_path=str(path),
                    carrier="md",
                    location="{0}:{1}".format(path.name, line_no),
                    text=line,
                    is_code=True,
                    line_no=line_no,
                )
            )
            idx += 1
            continue

        blocks.append(
            TextBlock(
                doc_path=str(path),
                carrier="md",
                location="{0}:{1}".format(path.name, line_no),
                text=line,
                is_code=False,
                line_no=line_no,
            )
        )
        idx += 1

    if in_code:
        structural_findings.append(
            {
                "rule_id": "MD_UNCLOSED_FENCE",
                "severity": "FAIL",
                "location": "{0}:{1}".format(path.name, fence_start),
                "message": "Markdown 代码围栏自第 {0} 行起未闭合".format(fence_start),
                "evidence": lines[fence_start - 1][:100],
                "exempted": False,
            }
        )

    return blocks, structural_findings


def _default_rules() -> List[RuleDef]:
    return [
        RuleDef(
            rule_id="DOCX_UNRENDERED_BOLD",
            applies_to=("docx",),
            severity="FAIL",
            exemptible=False,
            pattern=r"\*\*[^*\n]{1,120}\*\*",
            ignore_case=False,
            description="DOCX 中残留未渲染的 Markdown 加粗星号 **",
        ),
        RuleDef(
            rule_id="DOCX_UNRENDERED_BACKTICK",
            applies_to=("docx",),
            severity="FAIL",
            exemptible=False,
            pattern=r"`",
            ignore_case=False,
            description="DOCX 正文或表格中残留未渲染反引号 `",
        ),
        RuleDef(
            rule_id="DOCX_UNRENDERED_QUOTE",
            applies_to=("docx",),
            severity="FAIL",
            exemptible=False,
            pattern=r"(?m)^\s*>\s+\S",
            ignore_case=False,
            description="DOCX 中残留未解析的 Markdown 块引用前缀 >",
        ),
        RuleDef(
            rule_id="DOCX_RAW_FENCE",
            applies_to=("docx",),
            severity="FAIL",
            exemptible=False,
            pattern=r"(?:^|\n)\s*(?:```|~~~)",
            ignore_case=False,
            description="DOCX 中出现原始代码块围栏 ``` 或 ~~~",
        ),
        RuleDef(
            rule_id="RAW_HTML_BR",
            applies_to=("docx", "md"),
            severity="WARN",  # Overridden to FAIL for docx at evaluation time
            exemptible=False,
            pattern=r"<\s*br\s*/?\s*>",
            ignore_case=True,
            description="文档中残留原始 HTML <br> 换行标签",
        ),
        RuleDef(
            rule_id="HTML_COMMENT_LEAK",
            applies_to=("all",),
            severity="FAIL",
            exemptible=False,
            pattern=r"<!--[\s\S]*?-->",
            ignore_case=False,
            description="残留未清理的 HTML/Markdown 注释 <!-- ... -->",
        ),
        RuleDef(
            rule_id="PLACEHOLDER_LEAK",
            applies_to=("all",),
            severity="FAIL",
            exemptible=True,
            pattern=r"\b(?:TODO|TBD|FIXME|XXX)\b|(?:待补充|待完善|待替换|待核实|此处填写|正式提交前)",
            ignore_case=True,
            description="残留未填写或待替换占位符",
        ),
        RuleDef(
            rule_id="DRAFT_LINE_REF",
            applies_to=("all",),
            severity="FAIL",
            exemptible=True,
            pattern=r"(?<![A-Za-z0-9_])L\d{2,5}(?:\s*[-–—~]\s*L?\d{1,5})?\b|(?<![A-Za-z0-9_])L\d\s*[-–—~]\s*L?\d\b",
            ignore_case=False,
            description="疑似泄露旧版草稿行号引用（如 L204）",
        ),
        RuleDef(
            rule_id="RANDOM_SEED_LEAK",
            applies_to=("all",),
            severity="FAIL",
            exemptible=True,
            pattern=r"\b(?:random_?state|np\.random\.seed|torch\.manual_seed|seed)\s*=\s*\d+",
            ignore_case=True,
            description="正文中泄露代码调试伪随机种子参数（如 seed=42）",
        ),
        RuleDef(
            rule_id="BARE_SNAKE_CASE",
            applies_to=("all",),
            severity="WARN",
            exemptible=True,
            pattern=r"(?<![A-Za-z0-9_./:-])[a-z][a-z0-9]*(?:_[a-z0-9]+)+(?![A-Za-z0-9_])",
            ignore_case=False,
            description="中文叙事或表格中直接裸露 snake_case 程序变量名",
        ),
        RuleDef(
            rule_id="AI_SURGERY_THREAD",
            applies_to=("all",),
            severity="FAIL",
            exemptible=True,
            pattern=(
                r"(?:与原有表述相比|保留原研究|按.{0,12}指南替换|仅锁定\s*[A-Z]{1,3}\d+|"
                r"本版本|旧稿|内控脚本|防线\s*[A-Z]?\d+|作为\s*AI\s*语言模型|以下为修改后的)"
            ),
            ignore_case=False,
            description="疑似 AI 改写或内部控制指令手术线头",
        ),
    ]


def _load_rules(rules_path: Optional[Path]) -> Tuple[List[RuleDef], Set[str], Dict[str, Any]]:
    rules = _default_rules()
    whitelist: Set[str] = set()
    neg_cfg: Dict[str, Any] = {
        "left_chars": 18,
        "right_chars": 10,
        "extra_cues": [],
    }
    if rules_path is None:
        return rules, whitelist, neg_cfg

    try:
        cfg = json.loads(_read_text_with_fallback(rules_path))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("无法解析规则文件 {0}: {1}".format(rules_path, exc))

    if not cfg.get("inherit_defaults", True):
        rules = []

    disabled = set(cfg.get("disable_rule_ids", []))
    rules = [r for r in rules if r.rule_id not in disabled]

    for w in cfg.get("whitelist_terms", []):
        whitelist.add(str(w).strip().lower())

    nw = cfg.get("negation_window") or {}
    if "left_chars" in nw:
        neg_cfg["left_chars"] = int(nw["left_chars"])
    if "right_chars" in nw:
        neg_cfg["right_chars"] = int(nw["right_chars"])
    if "extra_cues" in nw:
        neg_cfg["extra_cues"] = [str(c) for c in nw["extra_cues"] if str(c).strip()]

    for cr in cfg.get("custom_rules", []):
        rules.append(
            RuleDef(
                rule_id=str(cr["id"]),
                applies_to=tuple(cr.get("applies_to", ["all"])),
                severity=str(cr.get("severity", "FAIL")).upper(),
                exemptible=bool(cr.get("exemptible", True)),
                pattern=str(cr["pattern"]),
                ignore_case=bool(cr.get("ignore_case", False)),
                description=str(cr.get("description", "自定义规则命中")),
            )
        )
    return rules, whitelist, neg_cfg


def _check_three_tier_negation(
    text: str,
    start: int,
    end: int,
    neg_cfg: Dict[str, Any],
) -> Optional[str]:
    """Return negation cue if exempted under three-tier window, else None."""
    left_chars = neg_cfg.get("left_chars", 18)
    right_chars = neg_cfg.get("right_chars", 10)
    extra = neg_cfg.get("extra_cues", [])

    left_raw = text[max(0, start - left_chars) : start]
    # Cut at the last sentence boundary before the match
    boundary_pos = max(
        left_raw.rfind("。"),
        left_raw.rfind("！"),
        left_raw.rfind("？"),
        left_raw.rfind("；"),
        left_raw.rfind("\n"),
    )
    if boundary_pos != -1:
        left_ctx = left_raw[boundary_pos + 1 :]
    else:
        left_ctx = left_raw

    neg_pattern = DEFAULT_NEGATION_LEFT
    if extra:
        escaped_extra = "|".join(re.escape(c) for c in extra)
        neg_pattern = "(?:{0}|{1})".format(DEFAULT_NEGATION_LEFT, escaped_extra)

    neg_matches = list(re.finditer(neg_pattern, left_ctx, flags=re.IGNORECASE))
    if neg_matches:
        last_neg = neg_matches[-1]
        after_neg = left_ctx[last_neg.end() :]
        if not re.search(DEFAULT_CONTRAST_BREAK, after_neg, flags=re.IGNORECASE):
            return last_neg.group(0)

    right_raw = text[end : min(len(text), end + right_chars)]
    for sep in ("。", "！", "？", "；", "\n"):
        pos = right_raw.find(sep)
        if pos != -1:
            right_raw = right_raw[:pos]
    m_right = re.search(DEFAULT_NEGATION_RIGHT, right_raw, flags=re.IGNORECASE)
    if m_right:
        return m_right.group(0)
    return None


def _strip_urls(text: str) -> str:
    return re.sub(r"https?://\S+", lambda m: " " * len(m.group(0)), text)


def _mask_inline_code_if_cs(text: str, mode: str, carrier: str) -> str:
    if mode == "cs" and carrier == "md":
        return re.sub(r"`[^`\n]+`", lambda m: " " * len(m.group(0)), text)
    return text


def _scan_blocks(
    blocks: Sequence[TextBlock],
    rules: Sequence[RuleDef],
    whitelist: Set[str],
    neg_cfg: Dict[str, Any],
    mode: str,
) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    has_cjk_re = re.compile(r"[\u4e00-\u9fff]")

    for blk in blocks:
        if blk.is_code:
            continue

        for rule in rules:
            if "all" not in rule.applies_to and blk.carrier not in rule.applies_to:
                continue

            scan_text = blk.text
            if rule.rule_id == "BARE_SNAKE_CASE":
                if blk.carrier == "md" and not has_cjk_re.search(scan_text):
                    continue
                scan_text = _strip_urls(scan_text)
                scan_text = _mask_inline_code_if_cs(scan_text, mode, blk.carrier)
            elif rule.rule_id == "DRAFT_LINE_REF":
                scan_text = _strip_urls(scan_text)

            flags = re.IGNORECASE if rule.ignore_case else 0
            try:
                compiled = re.compile(rule.pattern, flags=flags)
            except re.error as exc:
                raise ValueError("规则 {0} 正则语法错误: {1}".format(rule.rule_id, exc))

            for m in compiled.finditer(scan_text):
                matched = m.group(0)
                if matched.strip().lower() in whitelist:
                    continue

                severity = rule.severity
                if rule.rule_id == "RAW_HTML_BR" and blk.carrier == "docx":
                    severity = "FAIL"

                exempted = False
                neg_cue: Optional[str] = None
                if rule.exemptible:
                    neg_cue = _check_three_tier_negation(blk.text, m.start(), m.end(), neg_cfg)
                    if neg_cue is not None:
                        exempted = True
                        severity = "INFO"

                ctx_start = max(0, m.start() - 18)
                ctx_end = min(len(blk.text), m.end() + 18)
                evidence = blk.text[ctx_start:ctx_end].replace("\n", " ")

                msg = rule.description
                if exempted and neg_cue:
                    msg = "{0}（已被否定语境 '{1}' 豁免）".format(msg, neg_cue)

                findings.append(
                    {
                        "rule_id": rule.rule_id,
                        "severity": severity,
                        "location": blk.location,
                        "message": msg,
                        "evidence": evidence,
                        "exempted": exempted,
                    }
                )
    return findings


def _collect_input_files(paths: Sequence[str]) -> List[Path]:
    files: List[Path] = []
    for raw_p in paths:
        p = Path(raw_p)
        if not p.exists():
            raise FileNotFoundError("输入路径不存在: {0}".format(p))
        if p.is_file():
            if p.suffix.lower() in SUPPORTED_EXTS:
                files.append(p)
        else:
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and sub.suffix.lower() in SUPPORTED_EXTS:
                    files.append(sub)
    return files


def _extract_paragraphs_for_compare(path: Path) -> List[str]:
    ext = path.suffix.lower()
    if ext == ".docx":
        blocks, _ = _extract_docx_blocks(path)
        paras: List[str] = []
        for b in blocks:
            norm = re.sub(r"\s+", " ", b.text).strip()
            if norm:
                paras.append(norm)
        return paras

    content = _read_text_with_fallback(path)
    lines = content.splitlines()
    start_idx = 0
    if len(lines) >= 3 and lines[0].strip() == "---":
        for j in range(1, len(lines)):
            if lines[j].strip() in ("---", "..."):
                start_idx = j + 1
                break
    body = "\n".join(lines[start_idx:])
    body = re.sub(r"<!--[\s\S]*?-->", "", body)

    paras = []
    buf: List[str] = []
    for line in body.splitlines():
        s = line.strip()
        if s == "" or re.match(r"^[-*_]{3,}$", s):
            if buf:
                norm = re.sub(r"\s+", " ", " ".join(buf)).strip()
                if norm:
                    paras.append(norm)
                buf = []
        else:
            buf.append(s)
    if buf:
        norm = re.sub(r"\s+", " ", " ".join(buf)).strip()
        if norm:
            paras.append(norm)
    return paras


def _run_compare(merged_path: Path, part_paths: Sequence[Path]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    merged_paras = _extract_paragraphs_for_compare(merged_path)
    merged_fps = [hashlib.sha1(p.encode("utf-8")).hexdigest()[:12] for p in merged_paras]

    claimed: Set[int] = set()
    part_reports: List[Dict[str, Any]] = []
    findings: List[Dict[str, Any]] = []

    for p_path in part_paths:
        p_paras = _extract_paragraphs_for_compare(p_path)
        p_fps = [hashlib.sha1(p.encode("utf-8")).hexdigest()[:12] for p in p_paras]
        matcher = difflib.SequenceMatcher(None, merged_fps, p_fps, autojunk=False)
        matched_part_indices: Set[int] = set()
        matched_chars = 0

        for block in matcher.get_matching_blocks():
            for k in range(block.size):
                m_i = block.a + k
                p_j = block.b + k
                if p_j not in matched_part_indices:
                    matched_part_indices.add(p_j)
                    claimed.add(m_i)
                    matched_chars += len(p_paras[p_j])

        # Near-match pass for minor punctuation/spacing differences
        near_matches = 0
        for p_j, p_txt in enumerate(p_paras):
            if p_j in matched_part_indices:
                continue
            best_m: Optional[int] = None
            best_ratio = 0.0
            for m_i, m_txt in enumerate(merged_paras):
                if m_i in claimed:
                    continue
                ratio = difflib.SequenceMatcher(None, p_txt, m_txt, autojunk=False).ratio()
                if ratio >= 0.92 and ratio > best_ratio:
                    best_ratio = ratio
                    best_m = m_i
            if best_m is not None:
                matched_part_indices.add(p_j)
                claimed.add(best_m)
                matched_chars += len(p_txt)
                near_matches += 1
                findings.append(
                    {
                        "rule_id": "COMPARE_NEAR_MATCH",
                        "severity": "WARN",
                        "location": "{0}:para{1}".format(p_path.name, p_j + 1),
                        "message": "分章与合稿段落存在轻微标点/空格差异 (相似度 {0:.2f})".format(best_ratio),
                        "evidence": p_txt[:80],
                        "exempted": False,
                    }
                )

        part_chars = sum(len(x) for x in p_paras)
        total_p = len(p_paras)
        cov = (len(matched_part_indices) / float(total_p)) if total_p > 0 else 1.0
        missing_snippets = [
            p_paras[j][:80] for j in range(total_p) if j not in matched_part_indices
        ][:5]

        part_reports.append(
            {
                "part": str(p_path),
                "part_paras": total_p,
                "matched_paras": len(matched_part_indices),
                "near_matches": near_matches,
                "part_chars": part_chars,
                "matched_chars": matched_chars,
                "char_diff": part_chars - matched_chars,
                "coverage_ratio": round(cov, 4),
                "missing_snippets": missing_snippets,
            }
        )

        if cov < 1.0:
            findings.append(
                {
                    "rule_id": "COMPARE_SYNC_DRIFT",
                    "severity": "FAIL",
                    "location": str(p_path.name),
                    "message": "分章与合稿不同步：覆盖率 {0:.1%}，缺失 {1} 段".format(
                        cov, total_p - len(matched_part_indices)
                    ),
                    "evidence": " | ".join(missing_snippets[:2]),
                    "exempted": False,
                }
            )

    unclaimed = [
        merged_paras[i][:80]
        for i in range(len(merged_paras))
        if i not in claimed and len(merged_paras[i]) > 2
    ]
    if unclaimed:
        findings.append(
            {
                "rule_id": "COMPARE_SYNC_DRIFT",
                "severity": "FAIL",
                "location": str(merged_path.name),
                "message": "合稿中存在 {0} 个未被任何分章认领的孤立段落".format(len(unclaimed)),
                "evidence": " | ".join(unclaimed[:2]),
                "exempted": False,
            }
        )

    summary = {
        "merged": str(merged_path),
        "merged_paras": len(merged_paras),
        "unclaimed_in_merged_count": len(unclaimed),
        "unclaimed_snippets": unclaimed[:5],
        "parts": part_reports,
    }
    return findings, summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="扫描 Markdown/TXT/DOCX 中的泄漏符号、内部指令并核对合稿分章同步"
    )
    parser.add_argument("--inputs", nargs="+", help="待扫描的文件或目录列表 (.md/.txt/.docx)")
    parser.add_argument("--rules", help="可选外部 JSON 规则与白名单覆盖文件")
    parser.add_argument(
        "--compare",
        nargs="+",
        metavar="PATH",
        help="合稿与分章对齐比对：<merged> <part1> [<part2> ...]",
    )
    parser.add_argument(
        "--mode",
        choices=("prose", "cs"),
        default="prose",
        help="文本模式（cs 模式放宽 Markdown 反引号内变量告警）",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text", help="输出格式")
    parser.add_argument("--strict", action="store_true", help="将 WARN 视为退出码 1")

    args = parser.parse_args(argv)
    if not args.inputs and not args.compare:
        parser.error("至少需要提供 --inputs 或 --compare 参数之一")
    if args.compare and len(args.compare) < 2:
        parser.error("--compare 至少需要 2 个路径：<merged> <part1> ...")

    try:
        rules_path = Path(args.rules) if args.rules else None
        rules, whitelist, neg_cfg = _load_rules(rules_path)
    except (ValueError, OSError) as exc:
        sys.stderr.write("规则加载错误: {0}\n".format(exc))
        return 2

    all_findings: List[Dict[str, Any]] = []
    scanned_files: List[str] = []
    compare_summary: Optional[Dict[str, Any]] = None

    try:
        if args.inputs:
            files = _collect_input_files(args.inputs)
            if not files:
                sys.stderr.write("未找到可扫描的 .md/.txt/.docx 文件\n")
                return 2
            for fpath in files:
                scanned_files.append(str(fpath))
                if fpath.suffix.lower() == ".docx":
                    blocks, meta = _extract_docx_blocks(fpath)
                    for c in meta["comments"]:
                        all_findings.append(
                            {
                                "rule_id": "DOCX_COMMENTS_PRESENT",
                                "severity": "FAIL",
                                "location": "{0}:comments:{1}".format(fpath.name, c["id"]),
                                "message": "DOCX 中残留未清理批注 (作者: {0})".format(c["author"]),
                                "evidence": c["text"],
                                "exempted": False,
                            }
                        )
                    if meta["ins_count"] > 0 or meta["del_count"] > 0:
                        all_findings.append(
                            {
                                "rule_id": "DOCX_TRACKED_CHANGES",
                                "severity": "FAIL",
                                "location": "{0}:revisions".format(fpath.name),
                                "message": "DOCX 中存在未接受/未拒绝的修订痕迹 (ins={0}, del={1})".format(
                                    meta["ins_count"], meta["del_count"]
                                ),
                                "evidence": "w:ins/w:del",
                                "exempted": False,
                            }
                        )
                    all_findings.extend(_scan_blocks(blocks, rules, whitelist, neg_cfg, args.mode))
                else:
                    blocks, struct_f = _extract_md_blocks(fpath)
                    all_findings.extend(struct_f)
                    all_findings.extend(_scan_blocks(blocks, rules, whitelist, neg_cfg, args.mode))

        if args.compare:
            merged_p = Path(args.compare[0])
            part_ps = [Path(x) for x in args.compare[1:]]
            for p in [merged_p] + part_ps:
                if not p.exists():
                    raise FileNotFoundError("比对文件不存在: {0}".format(p))
            cmp_findings, compare_summary = _run_compare(merged_p, part_ps)
            all_findings.extend(cmp_findings)
    except (FileNotFoundError, ValueError, OSError) as exc:
        sys.stderr.write("输入处理错误: {0}\n".format(exc))
        return 2

    fail_cnt = sum(1 for f in all_findings if f["severity"] == "FAIL")
    warn_cnt = sum(1 for f in all_findings if f["severity"] == "WARN")
    exempted_cnt = sum(1 for f in all_findings if f["exempted"])
    status = "FAIL" if fail_cnt > 0 else ("WARN" if warn_cnt > 0 else "PASS")

    payload: Dict[str, Any] = {
        "tool": "doc_leak_scanner",
        "version": VERSION,
        "status": status,
        "summary": {
            "scanned_files": scanned_files,
            "fail_count": fail_cnt,
            "warn_count": warn_cnt,
            "exempted_count": exempted_cnt,
            "total_findings": len(all_findings),
            "compare": compare_summary,
        },
        "findings": all_findings,
    }

    if args.format == "json":
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    else:
        sys.stdout.write(
            "[doc_leak_scanner v{0}] status={1} fail={2} warn={3} exempted={4}\n".format(
                VERSION, status, fail_cnt, warn_cnt, exempted_cnt
            )
        )
        for item in all_findings:
            sys.stdout.write(
                "- [{0}] {1} @ {2}: {3} | {4}\n".format(
                    item["severity"],
                    item["rule_id"],
                    item["location"],
                    item["message"],
                    item["evidence"],
                )
            )
        if compare_summary:
            sys.stdout.write(
                "Compare: merged_paras={0}, unclaimed={1}\n".format(
                    compare_summary["merged_paras"],
                    compare_summary["unclaimed_in_merged_count"],
                )
            )

    if fail_cnt > 0 or (args.strict and warn_cnt > 0):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
