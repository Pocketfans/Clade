# M5 Organ Inheritance and Update Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move organ inheritance and update orchestration out of `speciation.py` without changing parent-copy behavior, input priority, callback dispatch, mutations, logs or compatibility behavior.

**Architecture:** Add one internal function to the existing `speciation_organs.py` module. It accepts the current plant predicate and the four existing service methods as callbacks so subclass overrides and already-extracted organ responsibilities remain effective. Keep `SpeciationService._inherit_and_update_organs` as the compatibility delegate.

**Tech Stack:** Python 3.12, pytest, existing `Species` model and organ helpers.

## Global Constraints

- Extract only organ inheritance and update orchestration.
- Preserve shallow per-category inheritance, default stage/progress insertion, nested-object sharing, plant-first handling, animal gradual-evolution priority, legacy fallback, mutation order, constants, logger category/text and return timing.
- Preserve calls to `_process_plant_organ_changes`, `_infer_biological_domain`, `_validate_gradual_evolution` and `_normalize_organ_evolution` through bound callbacks.
- Do not change organ rules, plant detection, validation, normalization, AI payloads, gameplay, persisted formats, models, repositories, dependencies, public interfaces or constructor arguments.
- Stop if a production file besides `speciation.py` and `speciation_organs.py` is required.

---

### Task 1: Extract organ inheritance and update orchestration

**Files:**
- Modify: `backend/app/services/species/speciation_organs.py`
- Modify: `backend/app/services/species/speciation.py:4341-4500`
- Test: `backend/app/services/species/tests/test_speciation_organs.py`

**Interface:**
- Produces: `inherit_and_update_organs(parent, ai_payload, turn_index, is_plant, process_plant_changes, infer_domain, validate_gradual, normalize_evolution) -> dict`.
- Compatibility: `SpeciationService._inherit_and_update_organs` passes `PlantTraitConfig.is_plant` and its four bound methods.

- [ ] **Step 1: Write failing characterization tests**

Import the wished-for function and add focused tests proving:

1. parent categories are copied, missing stage/progress defaults are added only to the child copy, and nested values retain the current shared identity;
2. truthy list `organ_changes` takes precedence for plants and returns the plant callback result without invoking animal callbacks;
3. gradual animal evolution invokes domain inference, validation and normalization in order, passes the original parent organ dictionary and the existing radius fallback, and applies initiate/enhance fields exactly;
4. enhance appends to the currently shared nested history list, preserving the observable parent mutation;
5. truthy non-list `organ_evolution` falls through to legacy `structural_innovations`;
6. legacy updates cap existing stages at four, add new organs at stage one, skip non-dictionaries and return inherited organs for a non-list payload;
7. the service compatibility delegate honors subclass overrides for all four service callbacks.

- [ ] **Step 2: Run the focused file and verify red**

Run:

```powershell
& 'E:\my word\https-github-com-pocketfans-clade-tree\backend\.venv\Scripts\python.exe' -m pytest app/services/species/tests/test_speciation_organs.py -q
```

Expected: collection fails because `inherit_and_update_organs` does not yet exist.

- [ ] **Step 3: Add the module orchestration function**

Move the executable body of `_inherit_and_update_organs` mechanically to `speciation_organs.py`. Replace only dependency access:

- `PlantTraitConfig.is_plant(parent)` becomes `is_plant(parent)`;
- `self._process_plant_organ_changes(...)` becomes `process_plant_changes(...)`;
- `self._infer_biological_domain(parent)` becomes `infer_domain(parent)`;
- `self._validate_gradual_evolution(...)` becomes `validate_gradual(...)`;
- `self._normalize_organ_evolution(...)` becomes `normalize_evolution(...)`.

Keep original local names, branches, constants, mutations and logging text.

- [ ] **Step 4: Keep the service compatibility delegate**

Replace the service method body with:

```python
return inherit_and_update_organs(
    parent,
    ai_payload,
    turn_index,
    PlantTraitConfig.is_plant,
    self._process_plant_organ_changes,
    self._infer_biological_domain,
    self._validate_gradual_evolution,
    self._normalize_organ_evolution,
)
```

Retain the existing method docstring.

- [ ] **Step 5: Verify focused and species regressions**

Run the focused file, then all `app/services/species/tests`. Expected: every test passes and no new warning category appears.

- [ ] **Step 6: Review and run one full quality gate**

Compare the moved executable block after normalizing callback access, run `git diff --check`, and inspect only the current diff and direct caller. Then run the backend full suite and frontend test, build and lint once. Expected: no failures; lint remains at 0 errors and no more than 162 warnings.

- [ ] **Step 7: Commit and ordinary-push**

Commit the implementation as `refactor(backend): extract organ update orchestration`, ordinary-push `phase-2c-outbound-url-security` to the Fork, and add one result comment to `Pocketfans/Clade#15`. Do not merge, force-push, create a PR, release or tag.
