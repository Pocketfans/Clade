# Phase 1 Engineering Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore a reproducible Python 3.12 environment and make frontend build, lint, and tests plus backend test collection and CI reliable without changing gameplay, saves, or simulation rules.

**Architecture:** Keep runtime behavior unchanged. Correct stale frontend contracts and fixtures, isolate Python dependencies in a 3.12 virtual environment, make tests importable as packages, and add CI commands that reproduce local verification.

**Tech Stack:** Python 3.12, FastAPI, SQLModel, pytest, Taichi, Node.js, React, TypeScript, Vite, Vitest, ESLint, GitHub Actions.

## Global Constraints

- Do not modify gameplay rules, simulation stage ordering, save formats, or database data.
- Preserve the user-owned untracked `outputs/` directory.
- Use Python `>=3.12,<3.13` for the backend.
- Run frontend installs with `npm ci` from `frontend/`.
- Every behavior correction must be demonstrated by a failing check before the fix and a passing check afterward.
- Do not weaken TypeScript strict mode or disable lint rules globally to hide failures.

---

### Task 1: Pin the backend runtime and create a reproducible environment

**Files:**
- Modify: `backend/pyproject.toml`
- Create: `.python-version`
- Create: `backend/requirements.lock`

**Interfaces:**
- Consumes: the currently installed CPython 3.12 interpreter.
- Produces: a backend environment contract limited to Python 3.12 and an exact dependency snapshot.

- [ ] **Step 1: Confirm the current metadata accepts unsupported versions**

Run: `py -3.12 -c "import tomllib, pathlib; print(tomllib.loads(pathlib.Path('backend/pyproject.toml').read_text(encoding='utf-8'))['project']['requires-python'])"`

Expected: output is `>=3.11`.

- [ ] **Step 2: Restrict the supported Python version**

Change `backend/pyproject.toml` to:

```toml
requires-python = ">=3.12,<3.13"
```

Create `.python-version` containing:

```text
3.12
```

- [ ] **Step 3: Build the isolated environment**

Run:

```powershell
py -3.12 -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install --upgrade pip
backend/.venv/Scripts/python.exe -m pip install -e "./backend[dev]"
```

Expected: all backend and development dependencies install successfully under Python 3.12.

- [ ] **Step 4: Generate and verify the lock snapshot**

Run:

```powershell
backend/.venv/Scripts/python.exe -m pip freeze --all | Sort-Object | Set-Content -Encoding UTF8 backend/requirements.lock
backend/.venv/Scripts/python.exe -c "import fastapi, sqlmodel, taichi; print('backend dependencies ok')"
```

Expected: output includes `backend dependencies ok` and `backend/requirements.lock` contains exact versions.

- [ ] **Step 5: Commit the environment contract**

```powershell
git add .python-version backend/pyproject.toml backend/requirements.lock
git commit -m "build: pin backend to Python 3.12"
```

### Task 2: Repair frontend type contracts and restore the production build

**Files:**
- Modify: `frontend/src/components/GlobalTrendsPanel/GlobalTrendsPanelNew.tsx`
- Modify: `frontend/src/components/GlobalTrendsPanel/types.ts`
- Modify: `frontend/src/components/SpeciesPanel/components/SpeciesListHeader.tsx`

**Interfaces:**
- Consumes: `BranchingEvent.parent_lineage`, `BranchingEvent.new_lineage`, `EnvironmentDataPoint.humidity`, and Recharts chart data.
- Produces: strictly typed chart and filter props accepted by TypeScript and Recharts.

- [ ] **Step 1: Reproduce the build failure**

Run: `cd frontend; npm ci; npm run build`

Expected: failure reports the eight existing errors involving `Sparklines`, branching event field names, humidity, Recharts data, and nullable status filter.

- [ ] **Step 2: Remove nonexistent Recharts exports**

Remove these unused imports from `GlobalTrendsPanelNew.tsx`:

```ts
Sparklines,
SparklinesLine,
```

- [ ] **Step 3: Use the actual branching-event contract**

Replace the recent-event fields with:

```ts
title: `新物种 ${e.new_lineage} 诞生`,
detail: `从 ${e.parent_lineage} 分化`,
```

- [ ] **Step 4: Derive humidity from the existing environment series**

Replace direct `TurnReport.global_humidity` access with:

```ts
const humidity = environmentData.at(-1)?.humidity ?? 0;
const prevHumidity = environmentData.at(-2)?.humidity ?? humidity;
```

- [ ] **Step 5: Make role chart data structurally compatible with Recharts**

Change `RoleDistribution` to:

```ts
export interface RoleDistribution {
  [key: string]: string | number;
  name: string;
  value: number;
  color: string;
}
```

- [ ] **Step 6: Prevent a null HTML select value**

Change the status select value to:

```tsx
value={filters.statusFilter ?? "all"}
```

- [ ] **Step 7: Verify and commit**

Run: `cd frontend; npm run build`

Expected: TypeScript and Vite finish with exit code 0.

```powershell
git add frontend/src/components/GlobalTrendsPanel/GlobalTrendsPanelNew.tsx frontend/src/components/GlobalTrendsPanel/types.ts frontend/src/components/SpeciesPanel/components/SpeciesListHeader.tsx
git commit -m "fix: restore frontend type-safe build"
```

### Task 3: Correct stale food-web tests and the ESLint configuration error

**Files:**
- Modify: `frontend/src/queries/useFoodWebData.test.tsx`

**Interfaces:**
- Consumes: the production `FoodWebData` contract with `nodes`, `links`, and node fields `id` and `name`.
- Produces: tests that exercise the actual API contract rather than the removed `species` and `relationships` shape.

- [ ] **Step 1: Reproduce the three failing tests and lint error**

Run:

```powershell
cd frontend
npm run test:run -- src/queries/useFoodWebData.test.tsx
npm run lint
```

Expected: three graph assertions fail with zero nodes; lint reports an unknown `react/display-name` rule.

- [ ] **Step 2: Replace the stale fixture with the production contract**

Use this fixture:

```ts
const mockFoodWebData = {
  nodes: [
    {
      id: "A",
      name: "Producer A",
      trophic_level: 1,
      population: 1000,
      diet_type: "producer",
      habitat_type: "land",
      prey_count: 0,
      predator_count: 1,
    },
    {
      id: "B",
      name: "Herbivore B",
      trophic_level: 2,
      population: 500,
      diet_type: "herbivore",
      habitat_type: "land",
      prey_count: 1,
      predator_count: 0,
    },
  ],
  links: [
    {
      source: "A",
      target: "B",
      value: 0.8,
      predator_name: "Herbivore B",
      prey_name: "Producer A",
    },
  ],
  keystone_species: ["B"],
  trophic_levels: { 1: ["A"], 2: ["B"] },
  total_species: 2,
  total_links: 1,
};
```

- [ ] **Step 3: Give the wrapper an explicit component name**

Replace the anonymous wrapper and obsolete disable comment with:

```tsx
function QueryWrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

return QueryWrapper;
```

- [ ] **Step 4: Verify and commit**

Run:

```powershell
cd frontend
npm run test:run -- src/queries/useFoodWebData.test.tsx
npm run lint
```

Expected: all six food-web tests pass and the unknown-rule lint error is gone. Remaining warnings are handled in Task 4.

```powershell
git add frontend/src/queries/useFoodWebData.test.tsx
git commit -m "test: align food web fixtures with API contract"
```

### Task 4: Remove runtime-risk lint warnings and establish a warning budget

**Files:**
- Modify: frontend files reported by `npm run lint` under `frontend/src/`
- Modify: `frontend/package.json`

**Interfaces:**
- Consumes: the existing ESLint rule set.
- Produces: corrected Hook dependencies and a lint command that prevents the existing warning count from increasing.

- [ ] **Step 1: Capture the full warning inventory**

Run: `cd frontend; npm run lint`

Expected: the current warning inventory includes unused imports/variables, explicit `any`, console output, missing hook dependencies, and Fast Refresh export warnings.

- [ ] **Step 2: Fix runtime-risk Hook warnings**

Correct the `react-hooks/exhaustive-deps` findings without introducing repeated requests, stale closures, or expensive render loops:

```text
Hook dependency warning: stabilize the callback with useCallback or add the actual dependency.
Ref cleanup warning: capture the current collection inside the effect and clean up that captured value.
Pointer event warning: avoid state dependencies when the event itself already identifies the active node.
```

Do not add file-wide disable comments and do not change warning rules to `off`. Leave cosmetic warning cleanup for a dedicated frontend refactor so Phase 1 stays outside gameplay and UI redesign scope.

- [ ] **Step 3: Make warnings block the standard lint script**

Record the current post-fix warning count in `frontend/package.json`:

```json
"lint": "eslint src --max-warnings=162"
```

- [ ] **Step 4: Verify and commit**

Run: `cd frontend; npm run lint`

Expected: `0 errors`, no `react-hooks/exhaustive-deps` warnings, no more than 162 legacy warnings, and exit code 0.

```powershell
git add frontend/package.json frontend/src
git commit -m "chore: establish frontend lint warning budget"
```

### Task 5: Restore backend test collection under Python 3.12

**Files:**
- Create: `backend/app/services/species/tests/__init__.py`
- Modify: `backend/pyproject.toml`

**Interfaces:**
- Consumes: the Task 1 Python 3.12 environment.
- Produces: importable test packages and deterministic pytest discovery rooted at `backend/app`.

- [ ] **Step 1: Reproduce collection failure**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/app --collect-only -q`

Expected: the species test uses a relative import without being inside a package.

- [ ] **Step 2: Make the species tests a package**

Create `backend/app/services/species/tests/__init__.py` containing:

```python
"""Tests for species services."""
```

- [ ] **Step 3: Add deterministic pytest configuration**

Append to `backend/pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["app"]
python_files = ["test_*.py"]
addopts = ["--strict-markers", "--strict-config"]
```

- [ ] **Step 4: Verify collection and run the suite**

Run:

```powershell
cd backend
.venv/Scripts/python.exe -m pytest --collect-only -q
.venv/Scripts/python.exe -m pytest -q
```

Expected: collection completes without import errors. Test failures caused by behavior are reported as test failures rather than collection failures.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/services/species/tests/__init__.py backend/pyproject.toml
git commit -m "test: restore backend pytest collection"
```

### Task 6: Add continuous integration and final verification

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: the commands proven in Tasks 1–5.
- Produces: repeatable frontend and backend validation on pushes and pull requests.

- [ ] **Step 1: Create the CI workflow**

Create `.github/workflows/ci.yml` with two jobs:

```yaml
name: CI

on:
  push:
  pull_request:

jobs:
  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
      - run: npm run lint
      - run: npm run test:run
      - run: npm run build

  backend:
    runs-on: windows-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: backend/requirements.lock
      - run: python -m pip install -r requirements.lock
      - run: python -m compileall -q app
      - run: python -m pytest --collect-only -q
```

The backend job intentionally validates dependency installation, syntax, and collection first; GPU execution is not claimed until a GPU runner is available.

- [ ] **Step 2: Run the full local verification**

Run:

```powershell
cd frontend
npm run lint
npm run test:run
npm run build

cd ../backend
.venv/Scripts/python.exe -m compileall -q app
.venv/Scripts/python.exe -m pytest --collect-only -q
```

Expected: every command exits 0.

- [ ] **Step 3: Confirm scope and repository cleanliness**

Run:

```powershell
git status --short
git diff --stat origin/main...HEAD
```

Expected: only Phase 1 engineering files are changed; `outputs/` remains untracked and untouched; no gameplay, save, database, or simulation-rule files changed.

- [ ] **Step 4: Commit CI**

```powershell
git add .github/workflows/ci.yml
git commit -m "ci: add frontend and backend quality gates"
```
