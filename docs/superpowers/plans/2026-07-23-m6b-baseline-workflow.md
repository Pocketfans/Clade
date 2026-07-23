# M6B Baseline Workflow Plan

**Goal:** Turn the existing contract, collector and deterministic scenarios
into a safe operator command, record the first complete baseline, and document
repeatable regression comparison.

**Architecture:** A parent command creates one temporary directory and launches
one fresh Python child process per stable scenario. Before each child imports
the application, the parent points `DATABASE_URL` at a unique temporary SQLite
file and sets the explicit isolation marker. The child runs the existing
scenario, performs a real save/load round trip inside a temporary save
directory, and writes one case result. The parent validates all case results,
captures best-effort GPU identity/video memory, and writes one versioned report
only to the explicitly supplied output path.

**Scope**

- Add `backend/app/simulation/performance_benchmark.py`.
- Add `backend/app/simulation/tests/test_performance_benchmark.py`.
- Extend `performance_scenarios.py` and its tests with real save/load metrics.
- Add `docs/performance/baseline-v1.json`.
- Add `docs/performance-baseline.md`.
- Do not modify ordinary simulation, repositories, database schema, save
  format or APIs.
- Do not add dependencies or contact AI/network services.

**Commands**

- Generate:
  `python -m app.simulation.performance_benchmark generate --output PATH`
- Compare:
  `python -m app.simulation.performance_benchmark compare --baseline OLD --current NEW`

**Steps**

1. Write failing tests for save/load evidence, child environment isolation,
   complete report assembly, GPU fallback and comparison exit behavior.
2. Add save size/save duration/load duration to each deterministic scenario.
3. Implement the private worker and public generate/compare commands.
4. Run focused tests, backend full and frontend test/build/lint; review the
   current diff at most twice.
5. Commit the tested tooling.
6. Run the real generate command using that tooling commit SHA, validate the
   complete report, and compare it with an immediate second run when practical.
7. Add operator documentation and the checked-in baseline as a separate
   evidence commit.
8. Ordinary-push the Fork branch and update only PR #15.

**Stop conditions**

- Stop if any child touches the normal database or save directory.
- Stop if the complete report lacks any stable case or required metric.
- Stop if save/load cannot restore the expected turn and species count.
- Stop if a metric would need to be guessed, AI/network access is attempted,
  or a new dependency is required.
