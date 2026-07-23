# M5 Offspring Planning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move successful-candidate offspring planning and entry assembly out of `process_async` without changing population allocation, random calls, persistence or payloads.

**Architecture:** Add the design-approved internal `_OffspringPlan`. A bounded planner handles population reconciliation, regional pressure, offspring count, retention, lineage codes, parent persistence and tile assignment; a thin builder preserves entry order and delegates each payload to `build_offspring_ai_entry`.

**Tech Stack:** Python 3.12, dataclasses and pytest.

## Constraints

- Preserve candidate/global population clamping, parent/child pool arithmetic and every early return.
- Preserve cluster pressure values, dynamic and legacy offspring-count paths, callback arguments and random call order.
- Preserve lineage-code generation, immediate `existing_codes` mutation, parent population write and repository upsert order.
- Preserve cluster/fallback tile allocation and `zip(new_codes, pop_splits)` truncation/order.
- Preserve every argument and object identity passed to `build_offspring_ai_entry`.
- Leave entry partitioning, AI execution and materialization outside this batch.
- Add no dependency, public interface, schema, formula or gameplay change.

## Task

- [ ] Add failing tests for population clamping, cluster pressure and dynamic/legacy offspring counts.
- [ ] Add failing tests for all pool early returns, code mutation, parent persistence and tile allocation.
- [ ] Add a focused entry-assembly order/payload delegation test.
- [ ] Implement `_OffspringPlan`, the bounded planner and thin entry builder.
- [ ] Compare normalized critical AST; run focused and all species tests.
- [ ] Review at most twice and enforce line-count gates.
- [ ] Run one backend full suite and one frontend test/build/lint gate.
- [ ] Commit as `refactor(backend): extract offspring planning`, ordinary-push and update only PR #15.
