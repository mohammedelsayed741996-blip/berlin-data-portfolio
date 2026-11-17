-- Month-on-month roll rates between delinquency buckets.
WITH bucketed AS (
    SELECT
        loan_id,
        months_on_book,
        CASE
            WHEN status = 'Defaulted' THEN '4 Default'
            WHEN status = 'Prepaid'   THEN '5 Prepaid'
            WHEN days_past_due = 0    THEN '0 Current'
            WHEN days_past_due = 30   THEN '1 DPD30'
            WHEN days_past_due = 60   THEN '2 DPD60'
            ELSE '3 DPD90'
        END AS bucket
    FROM performance
),
transitions AS (
    SELECT a.bucket AS from_bucket, b.bucket AS to_bucket
    FROM bucketed a
    JOIN bucketed b
      ON b.loan_id = a.loan_id AND b.months_on_book = a.months_on_book + 1
    WHERE a.bucket IN ('0 Current', '1 DPD30', '2 DPD60')
)
SELECT
    from_bucket,
    to_bucket,
    COUNT(*) AS transitions,
    ROUND(COUNT(*) * 1.0 / SUM(COUNT(*)) OVER (PARTITION BY from_bucket), 4) AS roll_rate
FROM transitions
GROUP BY from_bucket, to_bucket
ORDER BY from_bucket, to_bucket;
