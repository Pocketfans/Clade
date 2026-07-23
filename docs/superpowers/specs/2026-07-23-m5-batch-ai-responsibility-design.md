# M5 Batch AI Responsibility Design

## Goal

Move batch speciation AI payload construction, normalization, fallback creation, response parsing and invocation out of `speciation.py` without changing prompts, network behavior, timeout semantics, fallback priority, parsed data, logs, public interfaces or subclass overrides.

## Selected Architecture

Create one focused internal module, `speciation_ai.py`, and keep existing underscore-prefixed `SpeciationService` methods as compatibility delegates. Pass bound methods or current data as callbacks only where service overrides or lazy state must remain effective.

Extract in increasing risk order:

1. AI content normalization;
2. batch payload and prompt construction;
3. rule-based fallback content construction;
4. batch response matching and parsing;
5. single-call wrapper;
6. batch invocation, streaming and timeout handling.

Each item is an independent tested batch. No second AI module, injected service, constructor dependency or public abstraction is introduced.

## Preserved Behavior

- Input dictionaries, in-place mutations, list and dictionary iteration order, numeric conversions and exception filtering.
- Prompt templates, whitespace, naming seeds, context defaults and plant/animal branches.
- Rule fallback formulas, random seeds, species naming, organ shapes and private marker fields.
- Response matching by lineage code, positional fallback, required-field checks, endosymbiosis overrides and per-entry rule fallback.
- Router/model selection, heartbeat events, streaming callbacks, timeout/error markers and partial results.
- Existing logger category and message text.

## Rejected Alternatives

1. Move the complete AI subsystem in one change: rejected because prompt, parsing, fallback and async failure semantics cannot be independently verified.
2. Extract async invocation first: rejected because it has the highest network, timeout and streaming risk.
3. Add an injected AI service: rejected because M5 forbids new constructor dependencies and public abstractions.

## Testing

Characterize direct outputs, input mutations, callback order and failure paths before each move. Every new boundary must first fail by being absent, then pass focused species tests and one backend/frontend full gate. Normalized AST comparison is required for mechanically moved executable bodies.

## Stop Conditions

Stop if an extraction requires prompt changes, a new dependency, constructor argument, public interface, retry/timeout change, provider selection change, gameplay formula change, database/schema change, persisted-format change or a production file outside `speciation.py` and `speciation_ai.py`.
