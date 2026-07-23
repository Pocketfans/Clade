# M6B Performance Baseline Design

## Goal

Create reproducible, reviewable performance evidence for Clade instead of relying on informal timing observations.

The completed M6B workflow must record:

- one-turn scale cases with 10, 100 and 500 species;
- a fixed-seed 100-turn stability case;
- total and per-Stage timing;
- CPU time and Python peak memory;
- database write counts;
- save size, save time and load time;
- AI call and token counts when those values are available;
- GPU and video-memory information when the host can report it.

Unavailable measurements must be stored as `null` with a note. They must never be guessed.

## Selected Architecture

M6B is split into four independently verifiable behaviors:

1. a versioned JSON result contract and regression comparator;
2. an isolated measurement collector using the existing `PipelineMetrics`;
3. deterministic 10/100/500-species and 100-turn benchmark scenarios;
4. checked-in baseline evidence, an optional regression command and operator documentation.

The benchmark path must use an isolated temporary database and must not call public AI or network services. It may report zero AI calls for the deterministic core scenario. The benchmark must not modify the user's normal world database or save directory.

No new third-party dependency is needed. Wall/CPU timing uses `time`, Python allocation peaks use `tracemalloc`, database writes use SQLAlchemy's existing event system, and Stage timing comes from `PipelineMetrics`. GPU metadata is best-effort and remains nullable.

## Result Contract

Schema version 1 contains:

- environment identity: platform, Python, processor, logical CPU count and optional GPU;
- source identity: commit SHA and UTC generation time;
- stable case IDs;
- case dimensions: species count, turn count and seed;
- total wall/CPU duration and optional memory/write/save/AI measurements;
- aggregated per-Stage sample count, total, mean and maximum duration;
- notes explaining unavailable or intentionally disabled measurements.

A complete M6B report contains the stable case IDs:

- `scale-10`
- `scale-100`
- `scale-500`
- `seeded-100-turn`

Partial reports are valid while developing or diagnosing a single case, but the final completeness check must list any missing required cases.

## Comparison Rules

Comparisons are conclusive only when the environment identity matches. Different hardware or Python/platform identities produce an explicit incomparable result rather than a false alarm.

For matching cases, a regression requires both:

- a relative increase above the configured ratio (default 20%); and
- an absolute increase above the metric's noise floor.

Timing uses a 5 ms floor, Python memory uses a 1 MiB floor, and count metrics use a one-unit floor. Missing optional values and zero baselines are reported as skipped, not invented.

The first contract batch compares wall time, CPU time, peak Python memory, database write statements, save/load time and matching Stage mean time. AI tokens and database rows remain recorded evidence but are not automatic blockers until their collection semantics are proven stable.

## Safety and Scope

- Do not change simulation formulas, Stage order, repositories or transaction behavior.
- Do not add runtime instrumentation to ordinary game turns.
- Do not access public AI/network services.
- Do not require GPU metadata on hosts where it is unavailable.
- Do not write benchmark artifacts outside an explicitly supplied output path.
- Do not turn naturally noisy wall-clock measurements into hard unit-test timing assertions.

