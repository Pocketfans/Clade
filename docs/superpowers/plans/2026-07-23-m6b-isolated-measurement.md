# M6B Isolated Measurement Plan

**Goal:** Collect benchmark timing, Python allocation peaks, database write counts and existing per-Stage metrics only while an explicit benchmark workload is running.

**Architecture:** Add a standalone measurement module. An async case wrapper receives a workload callback and returns the existing versioned `BenchmarkCase`. It uses injectable clocks and a memory probe for deterministic tests, an optional SQLAlchemy event counter for an isolated engine, and an accumulator for existing `PipelineMetrics`. Every listener and tracer started by the wrapper is released in `finally`; ordinary simulation turns do not import or activate the collector.

**Scope**

- Add `backend/app/simulation/performance_measurement.py`.
- Add `backend/app/simulation/tests/test_performance_measurement.py`.
- Do not modify `SimulationEngine`, `Pipeline`, repositories, database schema, saves or APIs.
- Do not generate scale scenarios or run a real 100-turn benchmark in this batch.
- Do not add dependencies or contact AI/network services.

**Steps**

1. Write failing tests for stable Stage aggregation, exact injected timing/memory evidence, SQL write/row counts and cleanup after errors.
2. Implement environment capture with nullable best-effort GPU identity.
3. Implement the Stage accumulator and opt-in SQLAlchemy write counter.
4. Implement the async case measurement wrapper and evidence carrier.
5. Run focused tests, backend full and frontend test/build/lint; review the current diff at most twice.
6. Create one implementation commit, ordinary-push the Fork branch and update only PR #15.

**Stop conditions**

- Stop if measurement requires changing ordinary turn execution or repository write behavior.
- Stop if SQL listeners cannot be removed reliably after success and failure.
- Stop if a metric would need to be guessed or a new system package installed.
