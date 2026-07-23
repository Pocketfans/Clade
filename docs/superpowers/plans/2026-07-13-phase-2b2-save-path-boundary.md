# Phase 2B-2 Save Name and Path Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reject unsafe save names and guarantee that every save operation resolves to a directory contained within the configured save root, without renaming or breaking valid historical saves.

**Architecture:** Put name validation and resolved-path containment in one dependency-free security module. Pydantic request models validate user input at the API boundary, while `SaveManager` repeats validation and containment before file access as defense in depth. Historical directories are located by their valid `metadata.json` display name rather than trusting user-supplied folder paths.

**Tech Stack:** Python 3.12, pathlib, Pydantic v2, FastAPI, pytest, existing `SaveManager` JSON/gzip formats.

## Global Constraints

- Execute after reviewed Phase 2B-1, using its head as the new isolated-worktree base.
- Save names contain 1-50 Unicode code points.
- Allowed characters are Unicode letters/numbers, ordinary spaces, `_`, and `-`.
- Reject `.`, `..`, slash, backslash, absolute paths, control characters, trailing spaces/dots, and Windows device names including `CON`, `PRN`, `AUX`, `NUL`, `COM1`-`COM9`, and `LPT1`-`LPT9`.
- Do not silently sanitize invalid user input into a different name.
- Resolve every candidate directory and require it to remain inside the resolved `saves_dir`.
- Valid historical `save_<timestamp>_<suffix>` directories remain unchanged and are found through `metadata.json.save_name`.
- Do not change database schema, game-state JSON/gzip structure, simulation rules, or Phase 2C URL policy.
- Invalid input returns a safe `422` or `400` without including filesystem paths in logs or responses.
- Preserve the accepted test baseline: no more than `14 failed, 9 errors` in the complete backend suite.

---

### Task 1: Create the single save-name and path policy

**Files:**
- Create: `backend/app/security/save_paths.py`
- Create: `backend/app/security/tests/test_save_paths.py`

**Interfaces:**
- Produces: `validate_save_name(value: str) -> str`.
- Produces: `resolve_save_directory(saves_dir: str | Path, candidate: str | Path) -> Path`.
- Produces: `SavePathError`, `InvalidSaveNameError`, and `SavePathBoundaryError`.

- [ ] **Step 1: Write the failing policy tests**

Create `backend/app/security/tests/test_save_paths.py`:

```python
from pathlib import Path

import pytest

from ..save_paths import (
    InvalidSaveNameError,
    SavePathBoundaryError,
    resolve_save_directory,
    validate_save_name,
)


@pytest.mark.parametrize(
    "name",
    [
        "原初大陆",
        "历史 存档-1",
        "Save_2026",
        "Évolution 3",
        "１２３",
    ],
)
def test_valid_save_names_are_preserved_exactly(name: str) -> None:
    assert validate_save_name(name) == name


@pytest.mark.parametrize(
    "name",
    [
        "",
        "a" * 51,
        ".",
        "..",
        "../outside",
        r"..\outside",
        r"C:\outside",
        "/absolute",
        "name.json",
        "line\nbreak",
        "trailing ",
        "trailing.",
        "emoji😀",
    ],
)
def test_invalid_names_are_rejected_without_sanitizing(name: str) -> None:
    with pytest.raises(InvalidSaveNameError):
        validate_save_name(name)


@pytest.mark.parametrize(
    "name",
    ["CON", "con", "PRN", "AUX", "NUL", "COM1", "COM9", "LPT1", "LPT9"],
)
def test_windows_device_names_are_rejected_case_insensitively(name: str) -> None:
    with pytest.raises(InvalidSaveNameError, match="设备名"):
        validate_save_name(name)


def test_resolved_child_directory_is_allowed(tmp_path: Path) -> None:
    root = tmp_path / "saves"
    child = root / "save_20260713_valid"
    assert resolve_save_directory(root, child) == child.resolve()


def test_resolved_parent_escape_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "saves"
    outside = root / ".." / "outside"
    with pytest.raises(SavePathBoundaryError, match="超出允许范围"):
        resolve_save_directory(root, outside)
```

- [ ] **Step 2: Run the test and verify RED**

```powershell
cd backend
.venv\Scripts\python.exe -m pytest app/security/tests/test_save_paths.py -q
```

Expected: collection fails because `save_paths.py` does not exist.

- [ ] **Step 3: Implement exact validation and containment**

Create `backend/app/security/save_paths.py`:

```python
from __future__ import annotations

from pathlib import Path


WINDOWS_DEVICE_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


class SavePathError(ValueError):
    pass


class InvalidSaveNameError(SavePathError):
    pass


class SavePathBoundaryError(SavePathError):
    pass


def validate_save_name(value: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 50:
        raise InvalidSaveNameError("存档名称长度必须为 1–50 个字符")
    if value.endswith((" ", ".")):
        raise InvalidSaveNameError("存档名称不能以空格或点结尾")
    if value.upper() in WINDOWS_DEVICE_NAMES:
        raise InvalidSaveNameError("存档名称不能使用 Windows 设备名")
    if not all(character.isalnum() or character in {" ", "_", "-"} for character in value):
        raise InvalidSaveNameError("存档名称只能包含字母、数字、空格、下划线和连字符")
    return value


def resolve_save_directory(
    saves_dir: str | Path,
    candidate: str | Path,
) -> Path:
    root = Path(saves_dir).resolve()
    resolved = Path(candidate).resolve()
    if resolved == root or root not in resolved.parents:
        raise SavePathBoundaryError("存档目录超出允许范围")
    return resolved
```

- [ ] **Step 4: Run policy tests and static checks**

```powershell
.venv\Scripts\python.exe -m pytest app/security/tests/test_save_paths.py -q
.venv\Scripts\python.exe -m compileall -q app/security/save_paths.py
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 1**

```powershell
git add backend/app/security/save_paths.py backend/app/security/tests/test_save_paths.py
git commit -m "security: define save name and path policy"
```

---

### Task 2: Validate save names at every API input boundary

**Files:**
- Modify: `backend/app/schemas/requests.py:80-100`
- Modify: `backend/app/api/simulation.py:435-805`
- Create: `backend/app/api/tests/test_save_path_api.py`

**Interfaces:**
- Consumes: `validate_save_name` and `SavePathError` from Task 1.
- Produces: validated `CreateSaveRequest`, `SaveGameRequest`, `LoadGameRequest`, and DELETE path behavior.

- [ ] **Step 1: Write failing real-route tests**

Create `backend/app/api/tests/test_save_path_api.py`:

```python
import pytest
from fastapi.testclient import TestClient

from ...main import app


@pytest.fixture
def client(mock_container, mock_session):
    app.state.container = mock_container
    app.state.session = mock_session
    yield TestClient(app)
    del app.state.container
    del app.state.session


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "/api/saves/create", {"save_name": "../outside", "scenario": "原初大陆"}),
        ("post", "/api/saves/save", {"save_name": r"..\outside"}),
        ("post", "/api/saves/load", {"save_name": "NUL"}),
        ("delete", "/api/saves/CON", None),
    ],
)
def test_save_routes_reject_unsafe_names_before_manager_access(
    client: TestClient,
    mock_container,
    method: str,
    path: str,
    body: dict | None,
) -> None:
    response = client.request(method.upper(), path, json=body)
    assert response.status_code in {400, 422}
    assert response.json().get("detail")
    mock_container.save_manager.create_save.assert_not_called()
    mock_container.save_manager.save_game.assert_not_called()
    mock_container.save_manager.load_game.assert_not_called()
    mock_container.save_manager.delete_save.assert_not_called()


def test_unicode_save_name_reaches_the_manager_unchanged(
    client: TestClient,
    mock_container,
) -> None:
    mock_container.simulation_engine.turn_counter = 4
    response = client.post("/api/saves/save", json={"save_name": "历史 存档-1"})
    assert response.status_code == 200
    mock_container.save_manager.save_game.assert_called_once_with(
        "历史 存档-1",
        turn_index=4,
    )
```

Import `mock_container` and `mock_session` fixtures from the existing API conftest; do not duplicate partial container mocks.

- [ ] **Step 2: Run the route tests and verify RED**

```powershell
.venv\Scripts\python.exe -m pytest app/api/tests/test_save_path_api.py -q
```

Expected: traversal/device-name requests reach route logic or become `500` instead of a safe `400/422`.

- [ ] **Step 3: Share the validator across request models**

Update imports:

```python
from pydantic import BaseModel, Field, field_validator

from ..security.save_paths import validate_save_name
```

Add a reusable base model and inherit it:

```python
class SaveNameRequest(BaseModel):
    save_name: str = Field(min_length=1, max_length=50)

    @field_validator("save_name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return validate_save_name(value)


class CreateSaveRequest(SaveNameRequest):
    scenario: str = Field(default="原初大陆")
    species_prompts: list[str] | None = None
    map_seed: int | None = None


class SaveGameRequest(SaveNameRequest):
    pass


class LoadGameRequest(SaveNameRequest):
    pass
```

- [ ] **Step 4: Map manager boundary errors to safe client errors**

Import `SavePathError` and `validate_save_name` in `simulation.py`. Validate DELETE before calling the manager:

```python
@router.delete("/saves/{save_name}")
def delete_save(
    save_name: str,
    container: "ServiceContainer" = Depends(get_container),
) -> dict:
    try:
        validated_name = validate_save_name(save_name)
        deleted = container.save_manager.delete_save(validated_name)
        return {"success": True, "deleted": validated_name, "found": deleted}
    except SavePathError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except Exception:
        logger.exception("[存档API错误] 删除存档失败")
        raise HTTPException(status_code=500, detail="删除存档失败") from None
```

In create/save/load routes, insert `except SavePathError` before the generic exception and return the same safe `422`. Do not include the submitted name or filesystem path in generic error responses.

- [ ] **Step 5: Run route and schema tests**

```powershell
.venv\Scripts\python.exe -m pytest app/api/tests/test_save_path_api.py app/api/tests/test_api_integration.py -q
```

Expected: new tests pass; only the two accepted historical integration failures may remain.

- [ ] **Step 6: Commit Task 2**

```powershell
git add backend/app/schemas/requests.py backend/app/api/simulation.py backend/app/api/tests/test_save_path_api.py
git commit -m "security: validate save names at API boundaries"
```

---

### Task 3: Contain every SaveManager directory access

**Files:**
- Modify: `backend/app/services/system/save_manager.py:30-145`
- Modify: `backend/app/services/system/save_manager.py:457-850`
- Modify: `backend/app/services/system/save_manager.py:972-1055`
- Create: `backend/app/services/system/tests/__init__.py`
- Create: `backend/app/services/system/tests/test_save_manager_paths.py`

**Interfaces:**
- Consumes: `validate_save_name`, `resolve_save_directory`, and `SavePathError`.
- Produces: `SaveManager._iter_save_dirs()` and contained metadata-based lookup.

- [ ] **Step 1: Write failing manager boundary tests**

Create `backend/app/services/system/tests/test_save_manager_paths.py`:

```python
import json
from pathlib import Path

import pytest

from ....security.save_paths import InvalidSaveNameError
from ..save_manager import SaveManager


def write_legacy_save(root: Path, folder_name: str, display_name: str) -> Path:
    save_dir = root / folder_name
    save_dir.mkdir(parents=True)
    (save_dir / "metadata.json").write_text(
        json.dumps(
            {
                "save_name": display_name,
                "turn_index": 0,
                "species_count": 0,
                "scenario": "原初大陆",
                "last_saved": "2026-07-13T00:00:00",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (save_dir / "game_state.json").write_text(
        json.dumps({"turn_index": 0}),
        encoding="utf-8",
    )
    return save_dir


def test_valid_legacy_folder_is_found_by_metadata_name_without_rename(tmp_path: Path) -> None:
    root = tmp_path / "saves"
    legacy = write_legacy_save(
        root,
        "save_20200101_000000_old-folder",
        "历史 存档-1",
    )
    manager = SaveManager(root)

    assert manager.get_save_dir("历史 存档-1") == legacy.resolve()
    assert legacy.exists()
    assert manager.list_saves()[0]["name"] == "历史 存档-1"


@pytest.mark.parametrize(
    "method",
    [
        "create_save",
        "save_game",
        "load_game",
        "delete_save",
        "get_save_dir",
        "check_save_integrity",
        "migrate_save_to_compressed",
    ],
)
def test_public_entrypoints_reject_traversal_before_file_access(
    tmp_path: Path,
    method: str,
) -> None:
    manager = SaveManager(tmp_path / "saves")
    call = getattr(manager, method)
    with pytest.raises(InvalidSaveNameError):
        if method == "save_game":
            call("../outside", turn_index=0)
        else:
            call("../outside")


def test_resolved_outside_candidate_is_never_listed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = SaveManager(tmp_path / "saves")
    outside = tmp_path / "outside"
    outside.mkdir()
    original_glob = Path.glob

    def fake_glob(path: Path, pattern: str):
        if path == manager.saves_dir and pattern == "save_*":
            return iter([outside])
        return original_glob(path, pattern)

    monkeypatch.setattr(Path, "glob", fake_glob)
    assert list(manager._iter_save_dirs()) == []
```

- [ ] **Step 2: Run manager tests and verify RED**

```powershell
.venv\Scripts\python.exe -m pytest app/services/system/tests/test_save_manager_paths.py -q
```

Expected: traversal is sanitized/used by current methods, direct lookup can escape, and `_iter_save_dirs` does not exist.

- [ ] **Step 3: Resolve the root and centralize directory iteration**

In `SaveManager.__init__`:

```python
self.saves_dir = Path(saves_dir).resolve()
self.saves_dir.mkdir(parents=True, exist_ok=True)
```

Add:

```python
def _iter_save_dirs(self):
    for candidate in sorted(self.saves_dir.glob("save_*")):
        try:
            save_dir = resolve_save_directory(self.saves_dir, candidate)
        except SavePathBoundaryError:
            logger.warning("[存档管理器] 忽略超出范围的存档目录")
            continue
        if save_dir.is_dir():
            yield save_dir
```

Replace every direct `self.saves_dir.glob("save_*")` loop in `list_saves` and `get_storage_stats` with `self._iter_save_dirs()`.

- [ ] **Step 4: Validate before logging and resolve created directories**

At the first line of every public name-taking method, normalize with:

```python
save_name = validate_save_name(save_name)
```

This applies to `create_save`, `save_game`, `load_game`, `delete_save`, `get_save_dir`, `check_save_integrity`, and `migrate_save_to_compressed`.

Create directories only after containment:

```python
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
folder_suffix = save_name[:20]
save_dir = resolve_save_directory(
    self.saves_dir,
    self.saves_dir / f"save_{timestamp}_{folder_suffix}",
)
save_dir.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 5: Replace direct user-folder lookup with metadata lookup**

Implement `_find_save_dir` as:

```python
def _find_save_dir(self, save_name: str) -> Path | None:
    validated_name = validate_save_name(save_name)
    for save_dir in self._iter_save_dirs():
        metadata_path = save_dir / "metadata.json"
        if not metadata_path.exists():
            continue
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if metadata.get("save_name") == validated_name:
            return save_dir
    return None
```

Do not retain `self.saves_dir / save_name` as a direct user-controlled folder lookup.

- [ ] **Step 6: Run manager and API tests**

```powershell
.venv\Scripts\python.exe -m pytest app/services/system/tests/test_save_manager_paths.py app/api/tests/test_save_path_api.py -q
```

Expected: every new test passes; the historical folder keeps its original name.

- [ ] **Step 7: Commit Task 3**

```powershell
git add backend/app/services/system/save_manager.py backend/app/services/system/tests
git commit -m "security: contain save manager file access"
```

---

### Task 4: Preserve autosave and historical-save behavior under the 50-character rule

**Files:**
- Modify: `backend/app/api/simulation.py:160-235`
- Modify: `backend/app/api/tests/test_save_path_api.py`
- Modify: `backend/app/services/system/tests/test_save_manager_paths.py`

**Interfaces:**
- Produces: `build_autosave_name(base_name: str, slot: int) -> str` and `autosave_prefixes(base_name: str) -> tuple[str, ...]`.
- Consumes: strict `SaveManager` policy from Task 3.

- [ ] **Step 1: Write failing autosave compatibility tests**

Add to `test_save_path_api.py`:

```python
from ..simulation import autosave_prefixes, build_autosave_name


def test_short_autosave_name_keeps_the_existing_format() -> None:
    assert build_autosave_name("原初大陆", 2) == "原初大陆_autosave_2"


def test_long_autosave_name_is_valid_bounded_and_deterministic() -> None:
    base = "甲" * 50
    first = build_autosave_name(base, 123)
    second = build_autosave_name(base, 123)
    assert first == second
    assert len(first) <= 50
    assert first.endswith("_autosave_123")
    assert first in {
        prefix + "123"
        for prefix in autosave_prefixes(base)
    }


def test_long_bases_with_the_same_prefix_do_not_share_autosave_names() -> None:
    left = build_autosave_name("甲" * 49 + "乙", 1)
    right = build_autosave_name("甲" * 49 + "丙", 1)
    assert left != right
```

- [ ] **Step 2: Run the autosave tests and verify RED**

```powershell
.venv\Scripts\python.exe -m pytest app/api/tests/test_save_path_api.py -q -k autosave_name
```

Expected: helper imports fail because the bounded naming functions do not exist.

- [ ] **Step 3: Implement bounded names with a collision-resistant tag**

Add `hashlib` and these helpers to `simulation.py`:

```python
def autosave_prefixes(base_name: str) -> tuple[str, ...]:
    validated = validate_save_name(base_name)
    legacy = f"{validated}_autosave_"
    digest = hashlib.sha256(validated.encode("utf-8")).hexdigest()[:8]
    bounded_base = validated[:20]
    bounded = f"{bounded_base}_{digest}_autosave_"
    return (legacy,) if len(legacy) + 1 <= 50 else (bounded, legacy)


def build_autosave_name(base_name: str, slot: int) -> str:
    if slot < 1:
        raise ValueError("自动存档编号必须大于 0")
    slot_text = str(slot)
    for prefix in autosave_prefixes(base_name):
        candidate = prefix + slot_text
        if len(candidate) <= 50:
            return validate_save_name(candidate)
    raise InvalidSaveNameError("自动存档名称超过长度限制")
```

Use `build_autosave_name(save_name, counter // config.autosave_interval)` in `_perform_autosave`. In `_cleanup_old_autosaves`, match any prefix returned by `autosave_prefixes(base_save_name)` so existing short-format autosaves remain discoverable.

- [ ] **Step 4: Add a legal historical save regression**

Extend the legacy manager test to assert that `check_save_integrity("历史 存档-1")` and `migrate_save_to_compressed("历史 存档-1")` resolve the existing directory without renaming it. Build the minimal expected `metadata.json` and `game_state.json` in `write_legacy_save`; assert the migration creates `game_state.json.gz` in that same directory.

- [ ] **Step 5: Run save-boundary tests**

```powershell
.venv\Scripts\python.exe -m pytest app/security/tests/test_save_paths.py app/services/system/tests/test_save_manager_paths.py app/api/tests/test_save_path_api.py -q
```

Expected: all new policy, manager, route, autosave, and historical-save tests pass.

- [ ] **Step 6: Commit Task 4**

```powershell
git add backend/app/api/simulation.py backend/app/api/tests/test_save_path_api.py backend/app/services/system/tests/test_save_manager_paths.py
git commit -m "fix: preserve safe autosave and legacy lookup"
```

---

### Task 5: Complete Phase 2B-2 regression verification

**Files:**
- Modify only if verification finds a Phase 2B-2 regression in files listed above.
- Create report: `.superpowers/sdd/phase-2b2-verification.md`

**Interfaces:**
- Consumes: Tasks 1-4.
- Produces: a verified save-name and resolved-path boundary.

- [ ] **Step 1: Run all save-boundary and API tests**

```powershell
cd backend
.venv\Scripts\python.exe -m pytest app/security/tests/test_save_paths.py app/services/system/tests/test_save_manager_paths.py app/api/tests/test_save_path_api.py app/api/tests/test_api_integration.py -q
.venv\Scripts\python.exe -m pytest --collect-only -q
```

Expected: all Phase 2B-2 tests pass; only the two accepted integration failures may remain; collection exceeds the preceding Phase 2B-1 count.

- [ ] **Step 2: Run complete backend regression**

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Expected: no save-boundary failure and no more than `14 failed, 9 errors`.

- [ ] **Step 3: Run frontend gates even though no frontend runtime file changed**

```powershell
cd ..\frontend
npm run lint
npm run test:run
npm run build
```

Expected: lint exits 0 within the accepted warning budget, every test passes, and build exits 0.

- [ ] **Step 4: Scan path operations and scope**

```powershell
cd ..
rg -n "saves_dir / save_name|rmtree\(|glob\(\"save_\*\"\)|resolve_save_directory|validate_save_name" backend/app/services/system/save_manager.py backend/app/api/simulation.py backend/app/schemas/requests.py backend/app/security/save_paths.py
git diff --check
git status --short
```

Expected: no user-controlled direct path join remains; deletion uses a directory returned by contained metadata lookup; diff check is clean.

- [ ] **Step 5: Write the verification report**

Record exact commands, exit codes, test totals, baseline comparison, valid historical-save evidence, invalid-name matrix, path-containment evidence, changed files, and final worktree status in `.superpowers/sdd/phase-2b2-verification.md`. Do not create an empty commit.

Phase 2B is complete only when Phase 2B-1 and Phase 2B-2 have each passed independent review and their combined branch has passed final regression verification.
