# M5 Coordinator and Line Guards Plan

**Goal:** Finish the `process_async` split by moving its remaining candidate-loop orchestration into the existing internal process module and make the agreed size limits executable tests.

**Architecture:** Keep `SpeciationService.process_async` as the public coordinator. Move the stable-order per-candidate loop to one bounded internal coordinator that calls the already-tested phase helpers and receives repositories, settings, callbacks and mutable state explicitly. Preserve every early return, random call and write order. Add source-structure tests for the M5 limits instead of relying on manual counting.

**Scope**

- Modify `backend/app/services/species/speciation.py`.
- Modify `backend/app/services/species/speciation_process.py`.
- Add `backend/app/services/species/tests/test_speciation_structure.py`.
- Do not change gameplay formulas, AI behavior, repository semantics, public APIs, schemas, dependencies or unrelated files.

**Steps**

1. Add line-count and function-size tests and verify the current `speciation.py` limit fails.
2. Extract the remaining candidate-loop orchestration without changing its statement order.
3. Compare the moved control flow mechanically and run the focused structure/process tests.
4. Run all species tests, review the current diff at most twice, then run one backend full suite and one frontend test/build/lint gate.
5. Create one implementation commit, ordinary-push the current Fork branch and update only upstream PR #15.

**Stop conditions**

- Stop if the extraction needs a new public abstraction or constructor dependency.
- Stop if it changes randomness, formulas, repository ordering, AI calls or persisted data.
- Stop if any new non-coordinator responsibility exceeds 250 lines or either agreed file/function gate cannot be met without unrelated refactoring.
