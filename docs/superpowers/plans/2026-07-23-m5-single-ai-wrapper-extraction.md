# M5 Single AI Wrapper Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move the single-species heartbeat AI wrapper out of `speciation.py` without changing invocation arguments, callback compatibility, task scheduling, exception handling, logs or returned content.

**Architecture:** Add async `call_ai_wrapper(...)` to `speciation_ai.py`, passing the current router explicitly and retaining the lazy heartbeat-helper import. Keep `SpeciationService._call_ai_wrapper(...)` as a compatibility delegate.

**Tech Stack:** Python 3.12, asyncio and pytest.

## Constraints

- Preserve three-argument callback first, TypeError fallback to one argument, coroutine detection and `create_task`, callback-error isolation, exact invocation kwargs, timeout/generic exception results, response type check and content extraction.
- Do not change router/model selection, heartbeat interval, task name, streaming, retries, timeout ownership, prompts, public interfaces, dependencies, database or persisted formats.

## Task

- [ ] Add failing tests for no-callback invocation, three- and one-argument callbacks, coroutine scheduling, callback errors, timeout/generic errors, content extraction and service delegation.
- [ ] Run `pytest -q app/services/species/tests/test_speciation_ai.py` and verify import failure for `call_ai_wrapper`.
- [ ] Move the method body mechanically, replacing only `self.router` with an explicit router parameter.
- [ ] Replace the service body with an async delegate passing its current router.
- [ ] Run focused and all species tests.
- [ ] Compare AST after normalizing router access, run `git diff --check` and review the current diff.
- [ ] Run one backend full suite and one frontend test/build/lint gate.
- [ ] Commit as `refactor(backend): extract single AI wrapper`, ordinary-push and update only PR #15.
