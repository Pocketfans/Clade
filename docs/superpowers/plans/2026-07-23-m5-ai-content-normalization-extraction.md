# M5 AI Content Normalization Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move AI content normalization out of `speciation.py` without changing identity, in-place mutation, conversion, aggregation or compatibility behavior.

**Architecture:** Create `speciation_ai.py` with `normalize_ai_content(ai_content: Any) -> Any`; keep `SpeciationService._normalize_ai_content` as a direct delegate.

**Tech Stack:** Python 3.12 and pytest.

## Constraints

- Preserve non-dict identity, truthy `trait_changes` short-circuit, innovation order, name deduplication, `float(str(delta).replace("+", ""))`, caught exception types, sum order, conditional field insertion and input identity.
- Do not change prompts, parsing, fallback, network, timeouts, retries, formulas, interfaces, dependencies, database or persisted formats.

## Task

- [ ] Add failing tests for non-dict identity, existing trait changes, mixed innovations/gains, invalid values, duplicate names, existing key innovations, input mutation and service delegation.
- [ ] Run the focused file and verify import failure for `normalize_ai_content`.
- [ ] Create `speciation_ai.py` and move the method body mechanically.
- [ ] Import the function in `speciation.py` and replace the service body with a delegate.
- [ ] Run focused and all species tests.
- [ ] Compare normalized AST, run `git diff --check` and review the current diff.
- [ ] Run one backend full suite and one frontend test/build/lint gate.
- [ ] Commit as `refactor(backend): extract ai content normalization`, ordinary-push and update only PR #15.
