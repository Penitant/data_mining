-- Task E: one query across both systems, no staging either side. read_csv() hits MinIO
-- over httpfs; pg.* hits Postgres live over the postgres extension; DuckDB joins the
-- two streams itself.
--   duckdb question1/duckdb/annapurna.duckdb \
--       -init question1/duckdb/setup.sql -f question1/duckdb/federated_query.sql
-- For "which parts ran where", see EXPLAIN of this query in README.md Task E -- read
-- off the physical plan's operator names, not asserted from documentation.

SELECT
    s.store_name,
    pc.category_name,
    sum(r.qty * r.unit_price) AS gross_line_amount,
    count(*) AS n_lines
FROM read_csv('s3://annapurna-raw/sales/store=S01/year=2024/month=10/*.csv') r
JOIN pg.stores s
    ON s.store_id = split_part(r.bill_no, '/', 1)
JOIN pg.products p
    ON p.product_code = r.product_code
   AND strptime(split_part(r.bill_no, '/', 2), '%Y%m%d')::DATE
       BETWEEN p.valid_from AND p.valid_to
JOIN pg.product_categories pc
    ON pc.category_id = p.category_id
WHERE r.line_type = 'SALE'
GROUP BY s.store_name, pc.category_name
ORDER BY gross_line_amount DESC;
