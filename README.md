# data_mining

Datamining and Warehousing Submissions Repository -- this repo holds the
Lab 1 exam submission, split across two independent questions. Each has
its own writeup with all the decisions, evidence and authored code for
that question; this file is just the index.

- **[Question 1](data-mining-lab-1/question1/README.md)** -- Annapurna
  Stores billing/revenue reconciliation (Postgres + MinIO + DuckDB, a
  star-schema warehouse, and a month-by-month reconciliation against a
  finance spreadsheet).
- **[Question 2](data-mining-lab-1/question2/README.md)** -- SetuBid
  procurement-notice deduplication (MinHash/LSH near-duplicate
  detection, a cost-driven merge threshold, and a durable Postgres
  candidate index).

Both are self-contained: each README states its own layout, how to get
the exam-provided data in place, and how to rebuild/run everything from
scratch.
