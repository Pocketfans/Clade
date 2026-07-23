# M5 Entry Partition Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move prepared-entry classification, deferred-request merging and per-turn limiting out of `process_async` without changing order, list identity behavior or queue contents.

**Architecture:** Create `speciation_process.py` with pure `partition_speciation_entries(...)`. Return background entries, the active AI batch and the replacement deferred queue. Keep logging and early returns in `process_async`.

**Tech Stack:** Python 3.12 and pytest.

## Constraints

- Preserve `getattr(..., "is_background", False)`, background order, deferred-before-new-AI order, max-deferred truncation before per-turn slicing, slice semantics and non-mutation of the input lists.
- Do not change AI calls, random draws, repositories, formulas, callbacks, public interfaces, dependencies, database or persisted formats.

## Task

- [ ] Add failing tests for missing/background flags, identity/order, deferred priority, both limits, empty/zero limits and unchanged inputs.
- [ ] Run `pytest -q app/services/species/tests/test_speciation_process.py` and verify import failure for the new module/function.
- [ ] Add the pure function and replace only the inline classification/queue block.
- [ ] Run focused and all species tests.
- [ ] Compare the normalized moved AST, run `git diff --check` and review the current diff.
- [ ] Run one backend full suite and one frontend test/build/lint gate.
- [ ] Commit as `refactor(backend): extract speciation entry partition`, ordinary-push and update only PR #15.
