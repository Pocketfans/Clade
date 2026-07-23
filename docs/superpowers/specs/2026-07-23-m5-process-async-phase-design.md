# M5 `process_async` Phase Split Design

## Goal

Turn the 1547-line `SpeciationService.process_async` method into a coordinator of at most 500 lines and bring `speciation.py` to at most 3000 lines without changing candidate selection, randomness, AI behavior, repository writes, events, callbacks or public callers.

## Selected Architecture

Create one internal module, `speciation_process.py`, containing bounded phase functions. `SpeciationService.process_async` remains the caller-facing coordinator and passes its existing bound methods/state to the phase functions. Repository singletons and module globals are passed explicitly when a phase uses them, preserving current runtime and test override points.

For the candidate pipeline only, introduce at most two underscore-prefixed internal data carriers when the corresponding phase is extracted:

- `_CandidateWork`: normalized per-species candidate, population and isolation data;
- `_OffspringPlan`: lineage codes, population splits, tile assignments and pressure context.

These are internal return values, not service constructor dependencies or public interfaces.

## Extraction Order

Extract one independently tested behavior per batch, in increasing mutation and control-flow risk:

1. partition prepared entries into background, active and deferred groups;
2. generate rule-based content for background entries;
3. execute active AI batches and flatten matched results;
4. enhance queued rule-fallback descriptions;
5. materialize one background result, then its loop wrapper;
6. materialize one active result, then its loop wrapper;
7. build one offspring AI entry from an existing offspring plan;
8. normalize candidate population, tile, cluster and isolation state;
9. evaluate candidate eligibility and environmental pressure;
10. calculate the final speciation type, chance and random trigger;
11. plan parent/child populations, lineage codes and tile allocation;
12. replace the remaining inline flow with a short coordinator and enforce the M5 line-count gates.

The two result-materialization phases may be split into a single-entry function plus a thin loop if formatting would otherwise exceed 250 lines.

## Preserved Behavior

- Existing loop and repository-write order, including parent population writes before child entries.
- All `continue`, retry/deferred, background and stale-turn decisions.
- Random call order and exact probability/population formulas.
- Candidate-cache reads, tile/cluster normalization and geographic-isolation branches.
- AI payload text, naming seeds, rule preprocessing and batch scheduling.
- Validation, child creation, habitat/genetic/gene/organ updates, tensor writes and event logging.
- Description-enhancement queue order, clearing behavior and exception isolation.
- Existing service method and subclass override behavior.

## Testing

Before moving each phase, add focused tests for its outputs, input mutations, callback order and early-return reason. The new boundary must first fail because it is absent. For mechanical moves, compare normalized ASTs. For control-flow replacements, compare characterized outputs/state and run the existing speciation/integration regressions.

Each implementation batch gets:

- focused red/green tests;
- all species tests;
- at most two current-diff reviews;
- one backend full suite and one frontend test/build/lint gate;
- one implementation commit, ordinary push and a PR #15 update.

## Stop Conditions

Stop if a phase requires a new service constructor dependency, public API, gameplay formula change, new random draw, repository or transaction semantic change, schema/persisted-format change, AI prompt/network/timeout change, new third-party dependency or a production file outside `speciation.py` and `speciation_process.py`.
