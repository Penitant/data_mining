"""
Task C mitigation: drop corpus-wide high-document-frequency shingles
(the "universal" template scaffolding identified in build_sketches'
sibling investigation) before sketching, and re-measure everything --
separation, MinHash error, bucket skew, candidate volume, wall time --
so the mitigation's price is a measured number, not an assumption.
"""
import collections
import pickle
import time

from build_sketches import build, EPSILON, DELTA
from load import load_labelled_pairs, load_notices
from reduce import jaccard
from minhash import make_hash_functions, sketch, estimate_jaccard, required_k
from lsh import candidate_probability, build_index

CUTOFF_FRAC = 0.05
R, B = 4, 150
CACHE = "task_c_mitigation_cache.pkl"


def main():
    base = build()
    exact = base["exact"]
    N = len(exact)
    k = base["k"]

    df = collections.Counter()
    for s in exact.values():
        df.update(s)
    cutoff = CUTOFF_FRAC * N
    stoplist = {sh for sh, c in df.items() if c > cutoff}
    print(f"stoplist: {len(stoplist)} shingles present in >{CUTOFF_FRAC*100:.0f}% of notices"
          f" (out of {len(df)} distinct shingles)")

    filtered = {nid: (s - stoplist) for nid, s in exact.items()}
    sizes = [len(s) for s in filtered.values()]
    print(f"filtered shingle-set size: mean={sum(sizes)/N:.1f} min={min(sizes)} max={max(sizes)}"
          f"  (unfiltered mean was 267.0)")

    hash_funcs = make_hash_functions(k)  # same k, same seed -> same hash functions as Task B/C

    t0 = time.perf_counter()
    filtered_sketches = {nid: sketch(s, hash_funcs) for nid, s in filtered.items()}
    t1 = time.perf_counter()
    print(f"re-sketch {N} notices on filtered shingles: {t1-t0:.2f}s")

    # --- accuracy: same MinHash error check as Task B, on filtered representation ---
    pairs = load_labelled_pairs()
    errors = []
    same_scores, diff_scores = [], []
    for p in pairs:
        a_id, b_id = p["notice_id_a"], p["notice_id_b"]
        true_j = jaccard(filtered[a_id], filtered[b_id])
        est_j = estimate_jaccard(filtered_sketches[a_id], filtered_sketches[b_id])
        errors.append(abs(true_j - est_j))
        (same_scores if p["label"] == "same" else diff_scores).append(true_j)
    mean_err = sum(errors) / len(errors)
    same_min, diff_max = min(same_scores), max(diff_scores)
    gap = same_min - diff_max
    print(f"\n[filtered] mean |MinHash error| = {mean_err:.4f}  (unfiltered was 0.0103)")
    print(f"[filtered] same_min={same_min:.4f} diff_max={diff_max:.4f} gap={gap:.4f}"
          f"  (unfiltered gap was 0.0284)")

    weight = 25 / 26
    threshold = diff_max + gap * weight
    print(f"[filtered] new threshold = {threshold:.4f}")

    # --- retrieval: rebuild the LSH index on filtered sketches, same (r,b) ---
    t2 = time.perf_counter()
    candidates, buckets = build_index(filtered_sketches, B, R)
    t3 = time.perf_counter()
    print(f"\n[filtered] LSH index build at r={R} b={B}: {t3-t2:.2f}s"
          f"  (unfiltered was 23.53s)")
    print(f"[filtered] candidate pairs: {len(candidates):,}  (unfiltered was 25,488,938)")

    recall = candidate_probability(threshold, B, R)
    print(f"[filtered] recall @ new threshold {threshold:.4f}: {recall:.4f}")

    sizes_nonempty = sorted((len(m) for m in buckets.values() if len(m) >= 2), reverse=True)
    work = [s * (s - 1) // 2 for s in sizes_nonempty]
    total_work = sum(work)
    top01 = max(1, len(work) // 1000)
    top01_share = sum(work[:top01]) / total_work if total_work else 0
    print(f"[filtered] largest bucket size: {sizes_nonempty[0] if sizes_nonempty else 0}"
          f"  (unfiltered largest was 3,407)")
    print(f"[filtered] top 0.1% of buckets share of pairwise work: {top01_share*100:.1f}%"
          f"  (unfiltered was 88.3%)")

    with open(CACHE, "wb") as fh:
        pickle.dump({
            "stoplist": stoplist, "filtered": filtered, "filtered_sketches": filtered_sketches,
            "threshold": threshold, "same_min": same_min, "diff_max": diff_max,
            "candidates": candidates, "bucket_sizes": sizes_nonempty,
        }, fh)


if __name__ == "__main__":
    main()
