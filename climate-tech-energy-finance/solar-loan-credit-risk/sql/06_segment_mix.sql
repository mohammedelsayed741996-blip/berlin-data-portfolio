-- Open exposure and 30+ delinquency by region and product.
WITH latest AS (
    SELECT loan_id, outstanding_balance_eur, days_past_due
    FROM performance
    WHERE as_of_date = (SELECT MAX(as_of_date) FROM performance)
      AND status IN ('Performing', 'Delinquent')
)
SELECT
    l.region,
    l.product_type,
    COUNT(*)                                                       AS open_loans,
    ROUND(SUM(lt.outstanding_balance_eur), 0)                      AS exposure_eur,
    ROUND(SUM(CASE WHEN lt.days_past_due >= 30 THEN lt.outstanding_balance_eur ELSE 0 END)
          / SUM(lt.outstanding_balance_eur), 4)                    AS dpd30_plus_share,
    ROUND(AVG(l.savings_coverage_ratio), 3)                        AS avg_savings_coverage
FROM latest lt
JOIN loans l USING (loan_id)
GROUP BY l.region, l.product_type
ORDER BY exposure_eur DESC;
