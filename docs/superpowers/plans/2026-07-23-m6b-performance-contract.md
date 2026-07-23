# M6B Performance Contract Plan

**Goal:** Add the versioned, validated JSON contract and environment-aware regression comparator required before collecting real benchmark evidence.

**Scope**

- Add `backend/app/simulation/performance_baseline.py`.
- Add `backend/app/simulation/tests/test_performance_baseline.py`.
- Do not run real long benchmarks in this batch.
- Do not change simulation behavior, repositories, schemas, saves, APIs or dependencies.

**Steps**

1. Write failing tests for JSON round trips, invalid/missing values, complete-case detection, environment mismatch and threshold comparisons.
2. Implement immutable benchmark environment, Stage, case and report models.
3. Implement UTF-8 JSON read/write and the required-case completeness check.
4. Implement an environment-aware comparator with relative thresholds and absolute noise floors.
5. Run focused tests, backend full and frontend test/build/lint; review the current diff at most twice.
6. Create one implementation commit, ordinary-push the Fork branch and update only PR #15.

**Stop conditions**

- Stop if this requires runtime simulation changes, a new dependency or a persisted game/save schema change.
- Stop if comparison requires fabricated hardware or unavailable measurements.
- Stop if a stable metric meaning cannot be expressed without implementing the later collector.
