# ADR 0003: Human approval for every action with side effects

Status: accepted · November 2026

## Context
Useful agents do things: send a payment reminder, propose a credit hold. A wrong reminder damages a customer relationship; a wrong credit hold stops deliveries. Prompt injection (see the archived customer email in `docs/policies`) is most dangerous exactly here.

## Decision
Action tools only create approval requests. Nothing is sent or changed until a person decides through the API, and the approval rules live in code (`approvals.py`): account managers approve reminders for their own accounts, Finance approves any reminder, and a credit hold needs the Head of Finance and a different person from the one who proposed it. There is no approval tool the agent could call.

## Alternatives considered
- Let low-risk actions run automatically: possible later for reminder steps one and two, once the approval log shows a low rejection rate. Not before there is evidence.
- Ask for confirmation in the chat: rejected; the same session that might be compromised would be confirming.

## Consequences
- Every action leaves an auditable record with requester, decider and time; DynamoDB keeps them for a year.
- Account managers see one extra click per reminder. The draft is complete, so the click is a review, not rework.
