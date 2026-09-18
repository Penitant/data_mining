-- Task D: prove the access method, don't assert it.
-- Real lookup for the largest real bucket in the loaded index
-- (band_idx=73, size 53 -- see load_bands.py / the GROUP BY that found it).

\echo '=== 1. chosen: composite B-tree on (band_idx,k1,k2,k3), planner default ==='
EXPLAIN (ANALYZE, BUFFERS, TIMING)
SELECT notice_id FROM lsh_bands
WHERE band_idx = 73 AND k1 = 31867835869977615 AND k2 = 3755123195492001 AND k3 = 5647134920104216;

\echo '=== 2. rejected alternative: same query, index scans forced off (seq scan) ==='
SET enable_indexscan = off;
SET enable_bitmapscan = off;
SET enable_indexonlyscan = off;
EXPLAIN (ANALYZE, BUFFERS, TIMING)
SELECT notice_id FROM lsh_bands
WHERE band_idx = 73 AND k1 = 31867835869977615 AND k2 = 3755123195492001 AND k3 = 5647134920104216;
RESET enable_indexscan;
RESET enable_bitmapscan;
RESET enable_indexonlyscan;

\echo '=== 3. rejected alternative: single-column HASH index on bucket_hash ==='
EXPLAIN (ANALYZE, BUFFERS, TIMING)
SELECT notice_id FROM lsh_bands
WHERE bucket_hash = hashtext('73:31867835869977615:3755123195492001:5647134920104216');

\echo '=== 4. correctness check: bucket_hash alone, without the true-column recheck ==='
-- how many rows does the raw 32-bit hash match that do NOT belong to this
-- band key -- i.e. hash collisions the hash-only index would have to
-- filter back out, proving it cannot be used standalone.
SELECT count(*) AS hash_matches,
       count(*) FILTER (WHERE NOT (band_idx = 73 AND k1 = 31867835869977615
                                    AND k2 = 3755123195492001 AND k3 = 5647134920104216)) AS false_positive_rows
FROM lsh_bands
WHERE bucket_hash = hashtext('73:31867835869977615:3755123195492001:5647134920104216');
