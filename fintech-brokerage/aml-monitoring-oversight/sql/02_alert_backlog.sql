-- Alerts still open at a cut-off date, by age bucket and analyst.
WITH open_alerts AS (
    SELECT alert_id, analyst, rule,
           CAST(julianday(:as_of) - julianday(alert_date) AS INTEGER) AS age_days
    FROM alerts
    WHERE alert_date <= :as_of
      AND (l1_closed_date = '' OR l1_closed_date > :as_of)
)
SELECT analyst,
       COUNT(*)                                             AS open_alerts,
       SUM(CASE WHEN age_days > 30 THEN 1 ELSE 0 END)       AS over_sla,
       MAX(age_days)                                        AS oldest_days
FROM open_alerts
GROUP BY analyst
ORDER BY over_sla DESC, open_alerts DESC;
