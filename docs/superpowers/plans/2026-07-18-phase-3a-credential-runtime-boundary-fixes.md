# Phase 3A Credential and Runtime Boundary Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate credential tuple mixing, clear removed runtime providers immediately, and validate remote Embedding endpoints before cache lookup.

**Architecture:** Treat provider endpoint, API key, and provider type as one credential tuple whenever stored credentials or runtime overrides are used. Rebuild runtime provider state from a clean snapshot on every UI configuration refresh. Extract a DNS-free outbound base-URL canonicalizer from the existing policy so Embedding can reject invalid syntax before deriving cache identity while the runtime client remains responsible for the single DNS resolution.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, pytest, existing `OutboundURLPolicy`, `ModelRouter`, and `EmbeddingService`.

## Global Constraints

- Preserve the existing public UI configuration shape and preserve/replace/explicit-clear save semantics.
- Keep `ALLOW_LOCAL_AI_ENDPOINTS` behavior and administrator-token protection unchanged.
- Do not change database schema, save format, simulation rules, retry policy, timeout policy, or frontend behavior.
- Do not perform real network requests in tests and never print or persist a credential sentinel.
- Keep environment `AI_BASE_URL` and `AI_API_KEY` as the fallback tuple when no UI default provider exists.
- Follow red-green-refactor: every production behavior change must be preceded by a test that fails for the expected reason.

---

### Task 1: Bind stored probe credentials to their saved endpoint and type

**Files:**
- Modify: `backend/app/security/tests/test_config_secrets.py`
- Modify: `backend/app/api/tests/test_api_integration.py`
- Modify: `backend/app/security/config_secrets.py:23-40`

**Interfaces:**
- Consumes: `resolve_provider_credentials(request: dict[str, Any], current: UIConfig) -> ProviderCredentials`.
- Produces: stored-key resolution that accepts matching public fields, rejects changed endpoint/type without a new key, and preserves complete unsaved credential tuples.

- [x] **Step 1: Write the failing unit tests**

```python
@pytest.mark.parametrize(
    "override",
    [
        {"base_url": "https://changed.example/v1"},
        {"provider_type": "anthropic"},
    ],
)
def test_stored_key_rejects_changed_credential_tuple_without_new_key(override):
    current = config_with_key()
    current.providers["main"].base_url = "https://saved.example/v1"
    with pytest.raises(ValueError, match="new API Key"):
        resolve_provider_credentials(
            {"provider_id": "main", "api_key": "", **override}, current
        )


def test_stored_key_accepts_matching_public_provider_fields():
    current = config_with_key()
    current.providers["main"].base_url = "https://saved.example/v1"
    credentials = resolve_provider_credentials(
        {
            "provider_id": "main",
            "base_url": "https://saved.example/v1",
            "api_key": "",
            "provider_type": "openai",
        },
        current,
    )
    assert credentials.base_url == "https://saved.example/v1"
    assert credentials.api_key == "sk-secret"
    assert credentials.provider_type == "openai"
```

- [x] **Step 2: Run the new unit tests and verify RED**

Run from `backend`: `"E:\my word\https-github-com-pocketfans-clade-tree\.worktrees\phase-2b2-save-path-boundary\backend\.venv\Scripts\python.exe" -m pytest app/security/tests/test_config_secrets.py -q`

Expected: the changed tuple cases fail because the current implementation combines request fields with the saved key.

- [x] **Step 3: Add route-level no-network regression coverage**

```python
@pytest.mark.parametrize(
    ("route", "client_method"),
    [
        ("/api/config/test-api", "probe_status"),
        ("/api/config/fetch-models", "fetch_json_response"),
    ],
)
def test_probe_routes_reject_changed_endpoint_with_stored_key(
    self, client, mock_container, route, client_method
):
    current = UIConfig(
        providers={
            "main": ProviderConfig(
                id="main",
                name="Main",
                base_url="https://saved.example/v1",
                api_key="stored-key-sentinel",
            )
        }
    )
    mock_container.config_service.get_ui_config.return_value = current
    safe_client = MagicMock(spec=SafeProbeClient)
    with patch("app.api.analytics._SAFE_PROBE_CLIENT", safe_client):
        response = client.post(
            route,
            json={
                "provider_id": "main",
                "base_url": "https://changed.example/v1",
                "api_key": "",
            },
        )
    assert response.status_code == 200
    assert response.json()["success"] is False
    getattr(safe_client, client_method).assert_not_called()
    assert "stored-key-sentinel" not in response.text
```

- [x] **Step 4: Implement stored-versus-unsaved tuple selection**

```python
explicit_key = request.get("api_key")
if explicit_key:
    base_url = request.get("base_url") or (stored.base_url if stored else None)
    provider_type = request.get("provider_type") or (
        stored.provider_type if stored else "openai"
    )
    return ProviderCredentials(base_url, str(explicit_key), provider_type)

if not stored or not stored.api_key:
    raise ValueError("API Key is not configured")
if request.get("base_url") not in (None, "", stored.base_url):
    raise ValueError("A new API Key is required when changing provider endpoint")
if request.get("provider_type") not in (None, "", stored.provider_type):
    raise ValueError("A new API Key is required when changing provider type")
return ProviderCredentials(stored.base_url, stored.api_key, stored.provider_type)
```

- [x] **Step 5: Run unit and route tests and verify GREEN**

Run from `backend`: `"E:\my word\https-github-com-pocketfans-clade-tree\.worktrees\phase-2b2-save-path-boundary\backend\.venv\Scripts\python.exe" -m pytest app/security/tests/test_config_secrets.py app/api/tests/test_api_integration.py -q`

Expected: all selected tests pass and neither route calls the safe probe client for a changed stored tuple.

### Task 2: Replace runtime credentials atomically and clear removed providers

**Files:**
- Modify: `backend/app/core/tests/test_ai_router_config.py`
- Modify: `backend/app/ai/tests/test_model_router_security.py`
- Modify: `backend/app/ai/model_router.py:114-142,303-339,984-1012,1119-1162,1285-1315,1413-1446`
- Modify: `backend/app/core/ai_router_config.py:96-119`

**Interfaces:**
- Consumes: `ModelRouter.set_provider_pool()`, `ModelRouter.configure_overrides()`, and `configure_model_router()`.
- Produces: `ModelRouter.clear_provider_pools() -> None`, atomic override credential selection, and clean refresh from UI or environment fallback state.

- [x] **Step 1: Write failing refresh tests**

```python
def test_configure_model_router_clears_deleted_provider_runtime_state() -> None:
    router = ModelRouter(
        defaults={
            "speciation": ModelConfig(
                provider="openai", model="existing", endpoint="/chat/completions"
            )
        }
    )
    configured = UIConfig(
        providers={
            "old": ProviderConfig(
                id="old",
                name="Old",
                base_url="https://old.example/v1",
                api_key="old-key-sentinel",
                selected_models=["old-model"],
            )
        },
        default_provider_id="old",
        load_balance_enabled=True,
        capability_routes={
            "speciation": CapabilityRouteConfig(provider_ids=["old"])
        },
    )
    settings = SimpleNamespace(
        speciation_model="fallback",
        embedding_provider="openai",
        ai_base_url=None,
        ai_api_key=None,
    )
    configure_model_router(configured, router, None, settings)
    configure_model_router(
        UIConfig(providers={}, load_balance_enabled=True), router, None, settings
    )
    assert router.api_base_url is None
    assert router.api_key is None
    assert router.get_provider_pools_info() == {}
```

- [x] **Step 2: Run the refresh test and verify RED**

Run from `backend`: `"E:\my word\https-github-com-pocketfans-clade-tree\.worktrees\phase-2b2-save-path-boundary\backend\.venv\Scripts\python.exe" -m pytest app/core/tests/test_ai_router_config.py -q`

Expected: the deleted provider remains in the pool and the old global endpoint/key remain set.

- [x] **Step 3: Write the failing seven-entry atomic-override test**

Add a parameterized test over `NETWORK_ENTRY_TRANSPORTS`. Configure a complete global tuple and an override containing both credential field names with another endpoint and `api_key=None`. Invoke each entry using the existing helpers, tolerate the entry's normal local/missing-configuration result, and assert `runtime_client.calls == []`.

```python
router.configure_overrides(
    {
        "generate": {
            "base_url": "https://override.example/v1",
            "api_key": None,
            "provider_type": "openai",
            "model": "override-model",
        }
    }
)
```

Expected RED: every entry currently combines the override endpoint with the global key and reaches the recording client.

- [x] **Step 4: Implement atomic runtime selection and pool clearing**

Add `clear_provider_pools()` to clear `_provider_pools`, `_lb_counters`, and `_provider_latencies`. In each network entry, use the override endpoint and key together whenever either credential field name is present; only use the global tuple when neither credential field name exists. At the start of `configure_model_router()`, reset global values from `settings.ai_base_url`/`settings.ai_api_key`, clear overrides, and clear all pools before rebuilding.

```python
model_router.api_base_url = getattr(settings, "ai_base_url", None)
model_router.api_key = getattr(settings, "ai_api_key", None)
model_router.overrides = {}
model_router.clear_provider_pools()
```

- [x] **Step 5: Run router tests and verify GREEN**

Run from `backend`: `"E:\my word\https-github-com-pocketfans-clade-tree\.worktrees\phase-2b2-save-path-boundary\backend\.venv\Scripts\python.exe" -m pytest app/core/tests/test_ai_router_config.py app/ai/tests/test_model_router_security.py -q`

Expected: deleted providers disappear immediately, incomplete provider overrides never reach the runtime client, and model-only overrides continue using the complete global tuple.

### Task 3: Validate Embedding endpoint syntax before cache lookup

**Files:**
- Modify: `backend/app/security/tests/test_outbound_url.py`
- Modify: `backend/app/services/system/tests/test_embedding_security.py`
- Modify: `backend/app/security/outbound_url.py:130-315`
- Modify: `backend/app/security/__init__.py`
- Modify: `backend/app/services/system/embedding.py:41-51,306-332,387-405`

**Interfaces:**
- Produces: `canonicalize_outbound_base_url(url: str) -> CanonicalOutboundBaseURL`, a DNS-free syntactic canonicalizer reused by `OutboundURLPolicy.validate()` and Embedding cache identity.
- Preserves: exactly one DNS resolution when an uncached runtime request is sent.

- [x] **Step 1: Write failing canonicalizer tests**

```python
def test_canonicalize_outbound_base_url_normalizes_without_dns() -> None:
    canonical = canonicalize_outbound_base_url(
        "https://Endpoint.Example:443/v1/"
    )
    assert canonical.url == "https://endpoint.example:443/v1/"


@pytest.mark.parametrize(
    "url",
    [
        "https://public.example/v1?tenant=other",
        "https://public.example/v1#fragment",
        "https://user@public.example/v1",
    ],
)
def test_canonicalize_outbound_base_url_rejects_credential_or_suffix(url):
    with pytest.raises(OutboundRequestError) as exc_info:
        canonicalize_outbound_base_url(url)
    assert exc_info.value.code == "outbound_url_invalid"
```

- [x] **Step 2: Write the failing cache-collision test**

```python
def test_invalid_remote_endpoint_cannot_reuse_valid_memory_cache(tmp_path: Path) -> None:
    client = RecordingSafeRuntimeClient(
        [{"data": [{"index": 0, "embedding": [4.0]}]}]
    )
    service = EmbeddingService(
        provider="openai",
        dimension=1,
        base_url="https://embedding.example/v1",
        api_key="secret-key",
        model="model-a",
        enabled=True,
        cache_dir=tmp_path,
        runtime_client=client,
    )
    assert service.embed(["oak"], require_real=True) == [[4.0]]
    service.api_base_url = "https://embedding.example/v1?tenant=other"
    with pytest.raises(OutboundRequestError) as exc_info:
        service.embed(["oak"], require_real=True)
    assert exc_info.value.code == "outbound_url_invalid"
    assert len(client.calls) == 1
```

- [x] **Step 3: Run the new tests and verify RED**

Run from `backend`: `"E:\my word\https-github-com-pocketfans-clade-tree\.worktrees\phase-2b2-save-path-boundary\backend\.venv\Scripts\python.exe" -m pytest app/security/tests/test_outbound_url.py app/services/system/tests/test_embedding_security.py -q`

Expected: the canonicalizer import is absent and the invalid endpoint currently returns the cached vector.

- [x] **Step 4: Extract and reuse the pure canonicalizer**

Move the existing syntax, scheme, host, userinfo, query, fragment, port, IDNA, and normalized-URL logic into the new pure function. Have `OutboundURLPolicy.validate()` call it before resolution. In `EmbeddingService.embed()`, canonicalize a complete remote configuration before deriving `cache_source` or any cache key; use the canonical URL only for cache identity and keep the frozen original configuration for the runtime request.

- [x] **Step 5: Run outbound and Embedding tests and verify GREEN**

Run from `backend`: `"E:\my word\https-github-com-pocketfans-clade-tree\.worktrees\phase-2b2-save-path-boundary\backend\.venv\Scripts\python.exe" -m pytest app/security/tests/test_outbound_url.py app/security/tests/test_runtime_http.py app/services/system/tests/test_embedding_security.py -q`

Expected: all selected tests pass, invalid endpoints never read cache, and runtime resolver-count tests still prove one DNS resolution per network invocation.

### Task 4: Phase 3A verification and publication

**Files:**
- Modify: `docs/superpowers/plans/2026-07-18-phase-3a-credential-runtime-boundary-fixes.md` only to mark executed checkboxes after evidence is available.

**Interfaces:**
- Produces: a reviewed commit on `phase-2c-outbound-url-security`, pushed to the existing fork branch and reflected in PR #15 without changing Draft status.

- [x] **Step 1: Run focused Phase 3A tests**

Run the test selections from Tasks 1-3 together. Expected: all pass with no real network and no secret sentinel in output.

- [x] **Step 2: Run complete backend and frontend gates**

Run the existing full backend suite, frontend Vitest suite, ESLint at the current warning budget, TypeScript check, and production build. Expected: no failures and no increase from the recorded warning/skip baselines.

- [x] **Step 3: Inspect repository hygiene and exact diff**

Run `git diff --check`, `git status --short`, secret-sentinel scans outside tests, and review every changed hunk. Expected: only Phase 3A code, tests, and this plan are changed.

- [x] **Step 4: Commit and push**

Commit the verified Phase 3A scope with a security-focused message, push `phase-2c-outbound-url-security` to the existing fork, and verify PR #15 still points to the pushed head and remains Draft.
