"""Regression test for mandatory source and notebook documentation.

Front Matter
------------
Project: NBA Data Collection
File type: Python test module
Status: Active
Last updated: 2026-08-14

Purpose: ensure new or materially updated active files keep required module,
public API, and notebook-opening documentation.
Usage: included automatically in ``python -m unittest discover -s tests -v``;
developers can also run ``python scripts/check_documentation.py`` directly.
"""

from __future__ import annotations

import unittest

from scripts.check_documentation import build_report


class DocumentationStandardsTests(unittest.TestCase):
    """Fail the regression suite when active documentation requirements regress."""

    def test_active_code_and_notebook_documentation(self) -> None:
        """Require every active artifact to pass the documented audit rules."""
        report = build_report()
        self.assertEqual("pass", report["status"], report["violations"])


if __name__ == "__main__":
    unittest.main()
