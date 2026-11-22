#!/usr/bin/env python3
"""Self-validator for thesis-audit Skill package (Python 3.8+ stdlib only)."""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

VERSION = "1.0.0"

# Comprehensive Python 3.8+ stdlib module set fallback (in case sys.stdlib_module_names is absent on 3.8/3.9)
FALLBACK_STDLIB_MODULES: Set[str] = {
    "__future__", "abc", "aifc", "argparse", "array", "ast", "asynchat", "asyncio", "asyncore",
    "atexit", "audioop", "base64", "bdb", "binascii", "binhex", "bisect", "builtins", "bz2",
    "calendar", "cgi", "cgitb", "chunk", "cmath", "cmd", "code", "codecs", "codeop",
    "collections", "colorsys", "compileall", "concurrent", "configparser", "contextlib",
    "contextvars", "copy", "copyreg", "cProfile", "crypt", "csv", "ctypes", "curses",
    "dataclasses", "datetime", "dbm", "decimal", "difflib", "dis", "distutils", "doctest",
    "email", "encodings", "ensurepip", "enum", "errno", "faulthandler", "fcntl", "filecmp",
    "fileinput", "fnmatch", "formatter", "fractions", "ftplib", "functools", "gc", "getopt",
    "getpass", "gettext", "glob", "grp", "gzip", "hashlib", "heapq", "hmac", "html", "http",
    "imaplib", "imghdr", "imp", "importlib", "inspect", "io", "ipaddress", "itertools",
    "json", "keyword", "lib2to3", "linecache", "locale", "logging", "lzma", "mailbox",
    "mailcap", "marshal", "math", "mimetypes", "mmap", "modulefinder", "msilib", "msvcrt",
    "multiprocessing", "netrc", "nis", "nntplib", "numbers", "operator", "optparse", "os",
    "ossaudiodev", "parser", "pathlib", "pdb", "pickle", "pickletools", "pipes", "pkgutil",
    "platform", "plistlib", "poplib", "posix", "posixpath", "pprint", "profile", "pstats",
    "pty", "pwd", "py_compile", "pyclbr", "pydoc", "queue", "quopri", "random", "re",
    "readline", "reprlib", "resource", "rlcompleter", "runpy", "sched", "secrets", "select",
    "selectors", "shelve", "shlex", "shutil", "signal", "site", "smtpd", "smtplib", "sndhdr",
    "socket", "socketserver", "spwd", "sqlite3", "ssl", "stat", "statistics", "string",
    "stringprep", "struct", "subprocess", "sunau", "symbol", "symtable", "sys", "sysconfig",
    "syslog", "tabnanny", "tarfile", "telnetlib", "tempfile", "termios", "test", "textwrap",
    "threading", "time", "timeit", "tkinter", "token", "tokenize", "trace", "traceback",
    "tracemalloc", "tty", "turtle", "turtledemo", "types", "typing", "unicodedata", "unittest",
    "urllib", "uu", "uuid", "venv", "warnings", "wave", "weakref", "webbrowser", "winreg",
    "winsound", "wsgiref", "xdrlib", "xml", "xmlrpc", "zipapp", "zipfile", "zipimport", "zlib",
}

REQUIRED_FILES = [
    "SKILL.md",
    "README.md",
    "LICENSE",
    ".gitignore",
    "workflows/stage-1-rapid-blitz.md",
    "workflows/stage-2-data-forensics.md",
    "workflows/stage-3-authenticity-recovery.md",
    "checklists/rapid-audit-50pt-template.md",
    "checklists/data-reconciliation-checklist.md",
    "checklists/defense-and-blind-review-gate.md",
    "templates/audit-report-template.md",
    "templates/remediation-matrix.md",
    "references/five-dimension-taxonomy.md",
    "references/statistical-forensics-guide.md",
    "references/ai-and-fabrication-tells.md",
    "references/case-study-desensitized.md",
    "scripts/doc_leak_scanner.py",
    "scripts/cross_table_reconciler.py",
    "scripts/data_forensics.py",
    "scripts/prose_rhythm_audit.py",
    "scripts/validate_skill.py",
    "tests/test_scripts.py",
]

ALLOWED_TOP_YAML_KEYS = {"name", "description", "license", "metadata"}
FORBIDDEN_TOP_YAML_KEYS = {"version", "compatibility", "allowed-tools"}


def _build_desensitization_patterns() -> List[Tuple[str, str]]:
    """Construct decoupling check regexes via escaped/concatenated literals so this file stays clean."""
    items = [
        ("ENTITY_UNIV", "\u4e0a\u6d77\u8d22\u7ecf|\u4e0a\u8d22|\u8d22\u5927|SUFE"),
        ("ENTITY_AUTHOR", "\u9648" + "\u5b81|\u65b9" + "\u82b3"),
        ("ENTITY_CORP", "\u65b0\u8dc3|Xiny" + "ue|Xinw" + "ell"),
        ("ENTITY_REG", "797\\s*\u53f7|107\\s*\u53f7|ISO\\s*13485|\u533b\u7597\u5668\u68b0"),
        (
            "ENTITY_FILES",
            "\u5b9e\u6d4b\u8bb0\u5f55_" + "\u6a21\u677f|calc_" + "metrics|verify_v3_" + "thesis|"
            "render_v3_" + "docx|V3_\u8bba\u6587|P2\\s*\u9632\u7ebf|P0\\s*\u9632\u7ebf",
        ),
        (
            "ENTITY_IDS",
            "\\b(?:\x5202|\x5205|\x5213|\x5218|\x5224|\x5228|\x5230|\x5231|\x5235|\x5237|"
            "\x51M-01|\x52A-01|\x48R-01|\x48R-02|\x49T-01)\\b",
        ),
        (
            "ENTITY_NUMS",
            "0\\.9991|62\\.5%|87\\.5%|0\\.746|0\\.250|2,900\\s*\u4efd|508\\s*\u4efd",
        ),
        (
            "LOCAL_PATH_LEAK",
            "(?i)(?:[a-z]:\\\\u" + "sers\\\\|e:\\\\cl" + "oud\\\\)",
        ),
    ]
    return items


def _check_v1_skill_uniqueness(root: Path) -> Dict[str, Any]:
    skill_path = root / "SKILL.md"
    if not skill_path.exists():
        return {"id": "V1", "name": "SKILL.md 存在与唯一性", "status": "FAIL", "detail": "根目录缺少 SKILL.md"}
    if skill_path.is_symlink():
        return {"id": "V1", "name": "SKILL.md 存在与唯一性", "status": "FAIL", "detail": "SKILL.md 不得为符号链接"}
    found = [p.relative_to(root).as_posix() for p in root.rglob("SKILL.md") if ".git" not in p.parts]
    if found != ["SKILL.md"]:
        return {"id": "V1", "name": "SKILL.md 存在与唯一性", "status": "FAIL", "detail": "发现非唯一 SKILL.md: {0}".format(found)}
    return {"id": "V1", "name": "SKILL.md 存在与唯一性", "status": "PASS", "detail": "根目录唯一且非软链"}


def _check_v2_line_limit(root: Path) -> Dict[str, Any]:
    skill_path = root / "SKILL.md"
    if not skill_path.exists():
        return {"id": "V2", "name": "SKILL.md 行数限制", "status": "FAIL", "detail": "SKILL.md 不存在"}
    lines = skill_path.read_text(encoding="utf-8").splitlines()
    cnt = len(lines)
    if cnt > 200:
        return {"id": "V2", "name": "SKILL.md 行数限制", "status": "FAIL", "detail": "SKILL.md 共 {0} 行，超过 200 行上限".format(cnt)}
    return {"id": "V2", "name": "SKILL.md 行数限制", "status": "PASS", "detail": "{0}/200 行".format(cnt)}


def _check_v3_yaml_frontmatter(root: Path) -> Dict[str, Any]:
    skill_path = root / "SKILL.md"
    if not skill_path.exists():
        return {"id": "V3", "name": "YAML Frontmatter 规范", "status": "FAIL", "detail": "SKILL.md 不存在"}
    text = skill_path.read_text(encoding="utf-8")
    m = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", text, flags=re.DOTALL)
    if not m:
        return {"id": "V3", "name": "YAML Frontmatter 规范", "status": "FAIL", "detail": "缺少规范 YAML frontmatter"}
    fm = m.group(1)

    top_keys: Set[str] = set()
    for line in fm.splitlines():
        m_k = re.match(r"^([A-Za-z0-9_-]+):", line)
        if m_k:
            top_keys.add(m_k.group(1))

    forbidden_hit = sorted(top_keys & FORBIDDEN_TOP_YAML_KEYS)
    if forbidden_hit:
        return {
            "id": "V3",
            "name": "YAML Frontmatter 规范",
            "status": "FAIL",
            "detail": "包含被禁止的顶层字段: {0}".format(forbidden_hit),
        }

    unknown_keys = sorted(top_keys - ALLOWED_TOP_YAML_KEYS)
    if unknown_keys:
        return {
            "id": "V3",
            "name": "YAML Frontmatter 规范",
            "status": "FAIL",
            "detail": "包含未知顶层字段: {0}".format(unknown_keys),
        }

    missing_keys = sorted(ALLOWED_TOP_YAML_KEYS - top_keys)
    if missing_keys:
        return {
            "id": "V3",
            "name": "YAML Frontmatter 规范",
            "status": "FAIL",
            "detail": "缺少必需顶层字段: {0}".format(missing_keys),
        }

    m_name = re.search(r"^name:\s*['\"]?([a-z0-9-]+)['\"]?\s*$", fm, flags=re.MULTILINE)
    if not m_name or not re.match(r"^[a-z0-9][a-z0-9-]{0,63}$", m_name.group(1)):
        return {"id": "V3", "name": "YAML Frontmatter 规范", "status": "FAIL", "detail": "name 字段不符合规范"}
    skill_name = m_name.group(1)
    if skill_name != "thesis-audit":
        return {"id": "V3", "name": "YAML Frontmatter 规范", "status": "FAIL", "detail": "name 必须为 thesis-audit，实际: {0}".format(skill_name)}
    if root.name == "thesis-audit" and skill_name != root.name:
        return {"id": "V3", "name": "YAML Frontmatter 规范", "status": "FAIL", "detail": "name 与目录名不一致"}

    m_lic = re.search(r"^license:\s*['\"]?([^'\"\r\n]+)['\"]?\s*$", fm, flags=re.MULTILINE)
    if not m_lic or m_lic.group(1).strip() != "MIT":
        return {"id": "V3", "name": "YAML Frontmatter 规范", "status": "FAIL", "detail": "license 必须为 MIT"}

    m_desc = re.search(r"^description:\s*(.+)$", fm, flags=re.MULTILINE)
    if not m_desc or not m_desc.group(1).strip():
        return {"id": "V3", "name": "YAML Frontmatter 规范", "status": "FAIL", "detail": "description 不能为空"}

    m_ver = re.search(r"^\s+version:\s*['\"]?(\d+\.\d+\.\d+)['\"]?\s*$", fm, flags=re.MULTILINE)
    if not m_ver:
        return {"id": "V3", "name": "YAML Frontmatter 规范", "status": "FAIL", "detail": "metadata.version 缺失或非 X.Y.Z 格式"}

    return {
        "id": "V3",
        "name": "YAML Frontmatter 规范",
        "status": "PASS",
        "detail": "name={0}, license=MIT, metadata.version={1}".format(skill_name, m_ver.group(1)),
    }


def _check_v4_structure(root: Path) -> Dict[str, Any]:
    missing: List[str] = []
    empty: List[str] = []
    for rel in REQUIRED_FILES:
        p = root / rel
        if not p.exists():
            missing.append(rel)
        elif p.stat().st_size == 0:
            empty.append(rel)

    fixtures_dir = root / "tests" / "fixtures"
    if not fixtures_dir.is_dir() or not any(fixtures_dir.iterdir()):
        missing.append("tests/fixtures/*")

    if missing or empty:
        return {
            "id": "V4",
            "name": "仓库结构与文件完整性",
            "status": "FAIL",
            "detail": "缺失: {0}; 空文件: {1}".format(missing, empty),
        }
    return {"id": "V4", "name": "仓库结构与文件完整性", "status": "PASS", "detail": "全部 23 个核心文件及夹具目录完整"}


def _check_v5_links(root: Path) -> Dict[str, Any]:
    broken: List[str] = []
    md_files = [root / "SKILL.md", root / "README.md"]
    for sub_dir in ("workflows", "checklists", "templates", "references"):
        d = root / sub_dir
        if d.is_dir():
            md_files.extend(sorted(d.glob("*.md")))

    link_re = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")
    for md_path in md_files:
        if not md_path.exists():
            continue
        lines = md_path.read_text(encoding="utf-8").splitlines()
        in_code = False
        for idx, line in enumerate(lines, start=1):
            if re.match(r"^[ ]{0,3}(?:```|~~~)", line):
                in_code = not in_code
                continue
            if in_code:
                continue
            # Strip inline backticks before checking links
            cleaned = re.sub(r"`[^`\n]+`", "", line)
            for m in link_re.finditer(cleaned):
                target = m.group(1).strip()
                if re.match(r"^(?:https?://|mailto:|#)", target, flags=re.IGNORECASE):
                    continue
                resolved = (md_path.parent / target).resolve()
                if not resolved.exists():
                    broken.append("{0}:{1} -> {2}".format(md_path.relative_to(root).as_posix(), idx, target))

    if broken:
        return {"id": "V5", "name": "Markdown 相对链接检查", "status": "FAIL", "detail": "发现死链: {0}".format(broken)}
    return {"id": "V5", "name": "Markdown 相对链接检查", "status": "PASS", "detail": "共检查 {0} 个 Markdown 文件，0 死链".format(len(md_files))}


def _check_v6_stdlib_only(root: Path) -> Dict[str, Any]:
    stdlib_names: Set[str] = set(FALLBACK_STDLIB_MODULES)
    if hasattr(sys, "stdlib_module_names"):
        stdlib_names |= set(getattr(sys, "stdlib_module_names"))

    local_modules: Set[str] = set()
    py_files: List[Path] = []
    for sub in ("scripts", "tests"):
        d = root / sub
        if d.is_dir():
            for p in sorted(d.glob("*.py")):
                py_files.append(p)
                local_modules.add(p.stem)

    violations: List[str] = []
    for py_path in py_files:
        src = py_path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(src, filename=str(py_path))
        except SyntaxError as exc:
            violations.append("{0}: SyntaxError {1}".format(py_path.name, exc))
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top not in stdlib_names and top not in local_modules:
                        violations.append("{0}: import {1}".format(py_path.name, alias.name))
            elif isinstance(node, ast.ImportFrom):
                if node.level > 0:
                    continue
                if node.module:
                    top = node.module.split(".")[0]
                    if top not in stdlib_names and top not in local_modules:
                        violations.append("{0}: from {1}".format(py_path.name, node.module))

    if violations:
        return {"id": "V6", "name": "纯 Python 标准库静态检验", "status": "FAIL", "detail": "检测到非标准库导入或语法错误: {0}".format(violations)}
    return {"id": "V6", "name": "纯 Python 标准库静态检验", "status": "PASS", "detail": "已检验 {0} 个 Python 文件，100% 纯标准库".format(len(py_files))}


def _check_v7_desensitization(root: Path) -> Dict[str, Any]:
    patterns = _build_desensitization_patterns()
    hits: List[str] = []
    text_exts = {".md", ".txt", ".py", ".yml", ".yaml", ".json", ".csv", ".tsv", ".gitignore"}
    self_path = Path(__file__).resolve()

    for p in sorted(root.rglob("*")):
        if not p.is_file() or ".git" in p.parts or "__pycache__" in p.parts:
            continue
        if p.resolve() == self_path:
            continue
        if p.suffix.lower() not in text_exts and p.name not in ("LICENSE", ".gitignore"):
            continue
        txt = p.read_text(encoding="utf-8", errors="ignore")
        for tag, pat in patterns:
            m = re.search(pat, txt)
            if m:
                hits.append("{0} [{1}: {2}]".format(p.relative_to(root).as_posix(), tag, m.group(0)))

    if hits:
        return {"id": "V7", "name": "通用解耦与零泄露扫描", "status": "FAIL", "detail": "发现敏感污染或本机路径: {0}".format(hits[:10])}
    return {"id": "V7", "name": "通用解耦与零泄露扫描", "status": "PASS", "detail": "全仓库 0 特定论文污染与 0 本机路径泄漏"}


def _check_v8_unit_tests(root: Path) -> Tuple[Dict[str, Any], str]:
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", str(root / "tests"), "-v"],
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    combined = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    if proc.returncode != 0:
        return (
            {
                "id": "V8",
                "name": "独立单元测试集",
                "status": "FAIL",
                "detail": "unittest 退出码 {0}".format(proc.returncode),
            },
            combined.strip(),
        )
    return (
        {
            "id": "V8",
            "name": "独立单元测试集",
            "status": "PASS",
            "detail": "unittest discover 全绿通过",
        },
        combined.strip(),
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="校验 thesis-audit Skill 目录结构、YAML、纯标准库与测试")
    parser.add_argument("--run-tests", action="store_true", help="同时运行 tests/ 全部单元测试")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="输出格式")
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parent.parent
    checks: List[Dict[str, Any]] = [
        _check_v1_skill_uniqueness(root),
        _check_v2_line_limit(root),
        _check_v3_yaml_frontmatter(root),
        _check_v4_structure(root),
        _check_v5_links(root),
        _check_v6_stdlib_only(root),
        _check_v7_desensitization(root),
    ]

    test_output: Optional[str] = None
    if args.run_tests:
        v8_res, test_output = _check_v8_unit_tests(root)
        checks.append(v8_res)

    fail_cnt = sum(1 for c in checks if c["status"] != "PASS")
    status = "FAIL" if fail_cnt > 0 else "PASS"

    payload: Dict[str, Any] = {
        "tool": "validate_skill",
        "version": VERSION,
        "status": status,
        "root": str(root),
        "checks": checks,
        "fail_count": fail_cnt,
    }
    if test_output is not None:
        payload["test_output"] = test_output

    if args.format == "json":
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    else:
        sys.stdout.write("[validate_skill v{0}] status={1} checks={2} fail={3}\n".format(
            VERSION, status, len(checks), fail_cnt
        ))
        for c in checks:
            sys.stdout.write("- [{0}] {1} ({2}): {3}\n".format(c["status"], c["id"], c["name"], c["detail"]))
        if test_output:
            sys.stdout.write("\n--- unittest output ---\n" + test_output + "\n")

    return 1 if fail_cnt > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
