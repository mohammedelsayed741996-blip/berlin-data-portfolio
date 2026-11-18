-- Trial balance at the close month: balance sheet accounts cumulative, P&L for the fiscal year to date.
-- :close_month = 'YYYY-MM', :fiscal_year = 'YYYY/YY'
SELECT g.company_code,
       g.gl_account,
       a.account_name,
       ROUND(SUM(g.amount_eur), 2) AS balance_eur
FROM gl_items g
JOIN gl_accounts a ON a.gl_account = g.gl_account
WHERE g.month <= :close_month
  AND (a.account_type = 'BS' OR g.fiscal_year = :fiscal_year)
GROUP BY g.company_code, g.gl_account, a.account_name
ORDER BY g.company_code, g.gl_account;
