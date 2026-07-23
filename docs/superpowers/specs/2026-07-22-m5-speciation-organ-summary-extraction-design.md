# M5 Speciation Organ Summary Extraction Design

## Goal

Continue the ordered split of `backend/app/services/species/speciation.py` by moving its deterministic organ-summary formatter into the existing pure context module without changing any prompt text or call site.

## Selected Design

Add `summarize_organs(organs: dict | None) -> str` to `backend/app/services/species/speciation_context.py`.

Keep `SpeciationService._summarize_organs(species)` as a compatibility method. It passes `species.organs` to the pure function and returns the result unchanged. Existing callers therefore continue to supply a `Species` object through the same private service method.

## Alternatives

1. **Use the existing context module (selected).** The formatter is pure text context and fits the module already holding food-chain, map-change, and event summaries.
2. **Create an organ-only module.** This would isolate the code but create a disproportionately small production file for one formatter.
3. **Also extract prey summaries.** Deferred because prey summaries query `species_repository` and would broaden this batch into repository coupling.

## Behavior Contract

- Preserve dictionary insertion order in the output.
- Preserve the six category labels and unknown-category fallback.
- Preserve the default organ type, stage, and progress values.
- Preserve inactive-organ filtering.
- Preserve the stage-name mapping, stage threshold, percentage formatting, line format, newline joining, and empty fallback text exactly.
- Preserve existing exceptions for malformed non-dictionary organ entries; add no normalization or recovery.

## Tests

Add focused tests for empty inputs, inactive-only inputs, active stage formatting, completed organs, unknown categories/default types, output order, and the `SpeciationService` compatibility method.

Run the focused context tests first, then the existing direct speciation tests, then one backend full suite and the standard frontend test/build/lint quality gate.

## Non-Goals and Stop Conditions

Do not change prey summaries, repositories, databases, AI prompts, gameplay rules, formulas, dependencies, or public interfaces. Stop if implementation requires another production file or any output change.
