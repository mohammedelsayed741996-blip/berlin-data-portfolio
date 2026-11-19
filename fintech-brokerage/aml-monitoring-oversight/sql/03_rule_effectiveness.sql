-- Alerts, escalations and SAR conversion per rule (closed alerts only).
SELECT rule,
       COUNT(*)                                                          AS alerts,
       SUM(CASE WHEN l1_decision = 'escalated' THEN 1 ELSE 0 END)        AS escalated,
       SUM(CASE WHEN l2_decision = 'SAR filed' THEN 1 ELSE 0 END)        AS sars,
       ROUND(1.0 * SUM(CASE WHEN l2_decision = 'SAR filed' THEN 1 ELSE 0 END) / COUNT(*), 3) AS sar_conversion
FROM alerts
WHERE l1_decision <> 'open'
GROUP BY rule
ORDER BY rule;
