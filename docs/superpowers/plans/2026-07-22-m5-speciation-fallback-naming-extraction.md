# M5 Speciation Fallback Naming Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Project rules disable subagents for this single-file responsibility.

**Goal:** Extract the two deterministic fallback-name generators from `SpeciationService` without changing any output or call site.

**Architecture:** Add two pure functions in `speciation_naming.py` and retain the existing private service methods as compatibility delegates.

**Tech Stack:** Python 3.12, pytest, standard-library `hashlib`.

## Constraints

- Modify only the new naming module, `speciation.py`, and one focused test file.
- Add no dependency or public API.
- Change no keyword order, hash input, suffix length, generated text, repository behavior, AI behavior, gameplay rule, or formula.
- Use one red-green cycle, at most one repair cycle, and at most two review rounds.
- Create one independent implementation commit, ordinary-push it to the current Fork branch, and update only PR #15.

## Task: Extract deterministic fallback naming

**Files:**

- Create: `backend/app/services/species/speciation_naming.py`
- Modify: `backend/app/services/species/speciation.py:5043-5134`
- Test: `backend/app/services/species/tests/test_speciation_naming.py`

### Step 1: Add the failing boundary and output-contract tests

Create tests that import `fallback_latin_name` and `fallback_common_name`, then verify:

```python
from hashlib import md5

from ..speciation import SpeciationService
from ..speciation_naming import fallback_common_name, fallback_latin_name


def test_latin_fallback_preserves_keyword_order_and_genus() -> None:
    assert fallback_latin_name("Aqua primus", {"key_innovations": ["快速游泳"]}) == "Aqua natans"
    assert fallback_latin_name("Aqua primus", {"key_innovations": ["深海适应"]}) == "Aqua profundus"
    assert fallback_latin_name("单名", {"key_innovations": ["耐寒"]}) == "Species cryophilus"


def test_latin_fallback_preserves_hash_input() -> None:
    innovations = ["未知特征"]
    suffix = md5(str(innovations).encode()).hexdigest()[:6]
    assert fallback_latin_name("Aqua primus", {"key_innovations": innovations}) == f"Aqua sp{suffix}"


def test_common_fallback_preserves_feature_and_taxon_rules() -> None:
    assert fallback_common_name("远古海虫", {"key_innovations": ["多鞭毛"]}) == "多鞭海虫"
    assert fallback_common_name("远古海虫", {"key_innovations": ["坚固外壳"]}) == "坚固海虫"


def test_empty_common_fallback_preserves_hash_input() -> None:
    content = {"key_innovations": []}
    suffix = md5(str(content).encode()).hexdigest()[:2]
    assert fallback_common_name("虫", content) == f"型{suffix}生物"


def test_speciation_service_keeps_fallback_name_methods() -> None:
    service = object.__new__(SpeciationService)
    content = {"key_innovations": ["透明"]}
    assert service._fallback_latin_name("Aqua primus", content) == fallback_latin_name("Aqua primus", content)
    assert service._fallback_common_name("远古海虫", content) == fallback_common_name("远古海虫", content)
```

Run the focused test. Expected RED: `ModuleNotFoundError` for `app.services.species.speciation_naming`.

### Step 2: Add the pure module

Move the existing two method bodies verbatim into these functions:

```python
def fallback_latin_name(parent_latin: str, ai_content: dict) -> str:
    import hashlib

    genus = parent_latin.split()[0] if " " in parent_latin else "Species"
    innovations = ai_content.get("key_innovations", [])
    if innovations:
        innovation = innovations[0].lower()
        if "鞭毛" in innovation or "游" in innovation:
            epithet = "natans"
        elif "深" in innovation or "底" in innovation:
            epithet = "profundus"
        elif "快" in innovation or "速" in innovation:
            epithet = "velox"
        elif "慢" in innovation or "缓" in innovation:
            epithet = "lentus"
        elif "大" in innovation or "巨" in innovation:
            epithet = "magnus"
        elif "小" in innovation or "微" in innovation:
            epithet = "minutus"
        elif "透明" in innovation:
            epithet = "hyalinus"
        elif "耐盐" in innovation or "盐" in innovation:
            epithet = "salinus"
        elif "耐热" in innovation or "热" in innovation:
            epithet = "thermophilus"
        elif "耐寒" in innovation or "冷" in innovation:
            epithet = "cryophilus"
        else:
            hash_suffix = hashlib.md5(str(innovations).encode()).hexdigest()[:6]
            epithet = f"sp{hash_suffix}"
    else:
        hash_suffix = hashlib.md5(str(ai_content).encode()).hexdigest()[:6]
        epithet = f"sp{hash_suffix}"
    return f"{genus} {epithet}"


def fallback_common_name(parent_common: str, ai_content: dict) -> str:
    import hashlib

    if len(parent_common) >= 2:
        taxon = (
            parent_common[-2:]
            if parent_common[-1] in "虫藻菌类贝鱼"
            else parent_common[-3:]
        )
    else:
        taxon = "生物"

    innovations = ai_content.get("key_innovations", [])
    if innovations:
        innovation = innovations[0]
        if "鞭毛" in innovation:
            if "多" in innovation or "4" in innovation or "增" in innovation:
                feature = "多鞭"
            elif "长" in innovation:
                feature = "长鞭"
            else:
                feature = "异鞭"
        elif "游" in innovation or "速" in innovation:
            if "快" in innovation or "提升" in innovation:
                feature = "快游"
            else:
                feature = "慢游"
        elif "深" in innovation or "底" in innovation:
            feature = "深水"
        elif "浅" in innovation or "表" in innovation:
            feature = "浅水"
        elif "耐盐" in innovation or "盐" in innovation:
            feature = "耐盐"
        elif "透明" in innovation:
            feature = "透明"
        elif "大" in innovation or "巨" in innovation:
            feature = "巨型"
        elif "小" in innovation or "微" in innovation:
            feature = "微型"
        elif "滤食" in innovation:
            feature = "滤食"
        elif "夜" in innovation:
            feature = "夜行"
        else:
            words = [c for c in innovation if "\u4e00" <= c <= "\u9fff"]
            feature = "".join(words[:2]) if len(words) >= 2 else "变异"
    else:
        hash_suffix = hashlib.md5(str(ai_content).encode()).hexdigest()[:2]
        feature = f"型{hash_suffix}"

    return f"{feature}{taxon}"
```

Keep `hashlib` usage, branch order, string slicing, character filtering, and formatting identical.

### Step 3: Preserve compatibility methods

Import the two pure functions into `speciation.py` and replace only the two existing method bodies:

```python
def _fallback_latin_name(self, parent_latin: str, ai_content: dict) -> str:
    return fallback_latin_name(parent_latin, ai_content)


def _fallback_common_name(self, parent_common: str, ai_content: dict) -> str:
    return fallback_common_name(parent_common, ai_content)
```

### Step 4: Verify focused behavior

Run:

```powershell
& 'E:\my word\https-github-com-pocketfans-clade-tree\backend\.venv\Scripts\python.exe' -m pytest backend/app/services/species/tests/test_speciation_naming.py backend/app/services/species/tests/test_speciation_import.py backend/app/services/species/tests/test_speciation_repository.py backend/app/services/species/tests/test_speciation_streaming.py -q
```

Expected: all tests pass.

### Step 5: Review and final quality gate

Confirm only the three planned code/test files changed, compatibility names remain, `git diff --check` passes, and generated-name rules are unchanged. Then run backend full pytest once, frontend full Vitest once, frontend build once, and quiet lint once; every command must exit 0.

### Step 6: Commit and publish

```powershell
git add -- backend/app/services/species/speciation.py backend/app/services/species/speciation_naming.py backend/app/services/species/tests/test_speciation_naming.py
git commit -m "refactor(backend): extract speciation fallback naming"
git push fork HEAD:phase-2c-outbound-url-security
```

Comment on PR #15 with exact focused/full results. Confirm local HEAD, Fork branch, and PR head match and the worktree is clean.
