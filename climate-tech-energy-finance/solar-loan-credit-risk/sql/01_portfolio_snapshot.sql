-- Live book at the observation date: open loans by status, with balance shares.
WITH latest AS (
    SELECT p.*
    FROM performance p
    WHERE p.as_of_date = (SELECT MAX(as_of_date) FROM performance)
      AND p.status IN ('Performing', 'Delinquent')
)
SELECT
    CASE
        WHEN days_past_due = 0  THEN '0 current'
        WHEN days_past_due = 30 THEN '1 DPD 30'
        WHEN days_past_due = 60 THEN '2 DPD 60'
        ELSE '3 DPD 90+'
    END                                                      AS dpd_bucket,
    COUNT(*)                                                 AS loans,
    ROUND(SUM(outstanding_balance_eur), 0)                   AS outstanding_eur,
    ROUND(SUM(outstanding_balance_eur) * 1.0
          / SUM(SUM(outstanding_balance_eur)) OVER (), 4)    AS share_of_balance
FROM latest
GROUP BY dpd_bucket
ORDER BY dpd_bucket;
