-- Annapurna Stores Q1 -- DuckDB analytical engine bootstrap
-- Run:  duckdb question1/duckdb/annapurna.duckdb -init question1/duckdb/setup.sql

INSTALL httpfs;
INSTALL postgres;
LOAD httpfs;
LOAD postgres;

-- MinIO connection (S3-compatible), credentials match docker-compose.yml
CREATE OR REPLACE SECRET minio_annapurna (
    TYPE S3,
    KEY_ID 'annapurna',
    SECRET 'annapurna123',
    ENDPOINT 'localhost:9000',
    URL_STYLE 'path',
    USE_SSL false
);

-- Postgres warehouse (dimensions: stores, product_categories, products, price_revisions)
ATTACH IF NOT EXISTS 'host=localhost port=5432 dbname=annapurna user=annapurna password=annapurna'
    AS pg (TYPE postgres);

-- Raw sales objects live under sales/store=<S..>/year=<YYYY>/month=<MM>/*.csv in MinIO,
-- so a store+month query prunes to one partition instead of scanning the whole bucket:
--   SELECT * FROM read_csv('s3://annapurna-raw/sales/store=S01/year=2024/month=10/*.csv',
--       hive_partitioning = true, filename = true)
-- The three till generations use different delimiters/column orders/timestamp formats
-- (see billing_notes.md), so normalising them into one schema is load_fact_sales.sql, not this file.
