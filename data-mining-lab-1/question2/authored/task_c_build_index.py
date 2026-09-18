"""
Task C, operating point: build the real LSH candidate index over the full
12,000-notice corpus at the chosen (r=4, b=150), measure real wall time
and real candidate volume (not the Monte-Carlo projection), and dump
per-notice / per-portal bucket-size stats for the skew investigation.
"""
import collections
import pickle
import time

from build_sketches import build
from load import load_notices
from lsh import build_index

R, B = 4, 150


def main():
    cache = build()
    sketches = cache["sketches"]
    notices = load_notices()

    t0 = time.perf_counter()
    candidates, buckets = build_index(sketches, B, R)
    t1 = time.perf_counter()

    print(f"real candidate pairs at r={R}, b={B}: {len(candidates):,}")
    print(f"index build wall time: {t1 - t0:.2f}s")
    print(f"non-empty bucket count: {sum(1 for m in buckets.values() if len(m) >= 2):,}"
          f" / {len(buckets):,} total buckets")

    # per-notice candidate-degree (how many other notices this one collides with)
    degree = collections.Counter()
    for pair in candidates:
        a, b = tuple(pair)
        degree[a] += 1
        degree[b] += 1
    for nid in sketches:
        degree.setdefault(nid, 0)

    deg_sorted = sorted(degree.values())
    n = len(deg_sorted)
    print(f"\ncandidate-degree per notice: mean={sum(deg_sorted)/n:.2f}"
          f"  median={deg_sorted[n//2]}  p99={deg_sorted[int(0.99*n)]}  max={deg_sorted[-1]}")

    top_share = sum(sorted(deg_sorted, reverse=True)[: n // 100]) / sum(deg_sorted)
    print(f"top 1% of notices by degree account for {top_share*100:.1f}% of total candidate-slots")

    # per-portal aggregation
    portal_degree = collections.Counter()
    portal_count = collections.Counter()
    for nid, d in degree.items():
        p = notices[nid]["portal_id"]
        portal_degree[p] += d
        portal_count[p] += 1

    print("\ntop 10 portals by total candidate-degree:")
    for p, total_d in portal_degree.most_common(10):
        print(f"  {p}: notices={portal_count[p]:4d}  total_degree={total_d:7d}"
              f"  avg_degree/notice={total_d/portal_count[p]:.1f}")

    with open("task_c_index_cache.pkl", "wb") as fh:
        pickle.dump({"candidates": candidates, "degree": dict(degree), "buckets_sizes":
                     {k: len(v) for k, v in buckets.items()}}, fh)


if __name__ == "__main__":
    main()
