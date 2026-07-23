# M5 Differentiation Noise Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move lineage-deterministic differentiation noise out of `speciation.py` without changing seeds, direction patterns, random-call order, rounding, input identity or logs.

**Architecture:** Add `add_differentiation_noise(trait_changes, lineage_code)` to `speciation_traits.py`; retain `SpeciationService._add_differentiation_noise` as a direct compatibility delegate.

**Tech Stack:** Python 3.12, pytest, standard-library `hashlib` and `random`.

## Constraints

- Preserve MD5 seed derivation, empty-code `a` fallback, offspring-index modulo, pattern order/content, all uniform ranges, mutation order, final noise loop and logger text/category.
- Do not change formulas, gameplay, prompts, public interfaces, dependencies, database or persisted formats.

## Task

- [ ] Add failing tests for empty identity, exact A1a/A1b/empty-code output, input immutability and the service delegate.
- [ ] Run the focused file and verify import failure for the missing function.
- [ ] Move the executable method body mechanically to `speciation_traits.py`.
- [ ] Import it in `speciation.py` and replace the service body with a delegate.
- [ ] Run focused and species tests, AST equivalence, `git diff --check` and current-diff review.
- [ ] Run one backend full suite and one frontend test/build/lint gate.
- [ ] Commit as `refactor(backend): extract differentiation noise`, ordinary-push, and update only PR #15.
