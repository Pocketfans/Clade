# Phase 2C-1 Security Verification

**Verification date:** 2026-07-15 (Asia/Shanghai)

**Branch:** `phase-2c-outbound-url-security`

**Handoff base:** `9f0c26bf30321f19db76828b61daa12f3f5ed2ad`

**Final code-fix tip:** `fdd6a3d`

**Complete handoff range after this report refresh:** `9f0c26bf30321f19db76828b61daa12f3f5ed2ad..HEAD`

## Outcome

Phase 2C-1 configuration-probe and persistent local-AI-control gates pass after
the final review fixes. The outbound policy now rejects site-local, reserved and
other IANA special-purpose IPv6 ranges independently of Python 3.12's
`is_global` classification, including mapped and transition forms with embedded
IPv4. The model-list route now maps malformed HTTP-200 JSON schemas to the fixed,
redacted `outbound_bad_response` 502 contract.

This is not a Phase 2C completion or release approval.

```text
Phase 2C-1 protects configuration probes and the persistent local-AI control.
Phase 2C is not complete: actual AI, load-balancing, streaming, and embedding requests remain for Phase 2C-2.
This branch must not be merged or released before Phase 2C-2 and final review.
```

## Final-review TDD evidence

- URL-policy RED: 13 failures reproduced the Python 3.12 `fec0::/10`, NAT64,
  mapped/compatible/6to4/Teredo, DNS and mixed-answer gaps; 65 existing cases
  still passed in that RED run.
- Model-schema RED: all 6 malformed HTTP-200 cases failed as expected: `data`
  null/string, null/scalar list items, missing `id`, and non-string `id`.
- Focused GREEN: `backend/app/security/tests/test_outbound_url.py` passed 78/78;
  the selected malformed-schema, non-200 and route-redaction cases passed 8/8.
- Related GREEN: security tests plus API integration passed 301 tests with one
  existing skip and two focused-suite warnings.

## Backend gates

All fresh commands used the existing Python environment at
`..\phase-2b2-save-path-boundary\backend\.venv\Scripts\python.exe`; no dependency
installation or update was performed.

| Command | Exit | Fresh post-fix evidence |
| --- | ---: | --- |
| `& $PYTHON -m pytest backend/app -q` | 0 | 693 passed, 2 skipped, 45 warnings; 0 failures and 0 collection errors |
| Canonical fresh-process inline plugin guard from the backend directory | 0 | Loaded and registered exactly 6 built-in plugins |

The two skips are the existing Windows symlink skips. The 45 warnings equal the
allowed ceiling and do not exceed it.

### Retained stale planned-path failure and approved substitution

The Phase 2C-1 plan names
`backend/app/core/tests/test_plugin_registry_fresh_process.py`, but that file is
absent from this repository and its searched history. The original planned
command was run during Task 7 and exited 1 with zero tests because the path does
not exist. That historical failure remains recorded here; it is not hidden or
relabeled as a passing test.

The approved canonical guard comes from
`docs/superpowers/plans/2026-07-14-backend-baseline-recovery.md`, which specifies
an inline fresh-process import and no new permanent test file. It was run again
after the final-review fix from `backend`:

```powershell
$Python = (Resolve-Path "..\phase-2b2-save-path-boundary\backend\.venv\Scripts\python.exe").Path
Push-Location backend
& $Python -c "from app.services.embedding_plugins import PluginRegistry, load_all_plugins; expected={'ancestry','behavior_strategy','evolution_space','food_web','prompt_optimizer','tile_biome'}; loaded=set(load_all_plugins()); registered=set(PluginRegistry.list_plugins()); assert loaded == expected; assert registered == expected; print(sorted(registered))"
Pop-Location
```

It exited 0 and printed the six expected plugin names. This is the approved
substitution for the same fresh-process registration invariant.

## Frontend gates

Commands ran fresh after the final code fix from `frontend` using the already
linked dependencies.

| Command | Exit | Fresh post-fix evidence |
| --- | ---: | --- |
| `npm run test:run` | 0 | 12 test files passed; 84 tests passed; 0 failed |
| `npm run lint` | 0 | 0 errors, 162 warnings |
| `npx tsc --noEmit` | 0 | TypeScript check completed with no output |
| `npm run build` | 0 | TypeScript and Vite production build completed; 4,399 modules transformed |

The lint warning count equals the allowed ceiling and does not exceed it. The
build emitted the existing informational warning that one settings module is
both dynamically and statically imported; it did not fail the build.

## Repository hygiene and redaction scan

| Command | Exit | Fresh post-fix evidence |
| --- | ---: | --- |
| `git diff --check` | 0 | No whitespace errors |
| `rg -n "admin-secret\|sk-unsaved\|resolver sentinel\|upstream echoed\|upstream-schema-sentinel\|upstream-body-sentinel" backend/app frontend/src docs/api-guides -g '!**/test_*.py' -g '!**/*.test.ts' -g '!**/*.test.tsx'` | 1 | No production or API-guide matches; exit 1 is ripgrep's no-match result |
| `git diff --name-only 9f0c26bf30321f19db76828b61daa12f3f5ed2ad..HEAD -- backend/app/ai/model_router.py backend/app/services/system/embedding.py` | 0 | No forbidden-path changes |
| `git status --short` before this report refresh | 0 | Clean worktree |

The two route-level tests no longer claim to inject an upstream response body
when their mock cannot provide one. The transport-level
`test_fetch_json_response_non_200_skips_body_and_closes_one_request` remains the
concrete proof that a non-200 response performs exactly one request and reads
zero body bytes.

No API key, administrator token, sensitive query URL, upstream response body or
raw exception text is reproduced in this report.

## Commit ranges and physical counts

The complete handoff range is
`9f0c26bf30321f19db76828b61daa12f3f5ed2ad..HEAD`. After committing this report
refresh, it contains **15 physical commits**:

- Design range `9f0c26bf30321f19db76828b61daa12f3f5ed2ad..89eec7b`: 1 commit.
- Plan range `89eec7b..d41f7e3`: 1 commit.
- Implementation, task verification and review-hardening range
  `d41f7e3..fdd6a3d`: 12 commits, ending at the final code fix.
- This final verification-report refresh: 1 commit at `HEAD`.

The history is counted as it physically exists; task checkpoints are not used
as a substitute for commit count.

## Handoff

Proceed to a separate Phase 2C-2 design review. Keep this branch isolated and do
not merge or release it at this checkpoint.
