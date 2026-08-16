---
title: NBA Long-Term Performance Reward Report Runs
project: NBA Long-Term Performance Rewards
file_type: folder_readme
status: active
purpose: Explain timestamped report-run folders, latest-run discovery, and archive ownership.
usage: Use latest_run.json to locate current outputs or open a named run folder for immutable historical results.
last_updated: 2026-08-16
---

# Report Runs

Each successful analysis creates an immutable folder named `run_YYYY_MM_DD_HHMMSS`, optionally followed by a sanitized label. Every run keeps its analytical CSVs, parameters, data dictionary, AI guide, and manifest together.

`latest_run.json` points to the newest successfully completed run and its manifest. Run folders are never overwritten; same-second collisions receive `_02`, `_03`, and later suffixes.

Former flat report outputs and other superseded report evidence are retained beneath `__Archive__`.
