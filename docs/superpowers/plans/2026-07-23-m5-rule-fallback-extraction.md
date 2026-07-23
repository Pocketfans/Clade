# M5 Rule Fallback Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move rule-based fallback species content construction out of `speciation.py` without changing formulas, deterministic randomness, names, output shapes, copies, logs or service override behavior.

**Architecture:** Add `generate_rule_based_fallback(...)` to `speciation_ai.py`. Pass the current rule preprocessing method and background-name generator explicitly. Keep `SpeciationService._generate_rule_based_fallback(...)` as a compatibility delegate.

**Tech Stack:** Python 3.12 and pytest.

## Constraints

- Preserve the MD5 seed, random draw order, suffix/name generation, rule preprocessing arguments, default environment object, budget and organ branches, morphology formulas, description ordering, copied prey collections, private marker fields and logger text.
- Do not change rule formulas, gameplay values, AI invocation/parsing, retries, timeouts, prompts, public interfaces, dependencies, database or persisted formats.

## Task

- [ ] Add failing tests for deterministic default output, constrained budgets and organ evolution, empty/default collections, callback order and service override delegation.
- [ ] Run `pytest -q app/services/species/tests/test_speciation_ai.py` and verify import failure for `generate_rule_based_fallback`.
- [ ] Move the method body mechanically, replacing only rule preprocessing and background-name access with explicit callbacks.
- [ ] Replace the service body with a delegate passing current bound methods.
- [ ] Run focused and all species tests.
- [ ] Compare AST after normalizing dependency access, run `git diff --check` and review the current diff.
- [ ] Run one backend full suite and one frontend test/build/lint gate.
- [ ] Commit as `refactor(backend): extract rule fallback construction`, ordinary-push and update only PR #15.
