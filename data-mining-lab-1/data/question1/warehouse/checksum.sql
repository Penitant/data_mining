-- Idempotency proof: row count + order-independent checksum of the two
-- rebuilt tables. Run after each load; three runs must print identical
-- triples for this to prove "run three times == run once".
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
