"""
Task A: score every labelled pair under three competing representations
and report how well each one separates 'same' from 'different'.
"""
import statistics
import sys
from load import load_notices, load_labelled_pairs
from reduce import represent, jaccard

MODES = ["raw_word5", "signal_word5", "signal_char8"]


def auc(same_scores, diff_scores):
    """P(random same-pair score > random different-pair score), ties=0.5.
    Computed by rank-sum (Mann-Whitney U / n1*n2) -- no external deps."""
    labeled = [(s, 1) for s in same_scores] + [(s, 0) for s in diff_scores]
    labeled.sort(key=lambda x: x[0])
    n = len(labeled)
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j < n and labeled[j][0] == labeled[i][0]:
            j += 1
        avg_rank = (i + 1 + j) / 2.0
        for x in range(i, j):
            ranks[x] = avg_rank
        i = j
    rank_sum_pos = sum(r for r, (_, lab) in zip(ranks, labeled) if lab == 1)
    n1 = len(same_scores)
    n0 = len(diff_scores)
    u = rank_sum_pos - n1 * (n1 + 1) / 2.0
    return u / (n1 * n0)


def main():
    notices = load_notices()
    pairs = load_labelled_pairs()
    print(f"loaded {len(notices)} notices, {len(pairs)} labelled pairs")

    for mode in MODES:
        cache = {}

        def rep(nid):
            if nid not in cache:
                cache[nid] = represent(notices[nid], mode)
            return cache[nid]

        same_scores, diff_scores = [], []
        for p in pairs:
            a, b = rep(p["notice_id_a"]), rep(p["notice_id_b"])
            s = jaccard(a, b)
            (same_scores if p["label"] == "same" else diff_scores).append(s)

        print(f"\n=== mode: {mode} ===")
        print(
            f"same  n={len(same_scores):4d}  mean={statistics.mean(same_scores):.4f}"
            f"  median={statistics.median(same_scores):.4f}"
            f"  min={min(same_scores):.4f}  max={max(same_scores):.4f}"
        )
        print(
            f"diff  n={len(diff_scores):4d}  mean={statistics.mean(diff_scores):.4f}"
            f"  median={statistics.median(diff_scores):.4f}"
            f"  min={min(diff_scores):.4f}  max={max(diff_scores):.4f}"
        )
        print(f"AUC (P(same_score > diff_score)) = {auc(same_scores, diff_scores):.4f}")

        # how much overlap is there right at the boundary?
        same_sorted = sorted(same_scores)
        diff_sorted = sorted(diff_scores, reverse=True)
        p10_same = same_sorted[max(0, int(0.10 * len(same_sorted)) - 1)]
        p90_diff = diff_sorted[max(0, int(0.10 * len(diff_sorted)) - 1)]
        print(f"10th pct of 'same' scores = {p10_same:.4f}   90th pct of 'diff' scores = {p90_diff:.4f}")
        overlap = sum(1 for s in diff_scores if s >= p10_same)
        print(f"'different' pairs scoring >= that same-p10 cutoff: {overlap}/{len(diff_scores)}")


if __name__ == "__main__":
    main()
