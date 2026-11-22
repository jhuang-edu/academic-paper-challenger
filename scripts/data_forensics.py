#!/usr/bin/env python3
"""Universal statistical forensics and ledger verifier for CSV/TSV/XLSX (Python 3.8+ stdlib)."""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
import xml.etree.ElementTree as ET
import zipfile

VERSION = "1.0.0"
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

NUM_EXTRACT_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*(?:%|％|小时|人时|分钟|分|份|个|例|篇|天|元|万元|h|min|kg|mg|次)?\s*$")


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _parse_numeric(raw_str: str) -> Optional[float]:
    s = raw_str.strip()
    if not s or s in ("-", "—", "–", "N/A", "NA", "/", "null", "None", "nan", "NaN"):
        return None
    s_no_comma = s.replace(",", "")
    m = NUM_EXTRACT_RE.match(s_no_comma)
    if not m:
        return None
    try:
        val = float(m.group(1))
    except ValueError:
        return None
    if math.isnan(val) or math.isinf(val):
        return None
    return val


def _extract_last_digit(raw_str: str) -> Optional[int]:
    s = raw_str.strip().replace(",", "")
    s = re.sub(r"\s*(?:%|％|小时|人时|分钟|分|份|个|例|篇|天|元|万元|h|min|kg|mg|次)$", "", s)
    m = re.match(r"^[+-]?(\d+)(?:\.(\d+))?$", s)
    if not m:
        return None
    frac = m.group(2)
    digits = frac if frac is not None else m.group(1)
    if not digits:
        return None
    return int(digits[-1])


def _decode_bytes(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _read_csv_or_tsv(path: Path) -> Tuple[List[str], List[List[str]]]:
    text = _decode_bytes(path.read_bytes())
    if not text.strip():
        raise ValueError("数据文件为空: {0}".format(path))

    delimiter: Optional[str] = None
    if path.suffix.lower() == ".tsv":
        delimiter = "\t"
    else:
        head = text[:4096]
        try:
            dialect = csv.Sniffer().sniff(head, delimiters=",;\t|")
            delimiter = dialect.delimiter
        except csv.Error:
            first_line = text.splitlines()[0]
            delimiter = "\t" if first_line.count("\t") > first_line.count(",") else ","

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = [r for r in reader if any(cell.strip() for cell in r)]
    if len(rows) < 2:
        raise ValueError("数据行数不足（至少需要表头与 1 行数据）: {0}".format(path))

    headers = [h.strip() for h in rows[0]]
    width = len(headers)
    norm_rows: List[List[str]] = []
    for r in rows[1:]:
        padded = [c.strip() for c in r[:width]]
        if len(padded) < width:
            padded.extend([""] * (width - len(padded)))
        norm_rows.append(padded)
    return headers, norm_rows


def _col_ref_to_idx(ref: str) -> int:
    letters = "".join(ch for ch in ref if ch.isalpha()).upper()
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return max(0, idx - 1)


def _read_xlsx(path: Path, sheet_name: Optional[str]) -> Tuple[List[str], List[List[str]], Dict[str, int]]:
    stats = {"formula_cell_count": 0, "uncached_formula_count": 0, "formula_error_count": 0}
    try:
        zf = zipfile.ZipFile(str(path), "r")
    except (zipfile.BadZipFile, OSError) as exc:
        raise ValueError("无法打开 XLSX 文件 {0}: {1}".format(path, exc))

    with zf:
        names = set(zf.namelist())
        if "xl/workbook.xml" not in names or "xl/_rels/workbook.xml.rels" not in names:
            raise ValueError("无效 XLSX 结构（缺少 workbook.xml 或 rels）: {0}".format(path))

        shared_strings: List[str] = []
        if "xl/sharedStrings.xml" in names:
            ss_root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in ss_root.findall("{{{0}}}si".format(MAIN_NS)):
                t_parts = [t.text or "" for t in si.findall(".//{{{0}}}t".format(MAIN_NS))]
                shared_strings.append("".join(t_parts))

        rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        rid_to_target: Dict[str, str] = {}
        for rel in rels_root:
            if _local_name(rel.tag) == "Relationship":
                rid = rel.attrib.get("Id", "")
                target = rel.attrib.get("Target", "").lstrip("/")
                if not target.startswith("xl/"):
                    target = "xl/" + target
                rid_to_target[rid] = target

        wb_root = ET.fromstring(zf.read("xl/workbook.xml"))
        sheets = wb_root.findall(".//{{{0}}}sheet".format(MAIN_NS))
        if not sheets:
            raise ValueError("XLSX 中不存在工作表: {0}".format(path))

        chosen_target: Optional[str] = None
        for sh in sheets:
            name = sh.attrib.get("name", "")
            rid = sh.attrib.get("{{{0}}}id".format(REL_NS)) or sh.attrib.get("id", "")
            if sheet_name is None or name == sheet_name:
                chosen_target = rid_to_target.get(rid)
                break
        if chosen_target is None or chosen_target not in names:
            raise ValueError("未找到指定工作表 '{0}': {1}".format(sheet_name or "(first)", path))

        sh_root = ET.fromstring(zf.read(chosen_target))
        parsed_rows: List[Dict[int, str]] = []
        max_col = 0
        for row_elem in sh_root.findall(".//{{{0}}}row".format(MAIN_NS)):
            row_map: Dict[int, str] = {}
            seq_col = 0
            for c_elem in row_elem.findall("{{{0}}}c".format(MAIN_NS)):
                ref = c_elem.attrib.get("r", "")
                c_idx = _col_ref_to_idx(ref) if ref else seq_col
                seq_col = c_idx + 1
                max_col = max(max_col, c_idx)

                c_type = c_elem.attrib.get("t", "")
                f_elem = c_elem.find("{{{0}}}f".format(MAIN_NS))
                v_elem = c_elem.find("{{{0}}}v".format(MAIN_NS))
                is_elem = c_elem.find("{{{0}}}is".format(MAIN_NS))

                if f_elem is not None:
                    stats["formula_cell_count"] += 1
                    if v_elem is None or v_elem.text is None:
                        stats["uncached_formula_count"] += 1
                        row_map[c_idx] = ""
                        continue

                val_str = ""
                if c_type == "s" and v_elem is not None and v_elem.text is not None:
                    try:
                        val_str = shared_strings[int(v_elem.text)]
                    except (ValueError, IndexError):
                        val_str = v_elem.text
                elif c_type == "inlineStr" and is_elem is not None:
                    val_str = "".join(t.text or "" for t in is_elem.findall(".//{{{0}}}t".format(MAIN_NS)))
                elif c_type == "b" and v_elem is not None and v_elem.text is not None:
                    val_str = "TRUE" if v_elem.text.strip() == "1" else "FALSE"
                elif c_type == "e":
                    stats["formula_error_count"] += 1
                    val_str = ""
                elif v_elem is not None and v_elem.text is not None:
                    val_str = v_elem.text.strip()

                row_map[c_idx] = val_str.strip()

            if any(v for v in row_map.values()):
                parsed_rows.append(row_map)

    if len(parsed_rows) < 2:
        raise ValueError("工作表数据行数不足（至少需要表头与 1 行数据）: {0}".format(path))

    width = max_col + 1
    dense_rows: List[List[str]] = []
    for rm in parsed_rows:
        dense_rows.append([rm.get(c, "") for c in range(width)])

    headers = dense_rows[0]
    return headers, dense_rows[1:], stats


def _percentile_inc(sorted_vals: Sequence[float], p: float) -> float:
    n = len(sorted_vals)
    if n == 1:
        return sorted_vals[0]
    k = p * (n - 1)
    lo = int(math.floor(k))
    hi = int(math.ceil(k))
    return sorted_vals[lo] + (k - lo) * (sorted_vals[hi] - sorted_vals[lo])


def _percentile_exc(sorted_vals: Sequence[float], p: float) -> Optional[float]:
    n = len(sorted_vals)
    if n < 3 or p <= 1.0 / (n + 1.0) or p >= float(n) / (n + 1.0):
        return None
    pos = p * (n + 1.0) - 1.0
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    return sorted_vals[lo] + (pos - lo) * (sorted_vals[hi] - sorted_vals[lo])


def _mean_std_median(vals: Sequence[float]) -> Dict[str, Any]:
    n = len(vals)
    s = sorted(vals)
    mean_v = sum(s) / float(n)
    std_v = math.sqrt(sum((x - mean_v) ** 2 for x in s) / float(n - 1)) if n > 1 else 0.0
    med = s[n // 2] if n % 2 == 1 else (s[n // 2 - 1] + s[n // 2]) / 2.0
    q1_inc = _percentile_inc(s, 0.25)
    q3_inc = _percentile_inc(s, 0.75)
    iqr_inc = q3_inc - q1_inc
    q1_exc = _percentile_exc(s, 0.25)
    q3_exc = _percentile_exc(s, 0.75)
    iqr_exc = (q3_exc - q1_exc) if (q1_exc is not None and q3_exc is not None) else None
    iqr_diff = abs(iqr_inc - iqr_exc) if iqr_exc is not None else None
    return {
        "n": n,
        "mean": round(mean_v, 6),
        "std": round(std_v, 6),
        "median": round(med, 6),
        "min": round(s[0], 6),
        "max": round(s[-1], 6),
        "q1_inc": round(q1_inc, 6),
        "q3_inc": round(q3_inc, 6),
        "iqr_inc": round(iqr_inc, 6),
        "q1_exc": round(q1_exc, 6) if q1_exc is not None else None,
        "q3_exc": round(q3_exc, 6) if q3_exc is not None else None,
        "iqr_exc": round(iqr_exc, 6) if iqr_exc is not None else None,
        "iqr_diff": round(iqr_diff, 6) if iqr_diff is not None else None,
    }


def _pearson_r(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    n = len(xs)
    if n < 3 or n != len(ys):
        return None
    mx = sum(xs) / float(n)
    my = sum(ys) / float(n)
    dx = sum((x - mx) ** 2 for x in xs)
    dy = sum((y - my) ** 2 for y in ys)
    if dx <= 0.0 or dy <= 0.0:
        return None
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    r = cov / math.sqrt(dx * dy)
    return max(-1.0, min(1.0, r))


def _average_ranks(vals: Sequence[float]) -> List[float]:
    indexed = sorted((v, i) for i, v in enumerate(vals))
    ranks = [0.0] * len(vals)
    i = 0
    n = len(indexed)
    while i < n:
        j = i
        while j + 1 < n and indexed[j + 1][0] == indexed[i][0]:
            j += 1
        avg_rank = ((i + 1) + (j + 1)) / 2.0
        for k in range(i, j + 1):
            ranks[indexed[k][1]] = avg_rank
        i = j + 1
    return ranks


def _spearman_rho(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    return _pearson_r(_average_ranks(xs), _average_ranks(ys))


def _gammaincc(a: float, x: float) -> float:
    """Regularized upper incomplete gamma Q(a, x) for chi-square survival function."""
    if x <= 0.0:
        return 1.0
    if a <= 0.0:
        return 0.0
    if x < a + 1.0:
        # Series representation for P(a, x), return 1 - P(a, x)
        ap = a
        term = 1.0 / a
        summ = term
        for _ in range(200):
            ap += 1.0
            term *= x / ap
            summ += term
            if abs(term) <= abs(summ) * 1e-14:
                break
        p_val = summ * math.exp(-x + a * math.log(x) - math.lgamma(a))
        return max(0.0, min(1.0, 1.0 - p_val))
    # Modified Lentz's method for Q(a, x)
    tiny = 1e-30
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b if abs(b) > tiny else 1.0 / tiny
    h = d
    for i in range(1, 201):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-14:
            break
    q_val = h * math.exp(-x + a * math.log(x) - math.lgamma(a))
    return max(0.0, min(1.0, q_val))


def _chi2_sf(chi2_stat: float, df: int) -> float:
    return _gammaincc(df / 2.0, max(0.0, chi2_stat) / 2.0)


def _wald_wolfowitz_runs(vals: Sequence[float]) -> Dict[str, Any]:
    if len(vals) < 10:
        return {"status": "SKIPPED", "reason": "sample_too_small"}
    s = sorted(vals)
    n_all = len(s)
    med = s[n_all // 2] if n_all % 2 == 1 else (s[n_all // 2 - 1] + s[n_all // 2]) / 2.0
    signs = ["+" if v > med else "-" for v in vals if v != med]
    n1 = sum(1 for c in signs if c == "+")
    n2 = sum(1 for c in signs if c == "-")
    n = n1 + n2
    if n < 10 or n1 == 0 or n2 == 0:
        return {"status": "SKIPPED", "reason": "all_identical_or_equal_median"}
    runs = 1 + sum(1 for i in range(1, n) if signs[i] != signs[i - 1])
    mu = (2.0 * n1 * n2) / float(n) + 1.0
    denom = float(n * n * (n - 1))
    var = (2.0 * n1 * n2 * (2.0 * n1 * n2 - n)) / denom if denom > 0 else 0.0
    if var <= 0.0:
        return {"status": "SKIPPED", "reason": "zero_variance"}
    z = (runs - mu) / math.sqrt(var)
    p = math.erfc(abs(z) / math.sqrt(2.0))
    return {
        "status": "OK",
        "n_used": n,
        "n_above": n1,
        "n_below": n2,
        "runs": runs,
        "expected_runs": round(mu, 4),
        "z": round(z, 4),
        "p_value": round(p, 6),
        "pattern": "clustered" if z < 0 else "alternating",
    }


def _last_digit_test(raw_strs: Sequence[str], num_vals: Sequence[float]) -> Dict[str, Any]:
    if len(set(num_vals)) <= 1:
        return {"status": "SKIPPED", "reason": "constant_column"}
    counts = [0] * 10
    for rs in raw_strs:
        d = _extract_last_digit(rs)
        if d is not None:
            counts[d] += 1
    n = sum(counts)
    if n == 0:
        return {"status": "SKIPPED", "reason": "no_digits"}
    expected = n / 10.0
    chi2 = sum(((obs - expected) ** 2) / expected for obs in counts)
    p = _chi2_sf(chi2, 9)
    return {
        "status": "OK",
        "n": n,
        "low_sample_warning": n < 20,
        "counts": counts,
        "chi2": round(chi2, 4),
        "df": 9,
        "p_value": round(p, 6),
    }


def _benford_test(vals: Sequence[float]) -> Dict[str, Any]:
    pos = [v for v in vals if v > 0.0]
    if not pos:
        return {"status": "SKIPPED", "reason": "no_positive_values", "applicable": False}
    counts = [0] * 9
    for v in pos:
        m = re.search(r"[1-9]", "{0:.12g}".format(abs(v)))
        if m:
            counts[int(m.group(0)) - 1] += 1
    n_pos = sum(counts)
    if n_pos == 0:
        return {"status": "SKIPPED", "reason": "no_leading_digits", "applicable": False}
    ratio_span = (max(pos) / min(pos)) if min(pos) > 0 else 0.0
    applicable = n_pos >= 30 and ratio_span >= 10.0
    chi2 = 0.0
    for d in range(1, 10):
        exp_c = n_pos * math.log10(1.0 + 1.0 / d)
        chi2 += ((counts[d - 1] - exp_c) ** 2) / exp_c
    p = _chi2_sf(chi2, 8)
    return {
        "status": "OK",
        "n_pos": n_pos,
        "span_ratio": round(ratio_span, 4),
        "applicable": applicable,
        "applicability": "valid" if applicable else "narrow_range_or_small_n",
        "counts": counts,
        "chi2": round(chi2, 4),
        "df": 8,
        "p_value": round(p, 6),
    }


def _check_discrete_step(vals: Sequence[float]) -> Optional[Dict[str, Any]]:
    # Only check columns with non-integer values and >= 5 unique values
    if all(abs(v - round(v)) < 1e-9 for v in vals):
        return None
    uniq = sorted(set(round(v, 6) for v in vals))
    if len(uniq) < 5:
        return None
    diffs = [round(uniq[i + 1] - uniq[i], 6) for i in range(len(uniq) - 1) if uniq[i + 1] - uniq[i] > 1e-6]
    if not diffs:
        return None
    step_min = min(diffs)
    if step_min <= 0.0:
        return None
    aligned = sum(1 for v in vals if abs(v / step_min - round(v / step_min)) < 1e-4)
    ratio = aligned / float(len(vals))
    if ratio >= 0.95:
        return {"step_min": step_min, "aligned_ratio": round(ratio, 4)}
    return None


def _confusion_and_agreement(
    ref_vals: Sequence[str], pred_vals: Sequence[str], pos_label: Optional[str]
) -> Dict[str, Any]:
    pairs = [(r.strip(), p.strip()) for r, p in zip(ref_vals, pred_vals) if r.strip() and p.strip()]
    n = len(pairs)
    if n == 0:
        return {"status": "SKIPPED", "reason": "no_valid_pairs"}
    labels = sorted(set([r for r, _ in pairs] + [p for _, p in pairs]))
    idx_map = {lbl: i for i, lbl in enumerate(labels)}
    k = len(labels)
    matrix = [[0 for _ in range(k)] for _ in range(k)]
    for r, p in pairs:
        matrix[idx_map[r]][idx_map[p]] += 1

    diag = sum(matrix[i][i] for i in range(k))
    po = diag / float(n)
    row_sums = [sum(matrix[i]) for i in range(k)]
    col_sums = [sum(matrix[i][j] for i in range(k)) for j in range(k)]
    pe = sum(row_sums[i] * col_sums[i] for i in range(k)) / float(n * n)
    kappa = ((po - pe) / (1.0 - pe)) if pe < 1.0 else None

    result: Dict[str, Any] = {
        "status": "OK",
        "n_pairs": n,
        "labels": labels,
        "matrix": matrix,
        "agreement": round(po, 6),
        "kappa": round(kappa, 6) if kappa is not None else None,
    }

    if k == 2:
        chosen_pos = pos_label
        if chosen_pos is None or chosen_pos not in labels:
            for cand in labels:
                if cand.lower() in ("1", "true", "yes", "pass", "pos", "positive"):
                    chosen_pos = cand
                    break
            if chosen_pos is None:
                chosen_pos = labels[1]
        chosen_neg = labels[0] if labels[1] == chosen_pos else labels[1]
        ni = idx_map[chosen_neg]
        pi = idx_map[chosen_pos]
        tp = matrix[pi][pi]
        fn = matrix[pi][ni]
        fp = matrix[ni][pi]
        tn = matrix[ni][ni]

        prec = tp / float(tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / float(tp + fn) if (tp + fn) > 0 else 0.0
        spec = tn / float(tn + fp) if (tn + fp) > 0 else 0.0
        f1 = (2.0 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0

        b = fp
        c = fn
        bc = b + c
        if bc == 0:
            chi2_corr = 0.0
            p_chi2 = 1.0
            p_exact: Optional[float] = 1.0
        else:
            chi2_corr = (max(0.0, abs(b - c) - 1.0) ** 2) / float(bc)
            p_chi2 = _chi2_sf(chi2_corr, 1)
            if bc <= 1000:
                m_min = min(b, c)
                tail = sum(math.comb(bc, kk) for kk in range(m_min + 1)) * (0.5 ** bc)
                p_exact = min(1.0, 2.0 * tail)
            else:
                p_exact = None

        result["binary"] = {
            "pos_label": chosen_pos,
            "neg_label": chosen_neg,
            "TP": tp,
            "FP": fp,
            "FN": fn,
            "TN": tn,
            "precision": round(prec, 6),
            "recall": round(rec, 6),
            "specificity": round(spec, 6),
            "f1": round(f1, 6),
            "mcnemar": {
                "b_fp": b,
                "c_fn": c,
                "chi2_edwards": round(chi2_corr, 4),
                "p_chi2": round(p_chi2, 6),
                "p_exact": round(p_exact, 6) if p_exact is not None else None,
                "recommended_p": "p_exact" if (bc < 25 and p_exact is not None) else "p_chi2",
            },
        }
    return result


def main(argv: Optional[Sequence[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="对 CSV/TSV/XLSX 台账执行双口径分位数、共线性、游程、末位数字、Benford 与混淆矩阵法医校验"
    )
    parser.add_argument("--input", required=True, help="数据文件路径 (.csv / .tsv / .xlsx)")
    parser.add_argument("--sheet", help="XLSX 工作表名称（默认第 1 个）")
    parser.add_argument("--id-col", help="样本 ID 列名（排除出数值统计与重复特征检测）")
    parser.add_argument("--group-col", help="分组列名（输出各组均值/中位数/IQR）")
    parser.add_argument("--num-cols", help="逗号分隔的数值列名（默认自动探测可解析率>=0.8）")
    parser.add_argument("--ref-col", help="人工/真值基准标签列")
    parser.add_argument("--pred-col", help="系统/预测对照标签列")
    parser.add_argument("--pos-label", help="二分类正类标签值")
    parser.add_argument("--corr-threshold", type=float, default=0.90, help="共线性告警阈值（默认 0.90）")
    parser.add_argument("--alpha", type=float, default=0.05, help="统计检验显著性阈值（默认 0.05）")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="输出格式")
    parser.add_argument("--strict", action="store_true", help="将 WARN 视为退出码 1")

    args = parser.parse_args(argv)
    if bool(args.ref_col) ^ bool(args.pred_col):
        parser.error("--ref-col 与 --pred-col 必须成对提供")

    in_path = Path(args.input)
    if not in_path.exists():
        sys.stderr.write("输入文件不存在: {0}\n".format(in_path))
        return 2

    findings: List[Dict[str, Any]] = []
    xlsx_meta: Optional[Dict[str, int]] = None

    try:
        ext = in_path.suffix.lower()
        if ext == ".xlsx":
            headers, rows, xlsx_meta = _read_xlsx(in_path, args.sheet)
            if xlsx_meta["uncached_formula_count"] > 0:
                findings.append(
                    {
                        "rule_id": "XLSX_UNCACHED_FORMULAS",
                        "severity": "WARN",
                        "location": in_path.name,
                        "message": "XLSX 存在 {0} 个未缓存求值结果的公式单元格".format(
                            xlsx_meta["uncached_formula_count"]
                        ),
                        "evidence": "formula_cell_count={0}".format(xlsx_meta["formula_cell_count"]),
                        "exempted": False,
                    }
                )
            if xlsx_meta["formula_error_count"] > 0:
                findings.append(
                    {
                        "rule_id": "XLSX_FORMULA_ERRORS",
                        "severity": "FAIL",
                        "location": in_path.name,
                        "message": "XLSX 中存在 {0} 个公式错误单元格".format(
                            xlsx_meta["formula_error_count"]
                        ),
                        "evidence": "t='e'",
                        "exempted": False,
                    }
                )
        elif ext in (".csv", ".tsv", ".txt"):
            headers, rows = _read_csv_or_tsv(in_path)
        else:
            raise ValueError("不支持的数据文件扩展名: {0}".format(ext))
    except (ValueError, OSError) as exc:
        sys.stderr.write("读取数据失败: {0}\n".format(exc))
        return 2

    col_idx: Dict[str, int] = {h: i for i, h in enumerate(headers)}
    for arg_name, arg_val in (
        ("--id-col", args.id_col),
        ("--group-col", args.group_col),
        ("--ref-col", args.ref_col),
        ("--pred-col", args.pred_col),
    ):
        if arg_val and arg_val not in col_idx:
            sys.stderr.write("参数 {0} 指定的列 '{1}' 不存在（可用列: {2}）\n".format(arg_name, arg_val, headers))
            return 2

    excluded_cols: Set[str] = set()
    for c in (args.id_col, args.group_col, args.ref_col, args.pred_col):
        if c:
            excluded_cols.add(c)

    if args.num_cols:
        num_cols = [c.strip() for c in args.num_cols.split(",") if c.strip()]
        for c in num_cols:
            if c not in col_idx:
                sys.stderr.write("--num-cols 指定的列 '{0}' 不存在\n".format(c))
                return 2
    else:
        num_cols = []
        for h in headers:
            if h in excluded_cols:
                continue
            ci = col_idx[h]
            non_empty = [r[ci] for r in rows if r[ci].strip()]
            if len(non_empty) < 3:
                continue
            parsed_cnt = sum(1 for v in non_empty if _parse_numeric(v) is not None)
            if parsed_cnt / float(len(non_empty)) >= 0.8:
                num_cols.append(h)

    # Duplicate row & feature row detection
    seen_full: Dict[Tuple[str, ...], int] = {}
    id_pos = col_idx[args.id_col] if args.id_col else None
    seen_feat: Dict[Tuple[str, ...], int] = {}

    for r_i, row in enumerate(rows, start=2):
        full_key = tuple(row)
        if full_key in seen_full:
            findings.append(
                {
                    "rule_id": "EXACT_DUPLICATE_ROW",
                    "severity": "WARN",
                    "location": "{0}:row{1}".format(in_path.name, r_i),
                    "message": "发现与第 {0} 行完全相同的重复记录".format(seen_full[full_key]),
                    "evidence": ", ".join(row[:4]),
                    "exempted": False,
                }
            )
        else:
            seen_full[full_key] = r_i

        if id_pos is not None:
            feat_key = tuple(row[j] for j in range(len(row)) if j != id_pos)
            if feat_key in seen_feat and full_key not in seen_full:
                pass
            if feat_key in seen_feat:
                if full_key != tuple(rows[seen_feat[feat_key] - 2]):
                    findings.append(
                        {
                            "rule_id": "DUPLICATE_FEATURE_ROW",
                            "severity": "WARN",
                            "location": "{0}:row{1}".format(in_path.name, r_i),
                            "message": "除 ID 列外，特征值与第 {0} 行完全重复".format(seen_feat[feat_key]),
                            "evidence": "ID={0}".format(row[id_pos]),
                            "exempted": False,
                        }
                    )
            else:
                seen_feat[feat_key] = r_i

    # Per-column statistics & forensics
    col_stats: Dict[str, Any] = {}
    col_paired_vals: Dict[str, List[Optional[float]]] = {}

    for col_name in num_cols:
        ci = col_idx[col_name]
        raw_list: List[str] = []
        val_list: List[float] = []
        row_nums: List[int] = []
        aligned: List[Optional[float]] = []

        for r_i, row in enumerate(rows, start=2):
            raw_v = row[ci]
            parsed = _parse_numeric(raw_v)
            aligned.append(parsed)
            if parsed is not None:
                raw_list.append(raw_v)
                val_list.append(parsed)
                row_nums.append(r_i)

        col_paired_vals[col_name] = aligned
        if not val_list:
            continue

        desc = _mean_std_median(val_list)
        runs_res = _wald_wolfowitz_runs(val_list)
        last_d_res = _last_digit_test(raw_list, val_list)
        benford_res = _benford_test(val_list)
        step_res = _check_discrete_step(val_list)

        # Group breakdown if requested
        group_breakdown: Dict[str, Any] = {}
        if args.group_col:
            gi = col_idx[args.group_col]
            grp_vals: Dict[str, List[float]] = {}
            for r_i, row in enumerate(rows):
                pv = aligned[r_i]
                if pv is not None:
                    gkey = row[gi] or "(empty)"
                    grp_vals.setdefault(gkey, []).append(pv)
            for gk, gvs in sorted(grp_vals.items()):
                group_breakdown[gk] = _mean_std_median(gvs)

        # 3-IQR extreme outliers & zero IQR
        outliers_3iqr: List[Dict[str, Any]] = []
        if desc["iqr_inc"] == 0.0 and desc["n"] >= 6:
            findings.append(
                {
                    "rule_id": "ZERO_IQR_LOW_DISPERSION",
                    "severity": "WARN",
                    "location": "{0}:{1}".format(in_path.name, col_name),
                    "message": "列 '{0}' 的四分位距 IQR 为 0（高度集中/低离散度）".format(col_name),
                    "evidence": "median={0}".format(desc["median"]),
                    "exempted": False,
                }
            )
        elif desc["iqr_inc"] > 0.0:
            lo_fence = desc["q1_inc"] - 3.0 * desc["iqr_inc"]
            hi_fence = desc["q3_inc"] + 3.0 * desc["iqr_inc"]
            for rn, v in zip(row_nums, val_list):
                if v < lo_fence or v > hi_fence:
                    outliers_3iqr.append({"row": rn, "value": v})
            if outliers_3iqr:
                findings.append(
                    {
                        "rule_id": "EXTREME_3IQR_OUTLIER",
                        "severity": "WARN",
                        "location": "{0}:{1}".format(in_path.name, col_name),
                        "message": "列 '{0}' 检出 {1} 个超出 3-IQR 围栏的极端离群值".format(
                            col_name, len(outliers_3iqr)
                        ),
                        "evidence": str(outliers_3iqr[:4]),
                        "exempted": False,
                    }
                )

        if runs_res.get("status") == "OK" and runs_res["p_value"] < args.alpha:
            findings.append(
                {
                    "rule_id": "RUNS_NON_RANDOM",
                    "severity": "WARN",
                    "location": "{0}:{1}".format(in_path.name, col_name),
                    "message": "列 '{0}' 游程检验异常（{1}, R={2}, Z={3}, p={4}）".format(
                        col_name,
                        "聚簇分布" if runs_res["pattern"] == "clustered" else "过度交替",
                        runs_res["runs"],
                        runs_res["z"],
                        runs_res["p_value"],
                    ),
                    "evidence": "expected_runs={0}".format(runs_res["expected_runs"]),
                    "exempted": False,
                }
            )

        if (
            last_d_res.get("status") == "OK"
            and not last_d_res.get("low_sample_warning")
            and last_d_res["p_value"] < args.alpha
        ):
            findings.append(
                {
                    "rule_id": "LAST_DIGIT_BIAS",
                    "severity": "WARN",
                    "location": "{0}:{1}".format(in_path.name, col_name),
                    "message": "列 '{0}' 末位数字 0-9 分布显著偏离均匀分布 (chi2={1}, p={2})".format(
                        col_name, last_d_res["chi2"], last_d_res["p_value"]
                    ),
                    "evidence": "counts={0}".format(last_d_res["counts"]),
                    "exempted": False,
                }
            )

        if (
            benford_res.get("status") == "OK"
            and benford_res.get("applicable")
            and benford_res["p_value"] < args.alpha
        ):
            findings.append(
                {
                    "rule_id": "BENFORD_DEVIATION",
                    "severity": "WARN",
                    "location": "{0}:{1}".format(in_path.name, col_name),
                    "message": "列 '{0}' 首位数显著偏离 Benford 定律 (chi2={1}, p={2})".format(
                        col_name, benford_res["chi2"], benford_res["p_value"]
                    ),
                    "evidence": "counts={0}".format(benford_res["counts"]),
                    "exempted": False,
                }
            )

        if step_res is not None:
            findings.append(
                {
                    "rule_id": "DISCRETE_STEP_GRID",
                    "severity": "INFO",
                    "location": "{0}:{1}".format(in_path.name, col_name),
                    "message": "列 '{0}' 超过 {1:.0%} 观测值落在固定小数步长 {2} 的网格上".format(
                        col_name, step_res["aligned_ratio"], step_res["step_min"]
                    ),
                    "evidence": "step_min={0}".format(step_res["step_min"]),
                    "exempted": False,
                }
            )

        col_stats[col_name] = {
            "descriptive": desc,
            "groups": group_breakdown,
            "runs_test": runs_res,
            "last_digit_test": last_d_res,
            "benford_test": benford_res,
            "discrete_step": step_res,
            "outliers_3iqr": outliers_3iqr,
        }

    # Pairwise correlations
    correlations: List[Dict[str, Any]] = []
    valid_num_cols = [c for c in num_cols if c in col_paired_vals]
    for i in range(len(valid_num_cols)):
        for j in range(i + 1, len(valid_num_cols)):
            c1, c2 = valid_num_cols[i], valid_num_cols[j]
            xs: List[float] = []
            ys: List[float] = []
            for a, b in zip(col_paired_vals[c1], col_paired_vals[c2]):
                if a is not None and b is not None:
                    xs.append(a)
                    ys.append(b)
            pr = _pearson_r(xs, ys)
            sr = _spearman_rho(xs, ys)
            if pr is None and sr is None:
                continue
            correlations.append(
                {
                    "col_a": c1,
                    "col_b": c2,
                    "n_pairs": len(xs),
                    "pearson_r": round(pr, 6) if pr is not None else None,
                    "spearman_rho": round(sr, 6) if sr is not None else None,
                }
            )
            if (pr is not None and abs(pr) >= args.corr_threshold) or (
                sr is not None and abs(sr) >= args.corr_threshold
            ):
                findings.append(
                    {
                        "rule_id": "HIGH_COLLINEARITY",
                        "severity": "WARN",
                        "location": "{0}:{1}~{2}".format(in_path.name, c1, c2),
                        "message": "列 '{0}' 与 '{1}' 存在高度相关性 (r={2}, rho={3})".format(
                            c1,
                            c2,
                            round(pr, 4) if pr is not None else None,
                            round(sr, 4) if sr is not None else None,
                        ),
                        "evidence": "threshold={0}".format(args.corr_threshold),
                        "exempted": False,
                    }
                )

    confusion_summary: Optional[Dict[str, Any]] = None
    if args.ref_col and args.pred_col:
        ri = col_idx[args.ref_col]
        pi = col_idx[args.pred_col]
        confusion_summary = _confusion_and_agreement(
            [r[ri] for r in rows], [r[pi] for r in rows], args.pos_label
        )

    fail_cnt = sum(1 for f in findings if f["severity"] == "FAIL")
    warn_cnt = sum(1 for f in findings if f["severity"] == "WARN")
    status = "FAIL" if fail_cnt > 0 else ("WARN" if warn_cnt > 0 else "PASS")

    payload: Dict[str, Any] = {
        "tool": "data_forensics",
        "version": VERSION,
        "status": status,
        "summary": {
            "input": str(in_path),
            "row_count": len(rows),
            "headers": headers,
            "numeric_columns": valid_num_cols,
            "xlsx_meta": xlsx_meta,
            "fail_count": fail_cnt,
            "warn_count": warn_cnt,
            "columns": col_stats,
            "correlations": correlations,
            "confusion_agreement": confusion_summary,
        },
        "findings": findings,
    }

    if args.format == "json":
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    else:
        sys.stdout.write(
            "[data_forensics v{0}] status={1} rows={2} num_cols={3} fail={4} warn={5}\n".format(
                VERSION, status, len(rows), len(valid_num_cols), fail_cnt, warn_cnt
            )
        )
        for col_name, st in col_stats.items():
            d = st["descriptive"]
            sys.stdout.write(
                "  * {0}: n={1} mean={2} std={3} median={4} IQR(INC)={5} IQR(EXC)={6}\n".format(
                    col_name, d["n"], d["mean"], d["std"], d["median"], d["iqr_inc"], d["iqr_exc"]
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
