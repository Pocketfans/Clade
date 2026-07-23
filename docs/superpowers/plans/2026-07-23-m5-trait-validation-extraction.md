# M5 Trait Validation Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move deterministic trait-change validation out of `speciation.py` without changing limits, failure priority, messages, logging or compatibility behavior.

**Architecture:** Add `speciation_traits.py` for the fifth M5 responsibility. Its first internal function accepts the current attribute-limit method as a callback. Keep `SpeciationService._validate_trait_changes` as a compatibility delegate.

## Constraints

- Extract only `_validate_trait_changes`.
- Preserve `get_attribute_limits` call timing, dictionary iteration order, all numeric thresholds, strict comparisons, first specialized-trait selection, messages and warning text/category.
- Do not extract trade-off penalties, enforcement, differentiation noise or coordinator code.
- Do not change formulas, prompts, gameplay, models, repositories, dependencies, public interfaces or constructor arguments.
- Stop if another production file besides `speciation.py` and the new `speciation_traits.py` is required.

## Task: Extract deterministic trait validation

**Files:**
- Create: `backend/app/services/species/speciation_traits.py`
- Modify: `backend/app/services/species/speciation.py:4289-4340`
- Create: `backend/app/services/species/tests/test_speciation_traits.py`

1. Write characterization tests for net-gain rejection, total limit, first specialized trait, base-limit count, no-cost gain, exact boundaries, a compensating decrease and the service callback.
2. Run the new test file and verify collection fails because `validate_trait_changes` is missing.
3. Move the method body mechanically, replacing only `self.trophic_calculator.get_attribute_limits(...)` with `get_attribute_limits(...)`.
4. Keep the service method and full docstring, delegating with its bound limit callback.
5. Run the focused file and all species tests.
6. Compare normalized AST bodies, inspect the current diff, then run the backend/frontend quality gates once.
7. Commit as `refactor(backend): extract trait validation`, ordinary-push the current Fork branch and update only PR #15.
