# ADR 0005: A medallion lakehouse on S3, Glue and Athena

Status: accepted · November 2026

## Context
Receivables data comes from two ERP instances (Germany in EUR with German number formats, Gulf in AED), exported as JSON lines with repeats and gaps. The agent needs a small set of clean, documented tables, and Finance needs to trust that the numbers match the ERP.

## Decision
Bronze keeps exports exactly as received; silver de-duplicates, parses numbers, converts to EUR and fills missing due dates from payment terms; gold holds the three marts the agent may read. On AWS the layers are prefixes in one KMS-encrypted S3 bucket, the Glue catalog describes gold and Athena queries it through a workgroup with a 1 GB scan limit. Locally the same files are queried with SQLite. Reconciliation checks run after every build: in this dataset, gold open receivables equal the source to the cent.

## Alternatives considered
- Snowflake or Databricks: excellent if the customer already runs them; for one Finance assistant on a small dataset, serverless Athena costs less and keeps everything in the customer's account.
- Querying the ERP directly: rejected; the agent would load the ERP and see raw data with problems Finance has not signed off.

## Consequences
- Gold is CSV for transparency in this demo. In production it would be Parquet with Apache Iceberg tables for schema evolution and time travel.
- The agent reads only gold. Its IAM role cannot read bronze or silver.
