# ADR 0002: Enforce access control in the tools, not in the prompt

Status: accepted · November 2026

## Context
Account managers may only see their own accounts; Finance sees all. A system prompt that says "only show the user's accounts" is a request to the model, not a control: a prompt injection, a model error or a future model change can break it.

## Decision
The model proposes, the code disposes. Every tool call passes a guard (`tools.Toolbox.check`) that fails closed: unknown tool, invalid arguments, role not allowed and exhausted step budget all block the call. Row-level security is added in the semantic layer from the user's identity, which comes from the API's authoriser and never from the request body or the model. An account outside the user's scope returns exactly the same message as one that does not exist, so the agent cannot even confirm it exists.

## Alternatives considered
- Prompt instructions only: rejected for the reasons above.
- Filtering results after the query: rejected because the rows would already be in memory and in traces.
- Database-level row security per user: a good addition in production (Lake Formation data filters), but kept as defence in depth, not the primary control, so local tests can prove the rule.

## Consequences
- The evaluation can test the guard with a hostile planner that tries every forbidden call (`planners.ATTACKS`). In 42 runs across three roles there were no leaks and no unauthorised actions.
- The leak check re-reads what the planner saw and compares it with the gold data, so it does not trust the guard it is testing; a test removes row-level security on purpose and confirms the leak check notices.
