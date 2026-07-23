# Backend Baseline Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clear the stable backend baseline of 14 failures and 9 setup errors, including the confirmed ancestry-index defect revealed by plugin isolation, without changing simulation rules.

**Architecture:** Treat current runtime contracts as the source of truth and update the five stale test files. Restore deterministic plugin-test state through explicit registry fixtures, repair the confirmed pre-embedding ancestry filter in one product file, align configuration and stage assertions with the GPU-only architecture, and use a narrow float32 tolerance for the three affected values.

**Tech Stack:** Python 3.12, pytest 9, Pydantic v2, NumPy/float32, existing Clade simulation and plugin registries, Vitest, TypeScript, Vite, ESLint.

## Global Constraints

- Execute in worktree `.worktrees/backend-baseline-recovery` on branch `backend-baseline-recovery`.
- The approved starting point is `329d895b56307eee32faa8d3924a602aa4ce58de`; the approved design commit is `0d30c7b59ccc3c3f4b4edfc0e8e4d0774fa51399`.
- Modify only the five test files listed in Tasks 1-4 plus `backend/app/services/embedding_plugins/ancestry_embedding.py`; no other product code is in scope.
- Do not change simulation rules, stage execution order, APIs, configuration semantics, database schema, save format, or frontend behavior.
- Do not restore `preliminary_mortality`, `migration`, or `final_mortality` to `stage_registry`; current GPU processing is represented by `tensor_ecology`.
- Do not delete, skip, broadly weaken, or hide a failing test.
- Keep backend collection at exactly 556 tests: 554 passing, 0 failing, 0 errors, and 2 expected Windows symlink skips.
- The existing 45 backend warnings are out of scope and must not increase.
- Keep frontend results at 52/52 tests, lint exit 0 with no more than the existing 162 warnings, and a successful production build.
- Reuse the Phase 2B-2 Python environment and frontend dependencies; do not install or upgrade dependencies.
- Each task is a separate commit and must pass its focused verification before the next task begins.
- The only approved product behavior change is allowing `AncestryEmbeddingPlugin.build_index()` to generate embeddings before requiring a non-empty vector; do not change the inertia formula, thresholds, or return fields.
- If a fresh-process plugin check fails, a new failure appears outside the approved files, or other product code appears necessary, stop and re-scope instead of expanding the patch.
- Do not merge to `main` or push a remote branch during this plan.

---

### Task 1: Isolate plugin tests and restore ancestry indexing

**Files:**
- Modify: `backend/app/services/embedding_plugins/tests/test_plugins.py:1-616`
- Modify: `backend/app/services/embedding_plugins/ancestry_embedding.py:75-112`

**Interfaces:**
- Consumes: `PluginRegistry.register(name: str, plugin_class: type[EmbeddingPlugin]) -> None` and `PluginRegistry.clear() -> None`.
- Produces: pytest fixture `registered_builtin_plugins()` that explicitly registers the five plugin classes used by this test file and clears all registry state after every marked test.
- Produces: `AncestryEmbeddingPlugin.build_index()` that accepts pre-embedding ancestry records, creates embeddings, writes vectors back to the cache, and returns the indexed count.

- [ ] **Step 1: Reproduce the plugin-test RED baseline**

```powershell
$Python = (Resolve-Path "..\phase-2b2-save-path-boundary\backend\.venv\Scripts\python.exe").Path
Push-Location backend
& $Python -m pytest app/services/embedding_plugins/tests/test_plugins.py -q
Pop-Location
```

Expected: `8 failed, 9 passed, 9 errors`; failures/errors follow `PluginRegistry.clear()` and cached imports.

- [ ] **Step 2: Add one explicit built-in registry fixture**

Add after `MockEmbeddingService` and before `TestPluginRegistry`:

```python
@pytest.fixture
def registered_builtin_plugins():
    from ..ancestry_embedding import AncestryEmbeddingPlugin
    from ..behavior_strategy import BehaviorStrategyPlugin
    from ..evolution_space import EvolutionSpacePlugin
    from ..food_web_embedding import FoodWebEmbeddingPlugin
    from ..registry import PluginRegistry
    from ..tile_embedding import TileBiomePlugin

    plugin_classes = {
        "ancestry": AncestryEmbeddingPlugin,
        "behavior_strategy": BehaviorStrategyPlugin,
        "evolution_space": EvolutionSpacePlugin,
        "food_web": FoodWebEmbeddingPlugin,
        "tile_biome": TileBiomePlugin,
    }

    PluginRegistry.clear()
    for name, plugin_class in plugin_classes.items():
        PluginRegistry.register(name, plugin_class)

    yield

    PluginRegistry.clear()
```

Do not use `importlib.reload()`.

- [ ] **Step 3: Make class initialization depend on the registry fixture**

Replace the first five classes' `setup_method`/`teardown_method` pairs with the corresponding autouse fixture method. The explicit `registered_builtin_plugins` parameter is required because pytest 9 runs xunit `setup_method` before a class-level `usefixtures` fixture.

```python
@pytest.fixture(autouse=True)
def setup_plugin(self, registered_builtin_plugins):
    from ..registry import PluginRegistry

    self.service = MockEmbeddingService()
    self.plugin = PluginRegistry.get_instance("behavior_strategy", self.service)
    self.plugin.initialize()
```

```python
@pytest.fixture(autouse=True)
def setup_plugin(self, registered_builtin_plugins):
    from ..registry import PluginRegistry

    self.service = MockEmbeddingService()
    self.plugin = PluginRegistry.get_instance("food_web", self.service)
    self.plugin.initialize()
```

```python
@pytest.fixture(autouse=True)
def setup_plugin(self, registered_builtin_plugins):
    from ..registry import PluginRegistry

    self.service = MockEmbeddingService()
    self.plugin = PluginRegistry.get_instance("tile_biome", self.service)
    self.plugin.initialize()
```

```python
@pytest.fixture(autouse=True)
def setup_plugin(self, registered_builtin_plugins):
    from ..registry import PluginRegistry

    self.service = MockEmbeddingService()
    self.plugin = PluginRegistry.get_instance("evolution_space", self.service)
    self.plugin.initialize()
```

```python
@pytest.fixture(autouse=True)
def setup_plugin(self, registered_builtin_plugins):
    from ..registry import PluginRegistry

    self.service = MockEmbeddingService()
    self.plugin = PluginRegistry.get_instance("ancestry", self.service)
    self.plugin.initialize()
```

Add `@pytest.mark.usefixtures("registered_builtin_plugins")` only above `TestDegradationPaths`. Delete its `setup_method` and `teardown_method`. Inside its eight test methods, delete stale `from .. import behavior_strategy`, `from .. import tile_embedding`, `from .. import food_web_embedding`, and `from .. import ancestry_embedding` statements. Keep behavior assertions unchanged.

- [ ] **Step 4: Verify isolation exposes the hidden ancestry RED state**

```powershell
$Python = (Resolve-Path "..\phase-2b2-save-path-boundary\backend\.venv\Scripts\python.exe").Path
Push-Location backend
& $Python -m pytest app/services/embedding_plugins/tests/test_plugins.py -q
Pop-Location
```

Expected: `24 passed, 2 failed`; failures are `test_predict_genetic_inertia` and `test_build_index`.

- [ ] **Step 5: Prepare genetic-inertia state through the real index path**

Replace `test_predict_genetic_inertia` with:

```python
def test_predict_genetic_inertia(self):
    species = MockSpecies()
    ctx = MockContext(all_species=[species])

    for _ in range(5):
        self.plugin.build_index(ctx)

    inertia = self.plugin.predict_genetic_inertia(species, "攻击性")
    assert inertia["inertia"] > 0.5
    assert inertia["trend_direction"] == "stable"
```

Run both ancestry tests before product code changes:

```powershell
$Python = (Resolve-Path "..\phase-2b2-save-path-boundary\backend\.venv\Scripts\python.exe").Path
Push-Location backend
& $Python -m pytest app/services/embedding_plugins/tests/test_plugins.py::TestAncestryPlugin::test_predict_genetic_inertia app/services/embedding_plugins/tests/test_plugins.py::TestAncestryPlugin::test_build_index -q
Pop-Location
```

Expected: both fail because `build_index()` rejects every empty placeholder vector before embedding.

- [ ] **Step 6: Allow ancestry records to reach embedding**

In `AncestryEmbeddingPlugin.build_index()`, replace:

```python
if ancestry and len(ancestry.vector) > 0:
```

with:

```python
if ancestry:
```

Keep the existing post-embedding assignment into `_ancestry_cache`. Do not change `_compute_ancestry_vector()`, `predict_genetic_inertia()`, the inertia formula, or vector-store behavior.

- [ ] **Step 7: Verify plugin behavior and fresh-process loading**

```powershell
$Python = (Resolve-Path "..\phase-2b2-save-path-boundary\backend\.venv\Scripts\python.exe").Path
Push-Location backend
& $Python -m pytest app/services/embedding_plugins/tests/test_plugins.py -q
& $Python -c "from app.services.embedding_plugins import PluginRegistry, load_all_plugins; expected={'ancestry','behavior_strategy','evolution_space','food_web','prompt_optimizer','tile_biome'}; loaded=set(load_all_plugins()); registered=set(PluginRegistry.list_plugins()); assert loaded == expected; assert registered == expected; print(sorted(registered))"
Pop-Location
```

Expected: `26 passed`; the fresh-process command exits 0 and prints all six built-ins. No additional permanent test is added.

- [ ] **Step 8: Review and commit Task 1**

```powershell
git diff --check
git diff -- backend/app/services/embedding_plugins/tests/test_plugins.py backend/app/services/embedding_plugins/ancestry_embedding.py
git add backend/app/services/embedding_plugins/tests/test_plugins.py backend/app/services/embedding_plugins/ancestry_embedding.py
git commit -m "fix: restore ancestry plugin indexing"
```

Expected: registry isolation, real index-path preparation, and the one-condition ancestry fix only.

---

### Task 2: Align configuration and GPU compatibility assertions

**Files:**
- Modify: `backend/app/api/tests/test_api_integration.py:864-889`
- Modify: `backend/app/api/tests/test_api_integration.py:1229-1238`

**Interfaces:**
- Consumes: `ConfigService.get_ui_config() -> UIConfig` and the GPU-only `TileBasedMortalityEngine` compatibility methods.
- Produces: tests for value-equivalent independent defaults and the documented empty-result compatibility contract.

- [ ] **Step 1: Reproduce the two stale contract failures**

```powershell
$Python = (Resolve-Path "..\phase-2b2-save-path-boundary\backend\.venv\Scripts\python.exe").Path
Push-Location backend
& $Python -m pytest app/api/tests/test_api_integration.py::TestConfigServiceContract::test_config_service_caching app/api/tests/test_api_integration.py::TestServiceConfigInjectionContract::test_tile_mortality_engine_warns_without_config -q
Pop-Location
```

Expected: 2 failures—one from object identity (`config1 is config2`) and one from requiring a legacy warning.

- [ ] **Step 2: Replace object identity with default-value semantics**

Replace `test_config_service_caching` with:

```python
def test_config_service_returns_equivalent_independent_defaults(self, config_service):
    """配置文件不存在时，每次读取都返回内容一致的独立默认配置"""
    config1 = config_service.get_ui_config()
    config2 = config_service.get_ui_config()

    assert config1.model_dump() == config2.model_dump()
    assert config1 is not config2
```

This asserts the current no-file branch of `ConfigService.get_ui_config()` and does not change file-backed caching behavior.

- [ ] **Step 3: Replace the retired warning assertion with the compatibility contract**

Replace `test_tile_mortality_engine_warns_without_config` with:

```python
def test_tile_mortality_engine_is_gpu_compatibility_placeholder(self):
    """旧入口可安全构造，但实际计算已由 TensorEcologyStage 接管"""
    from ...simulation.tile_based_mortality import TileBasedMortalityEngine

    engine = TileBasedMortalityEngine()

    assert engine.evaluate([]) == []
    assert engine.get_speciation_candidates() == {}
    assert engine.export_tensor_state() is None
```

Remove the now-unused local `logging` import and `caplog` parameter. Do not add warning behavior to `TileBasedMortalityEngine`.

- [ ] **Step 4: Run focused and complete API integration verification**

```powershell
$Python = (Resolve-Path "..\phase-2b2-save-path-boundary\backend\.venv\Scripts\python.exe").Path
Push-Location backend
& $Python -m pytest app/api/tests/test_api_integration.py::TestConfigServiceContract::test_config_service_returns_equivalent_independent_defaults app/api/tests/test_api_integration.py::TestServiceConfigInjectionContract::test_tile_mortality_engine_is_gpu_compatibility_placeholder -q
& $Python -m pytest app/api/tests/test_api_integration.py -q
Pop-Location
```

Expected: 2 focused tests pass, then all 72 tests in the file pass.

- [ ] **Step 5: Review and commit Task 2**

```powershell
git diff --check
git diff -- backend/app/api/tests/test_api_integration.py
git add backend/app/api/tests/test_api_integration.py
git commit -m "test: align config compatibility contracts"
```

Expected: only the two stale tests are changed; `config_service.py` and `tile_based_mortality.py` remain untouched.

---

### Task 3: Align simulation dependency and registry contracts

**Files:**
- Modify: `backend/app/simulation/tests/test_ecological_realism.py:523-530`
- Modify: `backend/app/simulation/tests/test_pipeline.py:260-271`

**Interfaces:**
- Consumes: `EcologicalRealismStage.get_dependency() -> StageDependency` and global `stage_registry`.
- Produces: exact dependency assertions for current display names and registry assertions for the GPU-only stage set.

- [ ] **Step 1: Reproduce the two stage-contract failures**

```powershell
$Python = (Resolve-Path "..\phase-2b2-save-path-boundary\backend\.venv\Scripts\python.exe").Path
Push-Location backend
& $Python -m pytest app/simulation/tests/test_ecological_realism.py::TestEcologicalRealismStage::test_stage_dependency app/simulation/tests/test_pipeline.py::TestStageRegistry::test_registered_stages -q
Pop-Location
```

Expected: 2 failures—old dependency identifiers and the first unregistered legacy mortality stage.

- [ ] **Step 2: Assert the complete current ecological dependency**

Replace `test_stage_dependency` with:

```python
def test_stage_dependency(self, stage):
    """测试当前阶段依赖契约"""
    dependency = stage.get_dependency()

    assert dependency.requires_stages == {"获取物种列表", "物种分层与生态位"}
    assert dependency.requires_fields == {"species_batch", "all_tiles", "all_habitats"}
    assert dependency.writes_fields == {"plugin_data"}
    assert dependency.optional_stages == {"资源计算"}
```

Do not translate these display names back to `fetch_species` or `tiering_and_niche`; `StageDependency` currently uses stage display names.

- [ ] **Step 3: Replace the three unregistered legacy IDs with `tensor_ecology`**

Replace `test_registered_stages` with:

```python
def test_registered_stages(self):
    """测试 GPU-only 架构下的核心阶段注册"""
    expected_stages = [
        "init",
        "parse_pressures",
        "map_evolution",
        "fetch_species",
        "tensor_ecology",
        "population_update",
    ]
    legacy_stages = [
        "preliminary_mortality",
        "migration",
        "final_mortality",
    ]

    for stage_name in expected_stages:
        stage_class = stage_registry.get(stage_name)
        assert stage_class is not None, f"阶段 {stage_name} 未注册"

    for stage_name in legacy_stages:
        assert stage_registry.get(stage_name) is None, f"旧阶段 {stage_name} 不应注册"
```

The old configuration fields may remain for compatibility, but these three classes must not be reintroduced into the runtime registry.

- [ ] **Step 4: Run both complete simulation test files**

```powershell
$Python = (Resolve-Path "..\phase-2b2-save-path-boundary\backend\.venv\Scripts\python.exe").Path
Push-Location backend
& $Python -m pytest app/simulation/tests/test_ecological_realism.py app/simulation/tests/test_pipeline.py -q
Pop-Location
```

Expected: 40 tests pass; existing asyncio-marker warnings remain within the accepted global warning count.

- [ ] **Step 5: Review and commit Task 3**

```powershell
git diff --check
git diff -- backend/app/simulation/tests/test_ecological_realism.py backend/app/simulation/tests/test_pipeline.py
git add backend/app/simulation/tests/test_ecological_realism.py backend/app/simulation/tests/test_pipeline.py
git commit -m "test: align simulation stage contracts"
```

Expected: only two test functions change; `stage_config.py`, `stages.py`, and `ecological_realism_stage.py` remain untouched.

---

### Task 4: Use a narrow tolerance for float32 overlap floors

**Files:**
- Modify: `backend/app/tensor/tests/test_niche_hybridization_tensor.py:75-76`
- Modify: `backend/app/tensor/tests/test_niche_hybridization_tensor.py:501`

**Interfaces:**
- Consumes: existing `pytest.approx` and float32 matrices returned by `NicheTensorCompute`.
- Produces: three assertions that accept only float32 representation error around the business floor `0.1`.

- [ ] **Step 1: Reproduce the float32 assertion failures**

```powershell
$Python = (Resolve-Path "..\phase-2b2-save-path-boundary\backend\.venv\Scripts\python.exe").Path
Push-Location backend
& $Python -m pytest app/tensor/tests/test_niche_hybridization_tensor.py::TestNicheTensorCompute::test_compute_tile_overlap_matrix_basic app/tensor/tests/test_niche_hybridization_tensor.py::TestIntegration::test_niche_and_hybridization_consistency -q
Pop-Location
```

Expected: 2 failures showing actual float32 value `0.10000000149011612` versus expected decimal `0.1`.

- [ ] **Step 2: Change only the three overlap-floor assertions**

Replace the two basic matrix assertions with:

```python
assert overlap_matrix[0, 2] == pytest.approx(0.1, abs=1e-6)
assert overlap_matrix[1, 2] == pytest.approx(0.1, abs=1e-6)
```

Replace the integration assertion with:

```python
assert niche_overlap[0, 2] == pytest.approx(0.1, abs=1e-6)
```

Do not round product output and do not change matrix symmetry, diagonal, shared-tile, or greater-than-threshold assertions.

- [ ] **Step 3: Run the complete tensor test file**

```powershell
$Python = (Resolve-Path "..\phase-2b2-save-path-boundary\backend\.venv\Scripts\python.exe").Path
Push-Location backend
& $Python -m pytest app/tensor/tests/test_niche_hybridization_tensor.py -q
Pop-Location
```

Expected: all 16 tests pass.

- [ ] **Step 4: Review and commit Task 4**

```powershell
git diff --check
git diff -- backend/app/tensor/tests/test_niche_hybridization_tensor.py
git add backend/app/tensor/tests/test_niche_hybridization_tensor.py
git commit -m "test: tolerate tensor float32 representation"
```

Expected: exactly three assertions change and no tensor implementation file is staged.

---

### Task 5: Run final backend, frontend, and scope gates

**Files:**
- Verify only; do not modify files to force a gate to pass.

**Interfaces:**
- Consumes: the four focused commits.
- Produces: evidence that the backend baseline is fully green and the unchanged frontend remains green.

- [ ] **Step 1: Run all five modified test files together**

```powershell
$Python = (Resolve-Path "..\phase-2b2-save-path-boundary\backend\.venv\Scripts\python.exe").Path
Push-Location backend
& $Python -m pytest app/services/embedding_plugins/tests/test_plugins.py app/api/tests/test_api_integration.py app/simulation/tests/test_ecological_realism.py app/simulation/tests/test_pipeline.py app/tensor/tests/test_niche_hybridization_tensor.py -q
Pop-Location
```

Expected: all 155 focused tests pass with 0 failures and 0 errors.

- [ ] **Step 2: Run complete backend collection and regression**

```powershell
$Python = (Resolve-Path "..\phase-2b2-save-path-boundary\backend\.venv\Scripts\python.exe").Path
Push-Location backend
& $Python -m pytest --collect-only -q
& $Python -m pytest -q
Pop-Location
```

Expected: collection reports exactly 556 tests; execution reports `554 passed, 2 skipped, 45 warnings`, with 0 failures and 0 errors.

- [ ] **Step 3: Re-run the fresh-process plugin guard**

```powershell
$Python = (Resolve-Path "..\phase-2b2-save-path-boundary\backend\.venv\Scripts\python.exe").Path
Push-Location backend
& $Python -c "from app.services.embedding_plugins import PluginRegistry, load_all_plugins; expected={'ancestry','behavior_strategy','evolution_space','food_web','prompt_optimizer','tile_biome'}; assert set(load_all_plugins()) == expected; assert set(PluginRegistry.list_plugins()) == expected"
Pop-Location
```

Expected: exit code 0 with no assertion error.

- [ ] **Step 4: Run unchanged frontend gates with the reused dependency binaries**

```powershell
$FrontendBin = (Resolve-Path "..\phase-2b2-save-path-boundary\frontend\node_modules\.bin").Path
Push-Location frontend
& "$FrontendBin\eslint.cmd" src --max-warnings=162
& "$FrontendBin\vitest.cmd" run
& "$FrontendBin\tsc.cmd"
& "$FrontendBin\vite.cmd" build
Pop-Location
```

Expected: ESLint exits 0 with 0 errors and no more than 162 warnings; Vitest reports 52/52 passing; TypeScript and Vite both exit 0.

- [ ] **Step 5: Verify patch scope and repository cleanliness**

```powershell
$PlanCommit = git log -1 --format=%H -- docs/superpowers/plans/2026-07-14-backend-baseline-recovery.md
git diff "$PlanCommit..HEAD" --check
git diff "$PlanCommit..HEAD" --name-only
git status --short
git log --oneline --decorate -6
```

Expected changed implementation files after the plan commit are exactly:

```text
backend/app/api/tests/test_api_integration.py
backend/app/services/embedding_plugins/ancestry_embedding.py
backend/app/services/embedding_plugins/tests/test_plugins.py
backend/app/simulation/tests/test_ecological_realism.py
backend/app/simulation/tests/test_pipeline.py
backend/app/tensor/tests/test_niche_hybridization_tensor.py
```

Expected status is clean. If any gate fails, report the exact command and output; do not claim baseline recovery or begin Phase 2C.

- [ ] **Step 6: Perform final review before handoff**

Review the four commits against `docs/superpowers/specs/2026-07-14-backend-baseline-recovery-design.md`. Confirm line by line that no product file changed, no test was removed or skipped, the three legacy registry IDs remain absent, the `0.1` tolerance is exactly `1e-6`, and all gate evidence is fresh. Only then present merge/PR/cleanup choices; do not merge or push automatically.
