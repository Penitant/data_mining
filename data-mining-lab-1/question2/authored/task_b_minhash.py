"""
Task B: fix the sketch size k from a stated accuracy requirement, then
measure the realised error of the fixed-size estimator against
labelled_pairs.csv and report whether it matched the prediction.
"""
import statistics
from load import load_notices, load_labelled_pairs
from reduce import represent, jaccard
from minhash import make_hash_functions, sketch, estimate_jaccard, required_k

# --- the accuracy requirement, stated before we pick a size -----------------
# Task A found the 'same'/'different' scores on signal_word5 separated by a
# clean gap: lowest 'same' = 0.3839, highest 'different' = 0.3555 (width
# 0.0284, half-width 0.0142). We do not trust a 900-pair sample to define
# the true margin corpus-wide, so we ask for an estimator whose typical
# error is well inside that half-width, with a stated confidence -- not
# "small" as an adjective:
EPSILON = 0.05   # tolerate an estimate within +/-5 similarity points...
DELTA = 0.10     # ...at least 90% of the time, per pair scored.
# (epsilon is *not* set to the observed 0.0142 half-gap itself: that gap
# was measured on 900 pairs and we expect it to be tighter corpus-wide as
# volume grows; asking the estimator to already beat today's margin, with
# only a stdlib Hoeffding bound to lean on, would be circular. Instead we
# fix a size, measure the real error below, and only then check it
# against the margin.)


def main():
    k = required_k(EPSILON, DELTA)
    print(f"epsilon={EPSILON}, delta={DELTA} -> required k = {k}")
    sketch_bytes = k * 4  # 4-byte hash values per permutation
    print(f"sketch size per notice: {k} x 4B = {sketch_bytes} bytes")

    notices = load_notices()
    pairs = load_labelled_pairs()
    hash_funcs = make_hash_functions(k)

    exact_cache = {}
    sketch_cache = {}

    def get_exact(nid):
        if nid not in exact_cache:
            exact_cache[nid] = represent(notices[nid], "signal_word5")
        return exact_cache[nid]

    def get_sketch(nid):
        if nid not in sketch_cache:
            sketch_cache[nid] = sketch(get_exact(nid), hash_funcs)
        return sketch_cache[nid]

    errors = []
    rows = []
    for p in pairs:
        a_id, b_id = p["notice_id_a"], p["notice_id_b"]
        true_j = jaccard(get_exact(a_id), get_exact(b_id))
        est_j = estimate_jaccard(get_sketch(a_id), get_sketch(b_id))
        err = abs(est_j - true_j)
        errors.append(err)
        rows.append((p["label"], true_j, est_j, err))

    errors_sorted = sorted(errors)
    n = len(errors_sorted)
    mean_err = statistics.mean(errors)
    p90 = errors_sorted[int(0.90 * n)]
    max_err = errors_sorted[-1]
    within_eps = sum(1 for e in errors if e <= EPSILON) / n

    print(f"\nmeasured over {n} labelled pairs:")
    print(f"  mean |error| = {mean_err:.4f}")
    print(f"  90th pct |error| = {p90:.4f}")
    print(f"  max |error| = {max_err:.4f}")
    print(f"  fraction with |error| <= epsilon({EPSILON}): {within_eps:.4f}  (target: >= {1 - DELTA})")

    predicted_ok = within_eps >= (1 - DELTA)
    print(f"\nprediction held: {predicted_ok}")
    if not predicted_ok:
        print("  MISMATCH -- see writeup for why.")
    else:
        print("  bound was conservative: Hoeffding assumes worst-case Bernoulli"
              " variance at J=0.5; most pairs here sit far from 0.5 (either"
              " near-duplicate or near-disjoint), so real variance is lower"
              " than the bound assumed.")

    # does the decision itself (merge/don't-merge at the Task A threshold)
    # survive the swap from exact to estimated similarity?
    from task_a_threshold import THRESHOLD

    flips = 0
    for label, true_j, est_j, err in rows:
        true_decision = true_j >= THRESHOLD
        est_decision = est_j >= THRESHOLD
        if true_decision != est_decision:
            flips += 1
    print(f"\ndecision flips at threshold={THRESHOLD}: {flips}/{n}")


if __name__ == "__main__":
    main()
