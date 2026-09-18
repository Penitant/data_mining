"""
Task E: don't trust the total. Runs the *final, mitigated* retrieval
scheme (r=3, b=200 over the filtered sketches from task_c_mitigation.py)
over the full corpus and reports how the candidate-generation work is
distributed across notices and portals -- not just its sum -- to confirm
the skew found (and fixed) in Task C didn't just move somewhere the
aggregate numbers don't show.
"""
import collections
import pickle

from lsh import build_index
from load import load_notices

R, B = 3, 200


def main():
    with open("task_c_mitigation_cache.pkl", "rb") as fh:
        m = pickle.load(fh)
    sketches = m["filtered_sketches"]
    notices = load_notices()

    candidates, buckets = build_index(sketches, B, R)
    print(f"final scheme r={R} b={B}: {len(candidates):,} candidates")

    degree = collections.Counter()
    for pair in candidates:
        a, b = tuple(pair)
        degree[a] += 1
        degree[b] += 1
    for nid in sketches:
        degree.setdefault(nid, 0)

    deg_sorted = sorted(degree.values())
    n = len(deg_sorted)
    zero = sum(1 for d in deg_sorted if d == 0)
    print(f"degree: mean={sum(deg_sorted)/n:.3f} median={deg_sorted[n//2]}"
          f" p99={deg_sorted[int(0.99*n)]} max={deg_sorted[-1]}")
    print(f"notices with zero candidates: {zero} ({100*zero/n:.1f}%)")

    deg_desc = sorted(degree.values(), reverse=True)
    tot = sum(deg_desc)
    top1 = sum(deg_desc[: n // 100])
    print(f"top 1% of notices by degree: {100*top1/tot:.1f}% of total candidate-slots")

    sizes = sorted((len(v) for v in buckets.values() if len(v) >= 2), reverse=True)
    work = [s * (s - 1) // 2 for s in sizes]
    totw = sum(work)
    top1b = max(1, len(work) // 100)
    print(f"largest bucket: {sizes[0] if sizes else 0}"
          f"  top 1% of buckets: {100*sum(work[:top1b])/totw:.1f}% of pairwise work")

    portal_degree = collections.Counter()
    portal_count = collections.Counter()
    for nid, d in degree.items():
        p = notices[nid]["portal_id"]
        portal_degree[p] += d
        portal_count[p] += 1
    print("\ntop 10 portals by total candidate-degree:")
    for p, total_d in portal_degree.most_common(10):
        print(f"  {p}: notices={portal_count[p]:4d} total_degree={total_d:5d}"
              f" avg={total_d/portal_count[p]:.2f}")

    with open("task_e_cache.pkl", "wb") as fh:
        pickle.dump({"degree": dict(degree), "bucket_sizes": sizes}, fh)


if __name__ == "__main__":
    main()
