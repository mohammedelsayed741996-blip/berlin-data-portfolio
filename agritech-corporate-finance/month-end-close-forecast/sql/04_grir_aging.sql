-- Open GR/IR items by purchase order with age at month end, in aging buckets.
WITH po AS (
    SELECT company_code, po_number,
           -SUM(amount_eur) AS open_eur,
           MIN(posting_date) AS first_receipt
    FROM gl_items
    WHERE gl_account = '3310' AND po_number <> '' AND month <= :close_month
    GROUP BY company_code, po_number
    HAVING ROUND(SUM(amount_eur), 2) <> 0
)
SELECT company_code, po_number, ROUND(open_eur, 2) AS open_eur, first_receipt,
       CAST(julianday(:month_end) - julianday(first_receipt) AS INTEGER) AS age_days,
       CASE WHEN julianday(:month_end) - julianday(first_receipt) <= 30 THEN '0-30'
            WHEN julianday(:month_end) - julianday(first_receipt) <= 60 THEN '31-60'
            WHEN julianday(:month_end) - julianday(first_receipt) <= 90 THEN '61-90'
            ELSE '90+' END AS bucket
FROM po
ORDER BY age_days DESC;
