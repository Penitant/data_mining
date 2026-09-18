-- Task D: durable, queryable form of the Task C candidate index
-- (r=3, b=200 bands over the k=600, document-frequency-filtered MinHash
-- sketch). One row per (notice, band) -- this is the on-disk form of the
-- in-memory `buckets` dict lsh.py builds, so a lookup survives a process
-- restart and the application can query it directly.

DROP TABLE IF EXISTS lsh_bands;

CREATE TABLE lsh_bands (
    notice_id   TEXT     NOT NULL,
    band_idx    SMALLINT NOT NULL,
    k1          BIGINT   NOT NULL,
    k2          BIGINT   NOT NULL,
    k3          BIGINT   NOT NULL,
    -- single-column stand-in for (band_idx,k1,k2,k3), for the hash-index
    -- comparison in explain_lookup.py -- see README for why this loses.
    bucket_hash INTEGER GENERATED ALWAYS AS (
        hashtext(band_idx::text || ':' || k1::text || ':' || k2::text || ':' || k3::text)
    ) STORED,
    PRIMARY KEY (notice_id, band_idx)
);

-- Chosen access method: composite B-tree on the true equality columns.
-- No collision risk (it indexes the actual band key, not a hash of it),
-- supports the lookup query directly.
CREATE INDEX idx_lsh_btree ON lsh_bands (band_idx, k1, k2, k3);

-- Rejected alternative, built anyway so explain_lookup.py can measure it
-- rather than assert it loses. See README for the birthday-bound math on
-- why bucket_hash alone is not a safe standalone key at this row count.
CREATE INDEX idx_lsh_hash ON lsh_bands USING HASH (bucket_hash);

ANALYZE lsh_bands;
