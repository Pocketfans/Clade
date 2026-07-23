# M5 Speciation Responsibility Split Design

## Goal

Turn `backend/app/services/species/speciation.py` from a 6483-line mixed-responsibility class into a compatibility facade and bounded coordinator, without changing simulation results, prompts, persisted identifiers, repositories, or callers.

## Completion Standard

The `speciation.py` portion of M5 is complete only when all of these are true:

- `speciation.py` is at most 3000 lines;
- `SpeciationService.process_async` is at most 500 lines;
- no non-coordinator responsibility block exceeds 250 lines;
- extracted responsibilities have focused tests and keep existing service entry points as compatibility delegates where needed;
- backend and frontend quality gates pass;
- no gameplay formula, AI prompt/output rule, database behavior, persisted identifier, dependency, or public interface changes.

Line counts are guardrails, not the architecture by themselves. A responsibility must move behind a focused module boundary rather than merely being copied into an unrelated file.

## Selected Architecture

Keep `SpeciationService` as the existing caller-facing facade. Extract cohesive internal function modules in increasing risk order:

1. context formatting, fallback naming, and lineage-code utilities — completed;
2. dormant-gene summarization, activation, and new-gene construction — completed;
3. habitat and geographic allocation — completed;
4. organ evolution and complexity handling;
5. trait validation, trade-offs, and differentiation;
6. batch AI payload, invocation, parsing, and fallback creation;
7. `process_async` phase helpers so the remaining method is a readable coordinator.

Each extraction retains thin underscore-prefixed methods when existing code calls them. No new service object or constructor dependency is introduced.

## Alternatives

1. **Compatibility facade plus internal function modules (selected).** Moves real responsibilities while minimizing call-site and lifecycle risk.
2. **New injected service classes.** Rejected for M5 because it adds constructor dependencies and public abstractions.
3. **Move large methods unchanged without decomposing orchestration.** Rejected because it reduces one file's line count without reducing coupling or the 1547-line coordinator.

## First Complete Responsibility: Dormant Genes

The dormant-gene subsystem contains three consecutive methods totaling about 502 lines and none reads `self`:

- deterministic prompt summarization and scoring;
- AI-requested activation mutations;
- LLM-generated dormant-gene construction.

Move them to `speciation_dormant_genes.py` in three independently tested batches, from read-only to state-mutating. Preserve logger category, input defaults, sorting stability, mutation order, output text, data shapes, and existing exceptions.

## Second Responsibility: Habitat and Geography

Split habitat and geographic allocation into four independently testable behaviors, in this order:

1. habitat suitability scoring and initial child-habitat selection;
2. parent-habitat inheritance;
3. connected-cluster discovery and cluster allocation;
4. geographic-isolation detection and offspring tile allocation.

The first batch moves suitability scoring and initial child-habitat selection to `speciation_habitat.py`. The existing service methods remain compatibility delegates. The initial-selection function accepts the existing service suitability method as an internal callback so subclass overrides keep working exactly as before.

Preserve habitat filters, score constants, thresholds, stable sorting, top-ten limit, fallback order, normalization, repository calls, log text and logger category. Keep the repository singleton and current model construction; do not introduce dependency injection, schema changes, or new error handling.

## Third Responsibility: Organ Evolution and Complexity

Move organ and complexity handling to `speciation_organs.py` in increasing risk order:

1. capability-label derivation;
2. deterministic complexity rules and constraint lookup;
3. gradual-evolution validation;
4. plant organ changes;
5. organ-evolution normalization and deduplication;
6. embedding-based complexity inference and domain selection;
7. organ inheritance and update orchestration.

Keep the existing service methods as compatibility delegates and pass current service methods or data as internal callbacks where subclass overrides or lazy state must remain effective. Do not add an injected service, constructor dependency, public abstraction or a second organ module.

The first batch extracts only capability-label derivation. Preserve the legacy English-to-Chinese mapping, inherited unknown labels, inactive-organ filtering, category priority, keyword tests, set-based deduplication and resulting list behavior. It must not change organ data or species state.

## Testing and Error Handling

Characterize outputs and state mutations before each move. A missing new boundary must produce the initial red test; then direct speciation regressions and one full backend/frontend gate must pass. Introduce no new catch, fallback, normalization, or error translation.

## Stop Conditions

Stop if an extraction requires a new dependency, constructor argument, public interface, database/schema change, persisted-format change, AI/gameplay output change, or another production file outside the approved responsibility boundary.
