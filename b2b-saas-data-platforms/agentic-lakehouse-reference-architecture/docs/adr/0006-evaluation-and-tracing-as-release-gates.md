# ADR 0006: Evaluation and tracing as release gates

Status: accepted · November 2026

## Context
Agents change behaviour when a prompt, a tool description or the model changes. Without measurement, a release that leaks data or stops answering correctly looks the same as a good one.

## Decision
Every change runs the evaluation in CI (`scripts/evaluate.py --gate`):
- task success on core tasks of at least 90%;
- no leaks in tasks;
- no leaks and no unauthorised actions across the red-team attacks;
- all approval rules correct.

Every run is traced as OpenTelemetry-shaped spans (agent run, planner step, tool call with the guard's verdict, rows, tokens and estimated cost) and exported as JSON lines. In AWS they go to CloudWatch, where a metric filter counts guard blocks and an alarm fires on a spike, alongside alarms for errors and p95 latency.

## Alternatives considered
- Manual review of sample conversations: useful, but not repeatable and not a gate.
- A hosted LLM observability platform (Langfuse, Arize Phoenix, LangSmith): a good fit once the customer chooses one; the span format maps onto OTLP, so the exporter is the only change.

## Consequences
- Paraphrases are reported but not gated while the rule planner is in use, because they measure language understanding, which is the model's job. Once the Bedrock planner is evaluated, they become part of the gate.
- The task checks compute expected values from gold at run time, so they stay correct when the data is rebuilt.
