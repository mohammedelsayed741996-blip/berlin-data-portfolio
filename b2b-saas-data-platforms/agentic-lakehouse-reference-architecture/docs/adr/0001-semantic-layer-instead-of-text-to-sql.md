# ADR 0001: A semantic layer instead of free text-to-SQL

Status: accepted · November 2026

## Context
Account managers ask questions about receivables and revenue in their own words. The obvious design lets the model write SQL against the warehouse. That puts the model in charge of three things it should not own: which tables it may touch, which rows the user may see, and whether the query is safe and affordable.

## Decision
The agent never writes SQL. It calls `query_metric` with a named metric, at most two dimensions and up to four filters, all from allow-lists in `semantic.py`. The semantic layer compiles that into SQL, binds every value as a parameter, adds the row-level security predicate and caps the row count. Lookups that are not aggregates (one account, its open invoices, a ranked account list) get their own narrow tools.

## Alternatives considered
- Text-to-SQL with a read-only database user: flexible, but row-level security would depend on database views per user, and prompt injection could still read any column the user can see, including contact data.
- Text-to-SQL checked by a SQL parser: better, but the allow-list ends up being a semantic layer in disguise, with more ways to get it wrong.

## Consequences
- Every question the agent can answer maps to a definition Finance can review. New questions need a new metric or dimension, which is a code change with a test.
- Some ad-hoc questions are out of reach. That is acceptable for a Finance assistant; analysts keep their BI tool.
- The same compiled SQL runs on SQLite locally and on Athena in AWS, so local tests exercise production queries.
