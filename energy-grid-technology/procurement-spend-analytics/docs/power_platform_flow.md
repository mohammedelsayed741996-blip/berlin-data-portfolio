# Design: supplier master change requests with Power Apps and Power Automate

A design, not an implementation: this repository has no Microsoft 365 tenant. It shows how the quality rules would move from a monthly report to the point where data is entered.

## Problem
Buyers request new suppliers and changes (bank details, payment terms, country) by email. The master data team re-types them into two ERPs, which is how duplicates, missing countries and five spellings of "30 days net" get in (rules DQ06, DQ07, DQ08 and DQ11).

## Flow
1. Power App form (buyer): company name, country, VAT ID, payment terms from a fixed list, category, requesting plant.
2. On submit, Power Automate:
   - checks the VAT ID format for the country and that country and terms are filled;
   - looks the VAT ID and normalised name up in the golden supplier list (`dim_supplier`, via a SharePoint list or Dataverse table refreshed by the pipeline);
   - if a match exists, replies to the buyer with the existing supplier numbers instead of creating a new record;
   - otherwise creates an approval for the master data team (and compliance if the country risk is 3).
3. On approval: create the record in the ERP through the standard interface, write the request, approver and timestamp to an audit list, notify the buyer.
4. Monthly: the pipeline's quality scorecard is posted to the team channel; rules with findings open a task for the owner role in `dq_rules.yaml`.

## What it would change
| Rule | Before | After |
|---|---|---|
| DQ07 duplicates | found after the fact by matching | blocked at request time when VAT ID or name matches |
| DQ08 payment terms | free text in ERP_A | picked from one catalogue |
| DQ06, DQ11 country and VAT ID | optional | mandatory in the form |
