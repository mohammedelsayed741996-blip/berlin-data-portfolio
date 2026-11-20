-- Line KPIs for one period, the same definitions as analysis.line_kpis.
-- Load factor = passenger-km / seat-km over the whole line.
-- Uses logged trips only; the Python KPIs also count the trips missing from the log (V03), so passenger totals differ slightly.
WITH trips AS (
    SELECT o.line, o.trip_id, o.seats, b.pax, b.pax_km, b.revenue_eur, b.sold_out
    FROM operations AS o
    JOIN bookings   AS b USING (trip_id)
    WHERE o.status = 'operated'
      AND o.date BETWEEN :start AND :end
),
km AS (
    SELECT line, SUM(seg_km) AS line_km FROM line_km GROUP BY line
)
SELECT t.line,
       COUNT(*)                                             AS trips,
       SUM(t.pax)                                           AS pax,
       ROUND(SUM(t.pax_km) / SUM(t.seats * k.line_km), 4)   AS load_factor,
       ROUND(AVG(t.sold_out), 4)                            AS sold_out_share,
       ROUND(SUM(t.revenue_eur), 0)                         AS revenue_eur
FROM trips AS t
JOIN km    AS k USING (line)
GROUP BY t.line
ORDER BY t.line;
