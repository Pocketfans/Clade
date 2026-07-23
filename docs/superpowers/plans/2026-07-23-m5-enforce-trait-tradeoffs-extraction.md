# M5 Enforced Trait Trade-offs Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move deterministic enforced trait trade-offs out of `speciation.py` without changing seeds, random-call order, thresholds, candidate ordering, return identity, logs or compatibility behavior.

**Architecture:** Add `enforce_trait_tradeoffs(current_traits, proposed_changes, lineage_code)` to the existing `speciation_traits.py`. Keep `SpeciationService._enforce_trait_tradeoffs` as a thin compatibility delegate. Retain function-local `random` and `hashlib` imports so initialization and call order remain unchanged.

**Tech Stack:** Python 3.12, pytest, standard-library `hashlib` and `random`.

## Global Constraints

- Preserve MD5 seed derivation, 30% sufficient-decrease check, 40% required decrease, 50% gain reduction cap, candidate threshold `> 3.0`, stable dictionary order, shuffle/randint/uniform order, rounding and logger text/category.
- Do not extract differentiation noise or change formulas, gameplay, public interfaces, dependencies, database or persisted formats.

---

### Task 1: Extract enforced trait trade-offs

**Files:**
- Modify: `backend/app/services/species/speciation_traits.py`
- Modify: `backend/app/services/species/speciation.py`
- Modify: `backend/app/services/species/tests/test_speciation_traits.py`

**Interface:** `enforce_trait_tradeoffs(current_traits: dict[str, float], proposed_changes: dict[str, float], lineage_code: str) -> dict[str, float]`.

- [ ] Add failing tests for empty identity, sufficient-decrease identity, no-candidate reduction, exact deterministic A1a/A1b candidate outputs and the service delegate.
- [ ] Run `pytest -q app/services/species/tests/test_speciation_traits.py`; expect import failure for the missing function.
- [ ] Move the executable body mechanically to `speciation_traits.py`.
- [ ] Import the function in `speciation.py` and replace the service body with a direct delegate.
- [ ] Run focused tests and all `app/services/species/tests`.
- [ ] Normalize and compare AST bodies, run `git diff --check`, and review only this diff.
- [ ] Run one backend full suite and one frontend test/build/lint gate.
- [ ] Commit as `refactor(backend): extract enforced trait tradeoffs`, ordinary-push the current Fork branch, and add one comment to PR #15.
