# ADR 0004: Claude on Amazon Bedrock, behind a planner interface

Status: accepted · November 2026

## Context
The customer runs on AWS in Frankfurt and wants data processed in the EU. The agent needs a model that uses tools reliably and follows instructions about untrusted text.

## Decision
The production planner is Claude on Amazon Bedrock through the Converse API with tool use, called through the EU cross-region inference profile (default `eu.anthropic.claude-sonnet-4-5-20250929-v1:0`, configurable). The tool schemas the guard enforces are the same JSON schemas sent to the model. All planners share one interface, so the agent loop, the guard, tracing and evaluation do not change with the model.

A deterministic rule planner implements the same interface. It is the offline stand-in for CI and the baseline a model has to beat.

## Alternatives considered
- Calling the Anthropic API directly: simpler, but data would leave the customer's AWS account and contract.
- A self-hosted open model: possible for strict on-premises cases; the planner interface keeps that door open.

## Consequences
- The rule planner passes all 34 core tasks but only 1 of 6 paraphrases. That gap is what the model is for, and the evaluation will measure it when the Bedrock planner runs on the same tasks.
- The Bedrock planner is tested here against a stubbed client (message format, tool results, token accounting, guard blocks), not against the live model, because this environment has no AWS access.
- Cost and latency become real once the model is in the loop; the traces already record tokens and an estimated cost per run.
