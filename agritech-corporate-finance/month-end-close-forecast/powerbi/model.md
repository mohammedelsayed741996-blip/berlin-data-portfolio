# Power BI model

The pipeline writes a small star schema here as CSV. Import the files with Get Data > Text/CSV, set the
types below, create the relationships and paste the measures from `measures.dax`.

| Table | Grain | Key columns |
|---|---|---|
| fact_cost | month x company x cost center x account x scenario | month, cost_center, gl_account, scenario (Actual, Close adjustment, Budget, Forecast) |
| fact_revenue | month x company x crop x scenario | month, company_code, crop |
| dim_date | month | month (text YYYY-MM), fiscal_year, fiscal_period |
| dim_cost_center | cost center | cost_center, company_code, functional_area, blocked |
| dim_account | GL account | gl_account, account_type, account_group |
| dim_entity | company | company_code |
| dim_functional_area | function | functional_area, sort |

Relationships (single direction, many to one):

- fact_cost[month] -> dim_date[month]; fact_revenue[month] -> dim_date[month]
- fact_cost[cost_center] -> dim_cost_center[cost_center]
- fact_cost[gl_account] -> dim_account[gl_account]
- fact_cost[company_code] -> dim_entity[company_code]; fact_revenue[company_code] -> dim_entity[company_code]
- fact_cost[functional_area] -> dim_functional_area[functional_area]

Set `cost_center` and `gl_account` to Text so leading zeros survive (`0400`).

Suggested pages: close status (checklist from `outputs/controlling_pack.xlsx`), budget vs actual by function
with drill to cost center and account, outlook (actual + forecast by month), revenue bridge by crop.
