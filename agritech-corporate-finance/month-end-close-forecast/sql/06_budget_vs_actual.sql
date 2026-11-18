-- Fiscal YTD actual vs budget by functional area (expense accounts, intercompany charges included).
WITH act AS (
    SELECT g.functional_area, SUM(g.amount_eur) AS actual_ytd
    FROM gl_items g
    JOIN gl_accounts a ON a.gl_account = g.gl_account
    WHERE a.account_type IN ('EXP', 'EXP_IC') AND g.fiscal_year = :fiscal_year AND g.period <= :period
    GROUP BY g.functional_area
), bud AS (
    SELECT functional_area, SUM(budget_eur) AS budget_ytd
    FROM budget
    WHERE fiscal_year = :fiscal_year AND period <= :period
    GROUP BY functional_area
)
SELECT act.functional_area,
       ROUND(act.actual_ytd, 2) AS actual_ytd,
       ROUND(COALESCE(bud.budget_ytd, 0), 2) AS budget_ytd,
       ROUND(act.actual_ytd - COALESCE(bud.budget_ytd, 0), 2) AS var_ytd_eur
FROM act
LEFT JOIN bud ON bud.functional_area = act.functional_area
ORDER BY act.functional_area;
