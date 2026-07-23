# M5 Background Result Materialization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move background-result species creation, persistence, inheritance and event materialization out of `process_async` without changing mutation, callback or repository order.

**Architecture:** Add a bounded `materialize_background_result(...)` function plus a thin `materialize_background_results(...)` loop to `speciation_process.py`. Pass all existing service callbacks, mutable queues, repository operations, randomness, clocks and event factories explicitly.

**Tech Stack:** Python 3.12 and pytest.

## Constraints

- Preserve validation, child creation and `is_background` assignment before first upsert.
- Preserve use of the object returned by first upsert, fallback-description queue order, assigned-tile default, one `random.uniform(0.30, 0.50)` call per entry and habitat inheritance arguments.
- Preserve lazy gene-library property access, optional genus lookup, dormant-gene inheritance, conditional second/third upserts, breakthrough behavior, lineage-event write order and branching-event text/time.
- Preserve input/result order and append the returned background events to the existing active-event list.
- Do not change formulas, random draws, AI behavior, repository semantics, schemas, public interfaces, dependencies or persisted formats.

## Task

- [ ] Add failing focused tests for one background result, optional gene/breakthrough branches, exact callback order and stable multi-result order.
- [ ] Run the focused process test and verify import failure for the new boundary.
- [ ] Add the single-result function and loop wrapper, then replace only the inline background-result loop.
- [ ] Run focused and all species tests.
- [ ] Compare normalized moved AST or, where argument injection changes names, verify characterized callback/state equivalence; run `git diff --check` and review the current diff.
- [ ] Run one backend full suite and one frontend test/build/lint gate.
- [ ] Commit as `refactor(backend): extract background result materialization`, ordinary-push and update only PR #15.
