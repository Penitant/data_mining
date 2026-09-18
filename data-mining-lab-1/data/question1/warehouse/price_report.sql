-- "What did X sell for in <period>" report. Only the :report_month psql variable
-- changes between runs -- the query text never does:
--   docker exec -i annapurna-postgres psql -U annapurna -d annapurna \
--       -v report_month="'2024-03-01'" -f - < price_report.sql
--
-- A product can have several price_revisions rows inside one calendar month, so
-- "the price in March" needs one reference instant, not a range -- this uses the
-- LAST day of the requested month. Swap to month-START below for "price on the
-- 1st" instead; still one variable, not a code change.

\if :{?report_month}
\else
    \set report_month '''2024-03-01'''
\endif

SELECT
    :report_month::date AS report_month_start,
    (date_trunc('month', :report_month::date) + interval '1 month - 1 day')::date AS priced_as_of,
    pc.category_name,
    p.product_code,
    p.product_name,
    p.pack_size,
    pr.mrp,
    pr.selling_price,
    pr.effective_from,
    pr.effective_to
FROM products p
JOIN product_categories pc
    ON pc.category_id = p.category_id
JOIN price_revisions pr
    ON pr.product_sk = p.product_sk
   AND (date_trunc('month', :report_month::date) + interval '1 month - 1 day')::date
       BETWEEN pr.effective_from AND pr.effective_to
WHERE (date_trunc('month', :report_month::date) + interval '1 month - 1 day')::date
      BETWEEN p.valid_from AND p.valid_to
ORDER BY pc.category_name, p.product_name
LIMIT 10;
