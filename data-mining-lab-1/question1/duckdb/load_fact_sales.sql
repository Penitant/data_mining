-- Idempotent load: fact_sales_line / mart_revenue_daily, rebuilt from raw MinIO files.
--   duckdb question1/duckdb/annapurna.duckdb \
--       -init question1/duckdb/setup.sql -f question1/duckdb/load_fact_sales.sql
--
-- Strategy: full rebuild from the immutable raw files every run (TRUNCATE-equivalent
-- + INSERT in one Postgres transaction), not an incremental upsert. Source files under
-- s3://annapurna-raw/sales/ don't change between runs, so output is a pure function of
-- that input. Resends (original + __R<n>) are read every run and deduped on
-- (bill_no, line_no) -- billing_notes.md's safe dedup unit -- with the highest resend
-- number winning ties.

-- 1. Read all three till dialects, normalise to one column set + resend rank.
CREATE OR REPLACE TEMP TABLE stg_lines_raw AS
-- S01-S05: comma, ISO timestamp, natural column names
SELECT
    bill_no, line_no, product_code, qty, unit_price, line_type,
    ts::TIMESTAMP AS ts,
    COALESCE(TRY_CAST(regexp_extract(filename, '__R(\d+)', 1) AS INT), 0) AS resend_rank,
    filename
FROM read_csv(
    's3://annapurna-raw/sales/store=S0[1-5]/year=*/month=*/*.csv',
    filename = true
)

UNION ALL

-- S06-S09: semicolon, dd-mm-yyyy timestamp, renamed columns
SELECT
    bill_no, line_no, item_code AS product_code, quantity AS qty,
    rate AS unit_price, type AS line_type,
    strptime(txn_time, '%d-%m-%Y %H:%M:%S') AS ts,
    COALESCE(TRY_CAST(regexp_extract(filename, '__R(\d+)', 1) AS INT), 0) AS resend_rank,
    filename
FROM read_csv(
    's3://annapurna-raw/sales/store=S0[6-9]/year=*/month=*/*.csv',
    delim = ';',
    filename = true,
    types = {'txn_time': 'VARCHAR'}
)

UNION ALL

-- S10-S12: comma, UTF-8 BOM header, epoch-seconds ts, reordered columns
SELECT
    bill_no, line_no, product_code, qty, unit_price, line_type,
    to_timestamp(ts)::TIMESTAMP AS ts,
    COALESCE(TRY_CAST(regexp_extract(filename, '__R(\d+)', 1) AS INT), 0) AS resend_rank,
    filename
FROM read_csv(
    's3://annapurna-raw/sales/store=S1[0-2]/year=*/month=*/*.csv',
    filename = true
);

-- 2. Dedup on (bill_no, line_no): keep the highest resend rank; a partial resend
--    simply never outranks lines it didn't include.
CREATE OR REPLACE TEMP TABLE stg_lines AS
SELECT bill_no, line_no, product_code, qty, unit_price, line_type, ts
FROM (
    SELECT *,
        ROW_NUMBER() OVER (
            PARTITION BY bill_no, line_no
            ORDER BY resend_rank DESC, filename DESC
        ) AS rn
    FROM stg_lines_raw
)
WHERE rn = 1;

-- 3. store/date come from bill_no (authoritative per billing_notes.md); product_sk
--    and category resolve via the deterministic (product_code, business_date)
--    temporal join against pg.products -- exact match + date range, no fuzzy matching
--    needed (reissued codes are a single clean non-overlapping cutover).
CREATE OR REPLACE TEMP TABLE stg_fact AS
SELECT
    s.bill_no,
    s.line_no,
    split_part(s.bill_no, '/', 1) AS store_id,
    strptime(split_part(s.bill_no, '/', 2), '%Y%m%d')::DATE AS business_date,
    s.product_code,
    p.product_sk,
    -- 'DISC' is the bill-level discount pseudo-code (not a product); VOID mirrors
    -- of a cancelled DISCOUNT line carry it too, so match on code, not line_type.
    CASE WHEN s.product_code = 'DISC' THEN 'C00' ELSE p.category_id END AS category_id,
    s.line_type,
    s.qty,
    s.unit_price,
    (s.qty * s.unit_price)::DECIMAL(14,2) AS line_amount,
    s.line_type IN ('SALE','RETURN','DISCOUNT','VOID') AS is_revenue,
    s.ts
FROM stg_lines s
LEFT JOIN pg.products p
    ON p.product_code = s.product_code
   AND strptime(split_part(s.bill_no, '/', 2), '%Y%m%d')::DATE
       BETWEEN p.valid_from AND p.valid_to;

-- 4. dim_date: static for the observed data year.
CREATE OR REPLACE TEMP TABLE stg_dim_date AS
SELECT
    d::DATE AS date_sk,
    year(d) AS year,
    month(d) AS month,
    strftime(d, '%B') AS month_name,
    ((month(d) - 1) / 3) + 1 AS quarter,
    day(d) AS day_of_month,
    isodow(d) AS day_of_week,
    strftime(d, '%A') AS day_name,
    isodow(d) IN (6, 7) AS is_weekend
FROM range(DATE '2024-01-01', DATE '2025-01-01', INTERVAL 1 DAY) t(d);

-- 5. Atomic swap: one transaction, so a failed/interrupted run leaves nothing half-written.
BEGIN TRANSACTION;

-- children before parent (FK to dim_date), then parent before children back up
DELETE FROM pg.mart_revenue_daily;
DELETE FROM pg.fact_sales_line;
DELETE FROM pg.dim_date;

INSERT INTO pg.dim_date SELECT * FROM stg_dim_date;

INSERT INTO pg.fact_sales_line
SELECT bill_no, line_no, store_id, business_date, product_code, product_sk,
       category_id, line_type, qty, unit_price, line_amount, is_revenue, ts
FROM stg_fact;

INSERT INTO pg.mart_revenue_daily
SELECT business_date, store_id, category_id,
       sum(line_amount) AS revenue,
       count(*) AS line_count
FROM stg_fact
WHERE is_revenue
GROUP BY business_date, store_id, category_id;

COMMIT;
