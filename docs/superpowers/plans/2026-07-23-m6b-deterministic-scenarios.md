# M6B Deterministic Scenario Plan

**Goal:** Define and execute reproducible core benchmark scenarios for 10,
100 and 500 species plus a fixed-seed 100-turn stability run.

**Architecture:** Add a benchmark-only scenario module. It generates valid
species with a local seeded random generator, initializes an already-isolated
SQLite engine, and runs the existing lightweight core pipeline
(`ParsePressuresStage`, `MapEvolutionStage`, `FetchSpeciesStage`,
`FinalizeStage`). The runner collects each turn's existing `PipelineMetrics`
through the isolated measurement wrapper. Python and NumPy global random state
is restored after every run, and AI/embedding integration remains disabled.
The runner refuses to start unless the caller explicitly marks a dedicated
benchmark process and supplies that process's current application engine.

**Scope**

- Add `backend/app/simulation/performance_scenarios.py`.
- Add `backend/app/simulation/tests/test_performance_scenarios.py`.
- Do not modify `SimulationEngine`, `Pipeline`, repositories, database schema,
  save behavior or APIs.
- Do not run or check in real timing evidence in this batch.
- Do not add dependencies or contact AI/network services.

**Stable scenarios**

- `scale-10`: 10 species, 1 turn, seed 42.
- `scale-100`: 100 species, 1 turn, seed 42.
- `scale-500`: 500 species, 1 turn, seed 42.
- `seeded-100-turn`: 10 species, 100 turns, seed 42.

**Steps**

1. Write failing tests for the exact scenario matrix, deterministic species
   generation, isolated database initialization, successful measured execution
   and restoration of caller random state.
2. Implement immutable scenario definitions and deterministic species data.
3. Implement guarded isolated-database initialization without deleting or
   replacing existing data.
4. Build the benchmark-only core engine and collect all per-turn metrics.
5. Run focused tests, backend full and frontend test/build/lint; review the
   current diff at most twice.
6. Create one implementation commit, ordinary-push the Fork branch and update
   only PR #15.

**Stop conditions**

- Stop if a benchmark requires changing ordinary turn execution or repository
  behavior.
- Stop if the supplied database cannot be proven empty and isolated.
- Stop if deterministic execution requires AI/network access, a new
  dependency, or guessed measurements.
