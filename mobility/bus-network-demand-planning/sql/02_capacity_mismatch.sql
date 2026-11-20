-- Trips where the operations log reports fewer seats than the timetable planned (V05),
-- and how many of them sold more tickets than the bus had seats.
WITH planned AS (
    SELECT line, direction, dep_time,
           CASE bus_type_planned WHEN 'double' THEN 79 ELSE 49 END AS planned_seats
    FROM timetable
)
SELECT o.line,
       COUNT(*)                                        AS trips,
       SUM(CASE WHEN b.peak_load > o.seats THEN 1 ELSE 0 END) AS overbooked_trips,
       MAX(b.peak_load - o.seats)                      AS max_seats_over,
       MIN(o.date)                                     AS first_date
FROM operations AS o
JOIN planned    AS p USING (line, direction, dep_time)
JOIN bookings   AS b USING (trip_id)
WHERE o.seats < p.planned_seats
  AND o.status = 'operated'
GROUP BY o.line;
