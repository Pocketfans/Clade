# M5 Background Result Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move background-species pressure normalization and sequential rule-result generation out of `process_async` without changing filtering, overwrite order, callback arguments, result order or logs.

**Architecture:** Add `generate_background_results(...)` to `speciation_process.py`. Pass the current bound rule-fallback generator explicitly and return the existing `(entry, ai_content)` tuples.

**Tech Stack:** Python 3.12 and pytest.

## Constraints

- Preserve truthiness handling for `pressures`, `hasattr` filtering, duplicate-category last-write behavior, one shared pressure dictionary, entry order, exact fallback arguments, tuple identities and logger text.
- Do not change fallback formulas, random draws, AI, repositories, public interfaces, dependencies, database or persisted formats.

## Task

- [ ] Add failing tests for pressure filtering/overwrites, shared dictionary identity, callback order/arguments, result identity and empty inputs.
- [ ] Run the focused process test and verify import failure for `generate_background_results`.
- [ ] Add the function and replace only the inline pressure/result-generation block.
- [ ] Run focused and all species tests.
- [ ] Compare normalized moved AST, run `git diff --check` and review the current diff.
- [ ] Run one backend full suite and one frontend test/build/lint gate.
- [ ] Commit as `refactor(backend): extract background result generation`, ordinary-push and update only PR #15.
