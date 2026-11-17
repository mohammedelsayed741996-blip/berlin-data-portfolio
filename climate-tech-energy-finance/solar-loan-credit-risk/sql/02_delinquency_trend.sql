-- Monthly delinquency trend: share of open balance 30+ and 60+ days past due,
-- plus new defaults (loans that reached 90 DPD in the month).
SELECT
    as_of_date,
    COUNT(*) FILTER (WHERE status IN ('Performing', 'Delinquent'))           AS open_loans,
    ROUND(SUM(outstanding_balance_eur)
          FILTER (WHERE status IN ('Performing', 'Delinquent')), 0)          AS open_balance_eur,
    ROUND(SUM(outstanding_balance_eur) FILTER (WHERE days_past_due >= 30
          AND status IN ('Performing', 'Delinquent')) * 1.0
          / SUM(outstanding_balance_eur)
          FILTER (WHERE status IN ('Performing', 'Delinquent')), 4)          AS dpd30_plus_share,
    ROUND(SUM(outstanding_balance_eur) FILTER (WHERE days_past_due >= 60
          AND status IN ('Performing', 'Delinquent')) * 1.0
          / SUM(outstanding_balance_eur)
          FILTER (WHERE status IN ('Performing', 'Delinquent')), 4)          AS dpd60_plus_share,
    COUNT(*) FILTER (WHERE status = 'Defaulted')                             AS new_defaults,
    ROUND(SUM(outstanding_balance_eur) FILTER (WHERE status = 'Defaulted'), 0) AS new_default_eur
FROM performance
GROUP BY as_of_date
ORDER BY as_of_date;
