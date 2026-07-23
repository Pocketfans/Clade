# M5 Active Result Materialization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move active AI result preparation, species persistence and branching-event creation out of `process_async` without changing skip, retry, fallback, mutation, randomness or repository order.

**Architecture:** The existing 231-line loop would exceed the 250-line responsibility limit once dependencies are explicit. Split it into bounded `prepare_active_result(...)` and `materialize_active_result(...)` functions plus a thin stable-order loop. The coordinator passes existing callbacks, mutable state, repositories, randomness, clocks and event factories explicitly.

**Tech Stack:** Python 3.12 and pytest.

## Constraints

- Preserve stale-turn skips; exception/non-dict/missing-field retry and fallback thresholds; deferred-queue timing; normalization count and fallback arguments.
- Preserve rule validation, child creation, the existing duplicated offspring-count increments, fallback-enhancement queueing and every random/callback/repository operation in exact order.
- Preserve genetic discovery/inheritance, AI gene activation/new-gene handling, breakthrough, plant milestone, tensor viability branches and conditional upserts.
- Preserve event/reason fallback text, stable zip truncation and partial event appends if a later result fails.
- Keep every new non-coordinator function at or below 250 lines.
- Do not fix suspicious legacy behavior, change formulas, public interfaces, schemas, dependencies, AI prompts/network behavior or persisted formats.

## Task

- [ ] Add failing focused tests for stale/deferred/fallback preparation and normalized successful content.
- [ ] Add failing focused tests for materialization callback/state order, optional branches and thin-loop partial appends.
- [ ] Verify the new boundaries fail because they are absent.
- [ ] Implement the bounded helpers and replace only the active-result loop.
- [ ] Run focused and all species tests; compare normalized moved ASTs/characterized state.
- [ ] Review the current diff at most twice and enforce line-count gates.
- [ ] Run one backend full suite and one frontend test/build/lint gate.
- [ ] Commit as `refactor(backend): extract active result materialization`, ordinary-push and update only PR #15.
