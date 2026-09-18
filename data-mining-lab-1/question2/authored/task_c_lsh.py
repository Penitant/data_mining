"""
Task C: sublinear retrieval. Bands the k=600 MinHash sketch (already built
for Task B) into b bands of r rows, characterises P(candidate | true
similarity) in closed form, measures it against a real background sample
and the labelled pairs, and picks an operating point using the same 25:1
cost ratio from Task A -- applied in the opposite direction, because LSH
misses can only produce the cheap failure (false split), never the
expensive one (false merge always still needs the exact check to fire).
"""
import random
import time

from build_sketches import build
from load import load_labelled_pairs
from lsh import candidate_probability, build_index
from reduce import jaccard
from task_a_threshold import THRESHOLD

random.seed(20240917)


def background_sample(exact: dict, n_pairs: int = 30000):
    ids = list(exact.keys())
    scores = []
    for _ in range(n_pairs):
        a, b = random.sample(ids, 2)
        scores.append(jaccard(exact[a], exact[b]))
    return scores


def main():
    cache = build()
    k = cache["k"]
    exact = cache["exact"]
    sketches = cache["sketches"]
    print(f"loaded cache: k={k}, {len(exact)} notices")

    bg_scores = background_sample(exact)
    bg_scores.sort()
    n = len(bg_scores)
    print(f"\nbackground sample: {n} random pairs (not the curated labelled set)")
    print(f"  mean={sum(bg_scores)/n:.5f}  median={bg_scores[n//2]:.5f}"
          f"  p99={bg_scores[int(0.99*n)]:.5f}  max={bg_scores[-1]:.5f}")

    divisors = [r for r in range(1, k + 1) if k % r == 0]

    print(f"\n{'r':>3} {'b':>4} {'recall@thr':>11} {'E[P(cand)] bg':>14} {'proj. candidates':>18}")
    total_possible_pairs = n * (n - 1) // 2  # placeholder, corrected below
    from load import load_notices
    N = len(load_notices())
    total_possible_pairs = N * (N - 1) // 2

    grid = []
    for r in divisors:
        b = k // r
        if b < 2 or r < 1:
            continue
        recall = candidate_probability(THRESHOLD, b, r)
        # Monte-Carlo E[P(candidate|S)] over the *real* background distribution,
        # not P(candidate) at the background mean -- P(candidate|s) is convex
        # in s so the two are not the same number.
        e_p_cand = sum(candidate_probability(s, b, r) for s in bg_scores) / n
        projected = e_p_cand * total_possible_pairs
        grid.append((r, b, recall, e_p_cand, projected))
        if r in (2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 25, 30):
            print(f"{r:3d} {b:4d} {recall:11.4f} {e_p_cand:14.6f} {projected:18,.0f}")

    return grid, sketches, exact


if __name__ == "__main__":
    main()
