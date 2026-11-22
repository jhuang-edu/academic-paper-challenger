#!/usr/bin/env python3
"""Universal prose rhythm, broken fragment, and AI-trope auditor (Python 3.8+ stdlib)."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple
import xml.etree.ElementTree as ET
import zipfile

VERSION = "1.0.0"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
SUPPORTED_EXTS = {".md", ".txt", ".docx"}

DEFAULT_CONNECTORS_ZH = (
    r"此外|另外|同时|值得注意的是|需要指出的是|在此基础上|综上所述|总而言之|由此可见|基于此|进一步地|显而易见"
)
DEFAULT_CONNECTORS_EN = (
    r"Furthermore|Moreover|Additionally|Notably|Importantly|In summary|Consequently|Therefore|In addition"
)
DEFAULT_BUZZWORDS = (
    r"赋能|抓手|闭环|生态|具有重要意义|提供有力支撑|提供理论依据和实践指导|开创了.{0,4}先河|打下坚实基础|注入新动能|高质量发展"
)

STANDALONE_CONN_RE = re.compile(
    r"^(?:然而|但是|不过|因此|所以|此外|同时|另外|其次|最后|总之|综上所述|事实上|实际上|换言之|不仅如此|"
    r"第一|第二|第三|首先|一是|二是|三是|其一|其二)[。！？.,!?]?$"
)
PREP_PHRASE_RE = re.compile(
    r"^(?:在[^。]{1,18}[上中下内]|针对[^。]{1,18}|按[^。]{1,16}折算|基于[^。]{1,16}|从[^。]{1,16}来看)[。！？]$"
)
DANGLING_VERB_RE = re.compile(
    r"^.{2,28}?(?:强调|指出|表明|认为|显示|发现|提出|证实|总结|一致指出|研究表明)[。！]$"
)
DANGLING_WHITELIST_RE = re.compile(r"(?:得到证实|予以证实|加以证实|已证实)")


@dataclass
class ProsePara:
    location: str
    heading: str
    heading_level: int
    text: str


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


def _extract_docx_prose(path: Path) -> List[Tuple[str, int, str, str]]:
    """Return list of (location, heading_level, text, kind: 'heading'|'para')."""
    items: List[Tuple[str, int, str, str]] = []
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

        p_idx = 0
        for child in list(body):
            lname = _local_name(child.tag)
            if lname != "p":
                continue
            p_idx += 1
            style_val = ""
            p_pr = child.find("{{{0}}}pPr".format(W_NS))
            if p_pr is not None:
                ps = p_pr.find("{{{0}}}pStyle".format(W_NS))
                if ps is not None:
                    style_val = _w_attr(ps, "val") or ""
            if re.search(r"(?i)(code|verbatim|source|listing)", style_val):
                continue

            parts: List[str] = []
            for t_node in child.iter():
                tl = _local_name(t_node.tag)
                if tl == "del" or tl == "delText":
                    continue
                if tl == "t" and t_node.text:
                    # Skip if ancestor is del
                    parts.append(t_node.text)
            txt = re.sub(r"\s+", " ", "".join(parts)).strip()
            if not txt:
                continue
            m_h = re.match(r"(?i)^(?:heading\s*|标题\s*)?([1-6])$", style_val)
            if m_h:
                items.append(("{0}:p{1}".format(path.name, p_idx), int(m_h.group(1)), txt, "heading"))
            else:
                items.append(("{0}:p{1}".format(path.name, p_idx), 0, txt, "para"))
    return items


def _extract_md_prose(path: Path) -> List[Tuple[str, int, str, str]]:
    content = _read_text_with_fallback(path)
    lines = content.splitlines()
    n = len(lines)
    idx = 0
    if n >= 3 and lines[0].strip() == "---":
        for j in range(1, n):
            if lines[j].strip() in ("---", "..."):
                idx = j + 1
                break

    # Pre-strip HTML comments while preserving approximate line tracking
    raw_body = "\n".join(lines[idx:])
    raw_body = re.sub(r"<!--[\s\S]*?-->", "", raw_body)
    body_lines = raw_body.splitlines()

    items: List[Tuple[str, int, str, str]] = []
    in_code = False
    fence_char = ""
    fence_len = 0
    sep_re = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$")

    i = 0
    para_buf: List[str] = []
    para_start_line = 1

    def flush_para() -> None:
        if not para_buf:
            return
        joined = " ".join(para_buf)
        # Strip images, unwrap links, strip bare URLs, strip inline bold/code markers
        joined = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", joined)
        joined = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", joined)
        joined = re.sub(r"https?://\S+", "", joined)
        joined = joined.replace("**", "").replace("__", "").replace("`", "")
        joined = re.sub(r"\s+", " ", joined).strip()
        if joined:
            items.append(("{0}:{1}".format(path.name, para_start_line), 0, joined, "para"))
        para_buf.clear()

    while i < len(body_lines):
        line = body_lines[i]
        line_no = idx + i + 1
        m_fence = re.match(r"^[ ]{0,3}(`{3,}|~{3,})(.*)$", line)
        if not in_code and m_fence:
            flush_para()
            in_code = True
            fence_char = m_fence.group(1)[0]
            fence_len = len(m_fence.group(1))
            i += 1
            continue
        if in_code:
            if m_fence and m_fence.group(1)[0] == fence_char and len(m_fence.group(1)) >= fence_len and not m_fence.group(2).strip():
                in_code = False
            i += 1
            continue

        # Skip Markdown table blocks
        if "|" in line and i + 1 < len(body_lines) and sep_re.match(body_lines[i + 1]):
            flush_para()
            i += 2
            while i < len(body_lines) and "|" in body_lines[i]:
                i += 1
            continue

        m_head = re.match(r"^(#{1,6})\s+(.+?)\s*#*$", line)
        if m_head:
            flush_para()
            h_lvl = len(m_head.group(1))
            h_txt = re.sub(r"\s+", " ", m_head.group(2)).strip()
            items.append(("{0}:{1}".format(path.name, line_no), h_lvl, h_txt, "heading"))
            i += 1
            continue

        stripped = line.strip()
        if not stripped or re.match(r"^[-*_]{3,}$", stripped):
            flush_para()
            i += 1
            continue

        # Strip blockquote prefix
        stripped = re.sub(r"^>\s*", "", stripped)
        if not para_buf:
            para_start_line = line_no
        para_buf.append(stripped)
        i += 1

    flush_para()
    return items


def _effective_word_count(text: str) -> Tuple[int, int, int]:
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    no_cjk = re.sub(r"[\u4e00-\u9fff]", " ", text)
    latin = len(re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*", no_cjk))
    return cjk, latin, cjk + latin


def _split_sentences(para_text: str) -> List[str]:
    """Reversible shielding + mixed ZH/EN sentence splitter without variable-width lookbehind."""
    # Remove leading list markers
    cleaned = re.sub(r"^\s*(?:[-*+]\s+|\d+\.\s+|（\d+）\s*)", "", para_text).strip()
    if not cleaned:
        return []

    shields: List[str] = []

    def _shield(m: Any) -> str:
        token = "\x00S{0}\x00".format(len(shields))
        shields.append(m.group(0))
        return token

    # 1. Paired brackets / corner quotes (single-line <= 180 chars)
    work = re.sub(r"（[^（）\n]{1,180}）", _shield, cleaned)
    work = re.sub(r"\([^()\n]{1,180}\)", _shield, work)
    work = re.sub(r"「[^「」\n]{1,180}」", _shield, work)

    # 2. Ellipses / dot leaders (e.g. ..., ......) and decimals/versions (e.g. 1.5, v1.2)
    work = re.sub(r"\.{2,}", _shield, work)
    work = re.sub(r"(?<![A-Za-z0-9])\d+(?:\.\d+)+(?![A-Za-z0-9])", _shield, work)

    # 3. Multi-dot abbreviations (e.g., i.e., U.S.A.)
    work = re.sub(r"(?i)\b(?:[a-z]\.){2,}", _shield, work)

    # 4. Academic abbreviations
    work = re.sub(
        r"(?i)\b(?:et\s+al|vs|etc|figs?|tabs?|eqs?|sec|ch|vol|no|pp|dr|prof|mr|ms|mrs|inc|ltd|co|corp|approx|cf)\.",
        _shield,
        work,
    )

    # Inject split boundary markers using lambda (avoids Python 3.12 bad \x escape in re.sub template)
    work = re.sub(r"([。！？][”’\"'\)\）\]】]?)", lambda m: m.group(1) + "\x01", work)
    work = re.sub(
        r"([.!?][\"'\)\]]?)(?=\s+(?=[A-Z0-9\u4e00-\u9fff“\"\(（\x00])|$)",
        lambda m: m.group(1) + "\x01",
        work,
    )

    raw_sents = work.split("\x01")
    out: List[str] = []
    token_re = re.compile(r"\x00S(\d+)\x00")
    for rs in raw_sents:
        restored = token_re.sub(lambda m: shields[int(m.group(1))], rs).strip()
        if not restored:
            continue
        # Filter pure punctuation
        if re.match(r"^[。！？.,!?;；:：\"'“”‘’（）()\[\]【】\s]+$", restored):
            continue
        out.append(restored)
    return out


def _sentence_length(sent: str, lang: str) -> int:
    if lang == "zh":
        return len(re.sub(r"\s+", "", sent))
    return len(re.findall(r"\S+", sent))


def _load_buzzwords(path: Optional[Path]) -> Tuple[str, str]:
    conn_pat = "(?:{0}|{1})".format(DEFAULT_CONNECTORS_ZH, DEFAULT_CONNECTORS_EN)
    buzz_pat = DEFAULT_BUZZWORDS
    if path is None:
        return conn_pat, buzz_pat
    try:
        cfg = json.loads(_read_text_with_fallback(path))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("无法解析 buzzwords 配置 {0}: {1}".format(path, exc))

    mode = str(cfg.get("mode", "extend")).lower()
    extra_buzz = [re.escape(str(x)) for x in cfg.get("buzzwords", []) if str(x).strip()]
    extra_conn = [re.escape(str(x)) for x in cfg.get("connectors", []) if str(x).strip()]

    if mode == "replace":
        if extra_buzz:
            buzz_pat = "(?:{0})".format("|".join(extra_buzz))
        if extra_conn:
            conn_pat = "(?:{0})".format("|".join(extra_conn))
    else:
        if extra_buzz:
            buzz_pat = "(?:{0}|{1})".format(buzz_pat, "|".join(extra_buzz))
        if extra_conn:
            conn_pat = "(?:{0}|{1})".format(conn_pat, "|".join(extra_conn))
    return conn_pat, buzz_pat


def _collect_files(paths: Sequence[str]) -> List[Path]:
    files: List[Path] = []
    for rp in paths:
        p = Path(rp)
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


def main(argv: Optional[Sequence[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="核查中英文混排论文的句长 CV 节奏、机械断句残句、AI 连接词密度与有效字数分布"
    )
    parser.add_argument("--inputs", nargs="+", required=True, help="待审计文件或目录 (.md/.txt/.docx)")
    parser.add_argument("--lang", choices=("auto", "zh", "en"), default="auto", help="语言判定模式")
    parser.add_argument("--min-cv", type=float, default=0.35, help="句长变异系数 CV 下限（默认 0.35）")
    parser.add_argument("--max-sent", type=int, default=160, help="单句最大长度上限（默认 160）")
    parser.add_argument("--exclude-headings", default="", help="逗号分隔的跳过章节标题关键词")
    parser.add_argument("--buzzwords", help="可选扩展或替换空洞套话/连接词 JSON 文件")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="输出格式")
    parser.add_argument("--strict", action="store_true", help="将 WARN 视为退出码 1")

    args = parser.parse_args(argv)
    exclude_kws = [k.strip().lower() for k in args.exclude_headings.split(",") if k.strip()]

    try:
        conn_pat, buzz_pat = _load_buzzwords(Path(args.buzzwords) if args.buzzwords else None)
        files = _collect_files(args.inputs)
        if not files:
            raise ValueError("未找到任何 .md/.txt/.docx 输入文件")
    except (FileNotFoundError, ValueError, OSError) as exc:
        sys.stderr.write("初始化失败: {0}\n".format(exc))
        return 2

    conn_re = re.compile(conn_pat, flags=re.IGNORECASE)
    buzz_re = re.compile(buzz_pat, flags=re.IGNORECASE)

    paras: List[ProsePara] = []
    try:
        for fpath in files:
            items = _extract_docx_prose(fpath) if fpath.suffix.lower() == ".docx" else _extract_md_prose(fpath)
            cur_heading = "(root)"
            cur_top_heading = "(root)"
            excluded_level: Optional[int] = None

            for loc, lvl, txt, kind in items:
                if kind == "heading":
                    if excluded_level is not None and lvl <= excluded_level:
                        excluded_level = None
                    if any(kw in txt.lower() for kw in exclude_kws):
                        excluded_level = lvl
                    cur_heading = txt
                    if lvl == 1 or cur_top_heading == "(root)":
                        cur_top_heading = txt
                    continue
                if excluded_level is not None:
                    continue
                paras.append(
                    ProsePara(
                        location=loc,
                        heading=cur_top_heading if cur_top_heading != "(root)" else cur_heading,
                        heading_level=lvl,
                        text=txt,
                    )
                )
    except (ValueError, OSError) as exc:
        sys.stderr.write("文档解析错误: {0}\n".format(exc))
        return 2

    all_text = "\n".join(p.text for p in paras)
    cjk_total, latin_total, eff_total = _effective_word_count(all_text)
    if args.lang == "auto":
        total_nonspace = max(1, len(re.sub(r"\s+", "", all_text)))
        detected_lang = "zh" if (cjk_total / float(total_nonspace)) >= 0.20 else "en"
    else:
        detected_lang = args.lang

    chapter_counts: Dict[str, int] = {}
    sent_lengths: List[int] = []
    all_sentences: List[Tuple[str, str]] = []
    findings: List[Dict[str, Any]] = []

    for p in paras:
        _, _, p_eff = _effective_word_count(p.text)
        chapter_counts[p.heading] = chapter_counts.get(p.heading, 0) + p_eff

        sents = _split_sentences(p.text)
        for s in sents:
            all_sentences.append((p.location, s))
            slen = _sentence_length(s, detected_lang)
            sent_lengths.append(slen)

            if slen > args.max_sent:
                findings.append(
                    {
                        "rule_id": "OVERLONG_SENTENCE",
                        "severity": "FAIL",
                        "location": p.location,
                        "message": "单句长度 {0} 超过上限 {1}".format(slen, args.max_sent),
                        "evidence": s[:90],
                        "exempted": False,
                    }
                )

            if STANDALONE_CONN_RE.match(s):
                findings.append(
                    {
                        "rule_id": "FRAGMENT_STANDALONE_CONN",
                        "severity": "FAIL",
                        "location": p.location,
                        "message": "机械断句残句：连接词/序号独立成句",
                        "evidence": s,
                        "exempted": False,
                    }
                )
            elif PREP_PHRASE_RE.match(s):
                findings.append(
                    {
                        "rule_id": "FRAGMENT_PREP_PHRASE",
                        "severity": "WARN",
                        "location": p.location,
                        "message": "疑似介词短语独立成残句",
                        "evidence": s,
                        "exempted": False,
                    }
                )
            elif DANGLING_VERB_RE.match(s) and not DANGLING_WHITELIST_RE.search(s):
                findings.append(
                    {
                        "rule_id": "FRAGMENT_DANGLING_VERB",
                        "severity": "FAIL",
                        "location": p.location,
                        "message": "疑似悬空主语+引述动词断句残句",
                        "evidence": s,
                        "exempted": False,
                    }
                )
            else:
                _, _, s_eff = _effective_word_count(s)
                if (
                    0 < s_eff <= 6
                    and not re.match(r"^(?:图|表|Figure|Fig\.|Table)\s*[A-Z]?\d", s, re.IGNORECASE)
                    and not re.match(r"^\d+$", s)
                ):
                    findings.append(
                        {
                            "rule_id": "FRAGMENT_TINY_NOISE",
                            "severity": "WARN",
                            "location": p.location,
                            "message": "超短碎句残片（有效字数 {0} <= 6）".format(s_eff),
                            "evidence": s,
                            "exempted": False,
                        }
                    )

        # Paragraph connector triple check
        p_conns = conn_re.findall(p.text)
        if len(p_conns) >= 3:
            findings.append(
                {
                    "rule_id": "PARAGRAPH_CONNECTOR_TRIPLE",
                    "severity": "WARN",
                    "location": p.location,
                    "message": "单段出现 {0} 次高频连接词（连接词堆砌/三连击）".format(len(p_conns)),
                    "evidence": ", ".join(p_conns[:4]),
                    "exempted": False,
                }
            )
        elif len(sents) >= 3:
            # Check 3 consecutive sentences starting with connectors or parallel markers
            streak = 0
            for s in sents:
                if re.match(r"^(?:此外|另外|同时|首先|其次|最后|一是通过|二是通过|三是通过|一是|二是|三是)", s) or conn_re.match(s):
                    streak += 1
                    if streak >= 3:
                        findings.append(
                            {
                                "rule_id": "PARAGRAPH_CONNECTOR_TRIPLE",
                                "severity": "WARN",
                                "location": p.location,
                                "message": "段内连续 3 句以上使用排比/连接词句首",
                                "evidence": s[:80],
                                "exempted": False,
                            }
                        )
                        break
                else:
                    streak = 0

    # Global rhythm CV
    sent_count = len(sent_lengths)
    mean_len = (sum(sent_lengths) / float(sent_count)) if sent_count > 0 else 0.0
    if sent_count >= 5 and mean_len > 0.0:
        std_len = math.sqrt(sum((x - mean_len) ** 2 for x in sent_lengths) / float(sent_count - 1))
        cv = std_len / mean_len
    else:
        std_len = 0.0
        cv = 0.0

    if sent_count >= 5 and cv < args.min_cv:
        findings.append(
            {
                "rule_id": "LOW_RHYTHM_CV",
                "severity": "FAIL",
                "location": "global",
                "message": "句长变异系数 CV={0:.3f} 低于阈值 {1:.2f}，行文节奏过于整齐单调".format(
                    cv, args.min_cv
                ),
                "evidence": "mean={0:.1f}, std={1:.1f}, sentences={2}".format(mean_len, std_len, sent_count),
                "exempted": False,
            }
        )

    # Global connector, dash, buzzword density per 1k effective words
    scale = 1000.0 / float(max(1, eff_total))
    conn_count = len(conn_re.findall(all_text))
    dash_count = len(re.findall(r"(?:——|--|—)", all_text))
    buzz_count = len(buzz_re.findall(all_text))

    conn_per_1k = conn_count * scale
    dash_per_1k = dash_count * scale
    buzz_per_1k = buzz_count * scale

    if eff_total >= 100 and conn_per_1k > 8.0:
        findings.append(
            {
                "rule_id": "HIGH_CONNECTOR_DENSITY",
                "severity": "WARN",
                "location": "global",
                "message": "高频过渡连接词密度 {0:.2f}/千字 超过 8.0/千字".format(conn_per_1k),
                "evidence": "count={0}, effective_words={1}".format(conn_count, eff_total),
                "exempted": False,
            }
        )
    if eff_total >= 100 and dash_per_1k > 4.0:
        findings.append(
            {
                "rule_id": "HIGH_DASH_DENSITY",
                "severity": "WARN",
                "location": "global",
                "message": "破折号密度 {0:.2f}/千字 超过 4.0/千字".format(dash_per_1k),
                "evidence": "count={0}, effective_words={1}".format(dash_count, eff_total),
                "exempted": False,
            }
        )
    if eff_total >= 100 and buzz_per_1k > 4.0:
        findings.append(
            {
                "rule_id": "HIGH_BUZZWORD_DENSITY",
                "severity": "WARN",
                "location": "global",
                "message": "空洞拔高套话密度 {0:.2f}/千字 超过 4.0/千字".format(buzz_per_1k),
                "evidence": "count={0}, effective_words={1}".format(buzz_count, eff_total),
                "exempted": False,
            }
        )

    chapter_shares = [
        {
            "heading": h,
            "effective_words": w,
            "share_pct": round((w / float(max(1, eff_total))) * 100.0, 2),
        }
        for h, w in chapter_counts.items()
    ]

    fail_cnt = sum(1 for f in findings if f["severity"] == "FAIL")
    warn_cnt = sum(1 for f in findings if f["severity"] == "WARN")
    status = "FAIL" if fail_cnt > 0 else ("WARN" if warn_cnt > 0 else "PASS")

    payload: Dict[str, Any] = {
        "tool": "prose_rhythm_audit",
        "version": VERSION,
        "status": status,
        "summary": {
            "files": [str(f) for f in files],
            "detected_lang": detected_lang,
            "effective_words": eff_total,
            "cjk_chars": cjk_total,
            "latin_words": latin_total,
            "sentence_count": sent_count,
            "mean_sentence_len": round(mean_len, 2),
            "std_sentence_len": round(std_len, 2),
            "cv": round(cv, 4),
            "connectors_per_1k": round(conn_per_1k, 2),
            "dashes_per_1k": round(dash_per_1k, 2),
            "buzzwords_per_1k": round(buzz_per_1k, 2),
            "chapter_shares": chapter_shares,
            "fail_count": fail_cnt,
            "warn_count": warn_cnt,
        },
        "findings": findings,
    }

    if args.format == "json":
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    else:
        sys.stdout.write(
            "[prose_rhythm_audit v{0}] status={1} lang={2} words={3} sents={4} CV={5:.3f} fail={6} warn={7}\n".format(
                VERSION, status, detected_lang, eff_total, sent_count, cv, fail_cnt, warn_cnt
            )
        )
        for item in findings:
            sys.stdout.write(
                "- [{0}] {1} @ {2}: {3} | {4}\n".format(
                    item["severity"], item["rule_id"], item["location"], item["message"], item["evidence"]
                )
            )

    if fail_cnt > 0 or (args.strict and warn_cnt > 0):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
