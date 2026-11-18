-- Vendor invoices posted more than once (same company, vendor, reference and amount).
SELECT company_code, vendor, reference, -amount_eur AS amount_eur,
       COUNT(*) AS times_posted,
       GROUP_CONCAT(doc_no, ', ') AS documents
FROM gl_items
WHERE gl_account = '3300' AND doc_type = 'KR' AND reference <> ''
GROUP BY company_code, vendor, reference, amount_eur
HAVING COUNT(*) > 1;
