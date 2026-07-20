---
name: lint-n-test
description: Lint the service files and run the full test suite (Python + native C). Use when the user asks to lint, run tests, run the test suite, or check that the code is clean.
model: haiku
---

Lint the files and run all tests. Run every step, report each result, and do **not** stop early on the first failure — collect and report all of them.

1. **Ruff lint** (service Python):
   `cd ubo_service/070-doom && ../../.venv/bin/ruff check .`
   Use `ruff check` only. Do **not** run `ruff format` / `ruff format --check` — pre-existing untouched files are not ours to reformat.

2. **Python compile check** (from repo root):
   `.venv/bin/python -m compileall -q ubo_service/070-doom`

3. **Python tests** (pytest, pure-Python, no `.so` or device needed):
   `cd ubo_service/070-doom && ../../.venv/bin/python -m pytest`

4. **Native C unit tests** (pure logic, no engine/IWAD/device):
   `./native/scripts/run_unit_tests.sh`

Notes:
- All tools live in the repo-root venv `.venv/` — always use `.venv/bin/python` and `.venv/bin/ruff` (the Pi's system Python is externally managed / PEP 668 and can't install them).
- Only fix issues that are clearly within scope of recent changes; if a failure looks pre-existing or unrelated, report it rather than silently "fixing" unrelated files.
- Finish with a short summary: which of the four steps passed/failed, with the failing output for any that failed.
