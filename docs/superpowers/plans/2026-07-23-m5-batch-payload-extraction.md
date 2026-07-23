# M5 Batch Payload Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move batch speciation payload and prompt construction out of `speciation.py` without changing text, defaults, dependency calls, naming state, payload order or compatibility behavior.

**Architecture:** Add `build_batch_payload(...)` to `speciation_ai.py`. Pass plant helpers, service-bound hint/summary methods, the naming generator and a trade-off-ratio callback explicitly. Keep `SpeciationService._build_batch_payload` as a compatibility delegate.

**Tech Stack:** Python 3.12 and pytest.

## Constraints

- Preserve all string templates and whitespace, defaults, list/dict iteration order, plant trait filtering, all-parent competition input, AI-direction first-five slice, in-function time config lookup, naming seed formula, naming-generator mutation, summary call counts, payload insertion order and nested `getattr` trade-off fallback.
- Do not change prompts, AI calls, parsing, fallback, retries, timeouts, formulas, public interfaces, dependencies, database or persisted formats.

## Task

- [ ] Add failing tests for animal defaults, summaries, time/naming state, plant context, competition parent list, AI hints, empty entries, trade-off ratio and service override delegation.
- [ ] Run `pytest -q app/services/species/tests/test_speciation_ai.py` and verify import failure for `build_batch_payload`.
- [ ] Move the method body mechanically, replacing only dependency access with explicit parameters.
- [ ] Replace the service body with a delegate passing current globals, bound methods, naming generator and a late trade-off-ratio callback.
- [ ] Run focused and all species tests.
- [ ] Compare AST after normalizing dependency access, run `git diff --check` and review current diff.
- [ ] Run one backend full suite and one frontend test/build/lint gate.
- [ ] Commit as `refactor(backend): extract batch payload construction`, ordinary-push and update only PR #15.
