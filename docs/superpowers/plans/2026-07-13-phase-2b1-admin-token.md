# Phase 2B-1 Admin Token Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Require an explicit administrator token for every state-changing `/api/admin` request while keeping health and storage reads available, and let the existing Admin panel send that token without persisting it.

**Architecture:** Add one settings value and one FastAPI dependency that applies at the admin router boundary. The dependency bypasses only `GET` and `HEAD`, fails closed when the server token is absent, and compares supplied tokens in constant time. The browser holds the token only in `AdminPanel` component state and passes it through the existing HTTP client's per-request headers.

**Tech Stack:** Python 3.12, FastAPI, Pydantic Settings, pytest/TestClient, React 18, TypeScript, Vitest, Testing Library.

## Global Constraints

- Start implementation from reviewed Phase 2A commit `75eca7c` in a new isolated worktree.
- Do not merge to `main` while the accepted repository baseline remains `14 failed, 9 errors`.
- `CLADE_ADMIN_TOKEN` is optional at startup; when absent, state-changing admin requests return `503`.
- When configured, a missing or incorrect `X-Clade-Admin-Token` returns the same `403` response.
- Use `secrets.compare_digest` and never log, serialize, persist, or place the token in a URL.
- `GET` and `HEAD` admin routes remain readable without a token.
- The token exists in the browser only in current `AdminPanel` component memory; no localStorage, sessionStorage, settings export, query string, or global store.
- Do not modify database schema, simulation behavior, save format, or Phase 2C outbound URL behavior.
- Preserve the accepted baselines: frontend lint at no more than 162 warnings; full backend failures/errors at no more than `14/9`.

---

### Task 1: Define the fail-closed administrator-token dependency

**Files:**
- Modify: `backend/app/core/config.py:15-45`
- Create: `backend/app/security/admin_token.py`
- Create: `backend/app/security/tests/test_admin_token.py`

**Interfaces:**
- Consumes: `Settings` and FastAPI `Request`/`Header` dependency injection.
- Produces: `Settings.clade_admin_token: str | None` and `require_admin_token(...) -> None`.

- [ ] **Step 1: Write failing dependency tests**

Create `backend/app/security/tests/test_admin_token.py` with a small real FastAPI application:

```python
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from ...core.config import get_settings
from ..admin_token import require_admin_token


def make_client(token: str | None) -> TestClient:
    app = FastAPI()

    @app.get("/probe", dependencies=[Depends(require_admin_token)])
    def read_probe() -> dict:
        return {"ok": True}

    @app.head("/probe", dependencies=[Depends(require_admin_token)])
    def head_probe() -> None:
        return None

    @app.post("/probe", dependencies=[Depends(require_admin_token)])
    def write_probe() -> dict:
        return {"ok": True}

    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
        clade_admin_token=token
    )
    return TestClient(app)


@pytest.mark.parametrize("method", ["get", "head"])
def test_read_methods_do_not_require_admin_token(method: str) -> None:
    response = getattr(make_client(None), method)("/probe")
    assert response.status_code == 200


def test_write_fails_closed_when_server_token_is_not_configured() -> None:
    response = make_client(None).post("/probe")
    assert response.status_code == 503
    assert response.json() == {"detail": "管理员功能未启用"}


@pytest.mark.parametrize("headers", [{}, {"X-Clade-Admin-Token": "wrong"}])
def test_write_rejects_missing_and_wrong_tokens_identically(headers: dict) -> None:
    response = make_client("server-secret").post("/probe", headers=headers)
    assert response.status_code == 403
    assert response.json() == {"detail": "管理员令牌无效"}


def test_write_accepts_the_exact_configured_token() -> None:
    response = make_client("server-secret").post(
        "/probe",
        headers={"X-Clade-Admin-Token": "server-secret"},
    )
    assert response.status_code == 200
```

- [ ] **Step 2: Run the tests and verify RED**

Run from `backend`:

```powershell
.venv\Scripts\python.exe -m pytest app/security/tests/test_admin_token.py -q
```

Expected: collection fails because `app.security.admin_token` does not exist.

- [ ] **Step 3: Add the settings field and minimal dependency**

Add this field beside the network settings in `Settings`:

```python
clade_admin_token: str | None = Field(default=None, alias="CLADE_ADMIN_TOKEN")
```

Create `backend/app/security/admin_token.py`:

```python
from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request

from ..core.config import Settings, get_settings


def require_admin_token(
    request: Request,
    x_clade_admin_token: Annotated[
        str | None,
        Header(alias="X-Clade-Admin-Token"),
    ] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    if request.method in {"GET", "HEAD"}:
        return

    configured = settings.clade_admin_token
    if not configured:
        raise HTTPException(status_code=503, detail="管理员功能未启用")

    supplied = x_clade_admin_token or ""
    if not secrets.compare_digest(supplied, configured):
        raise HTTPException(status_code=403, detail="管理员令牌无效")
```

- [ ] **Step 4: Run focused and configuration tests**

```powershell
.venv\Scripts\python.exe -m pytest app/security/tests/test_admin_token.py app/core/tests/test_network_policy.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Scan the dependency for token leakage**

```powershell
rg -n "clade_admin_token|X-Clade-Admin-Token|logger|print" app/security/admin_token.py app/core/config.py
```

Expected: the token is read and compared, but no logger or print statement contains it.

- [ ] **Step 6: Commit Task 1**

```powershell
git add backend/app/core/config.py backend/app/security/admin_token.py backend/app/security/tests/test_admin_token.py
git commit -m "security: add fail-closed admin token policy"
```

---

### Task 2: Protect every state-changing admin route at the router boundary

**Files:**
- Modify: `backend/app/api/admin_routes.py:1-25`
- Create: `backend/app/api/tests/test_admin_auth.py`

**Interfaces:**
- Consumes: `require_admin_token` from Task 1.
- Produces: router-wide protection for current and future non-`GET`/`HEAD` `/api/admin` endpoints.

- [ ] **Step 1: Write route-level failing tests**

Create `backend/app/api/tests/test_admin_auth.py`:

```python
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ...core.config import get_settings
from ..admin_routes import router


WRITE_CASES = [
    ("post", "/api/admin/reset", {"keep_saves": True, "keep_map": True}),
    ("post", "/api/admin/drop-database", {"confirm": False}),
    ("post", "/api/admin/optimize-database", {}),
    ("post", "/api/admin/cleanup-habitat-history", {"confirm": False}),
    ("post", "/api/admin/create-indexes", None),
]


def make_client(token: str | None) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
        clade_admin_token=token
    )
    return TestClient(app)


@pytest.mark.parametrize(("method", "path", "body"), WRITE_CASES)
def test_every_admin_write_fails_closed_without_server_token(
    method: str,
    path: str,
    body: dict | None,
) -> None:
    response = getattr(make_client(None), method)(path, json=body)
    assert response.status_code == 503


def test_wrong_token_is_rejected_before_handler_execution() -> None:
    with patch("app.api.admin_routes.environment_repository.ensure_indexes") as ensure:
        response = make_client("right").post(
            "/api/admin/create-indexes",
            headers={"X-Clade-Admin-Token": "wrong"},
        )
    assert response.status_code == 403
    ensure.assert_not_called()


def test_correct_token_reaches_a_safe_idempotent_handler() -> None:
    with patch(
        "app.api.admin_routes.environment_repository.ensure_indexes",
        return_value={"idx_habitats": True},
    ):
        response = make_client("right").post(
            "/api/admin/create-indexes",
            headers={"X-Clade-Admin-Token": "right"},
        )
    assert response.status_code == 200
    assert response.json()["created_count"] == 1


def test_health_read_remains_available_without_token() -> None:
    response = make_client(None).get("/api/admin/health")
    assert response.status_code == 200
```

- [ ] **Step 2: Run the route tests and verify RED**

```powershell
.venv\Scripts\python.exe -m pytest app/api/tests/test_admin_auth.py -q
```

Expected: write requests reach their handlers instead of returning `503`/`403`.

- [ ] **Step 3: Apply the dependency once at the router**

Update the imports and router declaration in `admin_routes.py`:

```python
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from ..security.admin_token import require_admin_token

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin_token)],
)
```

Do not add per-endpoint token parameters. Router-level placement is what protects future write routes.

- [ ] **Step 4: Run route, dependency, and OpenAPI checks**

```powershell
.venv\Scripts\python.exe -m pytest app/api/tests/test_admin_auth.py app/security/tests/test_admin_token.py -q
.venv\Scripts\python.exe -c "from app.main import app; s=app.openapi(); assert any(p.get('name') == 'X-Clade-Admin-Token' for p in s['paths']['/api/admin/drop-database']['post']['parameters'])"
```

Expected: tests pass and the header appears in the write endpoint's OpenAPI operation.

- [ ] **Step 5: Commit Task 2**

```powershell
git add backend/app/api/admin_routes.py backend/app/api/tests/test_admin_auth.py
git commit -m "security: protect admin write routes"
```

---

### Task 3: Add the frontend admin-header API contract

**Files:**
- Modify: `frontend/src/services/api/admin.ts:1-30`
- Create: `frontend/src/services/api/admin.test.ts`

**Interfaces:**
- Consumes: existing `http.post` request configuration.
- Produces: `resetWorld(adminToken, keepSaves, keepMap)` and `dropDatabase(adminToken)`.

- [ ] **Step 1: Write failing API boundary tests**

Create `frontend/src/services/api/admin.test.ts`:

```typescript
import { beforeEach, describe, expect, it, vi } from "vitest";

const { post } = vi.hoisted(() => ({ post: vi.fn() }));

vi.mock("./base", () => ({
  http: {
    get: vi.fn(),
    post,
  },
}));

import { dropDatabase, resetWorld } from "./admin";

describe("admin API token boundary", () => {
  beforeEach(() => post.mockReset());

  it("sends the token only in the admin header", async () => {
    post.mockResolvedValue({ success: true });
    await dropDatabase("memory-only-token");

    expect(post).toHaveBeenCalledWith(
      "/api/admin/drop-database",
      { confirm: true },
      { headers: { "X-Clade-Admin-Token": "memory-only-token" } }
    );
    expect(JSON.stringify(post.mock.calls[0][1])).not.toContain("memory-only-token");
  });

  it("uses the same header contract for world reset", async () => {
    post.mockResolvedValue({ success: true });
    await resetWorld("memory-only-token", true, false);

    expect(post).toHaveBeenCalledWith(
      "/api/admin/reset",
      { keep_saves: true, keep_map: false },
      { headers: { "X-Clade-Admin-Token": "memory-only-token" } }
    );
  });
});
```

- [ ] **Step 2: Run the test and verify RED**

```powershell
npm run test:run -- src/services/api/admin.test.ts
```

Expected: existing functions do not accept or send the token.

- [ ] **Step 3: Implement the request configuration**

Add this helper and update the two write functions:

```typescript
const adminRequestConfig = (adminToken: string) => ({
  headers: { "X-Clade-Admin-Token": adminToken },
});

export async function resetWorld(
  adminToken: string,
  keepSaves: boolean,
  keepMap: boolean
): Promise<{ success: boolean }> {
  return http.post(
    "/api/admin/reset",
    { keep_saves: keepSaves, keep_map: keepMap },
    adminRequestConfig(adminToken)
  );
}

export async function dropDatabase(adminToken?: string): Promise<{ success: boolean }> {
  return http.post(
    "/api/admin/drop-database",
    { confirm: true },
    adminToken ? adminRequestConfig(adminToken) : undefined
  );
}
```

- [ ] **Step 4: Run the API test and type checker**

```powershell
npm run test:run -- src/services/api/admin.test.ts
npx tsc --noEmit
```

Expected: the API tests and TypeScript both pass. The temporary optional parameter keeps the existing call site buildable until Task 4 adds the required memory-only input.

- [ ] **Step 5: Commit Task 3**

```powershell
git add frontend/src/services/api/admin.ts frontend/src/services/api/admin.test.ts
git commit -m "security: send admin token in request headers"
```

---

### Task 4: Keep the token only in AdminPanel memory and document setup

**Files:**
- Modify: `frontend/src/services/api/admin.ts:1-30`
- Modify: `frontend/src/components/AdminPanel.tsx:1-110`
- Create: `frontend/src/components/AdminPanel.test.tsx`
- Modify: `README.md`

**Interfaces:**
- Consumes: `dropDatabase(adminToken)` from Task 3 and `ApiError.status` from `frontend/src/services/api/base.ts`.
- Produces: a password input whose value lives only in component state and actionable `403`/`503` feedback.

- [ ] **Step 1: Write failing component tests**

Create `frontend/src/components/AdminPanel.test.tsx`:

```typescript
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { checkHealth, dropDatabase } = vi.hoisted(() => ({
  checkHealth: vi.fn(),
  dropDatabase: vi.fn(),
}));

vi.mock("@/services/api", () => ({ checkHealth, dropDatabase }));

import { AdminPanel } from "./AdminPanel";

describe("AdminPanel token handling", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    checkHealth.mockResolvedValue({ api: "online", database: "ok" });
    vi.stubGlobal("confirm", vi.fn(() => true));
    vi.stubGlobal("alert", vi.fn());
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("passes the in-memory token to the destructive request", async () => {
    dropDatabase.mockRejectedValue(
      Object.assign(new Error("管理员令牌无效"), { status: 403 })
    );
    render(<AdminPanel onClose={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("管理员令牌"), {
      target: { value: "memory-only-token" },
    });
    fireEvent.change(screen.getByPlaceholderText("输入 DELETE 确认"), {
      target: { value: "DELETE" },
    });
    fireEvent.click(screen.getByRole("button", { name: /执行重置/ }));

    await waitFor(() =>
      expect(dropDatabase).toHaveBeenCalledWith("memory-only-token")
    );
  });

  it("does not write the token to browser storage", () => {
    const localSet = vi.spyOn(Storage.prototype, "setItem");
    render(<AdminPanel onClose={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("管理员令牌"), {
      target: { value: "memory-only-token" },
    });
    expect(localSet).not.toHaveBeenCalled();
  });

  it.each([
    [503, "服务端未配置管理员令牌"],
    [403, "管理员令牌无效"],
  ])("shows actionable feedback for status %i", async (status, message) => {
    dropDatabase.mockRejectedValue(Object.assign(new Error(message), { status }));
    render(<AdminPanel onClose={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("管理员令牌"), {
      target: { value: "wrong" },
    });
    fireEvent.change(screen.getByPlaceholderText("输入 DELETE 确认"), {
      target: { value: "DELETE" },
    });
    fireEvent.click(screen.getByRole("button", { name: /执行重置/ }));
    await waitFor(() => expect(alert).toHaveBeenCalledWith(expect.stringContaining(message)));
  });
});
```

- [ ] **Step 2: Run the component test and verify RED**

```powershell
npm run test:run -- src/components/AdminPanel.test.tsx
```

Expected: there is no administrator-token input and `dropDatabase` is called without an argument.

- [ ] **Step 3: Add memory-only state and status-specific feedback**

Add state:

```typescript
const [adminToken, setAdminToken] = useState("");
```

At the same time, remove the temporary optional marker from the Task 3 API:

```typescript
export async function dropDatabase(adminToken: string): Promise<{ success: boolean }> {
  return http.post(
    "/api/admin/drop-database",
    { confirm: true },
    adminRequestConfig(adminToken)
  );
}
```

Add this input before the existing `DELETE` confirmation:

```tsx
<label className="admin-token-field">
  <span>管理员令牌</span>
  <input
    aria-label="管理员令牌"
    type="password"
    autoComplete="off"
    value={adminToken}
    onChange={(event) => setAdminToken(event.target.value)}
    placeholder="仅保存在当前窗口内存中"
  />
</label>
```

Call `dropDatabase(adminToken)` and use this error mapping:

```typescript
} catch (err: unknown) {
  const status = typeof err === "object" && err !== null && "status" in err
    ? Number(err.status)
    : 0;
  const message =
    status === 503
      ? "服务端未配置管理员令牌"
      : status === 403
        ? "管理员令牌无效"
        : err instanceof Error
          ? err.message
          : "未知错误";
  alert("❌ 操作失败: " + message);
}
```

Disable the destructive button while `adminToken.length === 0`. Do not add storage effects or props that lift the token above `AdminPanel`.

- [ ] **Step 4: Document safe token setup**

Add a README administrator section with this PowerShell flow:

```powershell
$env:CLADE_ADMIN_TOKEN = Read-Host "请输入本次启动使用的管理员令牌"
.\start.ps1
```

State that the same value is entered in “开发者工具”, that an unset server token disables write operations with `503`, and that `start.ps1` never prints or injects it into the frontend bundle.

- [ ] **Step 5: Run frontend tests, type checking, and persistence scans**

```powershell
npm run test:run -- src/services/api/admin.test.ts src/components/AdminPanel.test.tsx
npm run lint
npm run build
rg -n "CLADE_ADMIN_TOKEN|X-Clade-Admin-Token|localStorage|sessionStorage" src README.md ..\start.ps1
```

Expected: tests/build/lint pass; token storage matches occur only in negative test assertions or unrelated existing session metadata, never in AdminPanel production code.

- [ ] **Step 6: Commit Task 4**

```powershell
git add frontend/src/services/api/admin.ts frontend/src/components/AdminPanel.tsx frontend/src/components/AdminPanel.test.tsx README.md
git commit -m "feat: request admin token for destructive actions"
```

---

### Task 5: Complete Phase 2B-1 regression verification

**Files:**
- Modify only if a Phase 2B-1 regression is found in files listed above.
- Create report: `.superpowers/sdd/phase-2b1-verification.md`

**Interfaces:**
- Consumes: Tasks 1-4.
- Produces: a reviewed, verified admin-token boundary.

- [ ] **Step 1: Run all frontend gates**

```powershell
cd frontend
npm run lint
npm run test:run
npm run build
```

Expected: lint exits 0 at or below 162 warnings, every Vitest test passes, and build exits 0.

- [ ] **Step 2: Run focused backend coverage**

```powershell
cd ..\backend
.venv\Scripts\python.exe -m pytest app/security/tests/test_admin_token.py app/api/tests/test_admin_auth.py app/api/tests/test_api_integration.py -q
.venv\Scripts\python.exe -m pytest --collect-only -q
```

Expected: every new admin-token test passes; only the two accepted historical integration failures may remain in the integration selection; collection is greater than the Phase 2A count of 420.

- [ ] **Step 3: Run the complete backend baseline**

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Expected: no new admin-token failure and no more than `14 failed, 9 errors`.

- [ ] **Step 4: Run secret and scope scans**

```powershell
cd ..
rg -n "CLADE_ADMIN_TOKEN|X-Clade-Admin-Token" README.md start.ps1 backend frontend/src
rg -n "localStorage|sessionStorage|console\.(log|debug|info|warn|error).*token|token.*console\.(log|debug|info|warn|error)" frontend/src
git diff --check 75eca7c..HEAD
git status --short
```

Expected: no production persistence/logging of the token, no token value in documentation or scripts, clean diff, and a clean worktree after commits.

- [ ] **Step 5: Write the verification report**

Record exact commands, exit codes, test totals, historical baseline comparison, scan interpretation, commit range, and worktree status in `.superpowers/sdd/phase-2b1-verification.md`. Do not create an empty verification commit.

The plan is complete when every task has its own review gate and Phase 2B-1 is ready to become the base for Phase 2B-2.
