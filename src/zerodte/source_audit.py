"""Conservative AST audit for potential temporal leakage and redundant hot loops.

Findings demand human review. A negative shift may be a legitimate training
label, for example; we do not report it as a proven future-data leak.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path


def _negative_constant(node: ast.AST) -> bool:
    return (isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub)
            and isinstance(node.operand, ast.Constant)
            and isinstance(node.operand.value, (int, float)) and node.operand.value > 0)


def analyze_python_source(path: str | Path) -> list[dict]:
    file = Path(path)
    source = file.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(file))
    except SyntaxError as err:
        return [{"file": str(file), "line": err.lineno, "rule": "syntax_error",
                 "severity": "error", "explanation": err.msg}]
    findings: list[dict] = []
    def add(node: ast.AST, rule: str, severity: str, explanation: str):
        findings.append({"file": str(file), "line": getattr(node, "lineno", None),
                         "rule": rule, "severity": severity, "explanation": explanation})
    declarations: dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in declarations:
                add(node, "duplicate_top_level_definition", "high",
                    f"The name {node.name} is redefined at module level, shadowing earlier code.")
            declarations[node.name] = node
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            name = node.func.attr
            if name in ("shift", "pct_change") and node.args and _negative_constant(node.args[0]):
                add(node, "future_shift_review", "high",
                    "Negative lag uses future observations; allowed for training labels only if isolated from features.")
            if name in ("fit", "fit_transform"):
                add(node, "fit_split_scope_review", "medium",
                    "Verify fitted preprocessing uses training fold only, never full history.")
            if name == "rolling":
                if any(k.arg == "center" and isinstance(k.value, ast.Constant)
                       and k.value.value is True for k in node.keywords):
                    add(node, "centered_rolling_future_review", "high",
                        "Centered rolling windows may include future values at prediction time.")
            if name in ("iterrows", "itertuples"):
                add(node, "row_loop_performance_review", "info",
                    "Hot-path feature calculation may benefit from precomputation; do not vectorize execution state blindly.")
            if name == "merge" and any(k.arg == "on" for k in node.keywords):
                add(node, "time_join_review", "info",
                    "For asynchronous price/Greek sources check as-of direction, publication time and staleness.")
    return findings


def scan_source(root: str | Path, out: str | Path | None = None) -> dict:
    folder = Path(root)
    if not folder.is_dir():
        raise ValueError("Source root must be a directory")
    paths = sorted(p for p in folder.rglob("*.py") if not any(
        d in {".venv", "__pycache__", "site-packages"} for d in p.parts))
    findings = [f for p in paths for f in analyze_python_source(p)]
    report = {"kind": "heuristic_ast_review_not_proof_of_correctness",
              "files_scanned": len(paths), "findings": findings,
              "high_severity_review_count": sum(f["severity"] == "high" for f in findings),
              "warning": "Static warnings can be false positives; absence of warnings does not prove no leakage."}
    if out is not None:
        target = Path(out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + "\n")
    return report
