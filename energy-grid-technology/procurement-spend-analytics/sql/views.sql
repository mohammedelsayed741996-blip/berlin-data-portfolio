-- Spend cube views. Spend excludes returns unless the name says otherwise; amounts in EUR.

DROP VIEW IF EXISTS v_spend_by_category;
CREATE VIEW v_spend_by_category AS
SELECT c.category, c.category_name, c.spend_type,
       ROUND(SUM(f.spend_eur), 0)                                   AS spend_eur,
       ROUND(100.0 * SUM(f.spend_eur) / (SELECT SUM(spend_eur) FROM fact_po_line WHERE is_return = 0), 1) AS share_pct,
       COUNT(DISTINCT f.supplier_id)                                AS suppliers,
       ROUND(100.0 * SUM(CASE WHEN f.on_contract = 1 THEN f.spend_eur END) / SUM(f.spend_eur), 1) AS on_contract_pct
FROM fact_po_line f JOIN dim_category c USING (category)
WHERE f.is_return = 0
GROUP BY c.category, c.category_name, c.spend_type;

-- Pareto: cumulative share of spend by supplier, largest first
DROP VIEW IF EXISTS v_supplier_pareto;
CREATE VIEW v_supplier_pareto AS
WITH s AS (
  SELECT supplier_id, SUM(spend_eur) AS spend_eur FROM fact_po_line WHERE is_return = 0 GROUP BY supplier_id
)
SELECT s.supplier_id, d.supplier_name, d.country, ROUND(s.spend_eur, 0) AS spend_eur,
       ROW_NUMBER() OVER (ORDER BY s.spend_eur DESC)                                        AS rank,
       ROUND(SUM(s.spend_eur) OVER (ORDER BY s.spend_eur DESC ROWS UNBOUNDED PRECEDING)
             / SUM(s.spend_eur) OVER (), 4)                                                AS cumulative_share
FROM s JOIN dim_supplier d USING (supplier_id);

-- Supplier concentration per category: Herfindahl-Hirschman index on spend shares (0-10,000)
DROP VIEW IF EXISTS v_category_concentration;
CREATE VIEW v_category_concentration AS
WITH s AS (
  SELECT category, supplier_id, SUM(spend_eur) AS spend_eur FROM fact_po_line WHERE is_return = 0 GROUP BY category, supplier_id
), sh AS (
  SELECT category, supplier_id, spend_eur, 100.0 * spend_eur / SUM(spend_eur) OVER (PARTITION BY category) AS share
  FROM s
)
SELECT category, COUNT(*) AS suppliers, ROUND(SUM(share * share), 0) AS hhi, ROUND(MAX(share), 1) AS top_supplier_share_pct
FROM sh GROUP BY category;

-- Monthly spend with a 3-month moving average
DROP VIEW IF EXISTS v_monthly_spend;
CREATE VIEW v_monthly_spend AS
WITH m AS (SELECT month, category, SUM(spend_eur) AS spend_eur FROM fact_po_line WHERE is_return = 0 GROUP BY month, category)
SELECT month, category, ROUND(spend_eur, 0) AS spend_eur,
       ROUND(AVG(spend_eur) OVER (PARTITION BY category ORDER BY month ROWS 2 PRECEDING), 0) AS spend_3m_avg
FROM m;

-- Off-contract ("maverick") spend in categories that have framework agreements
DROP VIEW IF EXISTS v_maverick;
CREATE VIEW v_maverick AS
SELECT f.category, f.plant, ROUND(SUM(f.spend_eur), 0) AS maverick_spend_eur, COUNT(*) AS lines, COUNT(DISTINCT f.supplier_id) AS suppliers
FROM fact_po_line f WHERE f.maverick = 1 GROUP BY f.category, f.plant;

-- Supplier performance: delivery and quality, only lines with a usable goods receipt
DROP VIEW IF EXISTS v_supplier_performance;
CREATE VIEW v_supplier_performance AS
SELECT f.supplier_id, d.supplier_name, d.country, d.country_risk,
       ROUND(SUM(f.spend_eur), 0)                       AS spend_eur,
       COUNT(*)                                         AS lines,
       SUM(f.on_time IS NOT NULL)                       AS receipts,
       ROUND(AVG(f.on_time), 3)                         AS on_time_rate,
       ROUND(AVG(CASE WHEN f.days_late > 2 THEN f.days_late END), 1) AS avg_days_late_when_late,
       ROUND(AVG(f.defect), 4)                          AS defect_rate
FROM fact_po_line f JOIN dim_supplier d USING (supplier_id)
WHERE f.is_return = 0
GROUP BY f.supplier_id, d.supplier_name, d.country, d.country_risk;
