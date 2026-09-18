-- Consolidated analytic/verification queries -- every query here was actually run
-- against the live containers while building this pipeline.
--   docker exec -i annapurna-postgres psql -U annapurna -d annapurna -f - < analytic.sql
-- Run duckdb/load_fact_sales.sql first (outside psql's reach) so these tables are populated.


-- TASK A/B -- sanity: what actually landed
SELECT 'dimension row counts' AS section;
SELECT
    (SELECT count(*) FROM stores)             AS stores,
    (SELECT count(*) FROM product_categories) AS categories,
    (SELECT count(*) FROM products)           AS products,
    (SELECT count(*) FROM price_revisions)    AS price_revisions;

SELECT 'fact/mart row counts' AS section;
SELECT
    (SELECT count(*) FROM fact_sales_line)   AS fact_sales_line_rows,
    (SELECT count(*) FROM mart_revenue_daily) AS mart_revenue_daily_rows,
    (SELECT count(*) FROM dim_date)           AS dim_date_rows;


-- TASK B -- idempotency proof: row count + order-independent checksum.
-- Run this after each of three successive loads; all three runs must print
-- the same two rows. (See README.md Task B for the recorded 3-run output.)
SELECT 'idempotency checksum' AS section;
SELECT
    'fact_sales_line' AS table_name,
    count(*) AS row_count,
    md5(string_agg(
        md5(bill_no || '|' || line_no || '|' || store_id || '|' || business_date
            || '|' || coalesce(product_code,'') || '|' || coalesce(product_sk::text,'')
            || '|' || coalesce(category_id,'') || '|' || line_type || '|' || qty
            || '|' || unit_price || '|' || line_amount || '|' || is_revenue || '|' || ts),
        '' ORDER BY bill_no, line_no
    )) AS checksum
FROM fact_sales_line
UNION ALL
SELECT
    'mart_revenue_daily',
    count(*),
    md5(string_agg(
        md5(business_date::text || '|' || store_id || '|' || category_id || '|' || revenue || '|' || line_count),
        '' ORDER BY business_date, store_id, category_id
    ))
FROM mart_revenue_daily;


-- TASK C -- dashboard slice shapes, with EXPLAIN so the index usage is
-- verified rather than assumed. All three should show Index/Bitmap scans
-- on mart_revenue_daily, not a sequential scan.
SELECT 'slice: one store, one month' AS section;
EXPLAIN (ANALYZE, COSTS OFF)
SELECT sum(revenue) FROM mart_revenue_daily
WHERE store_id = 'S01' AND business_date BETWEEN '2024-10-01' AND '2024-10-31';

SELECT 'slice: by category, one month' AS section;
EXPLAIN (ANALYZE, COSTS OFF)
SELECT category_id, sum(revenue) FROM mart_revenue_daily
WHERE business_date BETWEEN '2024-10-01' AND '2024-10-31'
GROUP BY category_id;

SELECT 'slice: by day of week, whole year' AS section;
EXPLAIN (ANALYZE, COSTS OFF)
SELECT d.day_name, sum(m.revenue)
FROM mart_revenue_daily m JOIN dim_date d ON d.date_sk = m.business_date
GROUP BY d.day_name;

SELECT 'slice: by month, whole year (answers the CFO directly)' AS section;
SELECT d.month_name, d.year, sum(m.revenue) AS revenue
FROM mart_revenue_daily m JOIN dim_date d ON d.date_sk = m.business_date
GROUP BY d.year, d.month, d.month_name
ORDER BY d.year, d.month;


-- TASK C -- product code reissue: prove the join is safe (no overlapping
-- validity ranges for any reissued code), not a fuzzy-match / embedding
-- problem.
SELECT 'reissued codes: count + cutover date' AS section;
SELECT product_code, count(*) AS n_versions, min(valid_from) AS first_valid_from, max(valid_to) AS last_valid_to
FROM products
GROUP BY product_code HAVING count(*) > 1
ORDER BY product_code;

SELECT 'reissued codes: overlap check (expect 0 rows)' AS section;
SELECT a.product_code
FROM products a JOIN products b
    ON a.product_code = b.product_code AND a.product_sk < b.product_sk
   AND a.valid_from <= b.valid_to AND b.valid_from <= a.valid_to;


-- TASK D -- price-as-of report, same query text, two periods. See
-- warehouse/price_report.sql for the parameterised version driven by
-- :report_month; reproduced here inline for both periods for convenience.
SELECT 'price as of March 2024 vs October 2024: Sunfeast Cookies 150g' AS section;
SELECT p.product_name, pr.selling_price, pr.effective_from, pr.effective_to
FROM products p JOIN price_revisions pr ON pr.product_sk = p.product_sk
WHERE p.product_name = 'Sunfeast Cookies 150g'
ORDER BY pr.effective_from;


-- TASK F -- reconciliation against the old spreadsheet
-- (finance_monthly.csv, loaded as finance_monthly_reported by
-- warehouse/reconcile_schema.sql). Nine of twelve months match to the
-- rupee; the three that don't are investigated in README.md Task F using
-- evidence from this data, not asserted.
SELECT 'reconciliation: pipeline vs finance-reported, by month' AS section;
SELECT
    f.month,
    m.revenue          AS pipeline_revenue,
    f.revenue_inr       AS finance_revenue,
    f.revenue_inr - m.revenue AS finance_minus_pipeline
FROM finance_monthly_reported f
JOIN (
    SELECT to_char(business_date,'YYYY-MM') AS month, sum(revenue) AS revenue
    FROM mart_revenue_daily GROUP BY 1
) m ON m.month = f.month
ORDER BY f.month;

SELECT 'March evidence: largest single bills (nothing near the 486,250 gap)' AS section;
SELECT bill_no, sum(line_amount) AS bill_revenue
FROM fact_sales_line WHERE is_revenue AND business_date BETWEEN '2024-03-01' AND '2024-03-31'
GROUP BY bill_no ORDER BY bill_revenue DESC LIMIT 5;

SELECT 'July evidence: S07 avg daily revenue vs the 3-day file gap' AS section;
SELECT count(*) AS days_present_in_july,
       round(avg(daily_rev),2) AS avg_daily_rev,
       round(avg(daily_rev) * 3, 2) AS est_revenue_for_3_missing_days
FROM (
    SELECT business_date, sum(revenue) AS daily_rev
    FROM mart_revenue_daily WHERE store_id = 'S07' AND business_date BETWEEN '2024-07-01' AND '2024-07-31'
    GROUP BY business_date
) t;

SELECT 'December evidence: rounding every bill to the rupee before summing' AS section;
WITH per_bill AS (
    SELECT bill_no, sum(line_amount) AS bill_revenue
    FROM fact_sales_line WHERE is_revenue AND business_date BETWEEN '2024-12-01' AND '2024-12-31'
    GROUP BY bill_no
)
SELECT count(*) AS n_bills,
       round(sum(bill_revenue), 2) AS exact_sum,
       sum(round(bill_revenue))    AS rounded_per_bill_sum,
       sum(round(bill_revenue)) - sum(bill_revenue) AS rounding_delta
FROM per_bill;
