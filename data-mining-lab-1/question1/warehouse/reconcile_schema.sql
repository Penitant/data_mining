-- Task F support: load the old spreadsheet (finance_monthly.csv) as its own table,
-- clearly separate from mart_revenue_daily, so it can be diffed without confusion.
--   docker exec -i annapurna-postgres psql -U annapurna -d annapurna -f - < reconcile_schema.sql
-- Idempotent: DROP+CREATE+\copy, safe to re-run against a file that never changes.

DROP TABLE IF EXISTS finance_monthly_reported;

CREATE TABLE finance_monthly_reported (
    month         TEXT NOT NULL PRIMARY KEY,  -- 'YYYY-MM', as printed in the CSV
    closed_on     DATE NOT NULL,
    revenue_inr   NUMERIC(14,2) NOT NULL,
    signed_off_by TEXT NOT NULL
);

\copy finance_monthly_reported FROM '/refdata/finance_monthly.csv' WITH (FORMAT csv, HEADER true)
