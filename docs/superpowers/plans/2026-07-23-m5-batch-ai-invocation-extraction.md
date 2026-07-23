# M5 Batch AI Invocation Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move batch speciation AI invocation, streaming outcome handling and concurrent endosymbiosis injection out of `speciation.py` without changing prompt selection, task scheduling, callbacks, timeout/error markers, JSON parsing or input mutations.

**Architecture:** Add async `call_batch_ai(...)` to `speciation_ai.py`. Pass the current router, endosymbiosis attempt method, plant classifier and plant organ-context helper explicitly. Keep `SpeciationService._call_batch_ai(...)` as a compatibility delegate.

**Tech Stack:** Python 3.12, asyncio and pytest.

## Constraints

- Preserve task creation and gather ordering, exception collection, pressure defaults, prompt/capability names, payload mutation for plant batches, heartbeat callback behavior, `StreamOutcome` branches, JSON acceptance rules, fallback markers, endosymbiosis mutation/injection and logger text.
- Do not change router/model selection, stream helper, heartbeat interval, timeouts, retries, prompts, fallback formulas, public interfaces, dependencies, database or persisted formats.

## Task

- [ ] Add failing tests for animal and plant invocation, exact arguments, callback scheduling/isolation, every stream outcome and task-exception branch, endosymbiosis ordering/mutation and service delegation.
- [ ] Run `pytest -q app/services/species/tests/test_speciation_ai.py` and verify import failure for `call_batch_ai`.
- [ ] Move the method body mechanically, replacing only service/global dependency access with explicit parameters.
- [ ] Replace the service body with an async delegate passing current runtime dependencies.
- [ ] Run focused, species and existing streaming regression tests.
- [ ] Compare AST after normalizing dependency access, run `git diff --check` and review the current diff.
- [ ] Run one backend full suite and one frontend test/build/lint gate.
- [ ] Commit as `refactor(backend): extract batch AI invocation`, ordinary-push and update only PR #15.
