# M5 Active AI Batch Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move active-entry two-item batching, staggered execution and result flattening out of `process_async` without changing batch boundaries, callback arguments, concurrency settings or exception expansion.

**Architecture:** Add async `execute_active_ai_batches(...)` to `speciation_process.py`. Pass current payload builder, batch caller, response parser and staggered gather function explicitly.

**Tech Stack:** Python 3.12, asyncio and pytest.

## Constraints

- Preserve batch size 2, stable slicing, payload/call/parse order, exact staggered-gather kwargs, result-list order, success counting/logs and repetition of a batch exception once per entry in that batch.
- Do not change AI payloads, prompts, model selection, streaming, timeouts, retries, parsing rules, public interfaces, dependencies, database or persisted formats.

## Task

- [ ] Add failing async tests for empty input, odd-sized stable batches, exact callback/gather arguments, successful flattening and repeated batch exceptions.
- [ ] Run the focused process test and verify import failure for `execute_active_ai_batches`.
- [ ] Add the async function and replace only the inline active-batch block.
- [ ] Run focused, all species and existing streaming tests.
- [ ] Compare normalized moved AST, run `git diff --check` and review the current diff.
- [ ] Run one backend full suite and one frontend test/build/lint gate.
- [ ] Commit as `refactor(backend): extract active AI batch execution`, ordinary-push and update only PR #15.
