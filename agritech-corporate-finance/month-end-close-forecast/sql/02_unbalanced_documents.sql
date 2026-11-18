-- Documents whose lines do not net to zero.
SELECT company_code, doc_no, doc_type, MIN(text) AS text,
       ROUND(SUM(amount_eur), 2) AS difference_eur
FROM gl_items
WHERE month = :close_month
GROUP BY company_code, doc_no, doc_type
HAVING ROUND(SUM(amount_eur), 2) <> 0;
