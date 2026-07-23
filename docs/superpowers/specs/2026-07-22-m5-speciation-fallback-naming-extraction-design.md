# M5 Speciation Fallback Naming Extraction Design

## Goal

Continue the ordered split of `backend/app/services/species/speciation.py` by moving its two deterministic fallback-name generators into a focused, dependency-free module without changing any generated name.

## Selected Scope

Extract exactly:

- fallback Latin-name generation;
- fallback Chinese common-name generation.

The new module is `backend/app/services/species/speciation_naming.py`. `SpeciationService` keeps `_fallback_latin_name` and `_fallback_common_name` as thin compatibility methods, so all callers remain unchanged.

## Alternatives Considered

1. **Fallback generators only (selected).** They depend only on supplied strings and dictionaries and never read or write project state.
2. **Include uniqueness enforcement.** Deferred because those methods query the species repository and would broaden this batch into database coupling.
3. **Extract organ and prey summaries.** Deferred because prey summaries query repository state and should be handled as a separate responsibility.

## Behavior Contract

- Preserve the existing keyword precedence exactly.
- Preserve genus and Chinese taxon extraction exactly.
- Preserve `hashlib.md5(str(value).encode()).hexdigest()` inputs and suffix lengths exactly.
- Preserve all fallback prefixes, epithets, and output formatting.
- Preserve current errors for malformed inputs; add no normalization or recovery.

## Tests

Add focused tests for known Latin epithets, genus fallback, Chinese feature/taxon composition, deterministic hash fallbacks, and compatibility delegates. Run the focused tests first, then the existing species-service regression tests, then one final backend and frontend quality gate.

## Non-Goals and Stop Conditions

Do not change uniqueness checks, repositories, databases, AI behavior, gameplay rules, formulas, dependencies, or public interfaces. Stop if the extraction requires touching another production file or changing any generated output.
