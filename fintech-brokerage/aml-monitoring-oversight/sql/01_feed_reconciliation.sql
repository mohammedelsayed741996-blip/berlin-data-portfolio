-- Core ledger vs transaction monitoring feed, by month and source. Any missing row is a finding.
SELECT substr(t.date, 1, 7)                                        AS month,
       CASE WHEN t.channel = 'CARD' THEN 'CARD ' || t.psp ELSE t.channel END AS source,
       COUNT(*)                                                    AS ledger_count,
       SUM(CASE WHEN f.tx_id IS NOT NULL THEN 1 ELSE 0 END)        AS feed_count,
       SUM(CASE WHEN f.tx_id IS NULL THEN 1 ELSE 0 END)            AS missing_count,
       ROUND(SUM(CASE WHEN f.tx_id IS NULL THEN t.amount_eur ELSE 0 END), 2) AS missing_eur
FROM transactions t
LEFT JOIN tm_feed_ids f ON f.tx_id = t.tx_id
GROUP BY 1, 2
HAVING missing_count > 0
ORDER BY 1, 2;
