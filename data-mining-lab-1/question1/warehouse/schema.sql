-- Annapurna Stores -- dashboard star schema (question1). Idempotent: safe to re-run.
--   psql -h localhost -U annapurna -d annapurna -f schema.sql

-- Sentinel category for DISCOUNT lines (product_code = 'DISC', not a real product).
INSERT INTO product_categories (category_id, category_name, department, gst_rate)
VALUES ('C00', 'Unallocated (bill-level discount)', 'Adjustment', 0.000)
ON CONFLICT (category_id) DO NOTHING;

-- Precomputed calendar so day-of-week/month slices are a join, not a per-row EXTRACT().
CREATE TABLE IF NOT EXISTS dim_date (
    date_sk       DATE PRIMARY KEY,
    year          INT  NOT NULL,
    month         INT  NOT NULL,
    month_name    TEXT NOT NULL,
    quarter       INT  NOT NULL,
    day_of_month  INT  NOT NULL,
    day_of_week   INT  NOT NULL,   -- ISO: 1=Monday .. 7=Sunday
    day_name      TEXT NOT NULL,
    is_weekend    BOOLEAN NOT NULL
);

-- Grain = one raw billing line, every line_type kept for audit. Rebuild target of
-- duckdb/load_fact_sales.sql. PK (bill_no, line_no) per billing_notes.md's dedup unit.
CREATE TABLE IF NOT EXISTS fact_sales_line (
    bill_no        TEXT NOT NULL,
    line_no        INT  NOT NULL,
    store_id       TEXT NOT NULL REFERENCES stores(store_id),
    business_date  DATE NOT NULL REFERENCES dim_date(date_sk),
    product_code   TEXT,
    product_sk     BIGINT REFERENCES products(product_sk),
    category_id    TEXT REFERENCES product_categories(category_id),
    line_type      TEXT NOT NULL,
    qty            NUMERIC(12,3) NOT NULL,
    unit_price     NUMERIC(12,2) NOT NULL,
    line_amount    NUMERIC(14,2) NOT NULL,   -- qty * unit_price
    is_revenue     BOOLEAN NOT NULL,          -- line_type IN (SALE,RETURN,DISCOUNT,VOID)
    ts             TIMESTAMP NOT NULL,
    PRIMARY KEY (bill_no, line_no)
);

CREATE INDEX IF NOT EXISTS ix_fact_store_date    ON fact_sales_line (store_id, business_date);
CREATE INDEX IF NOT EXISTS ix_fact_date           ON fact_sales_line (business_date);
CREATE INDEX IF NOT EXISTS ix_fact_product        ON fact_sales_line (product_sk);
CREATE INDEX IF NOT EXISTS ix_fact_category_date  ON fact_sales_line (category_id, business_date) WHERE is_revenue;

-- Pre-aggregated cube the dashboard queries directly: one row per (date, store, category).
CREATE TABLE IF NOT EXISTS mart_revenue_daily (
    business_date  DATE NOT NULL REFERENCES dim_date(date_sk),
    store_id       TEXT NOT NULL REFERENCES stores(store_id),
    category_id    TEXT NOT NULL REFERENCES product_categories(category_id),
    revenue        NUMERIC(14,2) NOT NULL,
    line_count     INT NOT NULL,
    PRIMARY KEY (business_date, store_id, category_id)
);

CREATE INDEX IF NOT EXISTS ix_mart_store_date     ON mart_revenue_daily (store_id, business_date);
CREATE INDEX IF NOT EXISTS ix_mart_category_date  ON mart_revenue_daily (category_id, business_date);
CREATE INDEX IF NOT EXISTS ix_mart_date           ON mart_revenue_daily (business_date);
