-- Exposure by installer partner at the observation date, with each partner's
-- share of the book and its lifetime default rate. HHI is computed on top.
WITH latest AS (
    SELECT loan_id, outstanding_balance_eur
    FROM performance
    WHERE as_of_date = (SELECT MAX(as_of_date) FROM performance)
      AND status IN ('Performing', 'Delinquent')
),
by_installer AS (
    SELECT
        l.installer_id,
        COUNT(*)                        AS open_loans,
        SUM(lt.outstanding_balance_eur) AS exposure_eur
    FROM latest lt
    JOIN loans l USING (loan_id)
    GROUP BY l.installer_id
),
history AS (
    SELECT installer_id, COUNT(*) AS loans_written, AVG(default_flag) AS lifetime_default_rate
    FROM loans
    GROUP BY installer_id
)
SELECT
    b.installer_id,
    i.installer_region,
    i.installer_tenure_years,
    b.open_loans,
    ROUND(b.exposure_eur, 0)                                        AS exposure_eur,
    ROUND(b.exposure_eur / SUM(b.exposure_eur) OVER (), 4)          AS share_of_book,
    h.loans_written,
    ROUND(h.lifetime_default_rate, 4)                               AS lifetime_default_rate,
    RANK() OVER (ORDER BY b.exposure_eur DESC)                      AS exposure_rank
FROM by_installer b
JOIN installers i USING (installer_id)
JOIN history h USING (installer_id)
ORDER BY exposure_rank;
