-- Payout accounts used by three or more clients: a mule-network signal no transaction rule covers.
SELECT payout_account,
       COUNT(*)                        AS clients,
       GROUP_CONCAT(client_id, ', ')   AS client_ids
FROM clients
GROUP BY payout_account
HAVING COUNT(*) >= 3
ORDER BY clients DESC, payout_account;
