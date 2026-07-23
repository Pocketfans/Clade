# M5 Candidate State Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move candidate population, tile, cluster, isolation and death-rate normalization out of `process_async` without changing synchronization mutations or downstream values.

**Architecture:** Add internal `_CandidateWork` and `normalize_candidate_state(...)` to `speciation_process.py`. The carrier contains only values already produced inline and is not a public API.

**Tech Stack:** Python 3.12, dataclasses and pytest.

## Constraints

- Preserve pre-screened candidate-data identity, required-key access, tile/global population synchronization, species population mutation and candidate-population cap.
- Preserve weighted candidate death rate, threshold calculation, 60% valid-cluster filter and isolation downgrade.
- Preserve legacy cache fallback, tile-total synchronization, configured inclusive tile filters and selected-population sum.
- Return the exact candidate/global population, tile maps/sets, death rate, isolation flag, gradient and clusters consumed by later formulas.
- Do not move or change direct-offspring checks, global minimum-population check, dynamic eligibility threshold, cooldown, pressure/probability formulas, schemas, dependencies or public interfaces.

## Task

- [ ] Add failing focused tests for pre-screened synchronization/capping/valid-cluster paths and fallback cache/filter paths.
- [ ] Verify the new boundary fails because it is absent.
- [ ] Implement `_CandidateWork`, the normalization function and replace only the inline normalization block.
- [ ] Run focused and all species tests; compare characterized state and normalized moved AST where applicable.
- [ ] Review the current diff at most twice and enforce line-count gates.
- [ ] Run one backend full suite and one frontend test/build/lint gate.
- [ ] Commit as `refactor(backend): extract candidate state normalization`, ordinary-push and update only PR #15.
