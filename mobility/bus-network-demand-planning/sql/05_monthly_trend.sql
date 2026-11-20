-- Passengers per line and month with the change against the same month a year earlier.
WITH m AS (
    SELECT o.line, SUBSTR(o.date, 1, 7) AS month, SUM(b.pax) AS pax
    FROM operations AS o
    JOIN bookings   AS b USING (trip_id)
    WHERE o.status = 'operated'
    GROUP BY o.line, SUBSTR(o.date, 1, 7)
)
SELECT line, month, pax,
       LAG(pax, 12) OVER (PARTITION BY line ORDER BY month)                         AS pax_last_year,
       ROUND(1.0 * pax / LAG(pax, 12) OVER (PARTITION BY line ORDER BY month) - 1, 3) AS yoy
FROM m
ORDER BY line, month;
