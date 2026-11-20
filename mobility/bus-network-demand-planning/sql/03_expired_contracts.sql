-- Trips run by a partner after its contract end date (V06).
SELECT p.partner_id, p.partner_name, p.contract_end,
       COUNT(*) AS trips_after_end, MIN(o.date) AS first_trip, MAX(o.date) AS last_trip
FROM operations AS o
JOIN partners   AS p USING (partner_id)
WHERE o.date > p.contract_end
GROUP BY p.partner_id, p.partner_name, p.contract_end;
