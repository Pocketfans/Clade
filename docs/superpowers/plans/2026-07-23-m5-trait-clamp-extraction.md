# M5 Trait Clamp Extraction Plan

**Goal:** Move deterministic trait clamping out of `speciation.py` without changing limits, proportional reduction, global scaling, specialization selection, rounding or compatibility behavior.

**Files:** Modify `speciation_traits.py`, `speciation.py`, and `test_speciation_traits.py`.

1. Characterize specialized caps, parent-plus-five/total caps, proportional reduction, global scaling, stable top-two specialization, rounding and the service delegate.
2. Verify red because `clamp_traits_to_limit` is missing.
3. Move the method body mechanically and accept `get_attribute_limits` as a callback.
4. Keep `_clamp_traits_to_limit` as the compatibility delegate.
5. Run focused/species tests, normalized AST comparison, one full backend/frontend gate and current-diff review.
6. Commit as `refactor(backend): extract trait clamping`, ordinary-push and update only PR #15.

Do not change formulas, thresholds, gameplay, interfaces, dependencies, database or persisted formats.
