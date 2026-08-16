---
title: NBA Data Collection Documentation Standards
project: NBA Data Collection
file_type: project_standard
status: active
purpose: Define mandatory front matter, docstrings, comments, and automated enforcement.
usage: Follow for every new or materially updated source or documentation file.
last_updated: 2026-08-14
---

# Documentation Standards

Python files use structured front matter inside their opening module docstring with project, file type, active status, last-updated date, purpose, and usage. Markdown uses YAML front matter with title, project, file type, status, purpose, usage, and last-updated date.

Public APIs require docstrings. Non-obvious source rules, formulas, leakage boundaries, retries, caching, file writes, and fallbacks require intent-focused comments. Archived Markdown uses `status: archived`; strict-schema JSON/CSV and generated data remain schema-safe and carry provenance through their existing metadata or manifests.

Run:

```powershell
python scripts/check_documentation.py
python -m unittest discover -s tests -v
```

