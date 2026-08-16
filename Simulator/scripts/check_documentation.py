"""Audit active Python and notebook documentation against project standards.

Front Matter
------------
Project: NBA Simulator
File type: Python script
Status: Active
Last updated: 2026-08-01

Purpose
-------
Prevent new or modified source files from omitting file-level purpose/usage
documentation or public API docstrings.

Usage
-----
Run ``python scripts/check_documentation.py`` from any directory. The command
prints a JSON report and exits nonzero when required documentation is missing.
Archived files are intentionally excluded from enforcement.
"""

from __future__ import annotations

import ast
import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

try:
    from ._project_paths import PROJECT_ROOT
except ImportError:  # Direct execution
    from _project_paths import PROJECT_ROOT


ACTIVE_PYTHON_ROOTS = ("nba_simulator", "scripts", "tests")
ACTIVE_NOTEBOOKS = (Path("notebooks/Simulation_robust_copy.ipynb"),)
REQUIRED_MODULE_SECTIONS = ("purpose", "usage")
REQUIRED_NOTEBOOK_SECTIONS = ("purpose", "how to use")
REQUIRED_PYTHON_FRONT_MATTER = (
    "front matter", "project: nba simulator", "file type:",
    "status: active", "last updated:",
)
REQUIRED_MARKDOWN_FRONT_MATTER = (
    "title", "project", "file_type", "status", "purpose", "usage", "last_updated",
)
# Build deprecated identifiers from parts so this validator does not flag its
# own source while still detecting the contiguous old name in project files.
FORBIDDEN_PROJECT_REFERENCES = ("nba" + "\\predictions", "nba" + " predictions")


def _active_python_files() -> Iterable[Path]:
    """Yield active Python files while excluding every archive directory."""
    for root_name in ACTIVE_PYTHON_ROOTS:
        for path in sorted((PROJECT_ROOT / root_name).rglob("*.py")):
            if "__Archive__" not in path.parts:
                yield path


def _requires_api_docstring(node: ast.AST) -> bool:
    """Return whether a top-level definition is part of the documented API surface."""
    name = getattr(node, "name", "")
    return isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and (
        not name.startswith("_") or name == "main"
    )


def audit_python_file(path: Path) -> List[str]:
    """Return documentation violations for one Python source file."""
    relative = path.relative_to(PROJECT_ROOT).as_posix()
    source_text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source_text, filename=str(path))
    except SyntaxError as error:
        return [f"{relative}: syntax error prevents documentation audit: {error}"]
    violations: List[str] = []
    module_doc = ast.get_docstring(tree) or ""
    if not module_doc:
        violations.append(f"{relative}: missing module docstring")
    else:
        normalized = module_doc.lower()
        for section in REQUIRED_MODULE_SECTIONS:
            if section not in normalized:
                violations.append(f"{relative}: module docstring missing {section.title()} section")
        for field in REQUIRED_PYTHON_FRONT_MATTER:
            if field not in normalized:
                violations.append(f"{relative}: Python front matter missing {field}")
    for node in tree.body:
        if _requires_api_docstring(node) and not ast.get_docstring(node):
            violations.append(f"{relative}:{node.lineno}: {node.name} missing public API docstring")
    if any(reference in source_text.lower() for reference in FORBIDDEN_PROJECT_REFERENCES):
        violations.append(f"{relative}: contains an obsolete former-project reference")
    return violations


def _markdown_front_matter(text: str) -> Dict[str, str]:
    """Parse the simple top-of-file YAML mapping used by project Markdown files."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields: Dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return fields
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    return {}


def audit_markdown(path: Path) -> List[str]:
    """Validate required YAML front matter and active/archive status for Markdown."""
    relative = path.relative_to(PROJECT_ROOT).as_posix()
    source_text = path.read_text(encoding="utf-8")
    fields = _markdown_front_matter(source_text)
    if not fields:
        return [f"{relative}: missing top-of-file YAML front matter"]
    violations = [
        f"{relative}: Markdown front matter missing {field}"
        for field in REQUIRED_MARKDOWN_FRONT_MATTER
        if not fields.get(field)
    ]
    if fields.get("project") != "NBA Simulator":
        violations.append(f"{relative}: project must be NBA Simulator")
    expected_status = "archived" if "__Archive__" in path.parts else "active"
    if fields.get("status") != expected_status:
        violations.append(f"{relative}: status must be {expected_status}")
    if any(reference in source_text.lower() for reference in FORBIDDEN_PROJECT_REFERENCES):
        violations.append(f"{relative}: contains an obsolete former-project reference")
    return violations


def audit_notebook(path: Path) -> List[str]:
    """Return opening-documentation violations for one active notebook."""
    relative = path.relative_to(PROJECT_ROOT).as_posix()
    source_text = path.read_text(encoding="utf-8")
    payload = json.loads(source_text)
    cells = payload.get("cells", [])
    if not cells or cells[0].get("cell_type") != "markdown":
        return [f"{relative}: first cell must be Markdown documentation"]
    opening = "".join(cells[0].get("source", [])).lower()
    violations = []
    for section in REQUIRED_NOTEBOOK_SECTIONS:
        if section not in opening:
            violations.append(f"{relative}: opening Markdown missing {section.title()} section")
    visible_fields = _markdown_front_matter("".join(cells[0].get("source", [])))
    for field in REQUIRED_MARKDOWN_FRONT_MATTER:
        if not visible_fields.get(field):
            violations.append(f"{relative}: visible front matter missing {field}")
    metadata = payload.get("metadata", {}).get("nba_simulator_front_matter", {})
    for field in REQUIRED_MARKDOWN_FRONT_MATTER:
        if not metadata.get(field):
            violations.append(f"{relative}: notebook metadata missing {field}")
    if visible_fields.get("project") != "NBA Simulator" or metadata.get("project") != "NBA Simulator":
        violations.append(f"{relative}: visible and notebook metadata project must be NBA Simulator")
    if any(reference in source_text.lower() for reference in FORBIDDEN_PROJECT_REFERENCES):
        violations.append(f"{relative}: contains an obsolete former-project reference")
    return violations


def build_report() -> Dict[str, Any]:
    """Audit all active code artifacts and return a serializable summary."""
    python_files = list(_active_python_files())
    violations = [message for path in python_files for message in audit_python_file(path)]
    markdown_files = sorted(PROJECT_ROOT.rglob("*.md"))
    violations.extend(message for path in markdown_files for message in audit_markdown(path))
    notebook_paths = [PROJECT_ROOT / relative for relative in ACTIVE_NOTEBOOKS]
    violations.extend(message for path in notebook_paths for message in audit_notebook(path))
    return {
        "status": "pass" if not violations else "fail",
        "python_files_checked": len(python_files),
        "markdown_files_checked": len(markdown_files),
        "notebooks_checked": len(notebook_paths),
        "violations": violations,
    }


def main() -> None:
    """Run the documentation audit and exit nonzero when violations exist."""
    parser = argparse.ArgumentParser(description="Check active code and notebook documentation.")
    parser.parse_args()
    report = build_report()
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["status"] == "pass" else 1)


if __name__ == "__main__":
    main()
