# M5 Offspring AI Entry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move construction of one offspring AI request entry out of `process_async` without changing payload fields, defaults, hashes, callback order or object identity.

**Architecture:** Add bounded `build_offspring_ai_entry(...)` to `speciation_process.py`. Pass the already planned offspring, region data, service callbacks/state, rules and naming generator explicitly; append its returned dictionary in the existing loop.

**Tech Stack:** Python 3.12 and pytest.

## Constraints

- Preserve history truncation, biological-domain inference, tile/cluster pressure branches and environment modifier merge order.
- Preserve rule preprocessing arguments, naming-seed formula and generator call order.
- Preserve every payload key/value/default, summary callback condition, dormant-gene arguments, organ catalog formatting and mature-organ context.
- Preserve parent/new-code/population/assigned-tile identities and request-turn value.
- Do not change formulas, randomness, AI prompts, public interfaces, schemas, dependencies or persisted formats.

## Task

- [ ] Add failing focused tests for cluster and fallback region branches, modifier merging, history truncation, naming order and full entry structure.
- [ ] Verify the new boundary fails because it is absent.
- [ ] Implement the bounded helper and replace only the inner entry-building block.
- [ ] Run focused and all species tests; compare normalized moved AST.
- [ ] Review the current diff at most twice and enforce the 250-line responsibility gate.
- [ ] Run one backend full suite and one frontend test/build/lint gate.
- [ ] Commit as `refactor(backend): extract offspring AI entry builder`, ordinary-push and update only PR #15.
