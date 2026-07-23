# M5 Rule-Fallback Description Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move queued description enhancement for rule-generated species out of `process_async` without changing queue order, processing limits, persistence order, error handling or cleanup.

**Architecture:** Add async `enhance_rule_fallback_descriptions(...)` to `speciation_process.py`. Pass the existing mutable pending list, description enhancer and repository upsert callback explicitly.

**Tech Stack:** Python 3.12, asyncio and pytest.

## Constraints

- Preserve the empty-list no-op, queue order, exact `queue_for_enhancement(...)` arguments, `max_items=20`, `timeout_per_item=25.0`, enhanced-species upsert order, exception swallowing/logging and unconditional clearing after attempted processing.
- Do not change prompts, AI routing, timeouts, queue limits, database formats, public interfaces, dependencies or gameplay.

## Task

- [ ] Add failing async tests for empty input, successful ordered enhancement and failed processing cleanup.
- [ ] Run the focused process test and verify import failure for `enhance_rule_fallback_descriptions`.
- [ ] Add the async helper and replace only the inline description-enhancement block.
- [ ] Run focused and all species tests.
- [ ] Compare normalized moved AST, run `git diff --check` and review the current diff.
- [ ] Run one backend full suite and one frontend test/build/lint gate.
- [ ] Commit as `refactor(backend): extract fallback description enhancement`, ordinary-push and update only PR #15.
