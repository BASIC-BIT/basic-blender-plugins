"""Run repository architecture, size, and plain-Python test checks."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "repository-policy.json"
ARCHITECTURE_PATH = ROOT / "architecture.json"
ARCHITECTURE_DOC_PATH = ROOT / "ARCHITECTURE.md"


def _git_text_paths(root=ROOT):
    output = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
    )
    for raw_path in output.split(b"\0"):
        if not raw_path:
            continue
        relative = raw_path.decode("utf-8").replace("\\", "/")
        path = root / relative
        if not path.is_file():
            continue
        payload = path.read_bytes()
        if b"\0" in payload:
            continue
        try:
            payload.decode("utf-8-sig")
        except UnicodeDecodeError:
            continue
        yield relative, payload


def _line_count(payload):
    text = payload.decode("utf-8-sig")
    return len(text.splitlines()) or (1 if text else 0)


def check_file_lengths(root=ROOT, policy_path=POLICY_PATH):
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    maximum = int(policy["max_lines"])
    warning = int(policy["warning_lines"])
    baseline = policy.get("oversized_baseline", {})
    exemptions = {
        item["path"]: item for item in policy.get("text_exemptions", [])
    }
    observed = {}
    errors = []
    warnings = []

    for relative, payload in _git_text_paths(root):
        if relative in exemptions:
            continue
        count = _line_count(payload)
        observed[relative] = count
        allowed = int(baseline.get(relative, maximum))
        if count > allowed:
            errors.append(f"{relative}: {count} lines exceeds allowed {allowed}")
        elif count > maximum:
            warnings.append(
                f"BASELINE {relative}: {count} lines; must not grow and must be split"
            )
        elif relative in baseline:
            errors.append(
                f"{relative}: now {count} lines; remove its stale oversized baseline"
            )
        elif count >= warning:
            warnings.append(f"NEAR LIMIT {relative}: {count}/{maximum} lines")

    for relative in sorted(set(baseline) - set(observed)):
        errors.append(f"oversized baseline references missing text file: {relative}")
    for relative, item in exemptions.items():
        if not item.get("reason"):
            errors.append(f"text exemption needs a reason: {relative}")
        if not (root / relative).exists():
            errors.append(f"text exemption references missing file: {relative}")
    return errors, warnings


def render_architecture(data):
    lines = [
        f"# {data['title']}",
        "",
        "This file is generated from `architecture.json`. Run "
        "`python scripts/verify_repository.py --write-architecture` after editing the map.",
        "",
        "Read the matching row before changing code. Core modules are Blender-free; "
        "operators adapt Blender state to core APIs; UI only exposes properties and commands.",
        "",
        "| Area | Reach here when | Source | Tests | Design docs |",
        "|---|---|---|---|---|",
    ]
    for area in data["areas"]:
        cells = []
        for key in ("source", "tests", "docs"):
            cells.append("<br>".join(f"`{path}`" for path in area.get(key, [])) or "-")
        lines.append(
            f"| {area['name']} | {area['when']} | {cells[0]} | {cells[1]} | {cells[2]} |"
        )
    lines.extend(
        [
            "",
            "## Dependency Rules",
            "",
            "- `core/` must not import `bpy`, `operators`, or `ui`.",
            "- `operators/` owns Blender data conversion and may depend on `core/`.",
            "- `ui/` owns layout only; mesh algorithms belong in `core/`.",
            "- Scripts and tests should consume public package APIs instead of private helpers.",
            "- Maintained text files have a hard 500-line maximum.",
            "",
        ]
    )
    return "\n".join(lines)


def check_architecture(write=False, root=ROOT):
    data = json.loads((root / "architecture.json").read_text(encoding="utf-8"))
    errors = []
    paths = set()
    for area in data.get("areas", []):
        for key in ("source", "tests", "docs"):
            for relative in area.get(key, []):
                paths.add(relative)
                if not (root / relative).exists():
                    errors.append(f"architecture map references missing path: {relative}")
    expected = render_architecture(data)
    output_path = root / "ARCHITECTURE.md"
    if write:
        output_path.write_text(expected, encoding="utf-8", newline="\n")
    elif not output_path.exists() or output_path.read_text(encoding="utf-8") != expected:
        errors.append(
            "ARCHITECTURE.md is stale; run verify_repository.py --write-architecture"
        )
    return errors


def _module_name(node):
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom):
        return [node.module or ""]
    return []


def check_dependency_rules(root=ROOT):
    errors = []
    core_root = root / "BASICs_shape_key_manager" / "core"
    for path in core_root.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            errors.append(f"{path.relative_to(root)}: syntax error: {exc}")
            continue
        for node in ast.walk(tree):
            for module in _module_name(node):
                if module == "bpy" or module.startswith("bpy."):
                    errors.append(f"{path.relative_to(root)}: core must not import bpy")
                if "operators" in module.split(".") or "ui" in module.split("."):
                    errors.append(
                        f"{path.relative_to(root)}: core must not import {module}"
                    )
    return errors


def run_tests(root=ROOT):
    failures = []
    tests = sorted((root / "tests").rglob("test_*.py"))
    for path in tests:
        result = subprocess.run([sys.executable, str(path)], cwd=root)
        if result.returncode:
            failures.append(f"test failed: {path.relative_to(root)}")
    return failures


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--structure-only", action="store_true")
    parser.add_argument("--write-architecture", action="store_true")
    args = parser.parse_args(argv)

    if args.write_architecture:
        check_architecture(write=True)
    errors, warnings = check_file_lengths()
    errors.extend(check_architecture())
    errors.extend(check_dependency_rules())
    for warning in warnings:
        print(f"WARNING: {warning}")
    if not args.structure_only:
        errors.extend(run_tests())
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Repository verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
