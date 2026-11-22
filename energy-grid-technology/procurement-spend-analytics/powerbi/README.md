# Power BI model

The pipeline writes the star schema to `data/model/` as CSV. Load each table with `load_star_schema.pq` (Get Data > Blank query > Advanced editor), then create the relationships below and paste the measures from `measures.dax`.

| From (many) | To (one) | Key |
|---|---|---|
| fact_po_line | dim_supplier | supplier_id |
| fact_po_line | dim_material | material_id |
| fact_po_line | dim_category | category |
| fact_po_line | dim_plant | plant |
| fact_po_line | dim_month | month |

All relationships are single direction, one to many. Mark `dim_month` as the date table on `month`.

Suggested pages:
1. Overview: Spend, Contract Coverage %, Maverick Spend, Active Suppliers as cards; spend by category stacked by `contract_status`; monthly spend with Spend 3M Avg.
2. Suppliers: Pareto with Cumulative Supplier Share %, a table with On-Time Delivery % and Defect Rate %, Supplier HHI by category.
3. Data quality: `outputs/dq_results.csv` as a table with owner and action, filtered on failing > 0.
4. Prices: `outputs/commodity_forecast.csv` as a line with the band, `outputs/budget_impact.csv` as a table.

The measures follow the same definitions as the SQL views in `sql/views.sql`, which the tests check. They have not been run in Power BI Desktop, because this repository was built on Linux, so there is no .pbix file. The Excel workbook in `outputs/` covers the same numbers with live formulas.
