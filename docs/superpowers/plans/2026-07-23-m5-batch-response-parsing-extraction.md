# M5 Batch Response Parsing Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move batch speciation response matching and parsing out of `speciation.py` without changing response mutation, endosymbiosis priority, fallback placement, matching order, field validation or result markers.

**Architecture:** Add `parse_batch_results(...)` to `speciation_ai.py`. Pass the current rule-fallback generator explicitly so service overrides remain effective. Keep `SpeciationService._parse_batch_results(...)` as a compatibility delegate.

**Tech Stack:** Python 3.12 and pytest.

## Constraints

- Preserve the in-place `_endo_overrides` pop, `_use_fallback` behavior, existing invalid-type and invalid-results branches, request-id integer/string mapping, positional fallback, truthiness checks, required fields, entry order, default pressure and `_is_fallback` mutation.
- Do not change AI invocation, streaming, timeouts, retries, prompts, fallback formulas, public interfaces, dependencies, database or persisted formats.

## Task

- [ ] Add failing tests for endosymbiosis priority and mutation, full fallback branches, invalid result arrays, request-id and positional matching, missing fields, callback arguments and service override delegation.
- [ ] Run `pytest -q app/services/species/tests/test_speciation_ai.py` and verify import failure for `parse_batch_results`.
- [ ] Move the method body mechanically, replacing only fallback generation with an explicit callback.
- [ ] Replace the service body with a delegate passing its current bound fallback method.
- [ ] Run focused and all species tests.
- [ ] Compare AST after normalizing dependency access, run `git diff --check` and review the current diff.
- [ ] Run one backend full suite and one frontend test/build/lint gate.
- [ ] Commit as `refactor(backend): extract batch response parsing`, ordinary-push and update only PR #15.
