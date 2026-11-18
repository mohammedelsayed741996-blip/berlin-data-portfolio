# Close memo: 2026-09 (period 3, FY 2026/27)

Feldkern Group (fictional). All data is synthetic. Amounts in EUR.

## Close status

12 checks ran; 11 need action before sign-off. The proposed corrections change P&L by EUR 124,426.

| check_id   | check                                                         | status   |   exceptions |   amount_eur |
|:-----------|:--------------------------------------------------------------|:---------|-------------:|-------------:|
| C01        | Every document balances (debit = credit)                      | FAIL     |            1 |       1250   |
| C02        | No postings on blocked cost centers                           | FAIL     |            1 |       8900   |
| C03        | Cost center belongs to the posting company                    | FAIL     |            1 |      12400   |
| C04        | Expense lines carry a cost center                             | FAIL     |            1 |       5600   |
| C05        | No duplicate vendor invoices                                  | FAIL     |            2 |      42350   |
| C06        | Entries made by working day 3 (2026-10-05)                    | WARN     |            6 |      37026   |
| C07        | Recurring postings complete (payroll, depreciation, rent, IC) | FAIL     |            3 |     166776   |
| C08        | Intercompany balances agree by partner                        | FAIL     |            1 |      19331.5 |
| C09        | GR/IR items older than 60 days                                | WARN     |            4 |      92986.7 |
| C10        | Suspense account cleared to zero                              | WARN     |            1 |       7800   |
| C11        | Billing extract agrees with revenue in the ledger             | PASS     |            0 |          0   |
| C12        | Capex projects within 110% of approved budget                 | WARN     |            1 |     288000   |

## Proposed adjustments

| check_id   | company_code   |   cost_center |   gl_account |   amount_eur | description                                              |
|:-----------|:---------------|--------------:|-------------:|-------------:|:---------------------------------------------------------|
| C07        | AT10           |          1200 |         6200 |      97813.2 | Post missing depreciation run (estimate: last month)     |
| C07        | AT10           |          3200 |         6200 |      14120.4 | Post missing depreciation run (estimate: last month)     |
| C07        | FR10           |          2300 |         6600 |      35511.1 | Post missing rent (estimate: last month)                 |
| C07        | AT10           |          4200 |         6950 |      19331.5 | Post missing IC IT recharge (estimate: last month)       |
| C05        | DE10           |          4120 |         6500 |     -42350   | Reverse duplicate invoice RE-2026-08817                  |
| C02        | DE10           |          4199 |         6500 |      -8900   | Move off blocked cost center                             |
| C02        | DE10           |          4100 |         6500 |       8900   | Rebook on successor cost center 4100                     |
| C03        | DE10           |          2300 |         6400 |     -12400   | Remove FR10 cost center from DE10 posting                |
| C03        | DE10           |          2120 |         6400 |      12400   | Rebook on own selling cost center                        |
| C04        | FR10           |          4300 |         6500 |       5600   | Assign cost center (pending confirmation from requester) |
| C04        | FR10           |               |         6500 |      -5600   | Clear unassigned line                                    |
| VAR        | DE10           |          3110 |         6500 |    -250000   | Reclass Corn launch campaign Q1 - agency invoice         |
| VAR        | DE10           |          2110 |         6500 |     250000   | Reclass Corn launch campaign Q1 - agency invoice         |

## Year to date vs budget (before adjustments)

| line                               |      actual_ytd |   budget_ytd |   prior_year_ytd |   var_vs_budget_eur |
|:-----------------------------------|----------------:|-------------:|-----------------:|--------------------:|
| Revenue                            |     2.63644e+07 |  2.83362e+07 |      2.67404e+07 |        -1.97175e+06 |
| Cost of sales                      |    -2.45427e+07 | -2.40776e+07 |     -2.27939e+07 |   -465008           |
| Gross profit                       |     1.82178e+06 |  4.25854e+06 |      3.94647e+06 |        -2.43676e+06 |
| Selling                            |    -8.87039e+06 | -9.19917e+06 |     -9.15544e+06 |    328786           |
| Research and development           |    -9.44146e+06 | -9.35581e+06 |     -9.03157e+06 |    -85651           |
| General and administration         |    -3.54745e+06 | -3.40879e+06 |     -3.26086e+06 |   -138657           |
| Not assigned (missing cost center) | -5600           |  0           |      0           |     -5600           |
| EBIT                               |    -2.00431e+07 | -1.77052e+07 |     -1.75014e+07 |        -2.33788e+06 |

Revenue by crop, volume and price effects:

| crop       |   units_vs_budget_pct |   price_vs_budget_pct |   volume_effect_eur |   price_effect_eur |   total_variance_eur |
|:-----------|----------------------:|----------------------:|--------------------:|-------------------:|---------------------:|
| cereals    |                 -0.15 |                  0.05 |        -2.99775e+06 |          812775    |         -2.18498e+06 |
| corn       |                  0.07 |                  0.02 |    174286           |           55906.8  |     230193           |
| sugarbeet  |                  0.01 |                 -0.03 |     30809.6         |          -68318.1  |     -37508.6         |
| vegetables |                  0.01 |                 -0    |     27999.2         |           -7457.98 |      20541.2         |

## Variance comments

|   cost_center | cost_center_name   | account             |   var_ytd_eur | explanation                                                                                                                   | action                                                 |
|--------------:|:-------------------|:--------------------|--------------:|:------------------------------------------------------------------------------------------------------------------------------|:-------------------------------------------------------|
|          3110 | Breeding corn      | External services   |      230136   | Document 1000009434 (Corn launch campaign Q1 - agency invoice) booked on 3110 Breeding corn, budgeted on 2110 Sales corn DACH | Reclass to the budgeted cost center                    |
|          2110 | Sales corn DACH    | External services   |     -217394   | Document 1000009434 (Corn launch campaign Q1 - agency invoice) booked on 3110 Breeding corn, budgeted on 2110 Sales corn DACH | Reclass to the budgeted cost center                    |
|          1100 | Production Einbeck | Energy              |      173245   | Energy prices above the planning assumption                                                                                   | Forecast item; review the hedge and tariff assumptions |
|          1110 | Seed processing    | Energy              |      140434   | Energy prices above the planning assumption                                                                                   | Forecast item; review the hedge and tariff assumptions |
|          4120 | IT                 | External services   |      115057   | Includes a duplicate vendor invoice RE-2026-08817 (check C05); the rest is cloud usage above plan                             | Reverse the second invoice and block the payment       |
|          1200 | Production Austria | Depreciation        |      -97813.2 | Recurring posting missing this month (check C07)                                                                              | Post the missing entry before the close                |
|          1300 | Production France  | Energy              |       51917   | Energy prices above the planning assumption                                                                                   | Forecast item; review the hedge and tariff assumptions |
|          2120 | Marketing          | Travel              |      -44403.9 | To be explained by the cost center owner                                                                                      | Ask the owner                                          |
|          1200 | Production Austria | Energy              |       39943.8 | Energy prices above the planning assumption                                                                                   | Forecast item; review the hedge and tariff assumptions |
|          2300 | Sales France       | Rent and facilities |      -35511.1 | Recurring posting missing this month (check C07)                                                                              | Post the missing entry before the close                |
|          3100 | Breeding sugarbeet | Energy              |       32322.6 | Energy prices above the planning assumption                                                                                   | Forecast item; review the hedge and tariff assumptions |
|          1200 | Production Austria | External services   |       29506.2 | To be explained by the cost center owner                                                                                      | Ask the owner                                          |

## Full-year outlook (3+9, after adjustments)

| line                       |   actual_ytd |   forecast_rest |   outlook_fy |    budget_fy |   prior_year_fy |   var_vs_budget_eur |   var_vs_budget_pct |
|:---------------------------|-------------:|----------------:|-------------:|-------------:|----------------:|--------------------:|--------------------:|
| Revenue                    |  2.63644e+07 |     1.87617e+08 |  2.13982e+08 |  2.1885e+08  |     2.07114e+08 |        -4.86818e+06 |             -0.0222 |
| Cost of sales              | -2.46405e+07 |    -6.70561e+07 | -9.16966e+07 | -8.98289e+07 |    -8.44901e+07 |        -1.8677e+06  |             -0.0208 |
| Selling                    | -9.1559e+06  |    -3.14655e+07 | -4.06214e+07 | -4.08568e+07 |    -4.08694e+07 |    235361           |              0.0058 |
| Research and development   | -9.20558e+06 |    -2.85519e+07 | -3.77575e+07 | -3.83989e+07 |    -3.69748e+07 |    641394           |              0.0167 |
| General and administration | -3.5107e+06  |    -1.05029e+07 | -1.40136e+07 | -1.39281e+07 |    -1.33846e+07 |    -85460           |             -0.0061 |
| EBIT                       | -2.01482e+07 |     5.00407e+07 |  2.98925e+07 |  3.5837e+07  |     3.13951e+07 |        -5.94458e+06 |             -0.1659 |

EBIT outlook EUR 29,892,451 against a budget of EUR 35,837,034.

Forecast methods, chosen by a backtest on FY 2025/26:

| functional_area   | cost_type   | chosen_method   |   chosen_wape |   budget_wape |
|:------------------|:------------|:----------------|--------------:|--------------:|
| COS               | Other costs | driver          |        0.0282 |        0.0403 |
| COS               | Personnel   | seasonal        |        0.0116 |        0.0234 |
| GNA               | Other costs | budget          |        0.0195 |        0.0195 |
| GNA               | Personnel   | driver          |        0.0091 |        0.0112 |
| RND               | Other costs | driver          |        0.0249 |        0.0285 |
| RND               | Personnel   | driver          |        0.0084 |        0.0117 |
| SEL               | Other costs | driver          |        0.031  |        0.046  |
| SEL               | Personnel   | driver          |        0.0107 |        0.0327 |

## Capital projects

| wbs      | description                 |   approved_budget_eur |   actual_to_date_eur |   open_commitments_eur |          eac_eur |   eac_vs_budget_pct |
|:---------|:----------------------------|----------------------:|---------------------:|-----------------------:|-----------------:|--------------------:|
| P-25-010 | Seed drying plant extension |               2400000 |          2.30615e+06 |                      0 |      2.30615e+06 |              -0.039 |
| P-26-001 | New seed processing line    |               4200000 |          2.58665e+06 |                 682280 |      4.13406e+06 |              -0.016 |
| P-26-002 | Greenhouse complex Chartres |               1800000 |          1.63879e+06 |                 449215 |      2.21543e+06 |               0.231 |
| P-26-003 | Biotech lab equipment       |                900000 |     503020           |                 254439 | 868989           |              -0.034 |
| P-26-004 | ERP S/4 upgrade             |               1500000 |      84096.5         |                 206805 |      1.46106e+06 |              -0.026 |
