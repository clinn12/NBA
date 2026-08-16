---
title: Code and Notebook Documentation Standards
project: NBA Simulator
file_type: project_standard
status: active
purpose: Define mandatory front matter, docstrings, comments, notebook guidance, and enforcement.
usage: Follow for every new or materially updated active file and during code review.
last_updated: 2026-08-01
---

# Code and Notebook Documentation Standards

These requirements apply whenever an active Python file, Markdown document, or notebook is created or materially updated. The canonical project identity is `NBA Simulator`, located at `C:\Users\clinn\Documents\NBA\Simulator` on the current workstation.

## Required front matter

Markdown files use YAML front matter as the first content in the file:

```yaml
---
title: Human-readable title
project: NBA Simulator
file_type: documentation_type
status: active
purpose: Why the file exists.
usage: When and how the file should be used.
last_updated: YYYY-MM-DD
---
```

Files inside an `__Archive__` directory must use `status: archived`; other maintained Markdown files use `status: active`.

Python cannot place YAML before executable code, so Python files use equivalent structured front matter inside the opening module docstring:

```python
"""Short module summary.

Front Matter
------------
Project: NBA Simulator
File type: Python module
Status: Active
Last updated: YYYY-MM-DD

Purpose: Why the module exists.
Usage: How it is imported or run.
"""
```

Active notebooks use the Markdown schema visibly in the first cell and duplicate the same fields under notebook metadata key `nba_simulator_front_matter`. Strict-schema JSON, generated datasets, CSV outputs, and immutable snapshots are exempt because inserting front matter would invalidate or change their consumer contracts. Their provenance belongs in existing metadata objects, manifests, or adjacent documentation.

## Python files

Every active `.py` file must begin with the structured module docstring above and state:

- **Purpose:** why the file exists and what responsibility it owns.
- **Usage:** how it is imported or run, including the primary entry point when applicable.
- Important inputs, outputs, side effects, or safety constraints when they are not obvious.

Every public class and function must have a docstring explaining its responsibility, important arguments, return value, and notable exceptions or side effects. Private helpers should also have docstrings when their behavior, assumptions, or formulas are not obvious from the name and signature.

Use inline comments to explain intent and reasoning, especially for:

- NBA rule interpretations and possession transitions.
- Statistical formulas, clamps, fallbacks, and calibration constants.
- Time-valid data boundaries and leakage prevention.
- Seed derivation, reproducibility, state mutation, and selection rules.
- File writes, caching, resumability, and external-source limitations.

Comments should explain **why** the code exists or why an approach was chosen. Avoid comments that only restate the next line of code. Update nearby documentation whenever behavior changes; stale comments are defects.

## Notebooks

Every active notebook must begin with a Markdown cell containing:

- Required YAML front matter with `project: NBA Simulator` and `status: active`.
- A clear title.
- A **Purpose** section.
- A **How to use** section with execution order and prerequisites.
- Inputs and outputs.
- A warning identifying any historical, exploratory, or non-active cells.

Each non-trivial code cell must either be introduced by a Markdown explanation or begin with a comment/docstring describing what the cell demonstrates. Canonical production logic belongs in importable Python modules; notebooks should import that logic and focus on exploration, examples, and review.

## Review and enforcement

Run these checks after creating or modifying code:

```powershell
python scripts/check_documentation.py
python -m unittest discover -s tests -v
```

`scripts/check_documentation.py` checks active Python front matter and public API docstrings, all maintained Markdown front matter, and both visible and machine-readable notebook front matter. Archived Python/notebook artifacts preserve their original contents and are excluded from active-code enforcement; archived Markdown indexes and handoffs must still identify themselves as archived.
