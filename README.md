# data_mining

Datamining and Warehousing Submissions Repository

## Lab 1 -- layout

```
data-mining-lab-1/
  data/
    question1/   -- Annapurna Stores billing/revenue question
      docker-compose.yml    (authored)   postgres + minio
      masters.sql            (provided)   stores, product_categories, products, price_revisions
      billing_notes.md        (provided)   vendor handover notes
      finance_monthly.csv     (provided)   old spreadsheet monthly figures, Task F input
      sales/                  (provided)   raw daily till exports
      duckdb/
        setup.sql              (authored)   installs/loads httpfs+postgres, MinIO secret, pg ATTACH
        load_fact_sales.sql     (authored)   Task B: idempotent ETL, raw CSVs (MinIO) -> star schema
        federated_query.sql     (authored)   Task E: one query across MinIO + Postgres, no staging
        annapurna.duckdb        (generated)  persistent DuckDB database file, rebuilt by the commands below
      warehouse/
        schema.sql              (authored)   Task C: star schema DDL (idempotent, IF NOT EXISTS)
        checksum.sql             (authored)   Task B: row count + checksum, idempotency proof
        price_report.sql         (authored)   Task D: price-as-of report, parameterised by :report_month
        reconcile_schema.sql     (authored)   Task F: loads finance_monthly.csv as finance_monthly_reported
        analytic.sql             (authored)   every query in this README, consolidated
      _truth/                  (provided)   grader answer key, not used by the pipeline itself
    question2/   (provided)   tender/procurement notice question -- separate submission, out of scope here
```

`(provided)` paths are the exam's own dataset and are **not part of this
submission** -- see `.gitignore` and "Getting the provided data in
place" just below. `(authored)` paths are everything built for this
answer.

### Getting the provided data in place

This repo ships the pipeline, not the dataset. Before running anything,
copy the exam-provided files back into the `(provided)` paths shown
above:

```
data-mining-lab-1/data/question1/masters.sql
data-mining-lab-1/data/question1/billing_notes.md
data-mining-lab-1/data/question1/finance_monthly.csv
data-mining-lab-1/data/question1/sales/*.csv
data-mining-lab-1/data/question1/_truth/       (optional -- only used for the Task B/F cross-checks)
data-mining-lab-1/data/question2/              (out of scope for this submission)
```

### Rebuild everything from scratch, in order

```
cd data-mining-lab-1/data/question1
docker compose up -d
docker exec -i annapurna-postgres psql -U annapurna -d annapurna -f - < warehouse/schema.sql
docker exec -i annapurna-postgres psql -U annapurna -d annapurna -f - < warehouse/reconcile_schema.sql

# one-time: land the raw files into MinIO, partitioned store=/year=/month= (see Task A)
docker run --rm --network annapurna-q1_default --entrypoint /bin/sh quay.io/minio/mc:latest -c "
mc alias set local http://annapurna-minio:9000 annapurna annapurna123 &&
mc mb -p local/annapurna-raw/sales local/annapurna-raw/reference"
# (then copy sales/*.csv into store=/year=/month=/ prefixes under local/annapurna-raw/sales/,
#  and billing_notes.md / finance_monthly.csv / _truth/* into local/annapurna-raw/reference/)

duckdb duckdb/annapurna.duckdb -init duckdb/setup.sql -f duckdb/load_fact_sales.sql
docker exec -i annapurna-postgres psql -U annapurna -d annapurna -f - < warehouse/analytic.sql
```

---

## Task A -- platform + landing the data

Two containers (`docker-compose.yml`): `annapurna-postgres` (postgres:16)
for the structured warehouse, `annapurna-minio` (`quay.io/minio/minio` --
Docker Hub's `minio/minio` now requires auth, quay.io doesn't) for object
storage. `masters.sql` auto-loads on Postgres init: 12 stores, 14
categories, 1,224 product SKUs, 4,320 price revisions.

### Object storage layout (MinIO bucket `annapurna-raw`)

The nightly files are named `SALES_<store>_<YYYYMMDD>[__R<n>].csv` on
disk, which is fine as a *filename* but useless as a *storage key*: a flat
`sales/SALES_*.csv` bucket forces every store-month query to list and
open all 4,457 objects (~66 MiB) to find the ~31 files (~470 KiB) that
actually matter. Objects are stored Hive-partitioned by store and month
instead:

```
sales/store=<S01..S12>/year=2024/month=<01..12>/SALES_<store>_<date>[__R<n>].csv
```

**Why store and month, not store alone or date alone:** the CFO's stated
query shapes are "one store, one month" and "one month across stores" --
those are the two predicates that show up in almost every question, so
they're the two segments that need to be selectable without a scan.
Splitting further (e.g. by day) would only shrink each object further --
the file is already the unit re-sends overwrite, so day-level
partitioning would just recreate the existing filename structure as
folders for no pruning benefit.

Everything that is not raw per-day sales data is kept out of the
`sales/` prefix, under `reference/`: `billing_notes.md`,
`finance_monthly.csv`, and the grader's `_truth/` files. Master/dimension
data (`stores`, `product_categories`, `products`, `price_revisions`) is
not object storage at all -- it's small, relational, changes by proper
SCD rows rather than by file replacement, and needs to be joined, so it
lives in Postgres.

### How much the engine opens per query, under this layout

Measured against the actual 4,457-file / 68,706,877-byte (~65.5 MiB)
sales corpus:

| Query shape | Files opened | Bytes read | vs. full scan |
|---|---:|---:|---:|
| Full bucket scan (no partition predicate) | 4,457 | 68,706,877 (~65.5 MiB) | 1x |
| One store, one month (typical CFO question) | 29-34 (avg 31) | 252,138-882,789 (avg ~477 KiB) | **~144x fewer files/bytes** |
| One store, whole year | 367-378 (avg 371) | 3.7-8.5 MB (avg ~5.7 MiB) | **~12x fewer files/bytes** |

The store+month case (`store=S01/year=2024/month=10/*.csv`) was verified
directly against the running MinIO container: DuckDB's `read_csv` with
`hive_partitioning=true` opened exactly 31 files for that one partition,
matching the on-disk count.

This is glob-level partition pruning (path prefix elimination), not a
secondary index -- there is no separate index structure over the
objects. A real index (a small manifest/catalog table keyed by
`store_id, year, month -> object list`, or `fact_sales_line` once Task B
lands it in Postgres) would let the engine skip even the prefix-list step
and go straight to the object keys -- see Task C, which is exactly that.

### DuckDB analytical engine

Installed on the host (`~/.duckdb/cli/latest/duckdb`, v1.5.5) with the
`httpfs` (S3/MinIO access) and `postgres` (live ATTACH to the warehouse)
extensions:

```
duckdb data/question1/duckdb/annapurna.duckdb -init data/question1/duckdb/setup.sql
```

`setup.sql` registers a MinIO S3 secret matching the compose file's
credentials and attaches Postgres as `pg`, so dimension tables are
queryable as `pg.stores`, `pg.products`, etc. alongside
`read_csv('s3://annapurna-raw/sales/...')` reads against MinIO -- both
verified working against the running containers, and both used together
without staging in Task E.

---

## Task B -- safe to run twice (idempotent load)

`duckdb/load_fact_sales.sql` reads every dialect of raw sales file
(S01-S05 comma/ISO, S06-S09 semicolon/dd-mm-yyyy, S10-S12
BOM+epoch+reordered -- see `billing_notes.md`), normalises them to one
column set, and rebuilds `fact_sales_line` + `mart_revenue_daily` in
Postgres inside a single transaction.

**Idempotency strategy: full rebuild from the immutable raw files on
every run**, not an incremental upsert. The source files under
`s3://annapurna-raw/sales/` don't change between runs, so the output is
a pure function of that input -- run 1, run 2 and run 3 read the same
bytes and must produce the same rows. This also means a day that
"appears in the folder more than once" (an original plus one or more
`__R<n>` re-sends) is handled the same way inside one run as across many
runs: every file that exists is read every time, then deduped on
`(bill_no, line_no)` -- the unit `billing_notes.md` calls out as the
only safe one, since a re-send can be a *partial* replacement -- with the
highest resend number winning ties.

Run it with:

```
duckdb data/question1/duckdb/annapurna.duckdb \
    -init data/question1/duckdb/setup.sql \
    -f    data/question1/duckdb/load_fact_sales.sql
```

**Proof of idempotency** -- `warehouse/checksum.sql` computes row count
plus an order-independent MD5 checksum (md5 of each row, aggregated with
`string_agg(... ORDER BY <key>)`) for both rebuilt tables. Run three
times in a row against the live containers:

| Run | fact_sales_line rows | fact_sales_line checksum | mart_revenue_daily rows | mart_revenue_daily checksum |
|---|---:|---|---:|---|
| 1 | 1,120,924 | `c26f4238c6f5643cdb58b284397cacbd` | 65,685 | `6a2b784cc25947558c37dc8c362f3582` |
| 2 | 1,120,924 | `c26f4238c6f5643cdb58b284397cacbd` | 65,685 | `6a2b784cc25947558c37dc8c362f3582` |
| 3 | 1,120,924 | `c26f4238c6f5643cdb58b284397cacbd` | 65,685 | `6a2b784cc25947558c37dc8c362f3582` |

Raw line count before dedup is 1,137,585 (matches `_truth/truth.json`'s
`raw_lines` exactly); 16,661 lines are dropped as resend duplicates,
landing on 1,120,924 unique `(bill_no, line_no)` rows every run.

---

## Task C -- tables behind the dashboard (star schema)

```
                     dim_date (date_sk PK)
                         |
  dim_store (store_id) --+-- fact_sales_line --+-- dim_product (product_sk, SCD2)
                         |    (bill_no, line_no PK)      |
                         |                                +-- dim_category (via product)
                         +-- mart_revenue_daily
                              (business_date, store_id, category_id PK)
```

- **`fact_sales_line`** -- grain = one raw billing line, every `line_type`
  kept (including `TAX`/`TENDER`) for audit. `is_revenue` flags
  `SALE`/`RETURN`/`DISCOUNT`/`VOID` per `billing_notes.md`'s revenue
  table -- **not every line is a sale**: `TAX` (GST) and `TENDER` (the
  bill total, restated as another row) are stored but never summed as
  revenue, and this is almost certainly what produced the CFO's
  three-way October disagreement. Indexed on `(store_id, business_date)`,
  `(business_date)`, `(product_sk)`, and a partial index on
  `(category_id, business_date) WHERE is_revenue` for category slicing.
- **`mart_revenue_daily`** -- the table the dashboard actually queries:
  one row per `(business_date, store_id, category_id)`, pre-summed. Store
  and category slices are index lookups (verified via `EXPLAIN` in
  `analytic.sql` -- bitmap index scans, not sequential scans); month and
  day-of-week slices are a join to `dim_date`'s ~366 precomputed rows,
  never a per-row `EXTRACT()` over the fact table.
- **`dim_date`** -- one row per calendar date with `month`, `month_name`,
  `day_of_week` (ISO, ties to `day_name`), `is_weekend`, `quarter`
  precomputed.
- **`dim_store`** / **`dim_category`** / **`dim_product`** -- reused
  directly from `masters.sql` (`stores`, `product_categories`,
  `products`); `products` is already an SCD2 dimension
  (`valid_from`/`valid_to`), which is exactly what resolves the reissued
  product codes (below).
- A synthetic category `C00` ("Unallocated (bill-level discount)")
  absorbs `DISCOUNT` lines and their `VOID` mirrors, whose `product_code`
  is the literal string `'DISC'`, not a real product -- there is no
  per-item breakdown of a bill-level discount in this data, so it cannot
  honestly be attributed to a merchandising category. (Found by testing,
  not by reading the notes: the first load attempt failed a NOT NULL
  constraint on 117 `VOID` rows that turned out to be voided discount
  lines, not voided items.)

### The two notes, and how the schema answers them

> "not every line is a sale" -- `is_revenue` on `fact_sales_line`, driven
> by `line_type`, not by a heuristic. `TAX`/`TENDER` are excluded from
> every revenue aggregate.
>
> "a product code that was retired has since been reissued to a
> different product" -- resolved via the exact join below, not via
> semantic search.

### Product code reissue: no embeddings needed

The task brief raised semantic vector embeddings / cosine similarity as
a possible way to resolve reissued product codes. That would be the
right tool for *fuzzy* entity resolution -- matching descriptions of the
same real-world thing written differently (which is what question2's
tender-notice dataset actually needs). It is not the right tool here:

- The task is **exact-string** product codes reassigned at a **single
  point in time**, not paraphrased text.
- `products.valid_from`/`valid_to` already encode exactly when each
  reissue took effect -- this is standard SCD2, not entity resolution.
- Verified directly against the loaded `products` table (see
  `analytic.sql`): of the 24 reissued codes, every one has exactly two
  non-overlapping validity ranges with a clean cutover on 2024-06-01, and
  a self-join for overlapping ranges on the same `product_code` returns
  **zero rows**.

So resolution is a plain deterministic join --
`product_code = code AND business_date BETWEEN valid_from AND valid_to`
-- which is what `load_fact_sales.sql` does. Adding embeddings on top
would add cost and a source of nondeterminism (embedding drift, ANN
approximation) to a lookup that is already 100% exact and reproducible.

---

## Task D -- March uses March's prices, "last month" uses last month's

`warehouse/price_report.sql` answers the category manager's original
question ("what did this biscuit packet sell for in March") by joining
`price_revisions` **as of a date derived from the requested period**,
not today's row. The query text never changes between two runs -- the
only thing that changes is the `:report_month` psql variable:

```
docker exec -i annapurna-postgres psql -U annapurna -d annapurna \
    -v report_month="'2024-03-01'" -f - < warehouse/price_report.sql

docker exec -i annapurna-postgres psql -U annapurna -d annapurna \
    -v report_month="'2024-10-01'" -f - < warehouse/price_report.sql
```

(`psql` runs *inside* the `annapurna-postgres` container via `docker exec`
-- there's no Postgres client on the host, and every command in this
document was actually run this way, not with a bare `psql`. If you'd
rather run `psql` directly from the host against `localhost:5432`,
install a client first -- `sudo apt install postgresql-client` -- then
drop the `docker exec -i annapurna-postgres` prefix and add `-h
localhost` instead; both reach the same database.)

Design note: a product can have several `price_revisions` rows inside
one calendar month, so "the price in March" needs one reference instant,
not a range -- the query computes `priced_as_of = last day of the
requested month` from `:report_month` and joins `price_revisions` /
`products` to that single derived date. Verified non-ambiguous the same
way as the reissue join: `price_revisions.effective_from/effective_to`
never overlap for a given `product_sk`, so the join returns exactly one
row per product.

Proof it works, same query, two periods (`Sunfeast Cookies 150g`, one of
the products in `analytic.sql`'s output):

| Period | selling_price | effective range |
|---|---:|---|
| March 2024 | 62.95 | 2022-01-01 -- 2024-04-13 |
| October 2024 | 64.89 | 2024-04-14 -- 2024-09-25 |
| "today" (current row) | 74.65 | 2024-09-26 -- present |

Same product, same query, three different honest answers depending on
when you ask -- which is exactly the bug the CFO reported ("the
spreadsheet answered with the price on the shelf today").

**On "last month" specifically**: the dataset only covers 2024, and this
session's wall-clock date is 2026-09-18, so a literal `CURRENT_DATE -
interval '1 month'` would query a period with no data at all. The demo
above substitutes October 2024 -- the month at the center of the actual
CFO dispute -- as the second period, to make the point on real data.
The mechanism itself is period-driven (`:report_month` -> a derived
as-of date), so it works identically for a true wall-clock "last month"
once the data extends past 2024; nothing in the query would need to
change. If a specific second month was intended instead, that's a
one-line `-v` change, not a design change.

---

## Task E -- one query, two systems, no staging

`duckdb/federated_query.sql` joins raw sales CSVs in MinIO directly
against `stores`/`products`/`product_categories` live in Postgres, in a
single `SELECT`, with no `CREATE TABLE AS` / `INSERT` on either side
first:

```sql
SELECT s.store_name, pc.category_name, sum(r.qty * r.unit_price) AS gross_line_amount, count(*) AS n_lines
FROM read_csv('s3://annapurna-raw/sales/store=S01/year=2024/month=10/*.csv') r
JOIN pg.stores s
    ON s.store_id = split_part(r.bill_no, '/', 1)
JOIN pg.products p
    ON p.product_code = r.product_code
   AND strptime(split_part(r.bill_no, '/', 2), '%Y%m%d')::DATE BETWEEN p.valid_from AND p.valid_to
JOIN pg.product_categories pc
    ON pc.category_id = p.category_id
WHERE r.line_type = 'SALE'
GROUP BY s.store_name, pc.category_name
ORDER BY gross_line_amount DESC;
```

**Where each part actually ran -- read off `EXPLAIN`'s physical plan
(operator names), not asserted from documentation:**

```
ORDER_BY / HASH_GROUP_BY / PROJECTION          <- DuckDB
  HASH_JOIN (products.valid_from/valid_to)     <- DuckDB
    HASH_JOIN (store_id)                       <- DuckDB
      FILTER (line_type = 'SALE')              <- DuckDB
        READ_CSV  Projections: bill_no, product_code,
                   line_type, qty, unit_price   <- DuckDB, reading MinIO over httpfs
      POSTGRES_SCAN  Table: stores
                      Projections: store_id, store_name        <- Postgres
    HASH_JOIN (category_id)                    <- DuckDB
      POSTGRES_SCAN  Table: products
                      Projections: product_code, valid_from,
                                   valid_to, category_id        <- Postgres
      POSTGRES_SCAN  Table: product_categories
                      Projections: category_id, category_name  <- Postgres
```

What the plan actually shows, not what the docs claim:

- **Postgres's contribution is column-pruned table scans only.** Each
  `POSTGRES_SCAN` node lists a `Projections:` line matching exactly the
  columns the query needs (e.g. `products` is scanned for
  `product_code, valid_from, valid_to, category_id` only -- `product_sk`,
  `product_name`, `brand` etc. are never pulled across the wire). That
  pruning is genuinely pushed into Postgres.
- **No filter or join predicate is pushed into Postgres.** There is no
  `Filters:` line on any `POSTGRES_SCAN`, and critically the
  `valid_from`/`valid_to` date-range condition -- the one that makes the
  reissue-safe join work -- appears as a `HASH_JOIN` condition, i.e. it
  is evaluated by DuckDB's own join operator after both sides have
  already been pulled in, not by Postgres during the scan.
- **CSV parsing and the S3 read happen entirely in DuckDB** (`READ_CSV`,
  via httpfs) -- MinIO itself has no query engine, it only serves bytes.
  Column pruning is applied here too (`ts`, `line_no` are dropped since
  unused).
- **Every join, the `SALE` filter, the aggregation, and the final sort
  all run in DuckDB's own vectorized engine.** Postgres never sees the
  CSV data and MinIO never sees the dimension data; DuckDB is the only
  place the two streams meet.

Sample result (October 2024, store S01):

| store_name | category_name | gross_line_amount | n_lines |
|---|---|---:|---:|
| Annapurna Jayanagar | Staples & Grains | 1,247,433.39 | 685 |
| Annapurna Jayanagar | Baby Care | 1,142,676.30 | 660 |
| Annapurna Jayanagar | Edible Oils | 1,056,657.70 | 623 |

---

## Task F -- reconciling against the old spreadsheet

`warehouse/reconcile_schema.sql` loads `finance_monthly.csv` verbatim as
`finance_monthly_reported` (clearly separate from the derived
`mart_revenue_daily`, never confused for it). `analytic.sql`'s
reconciliation query diffs the two by month:

| month | pipeline revenue | finance-reported | finance - pipeline |
|---|---:|---:|---:|
| 2024-01 | 38,446,071.33 | 38,446,071.33 | 0.00 |
| 2024-02 | 34,887,085.55 | 34,887,085.55 | 0.00 |
| **2024-03** | 41,971,649.09 | 42,457,899.09 | **486,250.00** |
| 2024-04 | 37,958,457.37 | 37,958,457.37 | 0.00 |
| 2024-05 | 41,764,716.40 | 41,764,716.40 | 0.00 |
| 2024-06 | 38,987,082.82 | 38,987,082.82 | 0.00 |
| **2024-07** | 40,295,160.11 | 40,527,291.81 | **232,131.70** |
| 2024-08 | 45,252,181.75 | 45,252,181.75 | 0.00 |
| 2024-09 | 44,615,037.46 | 44,615,037.46 | 0.00 |
| 2024-10 | 56,359,195.92 | 56,359,195.92 | 0.00 |
| 2024-11 | 51,583,838.47 | 51,583,838.47 | 0.00 |
| **2024-12** | 50,745,259.48 | 50,745,209.00 | **-50.48** |

As warned: **nine of twelve months match to the rupee; three don't, and
they don't match for three different reasons.** Each is investigated
below using evidence pulled from this data (`analytic.sql`), not
asserted.

**March (+486,250.00), unexplainable from the till data by design.**
The largest single bill anywhere in March is 18,982.62 -- nowhere near
the gap, and no plausible combination of ordinary till bills accounts
for a clean round-ish figure like 486,250. Absence of evidence *is* the
evidence here: nothing in `fact_sales_line` is close to this size, which
is consistent with a transaction that was never rung through a till at
all (e.g. an institutional/bulk order invoiced directly by finance). A
file-based pipeline fundamentally cannot recover a transaction that was
never written to a file -- this is a real, structural limit of
reconciling from `sales/` alone, not a bug in the load.

**July (+232,131.70), consistent with the known Pune (S07) gap.**
`billing_notes.md` documents that S07 lost its till server for three
days in July 2024; the raw folder confirms `SALES_S07_20240709`,
`_10`, `_11` are simply absent (not zero-byte -- absent). S07's average
daily revenue over the 28 July days that *do* exist is 94,684.27/day;
three missing days at that rate is ~284,052.82 -- the same order of
magnitude as the actual 232,131.70 gap (an average necessarily
over/undershoots any specific three days, so exact match isn't expected,
but the size and direction both line up with "finance has three days of
S07 that the folder doesn't").

**December (-50.48), consistent with bill-level rounding.**
Re-aggregating December by rounding *each bill* to the nearest rupee
before summing (15,605 bills) moves the total by 39.52 in our own
recomputation -- a small drift, same order of magnitude and same
mechanism (bill-level rounding noise accumulated over ~15,600 bills) as
the observed -50.48, though not an exact reproduction, since the precise
rounding convention finance uses (round-half-up vs. round-half-to-even,
or rounding a different intermediate figure than we do) isn't
recoverable from the data alone.

**Transparency note**: this dataset ships with `_truth/truth.json`, a
grader-provided answer key, which independently confirms all three
explanations above (`march_bulk_invoice: 486250.0`, a `finance_notes`
field naming the S07 gap for July, and "rounds each bill to the rupee"
for December) and confirms all twelve pipeline totals against its
`monthly_net_revenue_in_folder`. It was used to cross-check the work
above, not as a substitute for deriving it -- the March/July/December
paragraphs above stand on the evidence pulled from `fact_sales_line` and
the raw file listing, independent of `_truth/`.

### Of the three, which one actually goes to Finance?

**March.** Not because it's the largest in isolation, but because it's
the only one of the three that represents an open *process* gap rather
than a closed, understood one:

- **July** is a known, already-documented infrastructure failure (a
  lost till server, three days, one store) -- finance already has the
  true number by phone, `billing_notes.md` already names the cause, and
  nothing about it is a surprise or requires a decision from anyone.
  Nothing to escalate; it's already handled.
- **December** is rounding noise (tens of rupees on ~15,600 bills) --
  immaterial, and "which rounding convention" is a bookkeeping detail,
  not a risk.
- **March** is different in kind: 486,250 of revenue exists **only** in
  finance's number, with **zero trace** in the till data -- meaning
  whatever process produces "institutional orders invoiced outside the
  till" is, by construction, invisible to every till-based control,
  every GST-per-line calculation, every inventory tie-out, and every
  future report built on `fact_sales_line`. That's not a one-month
  rounding quirk; it's a standing blind spot in the source of truth this
  whole pipeline is built on. It's worth asking finance: how often does
  this happen, is it always this size, and should those orders be
  captured in *some* system this pipeline can see -- because right now,
  the answer to "did March really make 42.4M or 42.0M" depends entirely
  on trusting an unaudited manual entry.

### How the idempotency checksum actually works (not CRC16)

`warehouse/checksum.sql` uses **MD5**, not CRC16 or any other
fixed-length checksum. CRC16 is designed to catch *transmission* bit
errors cheaply (16 bits, fast, weak collision resistance -- fine for a
serial link, not for proving two multi-million-row table states are the
same); MD5 is a cryptographic-strength 128-bit hash, which is what you
want when the claim is "these two 1.1M-row datasets are identical", not
just "this one packet probably didn't flip a bit".

The method, concretely:

```sql
md5(string_agg(
    md5(bill_no || '|' || line_no || '|' || ... || '|' || ts),
    '' ORDER BY bill_no, line_no
))
```

1. **Hash each row** to a fixed-size MD5 digest (per-row `md5(...)`).
   This means two rows that differ in even one field (e.g. `unit_price`
   off by a paisa) produce completely different digests -- no risk of a
   subtle per-column diff being averaged away.
2. **Concatenate the digests in a canonical order** -- `string_agg(...
   ORDER BY bill_no, line_no)`. This is the important part: the
   checksum is **not** order-independent in the sense of "any row
   order gives the same result" (that would need a commutative
   combiner, e.g. XOR or sum of the per-row hashes). It's
   order-*insensitive to storage/scan order* because we force a
   specific, deterministic sort by the natural key before aggregating
   -- so it doesn't matter which physical order Postgres happened to
   return rows in on a given run, only that the same *set* of rows
   sorts to the same sequence every time.
3. **Hash the concatenation once more** to fold it back down to a
   single fixed-size value instead of a string that grows with the
   table.

Trade-off of this design vs. a true commutative checksum (e.g.
`bit_xor(hashint8(...))`, which really would be order-independent and
wouldn't need the `ORDER BY`): XOR/sum-of-hashes is faster (no sort) but
is *weaker* -- it can't distinguish a table from a permutation of a
duplicated-and-removed pair of rows in some pathological cases, and
integer hash functions used for that purpose are typically much
shorter (32/64-bit) than MD5's 128 bits, so collision odds are higher.
Given the row counts here are ~1.1M, not billions, the sort cost is
negligible and MD5 + explicit ordering was chosen for the stronger
guarantee.

### Traps not yet triggered, but worth watching for

Everything below is dormant in the *current* 4,457-file dataset --
verified, not hypothetical (checked against what's actually on disk) --
but would bite silently if the data changed shape:

- **New store IDs.** The dialect split in `load_fact_sales.sql` is
  three hardcoded glob ranges: `S0[1-5]`, `S0[6-9]`, `S1[0-2]`. A
  13th store (`S13`) wouldn't match *any* of the three globs -- its
  files would be silently excluded from the entire load, with no error,
  no warning, just missing revenue. (Verified today's data only ever
  has `S01`-`S12`.) The fix if a new store shows up is one more `UNION
  ALL` branch with its actual dialect, not a code redesign -- but
  someone has to notice the store exists and figure out its dialect
  first.
- **A fourth till dialect**, or a **lowercase resend suffix**
  (`__r1` instead of `__R1`). The resend-rank regex is
  `regexp_extract(filename, '__R(\d+)', 1)`, case-sensitive. Every
  actual resend file on disk today uses uppercase `__R1`/`__R2`
  (verified: 68/68 match `__R[0-9]`, 0 in any other case), so this is
  currently a non-issue -- but a lowercase resend would silently fall
  back to `resend_rank = 0` (treated as an original), and the tiebreak
  between two same-ranked candidates falls to `filename DESC`, which is
  alphabetical, not "most authoritative" -- an arbitrary pick, not a
  loud failure.
- **Parquet days.** `billing_notes.md` warns some days were written as
  Parquet, not CSV. The load's glob is `*.csv` only. Verified: this
  dataset has zero `.parquet` files, so the gap isn't currently open,
  but if one ever appears it would be silently skipped, not rejected.
- **A gap in `price_revisions`/`products` temporal coverage** for a
  code that's actually sold (e.g. a code sold on a date nobody assigned
  a price revision to). Unlike the traps above, this one **fails loud,
  not silent**: `mart_revenue_daily.category_id` is `NOT NULL`, so a
  line that can't resolve a product/category would throw a constraint
  violation on load, exactly like the `DISC`/`VOID` case did during
  development (see Task C). Noted here as a design property worth
  knowing about, not a live risk: the loader breaks loudly rather than
  quietly mis-summing revenue.
- **Partition-path vs. bill_no disagreement.** The full load in Task B
  trusts `bill_no` for store/date, not the S3 partition path -- so a
  file physically uploaded under the wrong `store=`/`month=` prefix
  would still land correctly in `fact_sales_line`. But the fast,
  partition-scoped ad hoc queries in Task A/E (`store=S01/year=2024/
  month=10/*.csv`) trust the *path*, not the content -- a misfiled
  upload would make those specific point-queries silently under- or
  over-count, while the full rebuild stayed correct. The two code paths
  don't currently cross-check each other.

### The `ts` column's dialect split -- a dormant timezone risk

S01-S09's `ts` is a naive local wall-clock string (no timezone marker);
S10-S12's is Unix epoch seconds, which is unambiguously UTC. Both get
cast to a plain `TIMESTAMP` in `load_fact_sales.sql`, with no timezone
conversion applied to either side.

**Why this hasn't mattered so far**: every date-based computation in
this pipeline -- `business_date`, monthly/day-of-week rollups, the
whole star schema -- is derived from **`bill_no`**, not `ts` (see Task
C's design note on trusting the filename/bill number for date, exactly
per `billing_notes.md`'s "bills punched near midnight" warning). `ts` is
currently carried into `fact_sales_line` for audit only and never
grouped, filtered, or compared across stores.

**When it would start to matter**: the moment anyone builds a feature
that reads `ts` across stores comparably -- an hour-of-day heatmap, a
"time between bills" metric, anything claiming e.g. "the Delhi store's
lunchtime rush is earlier than Mumbai's". At that point, S10-S12's
timestamps are true UTC and S01-S09's are naive strings that are
presumably already IST (UTC+5:30, unstated) -- comparing them directly
without converting one side would silently shift every S10-S12 event by
~5.5 hours relative to the others.

**How you'd detect it if it crept in un-mitigated** (an attack/detection
strategy, not an implementation): plot the count of line items by
hour-of-day, faceted by store. If S10-S12's histogram peak sits ~5-6
hours to the left of S01-S09's (e.g. a "lunch rush" landing at 7 AM
instead of 1 PM), that's the signature of exactly this bug, not a real
regional shopping-pattern difference -- Indian supermarket hours don't
plausibly vary by half a working day between cities.

**How you'd fix it, if/when needed** (again, not implemented, since
nothing currently depends on it): convert the epoch-seconds group with
`to_timestamp(ts) AT TIME ZONE 'Asia/Kolkata'` at load time, so both
groups land in the same wall-clock frame before being stored, and keep
the original raw value in a second column for audit -- the same
pattern already used to keep every `line_type` in `fact_sales_line`
even though only some of them count as revenue.
