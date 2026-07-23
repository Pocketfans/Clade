# M5 Speciation Lineage Code Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Project rules disable subagents for this single responsibility.

**Goal:** Extract both deterministic lineage-code generators from `SpeciationService` without changing any output or call site.

**Architecture:** Add a dependency-free `speciation_lineage.py` module. Keep the existing service methods as compatibility delegates.

**Tech Stack:** Python 3.12, pytest.

## Global Constraints

- Modify only the new lineage module, `speciation.py`, and one focused test file.
- Add no dependency or public API.
- Change no code format, collision behavior, ordering, persisted identifier, database behavior, gameplay, formula, or AI behavior.
- Preserve the current more-than-26 behavior; do not repair it in this refactor.
- Use one red-green cycle, at most one repair cycle, and at most two review rounds.
- Create one independent implementation commit, ordinary-push it to the current Fork branch, and update only PR #15.

---

### Task 1: Extract lineage-code generation

**Files:**

- Create: `backend/app/services/species/speciation_lineage.py`
- Modify: `backend/app/services/species/speciation.py:2655-2700`
- Create: `backend/app/services/species/tests/test_speciation_lineage.py`

**Interfaces:**

- Produces: `next_lineage_code(parent_code: str, existing_codes: set[str]) -> str`.
- Produces: `generate_multiple_lineage_codes(parent_code: str, existing_codes: set[str], num_offspring: int) -> list[str]`.
- Preserves both underscore-prefixed `SpeciationService` compatibility methods.

- [ ] **Step 1: Write the failing output-contract tests**

Create `test_speciation_lineage.py`:

```python
from ..speciation import SpeciationService
from ..speciation_lineage import (
    generate_multiple_lineage_codes,
    next_lineage_code,
)


def test_next_lineage_code_preserves_numbered_suffix_search() -> None:
    existing = {"A1a1", "A1a2"}

    assert next_lineage_code("A1", existing) == "A1a3"
    assert existing == {"A1a1", "A1a2"}


def test_multiple_lineage_codes_preserve_order_and_collisions() -> None:
    assert generate_multiple_lineage_codes("A1", set(), 3) == [
        "A1a",
        "A1b",
        "A1c",
    ]
    existing = {"A1a", "A1a1", "A1b"}
    assert generate_multiple_lineage_codes("A1", existing, 3) == [
        "A1a2",
        "A1b1",
        "A1c",
    ]
    assert existing == {"A1a", "A1a1", "A1b"}


def test_multiple_lineage_codes_preserve_count_boundaries() -> None:
    assert generate_multiple_lineage_codes("A1", set(), 0) == []
    codes = generate_multiple_lineage_codes("A1", set(), 27)
    assert codes[25] == "A1z"
    assert codes[26] == "A1a"


def test_speciation_service_keeps_lineage_code_methods() -> None:
    service = object.__new__(SpeciationService)
    existing = {"A1a"}

    assert service._next_lineage_code("A1", existing) == next_lineage_code(
        "A1", existing
    )
    assert service._generate_multiple_lineage_codes(
        "A1", existing, 2
    ) == generate_multiple_lineage_codes("A1", existing, 2)
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
& 'E:\my word\https-github-com-pocketfans-clade-tree\backend\.venv\Scripts\python.exe' -m pytest backend/app/services/species/tests/test_speciation_lineage.py -q
```

Expected: collection fails with `ModuleNotFoundError` because `speciation_lineage.py` does not exist.

- [ ] **Step 3: Add the pure module**

Create `speciation_lineage.py`:

```python
from __future__ import annotations


def next_lineage_code(parent_code: str, existing_codes: set[str]) -> str:
    base = f"{parent_code}a"
    index = 1
    new_code = f"{base}{index}"
    while new_code in existing_codes:
        index += 1
        new_code = f"{base}{index}"
    return new_code


def generate_multiple_lineage_codes(
    parent_code: str,
    existing_codes: set[str],
    num_offspring: int,
) -> list[str]:
    letters = "abcdefghijklmnopqrstuvwxyz"
    codes = []

    for index in range(num_offspring):
        if index < len(letters):
            letter = letters[index]
            new_code = f"{parent_code}{letter}"
        else:
            repeat_index = index // len(letters) - 1
            letter_index = index % len(letters)
            letter = letters[letter_index]
            repeat = "#" * repeat_index
            new_code = f"{parent_code}{repeat}{letter}"

        if new_code in existing_codes:
            suffix = 1
            while f"{new_code}{suffix}" in existing_codes:
                suffix += 1
            new_code = f"{new_code}{suffix}"

        codes.append(new_code)

    return codes
```

- [ ] **Step 4: Preserve compatibility methods**

Import both functions in `speciation.py` and replace only the old method bodies:

```python
def _next_lineage_code(self, parent_code: str, existing_codes: set[str]) -> str:
    return next_lineage_code(parent_code, existing_codes)


def _generate_multiple_lineage_codes(
    self, parent_code: str, existing_codes: set[str], num_offspring: int
) -> list[str]:
    return generate_multiple_lineage_codes(
        parent_code, existing_codes, num_offspring
    )
```

- [ ] **Step 5: Run focused and direct regression tests**

Run:

```powershell
& 'E:\my word\https-github-com-pocketfans-clade-tree\backend\.venv\Scripts\python.exe' -m pytest backend/app/services/species/tests/test_speciation_lineage.py backend/app/services/species/tests/test_speciation_import.py backend/app/services/species/tests/test_speciation_repository.py backend/app/services/species/tests/test_speciation_streaming.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Review and final quality gate**

Verify only the three planned files changed, `git diff --check` passes, compatibility methods remain, and every branch matches the original. Then run backend full pytest once, frontend full Vitest once, frontend build once, and quiet lint once; every command must exit 0.

- [ ] **Step 7: Commit and publish**

```powershell
git add -- backend/app/services/species/speciation_lineage.py backend/app/services/species/speciation.py backend/app/services/species/tests/test_speciation_lineage.py
git commit -m "refactor(backend): extract speciation lineage codes"
git push fork HEAD:phase-2c-outbound-url-security
```

Comment on PR #15 with exact results. Confirm local HEAD, Fork branch, and PR head match and the worktree is clean.
