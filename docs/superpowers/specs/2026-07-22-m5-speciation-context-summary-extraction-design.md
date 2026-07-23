# M5 Speciation Context Summary Extraction Design

## Goal

Begin the ordered M5 split of `backend/app/services/species/speciation.py` by moving one low-risk, independently testable responsibility into a focused module without changing simulation behavior.

## Scope

Extract exactly these three text-summary behaviors:

- food-chain status summarization;
- map-change summarization;
- major-event summarization.

The new module is `backend/app/services/species/speciation_context.py`. It contains pure functions and has no repository, AI, configuration, database, or service dependencies.

`SpeciationService` keeps its existing private method names as thin compatibility methods. Existing call sites therefore remain unchanged.

## Alternatives Considered

1. **Pure context-summary extraction (selected).** Lowest risk because it only formats already supplied data and does not write state or calculate gameplay outcomes.
2. **Naming extraction.** Removes more code but depends on uniqueness checks and repository state, so it is deferred.
3. **Geographic isolation extraction.** Has the largest structural benefit but touches tile allocation and gameplay calculations, so it is deferred until the split workflow is proven.

## Data Flow

Existing callers continue to call `SpeciationService._summarize_*()`. Each compatibility method forwards the same argument to the corresponding pure function and returns the string unchanged.

No values are added, removed, normalized, or reordered. Existing Chinese messages, thresholds, three-item map limit, and first-event rule remain byte-for-byte equivalent in behavior.

## Error Handling

No new error handling is introduced. Missing input keeps returning the existing empty or “unknown” text. Dictionary and attribute-based inputs remain supported exactly as before.

## Tests

Create `backend/app/services/species/tests/test_speciation_context.py` and prove:

- the new module boundary exists;
- empty and stable food-chain inputs retain their current messages;
- shortage and cascade-risk inputs retain current messages;
- map changes accept dictionaries and objects and inspect at most three entries;
- major events accept dictionaries and objects and use only the first entry;
- the `SpeciationService` compatibility methods return the same outputs.

Run the focused test first, then the existing species-service tests, then one backend full suite and the standard frontend test/build/lint quality gate.

## Non-Goals

- No gameplay, threshold, population, trait, or tile-allocation changes.
- No repository or database changes.
- No AI prompt, provider, timeout, or retry changes.
- No renaming or removal of existing `SpeciationService` methods.
- No extraction of any other `speciation.py` responsibility in this batch.

## Stop Conditions

Pause if extraction requires changing an existing call signature, output string, formula, repository contract, or another production file outside the three planned code/test files.
