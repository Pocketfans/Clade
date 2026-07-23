# M5 Final Speciation Trigger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move final speciation type/chance calculation and its single random trigger out of `process_async` without changing formulas, side effects or early returns.

**Architecture:** Extend `_CandidateWork` with the downstream generation, type, chance and cluster values. Add one bounded chance calculator and one small roll applicator so every new non-coordinator function stays below 250 lines.

**Tech Stack:** Python 3.12, dataclasses and pytest.

## Constraints

- Preserve generation, early floor, death-rate penalty and all geographic, map, ecological, event, overlap and coevolution branches.
- Preserve migration-history cleanup, ecological population rejection, AI boost, background penalty, type text and logging order.
- Preserve exactly one final random draw after chance logging.
- On failed roll, preserve pressure accumulation, repository upsert and early return; on success, preserve pressure reset and cooldown timestamp.
- Leave global/candidate population reconciliation and all offspring planning in phase 11.
- Reuse `_CandidateWork`; add no dependency, public interface, schema or gameplay change.

## Task

- [ ] Add failing focused tests for channel bonuses, early returns and state mutations.
- [ ] Add failing tests for migration, AI/background modifiers and final random call order.
- [ ] Implement the bounded calculator and roll applicator and replace only the approved block.
- [ ] Compare normalized critical AST and run focused plus all species tests.
- [ ] Review at most twice and enforce line-count gates.
- [ ] Run one backend full suite and one frontend test/build/lint gate.
- [ ] Commit as `refactor(backend): extract final speciation trigger`, ordinary-push and update only PR #15.
