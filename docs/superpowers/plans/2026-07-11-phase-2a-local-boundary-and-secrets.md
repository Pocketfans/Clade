# Phase 2A Local Boundary and Secret Redaction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Clade listen only on the local machine by default and stop returning stored AI API keys to the browser while preserving existing credentials and local/cloud provider workflows.

**Architecture:** A small backend network policy validates bind hosts before `start.ps1` launches either server. A separate configuration-secret boundary projects persisted `UIConfig` into a public response and merges public updates back with existing secrets. The frontend represents only “configured/not configured,” sends explicit clear requests, and lets connection-test endpoints resolve an already stored credential by provider ID.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, pytest, PowerShell, React, TypeScript, Vitest, Vite.

## Global Constraints

- Default backend and frontend hosts are exactly `127.0.0.1`.
- Non-loopback binding requires `ALLOW_LAN_ACCESS=true`; setting only a host variable must fail closed.
- `GET /api/config/ui` and `POST /api/config/ui` must never return a complete API key.
- Empty or omitted keys preserve stored values; non-empty keys replace them; only an explicit provider ID list clears them.
- Existing cloud providers and explicitly entered unsaved credentials remain testable.
- A stored credential may be used by test/fetch-model requests through `provider_id`, but is never returned.
- No simulation rules, database schema, save format, or turn behavior may change.
- Existing backend full-suite baseline is `343 passed, 14 failed, 9 errors`; failure/error counts must not increase.
- Do not add new runtime dependencies.

---

## File Structure

- Create `backend/app/core/network_policy.py`: pure bind-host validation and environment resolution.
- Create `backend/app/core/tests/test_network_policy.py`: network policy unit tests.
- Create `backend/app/security/__init__.py`: security package marker and public exports.
- Create `backend/app/security/config_secrets.py`: public projection, secret merge, and provider credential resolution.
- Create `backend/app/security/tests/__init__.py`: security test package marker.
- Create `backend/app/security/tests/test_config_secrets.py`: secret-boundary unit tests.
- Create `backend/app/repositories/tests/test_environment_repository_config.py`: atomic config-write tests.
- Modify `backend/app/core/config.py`: declare bind-host settings.
- Modify `backend/app/repositories/environment_repository.py`: save UI configuration atomically.
- Modify `backend/app/api/analytics.py`: use the public/update contracts and stored credential resolution.
- Modify `backend/app/api/tests/test_api_integration.py`: verify route-level secret behavior.
- Modify `start.ps1`: resolve validated hosts before launching backend/frontend.
- Modify `README.md`: document local-only defaults and explicit LAN opt-in.
- Modify `frontend/vite.config.ts`: use the validated frontend host supplied by the launcher.
- Modify `frontend/src/services/api.types.ts`: add public credential-state fields.
- Modify `frontend/src/services/api/config.ts`: send the update envelope and provider IDs.
- Create `frontend/src/services/api/config.test.ts`: verify update payload construction.
- Modify `frontend/src/components/SettingsDrawer/types.ts`: add credential-specific reducer actions.
- Modify `frontend/src/components/SettingsDrawer/reducer.ts`: update/new/clear credential state transitions.
- Create `frontend/src/components/SettingsDrawer/reducer.test.ts`: reducer tests.
- Modify `frontend/src/components/SettingsDrawer/sections/ConnectionSection.tsx`: configured status, clear button, and stored-key requests.
- Modify `frontend/src/components/SettingsDrawer/sections/EmbeddingSection.tsx`: treat configured keys as usable.

---

### Task 1: Enforce local-only bind hosts

> **Controller resolution (2026-07-12):** The fail-closed constraint applies
> inside Vite as well as the launcher. A direct Vite start must reject a
> non-loopback `FRONTEND_HOST` unless `ALLOW_LAN_ACCESS=true`. The proxy target
> follows `BACKEND_HOST`, mapping wildcard bind hosts (`0.0.0.0`, `::`) to
> `127.0.0.1` and preserving a specific backend address.

**Files:**
- Create: `backend/app/core/network_policy.py`
- Create: `backend/app/core/tests/test_network_policy.py`
- Modify: `backend/app/core/config.py`
- Modify: `start.ps1`
- Create: `frontend/src/config/networkPolicy.ts`
- Create: `frontend/src/config/networkPolicy.test.ts`
- Modify: `frontend/vite.config.ts`
- Modify: `README.md`

**Interfaces:**
- Consumes: environment values `BACKEND_HOST`, `FRONTEND_HOST`, and `ALLOW_LAN_ACCESS` through `Settings`.
- Produces: `BindHosts`, `is_loopback_host(host: str) -> bool`, and `resolve_bind_hosts(settings: Settings) -> BindHosts`.

- [ ] **Step 1: Write failing network-policy tests**

Create `backend/app/core/tests/test_network_policy.py`:

```python
import pytest

from app.core.config import Settings
from app.core.network_policy import resolve_bind_hosts


def make_settings(**overrides) -> Settings:
    values = {
        "BACKEND_HOST": "127.0.0.1",
        "FRONTEND_HOST": "127.0.0.1",
        "ALLOW_LAN_ACCESS": False,
    }
    values.update(overrides)
    return Settings(**values)


def test_default_hosts_are_loopback() -> None:
    hosts = resolve_bind_hosts(make_settings())
    assert hosts.backend == "127.0.0.1"
    assert hosts.frontend == "127.0.0.1"
    assert hosts.lan_enabled is False


@pytest.mark.parametrize("field", ["BACKEND_HOST", "FRONTEND_HOST"])
@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.25", "10.0.0.8"])
def test_non_loopback_host_requires_lan_opt_in(field: str, host: str) -> None:
    with pytest.raises(ValueError, match="ALLOW_LAN_ACCESS=true"):
        resolve_bind_hosts(make_settings(**{field: host}))


def test_explicit_lan_opt_in_allows_non_loopback_hosts() -> None:
    hosts = resolve_bind_hosts(
        make_settings(
            BACKEND_HOST="0.0.0.0",
            FRONTEND_HOST="0.0.0.0",
            ALLOW_LAN_ACCESS=True,
        )
    )
    assert hosts.backend == "0.0.0.0"
    assert hosts.frontend == "0.0.0.0"
    assert hosts.lan_enabled is True
```

- [ ] **Step 2: Run the tests and verify the missing-module failure**

Run:

```powershell
cd backend
.venv\Scripts\python.exe -m pytest app/core/tests/test_network_policy.py -q
```

Expected: collection fails because `app.core.network_policy` does not exist.

- [ ] **Step 3: Add bind settings and the pure policy**

Add to `Settings` in `backend/app/core/config.py` directly after the port fields:

```python
    backend_host: str = Field(default="127.0.0.1", alias="BACKEND_HOST")
    frontend_host: str = Field(default="127.0.0.1", alias="FRONTEND_HOST")
    allow_lan_access: bool = Field(default=False, alias="ALLOW_LAN_ACCESS")
```

Create `backend/app/core/network_policy.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address

from .config import Settings


@dataclass(frozen=True)
class BindHosts:
    backend: str
    frontend: str
    lan_enabled: bool


def is_loopback_host(host: str) -> bool:
    normalized = host.strip().lower().strip("[]")
    if normalized == "localhost":
        return True
    try:
        return ip_address(normalized).is_loopback
    except ValueError:
        return False


def resolve_bind_hosts(settings: Settings) -> BindHosts:
    backend = settings.backend_host.strip()
    frontend = settings.frontend_host.strip()
    if not backend or not frontend:
        raise ValueError("BACKEND_HOST and FRONTEND_HOST must not be empty")
    if not settings.allow_lan_access:
        unsafe = [host for host in (backend, frontend) if not is_loopback_host(host)]
        if unsafe:
            raise ValueError(
                "Non-loopback binding requires ALLOW_LAN_ACCESS=true: "
                + ", ".join(unsafe)
            )
    return BindHosts(
        backend=backend,
        frontend=frontend,
        lan_enabled=settings.allow_lan_access,
    )
```

- [ ] **Step 4: Run the focused backend tests**

Run: `cd backend; .venv\Scripts\python.exe -m pytest app/core/tests/test_network_policy.py -q`

Expected: `8 passed`.

- [ ] **Step 5: Make `start.ps1` consume the policy**

Immediately after `$backendPath` is defined, resolve the settings with the same Python environment and import root used by the backend:

```powershell
Push-Location $backendPath
try {
    $bindConfigJson = & ".\venv\Scripts\python.exe" -c "import json; from app.core.config import get_settings; from app.core.network_policy import resolve_bind_hosts; h=resolve_bind_hosts(get_settings()); print(json.dumps({'backend': h.backend, 'frontend': h.frontend, 'lan_enabled': h.lan_enabled}))"
    if ($LASTEXITCODE -ne 0) {
        throw "启动地址配置无效。非本机监听必须显式设置 ALLOW_LAN_ACCESS=true。"
    }
} finally {
    Pop-Location
}
$bindConfig = $bindConfigJson | ConvertFrom-Json
$backendHost = $bindConfig.backend
$frontendHost = $bindConfig.frontend
$allowLanAccess = if ($bindConfig.lan_enabled) { "true" } else { "false" }
if ($bindConfig.lan_enabled) {
    Write-Warning "局域网访问已启用。Clade API 和前端可能被同一网络中的其他设备访问。"
}
```

Change the backend launch line to:

```powershell
python -m uvicorn app.main:app --reload --host $backendHost --port $BACKEND_PORT
```

Pass the resolved policy values into the Vite process:

```powershell
`$env:BACKEND_HOST='$backendHost'
`$env:FRONTEND_HOST='$frontendHost'
`$env:ALLOW_LAN_ACCESS='$allowLanAccess'
npx.cmd vite --host `$env:FRONTEND_HOST --port $FRONTEND_PORT --config vite.config.ts
```

Create `frontend/src/config/networkPolicy.ts` as a pure policy module and add
focused tests in `frontend/src/config/networkPolicy.test.ts`. The tests must
cover rejection without opt-in, explicit opt-in, wildcard backend mapping for
both `0.0.0.0` and `::`, and preservation of a specific LAN backend address.
The policy must default both hosts to `127.0.0.1` and throw an error containing
`ALLOW_LAN_ACCESS=true` when a non-loopback host is used without opt-in.

In `frontend/vite.config.ts`, consume only the resolved policy:

```ts
import { resolveFrontendNetworkPolicy } from "./src/config/networkPolicy";

const NETWORK_POLICY = resolveFrontendNetworkPolicy(process.env);
```

Use the resolved frontend host and backend proxy host:

```ts
  server: {
    host: NETWORK_POLICY.frontendHost,
    port: FRONTEND_PORT,
    proxy: {
      "/api": {
        target: `http://${NETWORK_POLICY.backendProxyHost}:${BACKEND_PORT}`,
```

- [ ] **Step 6: Update manual-start documentation**

Replace the README backend command with:

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8022
```

Replace the frontend command with:

```powershell
npm run dev -- --host 127.0.0.1
```

Add this explicit opt-in note next to the commands:

```markdown
默认仅允许本机访问。只有确实需要局域网访问时，才同时设置
`ALLOW_LAN_ACCESS=true`、`BACKEND_HOST=0.0.0.0` 和
`FRONTEND_HOST=0.0.0.0`。局域网模式会暴露本地 API，请仅在可信网络中使用。
```

- [ ] **Step 7: Verify and commit Task 1**

Run:

```powershell
cd backend
.venv\Scripts\python.exe -m pytest app/core/tests/test_network_policy.py -q
cd ..\frontend
npm run test:run
npm run build
cd ..
git diff --check
```

Expected: focused backend tests and all frontend tests pass, frontend build
exits `0`, and diff check is clean.

Commit:

```powershell
git add backend/app/core/config.py backend/app/core/network_policy.py backend/app/core/tests/test_network_policy.py start.ps1 frontend/src/config/networkPolicy.ts frontend/src/config/networkPolicy.test.ts frontend/vite.config.ts README.md docs/superpowers/plans/2026-07-11-phase-2a-local-boundary-and-secrets.md
git commit -m "security: default servers to loopback"
```

---

### Task 2: Add the backend secret boundary and atomic config writes

**Files:**
- Create: `backend/app/security/__init__.py`
- Create: `backend/app/security/config_secrets.py`
- Create: `backend/app/security/tests/__init__.py`
- Create: `backend/app/security/tests/test_config_secrets.py`
- Create: `backend/app/repositories/tests/test_environment_repository_config.py`
- Modify: `backend/app/repositories/environment_repository.py`

**Interfaces:**
- Consumes: persisted `UIConfig` and provider IDs explicitly selected for clearing.
- Produces: `UIConfigUpdateRequest`, `public_ui_config`, `merge_ui_config_secrets`, and atomic `save_ui_config` behavior.

- [ ] **Step 1: Write failing projection and merge tests**

Create package marker files and `backend/app/security/tests/test_config_secrets.py`:

```python
from app.models.config import ProviderConfig, UIConfig
from app.security.config_secrets import merge_ui_config_secrets, public_ui_config


def config_with_key(key: str = "sk-secret") -> UIConfig:
    return UIConfig(
        providers={
            "main": ProviderConfig(
                id="main",
                name="Main",
                provider_type="openai",
                api_key=key,
            )
        },
        ai_api_key="legacy-chat",
        embedding_api_key="legacy-embedding",
    )


def test_public_config_never_contains_stored_secrets() -> None:
    public = public_ui_config(config_with_key())
    assert public["providers"]["main"]["api_key"] == ""
    assert public["providers"]["main"]["api_key_configured"] is True
    assert public["ai_api_key"] == ""
    assert public["ai_api_key_configured"] is True
    assert public["embedding_api_key"] == ""
    assert public["embedding_api_key_configured"] is True
    assert "sk-secret" not in str(public)


def test_empty_key_preserves_existing_secret() -> None:
    incoming = config_with_key("")
    merged = merge_ui_config_secrets(config_with_key(), incoming, set())
    assert merged.providers["main"].api_key == "sk-secret"


def test_non_empty_key_replaces_existing_secret() -> None:
    incoming = config_with_key("sk-new")
    merged = merge_ui_config_secrets(config_with_key(), incoming, set())
    assert merged.providers["main"].api_key == "sk-new"


def test_explicit_clear_removes_provider_secret() -> None:
    incoming = config_with_key("")
    merged = merge_ui_config_secrets(config_with_key(), incoming, {"main"})
    assert merged.providers["main"].api_key is None


def test_removed_provider_is_not_reintroduced() -> None:
    incoming = UIConfig(providers={})
    merged = merge_ui_config_secrets(config_with_key(), incoming, set())
    assert merged.providers == {}
```

- [ ] **Step 2: Run and verify the missing-module failure**

Run: `cd backend; .venv\Scripts\python.exe -m pytest app/security/tests/test_config_secrets.py -q`

Expected: collection fails because `app.security.config_secrets` does not exist.

- [ ] **Step 3: Implement the public/update contracts**

Create `backend/app/security/config_secrets.py`:

```python
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..models.config import UIConfig


class UIConfigUpdateRequest(BaseModel):
    config: UIConfig
    clear_provider_api_keys: set[str] = Field(default_factory=set)


def public_ui_config(config: UIConfig) -> dict[str, Any]:
    data = config.model_dump(mode="json")
    for provider in data.get("providers", {}).values():
        provider["api_key_configured"] = bool(provider.get("api_key"))
        provider["api_key"] = ""
    for field in ("ai_api_key", "embedding_api_key"):
        data[f"{field}_configured"] = bool(data.get(field))
        data[field] = ""
    return data


def merge_ui_config_secrets(
    current: UIConfig,
    incoming: UIConfig,
    clear_provider_api_keys: set[str],
) -> UIConfig:
    data = incoming.model_dump(mode="python")
    current_providers = current.providers
    for provider_id, provider in data.get("providers", {}).items():
        if provider_id in clear_provider_api_keys:
            provider["api_key"] = None
        elif not provider.get("api_key") and provider_id in current_providers:
            provider["api_key"] = current_providers[provider_id].api_key
    for field in ("ai_api_key", "embedding_api_key"):
        if not data.get(field):
            data[field] = getattr(current, field)
    return UIConfig.model_validate(data)
```

Export the four public names from `backend/app/security/__init__.py`.

- [ ] **Step 4: Run the secret tests**

Run: `cd backend; .venv\Scripts\python.exe -m pytest app/security/tests/test_config_secrets.py -q`

Expected: `5 passed`.

- [ ] **Step 5: Write a failing atomic-write test**

Create `backend/app/repositories/tests/test_environment_repository_config.py`:

```python
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event, Lock

from app.models.config import UIConfig
from app.repositories.environment_repository import EnvironmentRepository


def test_save_ui_config_replaces_file_and_removes_temp_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = tmp_path / "settings.json"
    path.write_text('{"autosave_enabled": false}', encoding="utf-8")
    repo = EnvironmentRepository()
    replacements: list[tuple[Path, Path]] = []
    original_replace = Path.replace

    def tracking_replace(source: Path, target: Path) -> Path:
        replacements.append((source, target))
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", tracking_replace)

    repo.save_ui_config(path, UIConfig(autosave_enabled=True))

    assert UIConfig.model_validate_json(path.read_text(encoding="utf-8")).autosave_enabled is True
    assert len(replacements) == 1
    temp_path, target_path = replacements[0]
    assert temp_path.parent == path.parent
    assert temp_path != path
    assert target_path == path
    assert not temp_path.exists()
    assert list(tmp_path.glob("*.tmp")) == []


def test_concurrent_save_ui_config_uses_independent_temp_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = tmp_path / "settings.json"
    repo = EnvironmentRepository()
    write_barrier = Barrier(2)
    replace_barrier = Barrier(2)
    first_replace_done = Event()
    replacements: list[tuple[Path, Path, bool]] = []
    replacements_lock = Lock()
    original_replace = Path.replace
    original_write_text = Path.write_text

    def synchronized_write_text(destination: Path, data: str, **kwargs) -> int:
        written = original_write_text(destination, data, **kwargs)
        if destination == path.with_suffix(path.suffix + ".tmp"):
            write_barrier.wait(timeout=5)
        return written

    def synchronized_replace(source: Path, target: Path) -> Path:
        saved = UIConfig.model_validate_json(source.read_text(encoding="utf-8"))
        with replacements_lock:
            replacement_order = len(replacements)
            replacements.append((source, target, saved.autosave_enabled))
        replace_barrier.wait(timeout=5)
        if replacement_order == 0:
            try:
                return original_replace(source, target)
            finally:
                first_replace_done.set()
        first_replace_done.wait(timeout=5)
        return original_replace(source, target)

    monkeypatch.setattr(Path, "write_text", synchronized_write_text)
    monkeypatch.setattr(Path, "replace", synchronized_replace)

    configs = [UIConfig(autosave_enabled=False), UIConfig(autosave_enabled=True)]
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(repo.save_ui_config, path, config) for config in configs]
        exceptions = [future.exception(timeout=5) for future in futures]

    assert exceptions == [None, None]
    assert len({source for source, _, _ in replacements}) == 2
    assert {target for _, target, _ in replacements} == {path}
    assert {enabled for _, _, enabled in replacements} == {False, True}
    assert list(tmp_path.glob("*.tmp")) == []
```

Run: `cd backend; .venv\Scripts\python.exe -m pytest app/repositories/tests/test_environment_repository_config.py -q`

Expected: the direct writer fails the replacement test; the fixed-name temporary
writer fails the controlled concurrent test with `FileNotFoundError`.

- [ ] **Step 6: Save the configuration atomically**

Import `NamedTemporaryFile` from `tempfile`, then replace `save_ui_config` with:

```python
    def save_ui_config(self, path: Path, config: UIConfig) -> UIConfig:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path: Path | None = None
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                temp_path = Path(temp_file.name)
                temp_file.write(config.model_dump_json(indent=2, ensure_ascii=False))
                temp_file.flush()
            temp_path.replace(path)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
        logger.debug(f"[配置] 已保存配置到 {path}")
        return config
```

- [ ] **Step 7: Verify and commit Task 2**

Run:

```powershell
cd backend
.venv\Scripts\python.exe -m pytest app/security/tests/test_config_secrets.py app/repositories/tests/test_environment_repository_config.py -q
cd ..
git diff --check
```

Expected: `6 passed` and clean diff.

Commit:

```powershell
git add backend/app/security backend/app/repositories/environment_repository.py backend/app/repositories/tests/test_environment_repository_config.py
git commit -m "security: redact and preserve configuration secrets"
```

---

### Task 3: Apply the safe configuration contract to API routes

**Files:**
- Modify: `backend/app/security/config_secrets.py`
- Modify: `backend/app/security/tests/test_config_secrets.py`
- Modify: `backend/app/api/analytics.py`
- Modify: `backend/app/api/tests/test_api_integration.py`

**Interfaces:**
- Consumes: `UIConfigUpdateRequest`, provider ID, optional unsaved base URL/API key, and the container's current `UIConfig`.
- Produces: `resolve_provider_credentials(request: dict[str, Any], current: UIConfig) -> ProviderCredentials` and safe GET/POST configuration responses.

- [ ] **Step 1: Write failing stored-credential resolution tests**

Append to `test_config_secrets.py`:

```python
import pytest

from app.security.config_secrets import resolve_provider_credentials


def test_provider_id_resolves_stored_credentials() -> None:
    credentials = resolve_provider_credentials(
        {"provider_id": "main"},
        config_with_key(),
    )
    assert credentials.base_url is None
    assert credentials.api_key == "sk-secret"
    assert credentials.provider_type == "openai"


def test_unsaved_values_override_stored_credentials() -> None:
    credentials = resolve_provider_credentials(
        {
            "provider_id": "main",
            "base_url": "https://new.example/v1",
            "api_key": "sk-unsaved",
            "provider_type": "anthropic",
        },
        config_with_key(),
    )
    assert credentials.base_url == "https://new.example/v1"
    assert credentials.api_key == "sk-unsaved"
    assert credentials.provider_type == "anthropic"


def test_unknown_provider_without_explicit_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="API Key"):
        resolve_provider_credentials({"provider_id": "missing"}, config_with_key())
```

- [ ] **Step 2: Implement provider credential resolution**

Add to `config_secrets.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderCredentials:
    base_url: str | None
    api_key: str
    provider_type: str


def resolve_provider_credentials(
    request: dict[str, Any],
    current: UIConfig,
) -> ProviderCredentials:
    provider_id = str(request.get("provider_id") or "")
    stored = current.providers.get(provider_id)
    base_url = request.get("base_url") or (stored.base_url if stored else None)
    api_key = request.get("api_key") or (stored.api_key if stored else None)
    provider_type = request.get("provider_type") or (
        stored.provider_type if stored else "openai"
    )
    if not api_key:
        raise ValueError("API Key is not configured")
    return ProviderCredentials(
        base_url=base_url,
        api_key=api_key,
        provider_type=provider_type,
    )
```

Run the focused security tests and expect `8 passed`.

- [ ] **Step 3: Write route integration tests before changing routes**

Add these methods inside the existing `TestNewRouterIntegration` class so they use its `client` fixture. Patch the runtime reconfiguration calls because these tests verify only the HTTP secret boundary:

```python
    def test_get_config_redacts_provider_key(self, client, mock_container):
        from ...models.config import ProviderConfig, UIConfig

        mock_container.config_service.get_ui_config.return_value = UIConfig(
            providers={
                "main": ProviderConfig(
                    id="main", name="Main", api_key="sk-secret"
                )
            }
        )
        response = client.get("/api/config/ui")
        assert response.status_code == 200
        body = response.json()
        assert body["providers"]["main"]["api_key"] == ""
        assert body["providers"]["main"]["api_key_configured"] is True
        assert "sk-secret" not in response.text

    def test_post_config_preserves_empty_key(self, client, mock_container):
        from ...models.config import ProviderConfig, UIConfig

        current = UIConfig(
            providers={
                "main": ProviderConfig(
                    id="main", name="Main", api_key="sk-secret"
                )
            }
        )
        mock_container.config_service.get_ui_config.return_value = current
        mock_container.settings.ui_config_path = "data/test-settings.json"
        mock_container.environment_repository.save_ui_config.side_effect = (
            lambda _path, config: config
        )
        with patch("app.api.analytics.configure_model_router"):
            response = client.post(
                "/api/config/ui",
                json={
                    "config": {
                        "providers": {
                            "main": {"id": "main", "name": "Main", "api_key": ""}
                        }
                    },
                    "clear_provider_api_keys": [],
                },
            )
        assert response.status_code == 200
        saved = mock_container.environment_repository.save_ui_config.call_args.args[1]
        assert saved.providers["main"].api_key == "sk-secret"
        assert "sk-secret" not in response.text
```

Run only these tests and verify they fail because the route returns/saves the raw config.

- [ ] **Step 4: Replace GET/POST route behavior**

In `analytics.py`, import the secret-boundary helpers. Change GET to:

```python
@router.get("/config/ui")
def get_ui_config(
    container: 'ServiceContainer' = Depends(get_container),
) -> dict:
    return public_ui_config(container.config_service.get_ui_config())
```

Change POST to accept `UIConfigUpdateRequest`, merge before saving, apply only after a successful save, and return `public_ui_config(saved)`:

```python
@router.post("/config/ui")
def update_ui_config(
    request: UIConfigUpdateRequest,
    container: 'ServiceContainer' = Depends(get_container),
) -> dict:
    current = container.config_service.get_ui_config()
    merged = merge_ui_config_secrets(
        current,
        request.config,
        request.clear_provider_api_keys,
    )
    saved = container.environment_repository.save_ui_config(
        Path(container.settings.ui_config_path),
        merged,
    )
    container.config_service.invalidate_cache()
    configure_model_router(
        saved,
        container.model_router,
        container.embedding_service,
        container.settings,
    )
    return public_ui_config(saved)
```

Keep the existing simulation-config refresh block after the successful save, but do not import or use any public/redacted object for runtime configuration.

- [ ] **Step 5: Use stored credentials in test/fetch-model routes**

At the start of both route functions:

```python
    try:
        credentials = resolve_provider_credentials(
            request,
            container.config_service.get_ui_config(),
        )
    except ValueError as exc:
        return {"success": False, "error": str(exc), "models": []}

    base_url = credentials.base_url or ""
    api_key = credentials.api_key
    provider_type = credentials.provider_type
```

For the connection-test route omit the `models` key from its error dictionary. Do not log `request`, `credentials`, headers, or a URL containing a key.

- [ ] **Step 6: Verify and commit Task 3**

Run:

```powershell
cd backend
.venv\Scripts\python.exe -m pytest app/security/tests/test_config_secrets.py app/api/tests/test_api_integration.py -q
cd ..
git diff --check
```

Expected: new secret tests pass. Any pre-existing `test_config_service_caching` failure must be identified separately and the failure/error baseline must not increase.

Commit:

```powershell
git add backend/app/security/config_secrets.py backend/app/security/tests/test_config_secrets.py backend/app/api/analytics.py backend/app/api/tests/test_api_integration.py
git commit -m "security: stop exposing stored API keys"
```

---

### Task 4: Update the frontend credential-state contract

**Files:**
- Modify: `frontend/src/services/api.types.ts`
- Modify: `frontend/src/services/api/config.ts`
- Create: `frontend/src/services/api/config.test.ts`
- Modify: `frontend/src/components/SettingsDrawer/types.ts`
- Modify: `frontend/src/components/SettingsDrawer/reducer.ts`
- Create: `frontend/src/components/SettingsDrawer/reducer.test.ts`
- Modify: `frontend/src/components/SettingsDrawer/sections/ConnectionSection.tsx`
- Modify: `frontend/src/components/SettingsDrawer/sections/EmbeddingSection.tsx`

**Interfaces:**
- Consumes: public provider fields `api_key_configured` and local-only `api_key_clear_requested`.
- Produces: update envelope `{ config, clear_provider_api_keys }` and stored-key connection requests containing `provider_id`.

- [ ] **Step 1: Add failing API payload tests**

Create `frontend/src/services/api/config.test.ts` with a mocked `http.post`:

```ts
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock("./base", () => ({ http: { get: vi.fn(), post: mocks.post } }));

import { updateUIConfig } from "./config";
import type { UIConfig } from "../api.types";

describe("updateUIConfig", () => {
  beforeEach(() => mocks.post.mockReset());

  it("sends explicit provider clear requests outside the persisted config", async () => {
    const config = {
      providers: {
        main: {
          id: "main",
          name: "Main",
          type: "openai",
          provider_type: "openai",
          api_key: "",
          api_key_configured: true,
          api_key_clear_requested: true,
          models: [],
        },
      },
      capability_routes: {},
    } satisfies UIConfig;
    mocks.post.mockResolvedValue(config);

    await updateUIConfig(config);

    expect(mocks.post).toHaveBeenCalledWith(
      "/api/config/ui",
      expect.objectContaining({ clear_provider_api_keys: ["main"] }),
    );
  });
});
```

Run: `cd frontend; npm run test:run -- src/services/api/config.test.ts`

Expected: fail because the current API sends the raw config directly.

- [ ] **Step 2: Add public/UI-only fields and build the update envelope**

Extend `ProviderConfig`:

```ts
  api_key_configured?: boolean;
  api_key_clear_requested?: boolean;
```

Extend `UIConfig` with:

```ts
  ai_api_key_configured?: boolean;
  embedding_api_key_configured?: boolean;
```

Add `provider_id?: string` to `ApiTestParams` and the fetch-model parameter type.

Change `updateUIConfig` to:

```ts
export async function updateUIConfig(config: UIConfig): Promise<UIConfig> {
  const clearProviderApiKeys = Object.values(config.providers || {})
    .filter((provider) => provider.api_key_clear_requested)
    .map((provider) => provider.id);
  return http.post<UIConfig>("/api/config/ui", {
    config,
    clear_provider_api_keys: clearProviderApiKeys,
  });
}
```

- [ ] **Step 3: Write failing reducer tests**

Create `frontend/src/components/SettingsDrawer/reducer.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { createInitialState, settingsReducer } from "./reducer";

const config = {
  providers: {
    main: {
      id: "main",
      name: "Main",
      type: "openai",
      provider_type: "openai" as const,
      api_key: "",
      api_key_configured: true,
      models: [],
    },
  },
  capability_routes: {},
};

describe("credential reducer actions", () => {
  it("marks an existing key for explicit clearing", () => {
    const state = settingsReducer(createInitialState(config), {
      type: "CLEAR_PROVIDER_API_KEY",
      providerId: "main",
    });
    expect(state.form.providers.main.api_key).toBe("");
    expect(state.form.providers.main.api_key_configured).toBe(false);
    expect(state.form.providers.main.api_key_clear_requested).toBe(true);
  });

  it("typing a replacement cancels a pending clear", () => {
    const cleared = settingsReducer(createInitialState(config), {
      type: "CLEAR_PROVIDER_API_KEY",
      providerId: "main",
    });
    const replaced = settingsReducer(cleared, {
      type: "UPDATE_PROVIDER_API_KEY",
      providerId: "main",
      apiKey: "sk-new",
    });
    expect(replaced.form.providers.main.api_key).toBe("sk-new");
    expect(replaced.form.providers.main.api_key_clear_requested).toBe(false);
  });
});
```

- [ ] **Step 4: Implement credential reducer actions**

Add to `SettingsAction`:

```ts
  | { type: "UPDATE_PROVIDER_API_KEY"; providerId: string; apiKey: string }
  | { type: "CLEAR_PROVIDER_API_KEY"; providerId: string }
```

Add reducer cases:

```ts
    case "UPDATE_PROVIDER_API_KEY":
      return {
        ...state,
        form: {
          ...state.form,
          providers: {
            ...state.form.providers,
            [action.providerId]: {
              ...state.form.providers[action.providerId],
              api_key: action.apiKey,
              api_key_clear_requested: false,
            },
          },
        },
      };

    case "CLEAR_PROVIDER_API_KEY":
      return {
        ...state,
        form: {
          ...state.form,
          providers: {
            ...state.form.providers,
            [action.providerId]: {
              ...state.form.providers[action.providerId],
              api_key: "",
              api_key_configured: false,
              api_key_clear_requested: true,
            },
          },
        },
      };
```

Run both new frontend test files and expect all new tests to pass.

- [ ] **Step 5: Update connection and embedding behavior**

In `ConnectionSection.tsx`:

- Consider a credential usable when `provider.api_key` is non-empty or `provider.api_key_configured` is true.
- Dispatch `UPDATE_PROVIDER_API_KEY` from the input.
- Use placeholder `已配置；留空会保留现有密钥` when configured.
- Show a `清除已保存密钥` button only when configured and no new key is being entered.
- Dispatch `CLEAR_PROVIDER_API_KEY` only after the existing confirmation-dialog mechanism confirms.
- Disable test/fetch actions when `api_key_clear_requested` is true.
- Include `provider_id: provider.id` in both requests; send `api_key: provider.api_key || ""` so the backend can resolve the stored value.

Use this guard consistently:

```ts
const hasUsableApiKey = (provider: ProviderConfig) =>
  Boolean(provider.api_key || provider.api_key_configured) &&
  !provider.api_key_clear_requested;
```

In `EmbeddingSection.tsx`, change the provider list and validation to use the same configured-state meaning, add `provider_id`, and pass an empty string when only a stored key exists.

- [ ] **Step 6: Verify and commit Task 4**

Run:

```powershell
cd frontend
npm run test:run
npm run lint
npm run build
cd ..
git diff --check
```

Expected: all frontend tests, lint budget, TypeScript, and Vite build pass.

Commit:

```powershell
git add frontend/src/services/api.types.ts frontend/src/services/api/config.ts frontend/src/services/api/config.test.ts frontend/src/components/SettingsDrawer/types.ts frontend/src/components/SettingsDrawer/reducer.ts frontend/src/components/SettingsDrawer/reducer.test.ts frontend/src/components/SettingsDrawer/sections/ConnectionSection.tsx frontend/src/components/SettingsDrawer/sections/EmbeddingSection.tsx
git commit -m "feat: represent stored API keys without exposing them"
```

---

### Task 5: Complete Phase 2A regression verification

**Files:**
- Modify only if verification finds a Phase 2A regression in files already listed above.

**Interfaces:**
- Consumes: all Task 1–4 deliverables.
- Produces: a verified Phase 2A branch with no new backend failures and no exposed test secrets.

- [ ] **Step 1: Run all standard frontend gates**

```powershell
cd frontend
npm run lint
npm run test:run
npm run build
```

Expected: lint exits `0` within the existing warning budget, every Vitest test passes, and production build exits `0`.

- [ ] **Step 2: Run focused backend security tests and collection**

```powershell
cd ..\backend
.venv\Scripts\python.exe -m pytest app/core/tests/test_network_policy.py app/security/tests/test_config_secrets.py app/repositories/tests/test_environment_repository_config.py app/api/tests/test_api_integration.py -q
.venv\Scripts\python.exe -m pytest --collect-only -q
```

Expected: all new tests pass; collection reports at least 366 tests.

- [ ] **Step 3: Run the complete backend suite and compare the baseline**

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Expected: Phase 2A tests pass and the historical baseline does not exceed `14 failed, 9 errors`. If a new failure contains `network_policy`, `config_secrets`, `/config/ui`, `ConnectionSection`, or the atomic writer, stop and fix it before proceeding.

- [ ] **Step 4: Scan for secret exposure and unsafe default bind commands**

```powershell
cd ..
rg -n "--host 0\.0\.0\.0|api_key\]\s*=|return .*api_key|model_dump.*config" README.md start.ps1 backend/app/api backend/app/security
git diff --check
git status --short
```

Expected: no default `0.0.0.0` command remains; configuration responses pass through `public_ui_config`; diff check is clean; only intended files are changed.

- [ ] **Step 5: Record the Phase 2A verification commit**

If verification required no fixes, do not create an empty commit. If it required in-scope fixes, commit only those verified fixes:

```powershell
git add backend/app/core backend/app/security backend/app/repositories/environment_repository.py backend/app/repositories/tests backend/app/api/analytics.py backend/app/api/tests/test_api_integration.py frontend/src/services frontend/src/components/SettingsDrawer start.ps1 frontend/vite.config.ts README.md
git commit -m "test: complete phase 2a security verification"
```

The phase is ready for review when Tasks 1–5 are complete. Phase 2B must begin from this verified state and gets its own plan.
