# M5 Candidate Eligibility and Pressure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move candidate eligibility and environmental-pressure evaluation out of `process_async` without changing early returns, thresholds, plant/radiation behavior or random draw order.

**Architecture:** Extend existing internal `_CandidateWork` with downstream eligibility values. Add bounded `evaluate_candidate_eligibility(...)` and `evaluate_environmental_pressure(...)`; each returns updated work or `None` for the existing `continue`.

**Tech Stack:** Python 3.12, dataclasses and pytest.

## Constraints

- Preserve threshold multipliers, strict comparison boundaries, cooldown behavior, early-game cooldown bypass, evolution-potential fallback and candidate logs.
- Preserve early/late pressure thresholds, giant-population and accumulated-pressure branches, plant milestone checks and readiness pressure mutation.
- Preserve radiation chance terms/caps/penalties, short-circuit random call position, local type assignments/logs and legacy death-rate early return.
- Leave final generation/base chance, channel bonuses, migration/background penalties and final random roll in phase 10.
- Reuse `_CandidateWork`; do not add a third carrier, dependency, public interface or schema.

## Task

- [ ] Add failing focused tests for eligibility pass and each early-return class.
- [ ] Add failing tests for pressure branches, plant readiness/milestone, radiation random order and legacy death-rate return.
- [ ] Implement both bounded functions and replace only the approved blocks.
- [ ] Run focused and all species tests; compare normalized AST and characterized state/random calls.
- [ ] Review at most twice and enforce line-count gates.
- [ ] Run one backend full suite and one frontend test/build/lint gate.
- [ ] Commit as `refactor(backend): extract candidate eligibility and pressure`, ordinary-push and update only PR #15.
