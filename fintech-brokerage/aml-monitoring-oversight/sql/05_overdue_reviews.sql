-- Clients past their periodic review date (12 / 24 / 36 months by risk rating).
SELECT risk_rating,
       COUNT(*) AS clients,
       SUM(CASE WHEN julianday(last_review_date) +
                     (CASE risk_rating WHEN 'high' THEN 12 WHEN 'medium' THEN 24 ELSE 36 END) * 30.4
                     < julianday(:as_of) THEN 1 ELSE 0 END) AS overdue
FROM clients
GROUP BY risk_rating
ORDER BY CASE risk_rating WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END;
