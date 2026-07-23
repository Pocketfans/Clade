# M5 Speciation Lineage Code Extraction Design

## Goal

Continue the ordered split of `speciation.py` by moving its two deterministic lineage-code generators into a focused pure module without changing any generated code.

## Selected Design

Create `backend/app/services/species/speciation_lineage.py` with:

- `next_lineage_code(parent_code, existing_codes) -> str`;
- `generate_multiple_lineage_codes(parent_code, existing_codes, num_offspring) -> list[str]`.

Keep both existing `SpeciationService` private methods as compatibility delegates. Existing call sites and return types remain unchanged.

## Alternatives

1. **Extract both pure code generators (selected).** They form one responsibility and depend only on supplied values.
2. **Extract dormant-gene summarization.** Deferred because its scoring affects AI evolution choices.
3. **Extract prey summarization.** Deferred because it queries the species repository.

## Behavior Contract

Preserve the single-code `a1`, `a2`, and subsequent numbered-suffix search; multi-code alphabet order; collision suffix search; input-set non-mutation; output order; non-positive offspring behavior; and the current more-than-26 behavior exactly. This batch deliberately does not repair or reinterpret any lineage-code rule.

## Tests

Cover single-code collision increments, ordinary multi-code output, collision suffixes, zero offspring, the existing 27th-code behavior, input-set non-mutation, and compatibility delegates. Run direct tests, then one backend/full frontend quality gate.

## Non-Goals and Stop Conditions

Do not change lineage formats, persisted identifiers, databases, repositories, gameplay, formulas, AI, dependencies, callers, or public interfaces. Stop if any expected code would change.
