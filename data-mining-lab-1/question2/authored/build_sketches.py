"""
Builds and caches (exact shingle set, MinHash sketch) for every notice in
the corpus, once. Sketch-building at k=600 in pure Python is the slow
step (~190s for 12,000 notices) -- cache it to disk so every other script
in this directory can load it in under a second instead of repeating it.
"""
import os
import pickle
import time

from load import load_notices
from reduce import represent
from minhash import make_hash_functions, sketch, required_k

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(HERE, ".cache_sketches.pkl")

EPSILON, DELTA = 0.05, 0.10


def build(force=False):
    if not force and os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, "rb") as fh:
            return pickle.load(fh)

    notices = load_notices()
    k = required_k(EPSILON, DELTA)
    hash_funcs = make_hash_functions(k)

    t0 = time.perf_counter()
    exact = {nid: represent(n, "signal_word5") for nid, n in notices.items()}
    t1 = time.perf_counter()
    sketches = {nid: sketch(s, hash_funcs) for nid, s in exact.items()}
    t2 = time.perf_counter()

    result = {
        "k": k,
        "exact": exact,
        "sketches": sketches,
        "build_time_exact_s": t1 - t0,
        "build_time_sketch_s": t2 - t1,
    }
    with open(CACHE_PATH, "wb") as fh:
        pickle.dump(result, fh)
    return result


if __name__ == "__main__":
    r = build(force=True)
    print(f"k={r['k']}  exact reps: {r['build_time_exact_s']:.2f}s"
          f"  sketches: {r['build_time_sketch_s']:.2f}s"
          f"  ({len(r['exact'])} notices,"
          f" {len(r['exact']) / r['build_time_sketch_s']:.1f} notices/sec sketching)")
