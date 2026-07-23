# M5 Organ Complexity Rules Extraction Plan

**Goal:** Move deterministic biological-complexity inference and complexity-constraint lookup out of `speciation.py` without changing results or errors.

**Architecture:** Extend the existing internal `speciation_organs.py` module. Keep both `SpeciationService` methods as compatibility delegates so all existing callers continue to work.

**Tech Stack:** Python 3.12, pytest, existing `Species` model.

## Constraints

- Extract only rule-based complexity inference and basic constraint lookup.
- Preserve keyword order, prokaryote/eukaryote conflict handling, active-organ counting, body-length thresholds, returned dictionaries and malformed-level exceptions.
- Do not extract embedding inference, biological-domain selection or gradual-evolution validation in this batch.
- Do not change models, repositories, formulas, dependencies, public interfaces or constructor arguments.
- Stop if a production file besides `speciation.py` and `speciation_organs.py` is required.

## Files

- Modify `backend/app/services/species/speciation_organs.py`: add the two deterministic functions.
- Modify `backend/app/services/species/speciation.py`: retain methods as delegates.
- Modify `backend/app/services/species/tests/test_speciation_organs.py`: add characterization and compatibility coverage.

## Tasks

- [ ] Add focused tests for keyword priority, prokaryote conflicts, active-organ counts, body-length boundaries and both constraint families.
- [ ] Run the focused tests and record the expected import failure before implementation.
- [ ] Mechanically move both implementations and replace the service methods with delegates.
- [ ] Run focused tests and all species-service tests.
- [ ] Compare the moved function bodies, inspect only the current diff and run one full backend/frontend quality gate.
- [ ] Create one independent commit, ordinary-push the current Fork branch and update only PR #15.

## Acceptance Commands

```powershell
& 'E:\my word\https-github-com-pocketfans-clade-tree\backend\.venv\Scripts\python.exe' -m pytest app/services/species/tests/test_speciation_organs.py -q
& 'E:\my word\https-github-com-pocketfans-clade-tree\backend\.venv\Scripts\python.exe' -m pytest app/services/species/tests -q
```

At the batch boundary, run the backend full test suite and the frontend test, build and lint commands once. Lint must remain at 0 errors and no more than the existing 162-warning ceiling.
