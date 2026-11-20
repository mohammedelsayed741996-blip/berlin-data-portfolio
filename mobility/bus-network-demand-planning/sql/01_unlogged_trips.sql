-- Booked trips that never appear in the operations log (V03).
-- A trip with passengers but no operations record is either missing from the log
-- or was sold on a departure that did not run. Either way the partner bill and the KPIs are off.
-- Bookings for departures that are not in the timetable are a separate issue (V04) and excluded here.
SELECT b.trip_id, b.pax, b.revenue_eur
FROM bookings AS b
JOIN timetable AS t
  ON t.line      = SUBSTR(b.trip_id, 1, 4)
 AND t.direction = SUBSTR(b.trip_id, 5, 1)
 AND t.dep_time  = SUBSTR(b.trip_id, 16, 2) || ':' || SUBSTR(b.trip_id, 18, 2)
LEFT JOIN operations AS o ON o.trip_id = b.trip_id
WHERE o.trip_id IS NULL
  AND b.pax > 0
ORDER BY b.pax DESC;
