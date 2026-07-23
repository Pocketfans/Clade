# M5 Trade-off Penalty Extraction Plan

**Goal:** Move automatic trade-off penalty calculation and merging out of `speciation.py` without changing calculator calls, identity-preserving returns, exception fallback, logs or merged values.

**Files:** Modify `speciation_traits.py`, `speciation.py`, and `test_speciation_traits.py`.

1. Add tests for empty input, missing calculator, no gains, calculator failure, empty penalties, merge behavior and the service delegate.
2. Verify red because `apply_tradeoff_penalties` is missing.
3. Move the method body mechanically; accept the current calculator as an argument.
4. Keep `_apply_tradeoff_penalties` as a compatibility delegate.
5. Run focused/species tests, normalized AST comparison, one full backend/frontend gate and current-diff review.
6. Commit as `refactor(backend): extract tradeoff penalties`, ordinary-push and update only PR #15.

Do not change formulas, calculator construction, exception behavior, public interfaces, dependencies, gameplay, database or persisted formats.
