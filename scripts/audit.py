"""Adversarial audit: tests, lint, dead-code check, static security, optional LLM review.

Only reads tracked source files, does not apply patches. LLM review is *optional* and
requires separate consent via --llm, using only source code (never API tokens/data).
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "results" / "audit"
FILES = (list((ROOT / "src" / "zerodte").glob("*.py")) +
         list((ROOT / "tests").glob("*.py")))


def run(name: str, command: list[str]) -> dict:
    try:
        env = os.environ.copy()
        env["PYTHONPATH"] = (str(ROOT / "src") + os.pathsep + env["PYTHONPATH"]
                             if env.get("PYTHONPATH") else str(ROOT / "src"))
        result = subprocess.run(command, cwd=ROOT, env=env,
                                capture_output=True, text=True, timeout=180, check=False)
        return {"name": name, "exit_code": result.returncode,
                "output": (result.stdout + "\n" + result.stderr)[-20000:]}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"name": name, "exit_code": -1, "output": str(exc)}


def llm_audit() -> dict:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return {"error": "OPENAI_API_KEY missing; skipping"}
    # Source only; excludes .env, historical data, logs and any trading credentials.
    code = "\n".join(f"\n### {f.relative_to(ROOT)}\n{f.read_text()}" for f in FILES)
    payload = {
        "model": os.environ.get("AUDIT_LLM_MODEL", "gpt-5-mini"),
        "input": [
            {"role": "system", "content": "You are a skeptical quantitative trading code auditor. Only review; no tool use, code edits or trading. Find critical bugs, lookahead/data leakage, bad bid/ask fills, expiry and timezone errors, fail-open risk behavior, redundant/dead code, missing tests. Give filename, line/function and reproducible test proposal. Never claim strategies are profitable."},
            {"role": "user", "content": code[:150000]}
        ],
        "max_output_tokens": 3500,
        "store": False,
    }
    req = Request("https://api.openai.com/v1/responses", data=json.dumps(payload).encode(),
                  headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                  method="POST")
    try:
        with urlopen(req, timeout=120) as response:  # noqa: S310 - fixed HTTPS API endpoint
            result = json.loads(response.read().decode())
        blocks = [part.get("text", "") for item in result.get("output", [])
                  for part in item.get("content", []) if part.get("type") == "output_text"]
        return {"review": "\n".join(blocks), "model": payload["model"]}
    except Exception as exc:
        return {"error": f"LLM review failed: {type(exc).__name__}: {exc}"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true", help="Explicitly send code to LLM for read-only review")
    args = parser.parse_args()
    AUDIT.mkdir(parents=True, exist_ok=True)
    results = [
        run("stdlib-unittest", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]),
        run("compileall", [sys.executable, "-m", "compileall", "-q", "src", "scripts", "tests"]),
    ]
    optional = {
        "ruff": ["ruff", "check", "src", "scripts", "tests"],
        "vulture": ["vulture", "src", "scripts", "--min-confidence", "80"],
        "bandit": ["bandit", "-ll", "-q", "-r", "src", "scripts"],
    }
    for name, cmd in optional.items():
        results.append(run(name, cmd) if shutil.which(name) else
                       {"name": name, "exit_code": None, "output": "Not installed; pip install '.[audit]'"})
    # A quick temporal AST scan complements lint/security tools. Warnings are
    # review candidates, never automatically classified as proven violations.
    sys.path.insert(0, str(ROOT / "src"))
    from zerodte.source_audit import scan_source
    temporal = scan_source(ROOT / "src" / "zerodte", AUDIT / "temporal_source_review.json")
    payload = {"created_utc": datetime.now(timezone.utc).isoformat(), "checks": results,
               "heuristic_temporal_audit": temporal}
    if args.llm:
        payload["llm"] = llm_audit()
    output = AUDIT / "latest.json"
    output.write_text(json.dumps(payload, indent=2))
    for item in results:
        print(f"[{item['name']}] {item['exit_code']}: {item['output'][-250:]}")
    print(f"Audit written to {output}")
    return 1 if any(item["exit_code"] not in (0, None) for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
