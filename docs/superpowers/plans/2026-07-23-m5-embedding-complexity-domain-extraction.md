# M5 Embedding Complexity and Domain Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move embedding-based complexity inference and biological-domain selection out of `speciation.py` without changing lazy service lookup, cache ownership, similarity scoring, fallback or compatibility behavior.

**Architecture:** Add two internal functions to the existing `speciation_organs.py` module. The domain selector accepts the current embedding and rule methods as callbacks so subclass overrides remain active; the embedding function accepts the current service, references and three cache callbacks so base-class initialization timing and instance/subclass cache lookup stay unchanged. Existing underscore-prefixed service methods remain compatibility delegates.

**Tech Stack:** Python 3.12, pytest, NumPy already used by the project, existing `EmbeddingService` and `Species` model.

## Global Constraints

- Extract only embedding-based complexity inference and biological-domain selection.
- Preserve Router lazy lookup, `_embedding_service` instance caching, `_COMPLEXITY_REFERENCES`, `SpeciationService._complexity_embeddings` ownership, post-initialization `self._complexity_embeddings` lookup, `require_real=False`, species text options, normalization, strict `>` tie handling, default level 1, zero-vector handling, logger category/text and broad exception fallback to `None`.
- Preserve embedding-first selection, rule fallback only on `None`, and the exact `complexity_N` result format.
- Do not extract organ inheritance/update orchestration, move the class reference descriptions or cache, change embedding/network policy, add error handling, modify gameplay, models, repositories, dependencies, public interfaces or constructor arguments.
- Stop if a production file besides `speciation.py` and `speciation_organs.py` is required.

---

### Task 1: Extract embedding complexity inference and domain selection

**Files:**
- Modify: `backend/app/services/species/speciation_organs.py`
- Modify: `backend/app/services/species/speciation.py:4908-4990`
- Test: `backend/app/services/species/tests/test_speciation_organs.py`

**Interfaces:**
- Produces: `infer_biological_domain(species, infer_by_embedding, infer_by_rules) -> str`.
- Produces: `infer_complexity_by_embedding(species, embedding_service, complexity_references, get_cached_embeddings, set_cached_embeddings, get_effective_embeddings) -> int | None`.
- Compatibility: `SpeciationService._infer_biological_domain` passes its two existing methods; `_infer_complexity_by_embedding` keeps lazy Router lookup and passes callbacks for base-class cache read/write plus effective instance/subclass cache read.

- [ ] **Step 1: Write failing characterization tests**

Import the wished-for functions and add a small real fake embedding implementation:

```python
from ..speciation_organs import (
    infer_biological_domain,
    infer_complexity_by_embedding,
)


COMPLEXITY_REFERENCES = {
    0: "level zero",
    1: "level one",
    2: "level two",
}


class _EmbeddingVectors:
    def __init__(self, reference_vectors, species_vector, *, fail_species=False):
        self.reference_vectors = reference_vectors
        self.species_vector = species_vector
        self.fail_species = fail_species
        self.calls = []

    def embed(self, texts, require_real=False):
        self.calls.append((list(texts), require_real))
        if len(texts) > 1:
            return self.reference_vectors
        if self.fail_species:
            raise RuntimeError("species embedding failed")
        return [self.species_vector]


def _embedding_species():
    return SimpleNamespace(
        common_name="test species",
        description="test description",
        abstract_traits={"speed": 8.0, "armor": 2.0},
    )


def _infer_with_cache(service, state, *, effective=None):
    return infer_complexity_by_embedding(
        _embedding_species(),
        service,
        COMPLEXITY_REFERENCES,
        lambda: state["base"],
        lambda value: state.__setitem__("base", value),
        lambda: state["base"] if effective is None else effective,
    )
```

Add focused tests proving the current behavior:

```python
def test_domain_selection_prefers_embedding_and_skips_rules() -> None:
    calls = []
    assert infer_biological_domain(
        _embedding_species(),
        lambda species: calls.append(("embedding", species)) or 4,
        lambda species: calls.append(("rules", species)) or 2,
    ) == "complexity_4"
    assert [name for name, _ in calls] == ["embedding"]


def test_domain_selection_falls_back_to_rules_only_for_none() -> None:
    species = _embedding_species()
    assert infer_biological_domain(
        species,
        lambda current: None,
        lambda current: 2,
    ) == "complexity_2"


def test_embedding_complexity_initializes_cache_and_selects_best_level() -> None:
    service = _EmbeddingVectors(
        [[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]],
        [0.0, 2.0],
    )
    state = {"base": None}
    assert _infer_with_cache(service, state) == 1
    assert state["base"] == {
        0: [1.0, 0.0],
        1: [0.0, 1.0],
        2: [-1.0, 0.0],
    }
    assert service.calls[0] == (list(COMPLEXITY_REFERENCES.values()), False)
    assert service.calls[1][1] is False


def test_embedding_complexity_uses_effective_cache_without_reembedding_references() -> None:
    service = _EmbeddingVectors([], [0.0, 1.0])
    state = {"base": {0: [1.0, 0.0]}}
    effective = {4: [0.0, 1.0]}
    assert _infer_with_cache(service, state, effective=effective) == 4
    assert len(service.calls) == 1


def test_embedding_complexity_returns_none_for_zero_species_vector() -> None:
    service = _EmbeddingVectors([], [0.0, 0.0])
    state = {"base": {0: [1.0, 0.0]}}
    assert _infer_with_cache(service, state) is None


def test_embedding_complexity_skips_zero_references_and_keeps_default_level() -> None:
    service = _EmbeddingVectors([], [1.0, 0.0])
    state = {"base": {0: [0.0, 0.0], 5: [0.0, 0.0]}}
    assert _infer_with_cache(service, state) == 1


def test_embedding_complexity_keeps_first_level_on_similarity_tie() -> None:
    service = _EmbeddingVectors([], [1.0, 0.0])
    state = {"base": {3: [1.0, 0.0], 4: [2.0, 0.0]}}
    assert _infer_with_cache(service, state) == 3


def test_embedding_complexity_preserves_initialized_cache_when_species_embed_fails() -> None:
    service = _EmbeddingVectors(
        [[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]],
        [0.0, 1.0],
        fail_species=True,
    )
    state = {"base": None}
    assert _infer_with_cache(service, state) is None
    assert state["base"] is not None


def test_service_embedding_delegate_lazily_uses_router_and_class_cache(monkeypatch) -> None:
    service_vectors = _EmbeddingVectors(
        [[1.0, 0.0] for _ in SpeciationService._COMPLEXITY_REFERENCES],
        [1.0, 0.0],
    )
    service = object.__new__(SpeciationService)
    service.router = SimpleNamespace(embedding_service=service_vectors)
    monkeypatch.setattr(SpeciationService, "_complexity_embeddings", None)
    assert service._infer_complexity_by_embedding(_embedding_species()) == 0
    assert service._embedding_service is service_vectors
    assert SpeciationService._complexity_embeddings is not None


def test_service_embedding_delegate_returns_none_without_available_service() -> None:
    service = object.__new__(SpeciationService)
    service.router = SimpleNamespace()
    assert service._infer_complexity_by_embedding(_embedding_species()) is None


def test_service_domain_delegate_preserves_method_overrides() -> None:
    calls = []

    class _OverriddenService(SpeciationService):
        def _infer_complexity_by_embedding(self, species):
            calls.append("embedding")
            return None

        def _infer_complexity_by_rules(self, species):
            calls.append("rules")
            return 5

    service = object.__new__(_OverriddenService)
    assert service._infer_biological_domain(_embedding_species()) == "complexity_5"
    assert calls == ["embedding", "rules"]
```

- [ ] **Step 2: Run the focused file and verify red**

Run:

```powershell
& 'E:\my word\https-github-com-pocketfans-clade-tree\backend\.venv\Scripts\python.exe' -m pytest app/services/species/tests/test_speciation_organs.py -q
```

Expected: collection fails because the two new module functions do not yet exist.

- [ ] **Step 3: Add the domain selector**

Add this function to `speciation_organs.py`:

```python
def infer_biological_domain(
    species: Species,
    infer_by_embedding: Callable[[Species], int | None],
    infer_by_rules: Callable[[Species], int],
) -> str:
    complexity_level = infer_by_embedding(species)
    if complexity_level is None:
        complexity_level = infer_by_rules(species)
    return f"complexity_{complexity_level}"
```

Retain the full original method docstring on both the module function and compatibility method so runtime introspection remains unchanged.

- [ ] **Step 4: Add embedding complexity inference**

Move the current `try` body mechanically into:

```python
def infer_complexity_by_embedding(
    species: Species,
    embedding_service: Any,
    complexity_references: dict[int, str],
    get_cached_embeddings: Callable[[], dict[int, list[float]] | None],
    set_cached_embeddings: Callable[[dict[int, list[float]]], None],
    get_effective_embeddings: Callable[[], dict[int, list[float]]],
) -> int | None:
    try:
        if get_cached_embeddings() is None:
            reference_descriptions = list(complexity_references.values())
            reference_vectors = embedding_service.embed(
                reference_descriptions, require_real=False
            )
            set_cached_embeddings(
                {level: vector for level, vector in enumerate(reference_vectors)}
            )

        from ..system.embedding import EmbeddingService

        species_text = EmbeddingService.build_species_text(
            species, include_traits=True, include_names=False
        )
        species_vector = embedding_service.embed(
            [species_text], require_real=False
        )[0]

        import numpy as np

        species_array = np.array(species_vector)
        species_norm = np.linalg.norm(species_array)
        if species_norm == 0:
            return None
        species_array = species_array / species_norm
        best_level = 1
        best_similarity = -1
        for level, reference_vector in get_effective_embeddings().items():
            reference_array = np.array(reference_vector)
            reference_norm = np.linalg.norm(reference_array)
            if reference_norm == 0:
                continue
            reference_array = reference_array / reference_norm
            similarity = float(np.dot(species_array, reference_array))
            if similarity > best_similarity:
                best_similarity = similarity
                best_level = level
        logger.debug(
            f"[复杂度推断-embedding] {species.common_name}: "
            f"等级{best_level} (相似度{best_similarity:.3f})"
        )
        return best_level
    except Exception as error:
        logger.warning(f"[复杂度推断] Embedding推断失败: {error}")
        return None
```

When applying the move, retain original local names, import placement, loop order and log text so only dependency access changes.

- [ ] **Step 5: Keep both service compatibility delegates**

Replace the domain method body with:

```python
return infer_biological_domain(
    species,
    self._infer_complexity_by_embedding,
    self._infer_complexity_by_rules,
)
```

Keep the existing lazy embedding-service lookup in `_infer_complexity_by_embedding`, then delegate:

```python
return infer_complexity_by_embedding(
    species,
    self._embedding_service,
    self._COMPLEXITY_REFERENCES,
    lambda: SpeciationService._complexity_embeddings,
    lambda embeddings: setattr(
        SpeciationService, "_complexity_embeddings", embeddings
    ),
    lambda: self._complexity_embeddings,
)
```

- [ ] **Step 6: Verify focused and species regressions**

Run the focused file, then all `app/services/species/tests`. Expected: every test passes and no new warning category appears.

- [ ] **Step 7: Review and run one full quality gate**

Compare moved executable blocks after normalizing the dependency accesses, run `git diff --check`, and inspect only the current diff and direct callers. Then run the backend full suite and frontend test, build and lint once. Expected: no failures; lint remains at 0 errors and no more than 162 warnings.

- [ ] **Step 8: Commit and ordinary-push**

Commit the implementation as `refactor(backend): extract embedding complexity`, ordinary-push `phase-2c-outbound-url-security` to the Fork, and add one result comment to `Pocketfans/Clade#15`. Do not merge, force-push, create a PR, release or tag.
