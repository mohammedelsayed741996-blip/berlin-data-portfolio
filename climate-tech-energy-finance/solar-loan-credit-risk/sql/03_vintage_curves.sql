-- Cumulative default rate by quarterly vintage and months on book.
-- A vintage only reports months that every loan in it has reached,
-- so young vintages are not flattered by loans with no history yet.
WITH RECURSIVE mobs(mob) AS (
    SELECT 1 UNION ALL SELECT mob + 1 FROM mobs WHERE mob < 48
),
loan_vintage AS (
    SELECT
        loan_id,
        strftime('%Y', origination_date) || '-Q'
            || ((CAST(strftime('%m', origination_date) AS INTEGER) + 2) / 3) AS vintage,
        default_mob
    FROM loans
),
last_obs AS (
    SELECT loan_id, MAX(months_on_book) AS max_mob
    FROM performance
    GROUP BY loan_id
),
vintage_window AS (
    -- Months that every still-open loan in the vintage has reached.
    SELECT lv.vintage, MIN(o.max_mob) AS observed_mob
    FROM loan_vintage lv
    JOIN last_obs o ON o.loan_id = lv.loan_id
    JOIN loans l ON l.loan_id = lv.loan_id
    WHERE l.default_flag = 0 AND l.prepaid_flag = 0
    GROUP BY lv.vintage
)
SELECT
    lv.vintage,
    m.mob AS months_on_book,
    COUNT(*) AS loans,
    SUM(CASE WHEN lv.default_mob <= m.mob THEN 1 ELSE 0 END) AS cumulative_defaults,
    ROUND(AVG(CASE WHEN lv.default_mob <= m.mob THEN 1.0 ELSE 0.0 END), 4) AS cumulative_default_rate
FROM loan_vintage lv
JOIN vintage_window vw USING (vintage)
JOIN mobs m ON m.mob <= vw.observed_mob
GROUP BY lv.vintage, m.mob
ORDER BY lv.vintage, m.mob;
