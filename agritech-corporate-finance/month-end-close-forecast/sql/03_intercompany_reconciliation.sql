-- DE10 receivable from each partner against the partner's payable to DE10, cumulative to the close month.
WITH recv AS (
    SELECT partner_company AS partner, SUM(amount_eur) AS receivable
    FROM gl_items
    WHERE company_code = 'DE10' AND gl_account = '1400' AND month <= :close_month
    GROUP BY partner_company
), pay AS (
    SELECT company_code AS partner, -SUM(amount_eur) AS payable
    FROM gl_items
    WHERE gl_account = '3400' AND partner_company = 'DE10' AND month <= :close_month
    GROUP BY company_code
)
SELECT 'DE10-' || recv.partner AS pair,
       ROUND(recv.receivable, 2) AS de10_receivable_eur,
       ROUND(COALESCE(pay.payable, 0), 2) AS partner_payable_eur,
       ROUND(recv.receivable - COALESCE(pay.payable, 0), 2) AS difference_eur
FROM recv
LEFT JOIN pay ON pay.partner = recv.partner
ORDER BY pair;
