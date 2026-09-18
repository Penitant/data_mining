"""
Fixed-size MinHash sketch over the signal_word5 shingle set, and the size
argument behind k (see task_b_minhash.py for the derivation and the
measured-vs-predicted error check).
"""
import hashlib
import math

MERSENNE_61 = (1 << 61) - 1


def _stable_hash(token: str) -> int:
    return int.from_bytes(hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest(), "big")


def make_hash_functions(k: int, seed: int = 20240917):
    """k independent (a,b) pairs for h(x) = (a*x + b) mod p, p prime > 2^32."""
    rng_state = seed
    funcs = []
    for i in range(k):
        rng_state = (rng_state * 6364136223846793005 + 1442695040888963407 + i) & ((1 << 64) - 1)
        a = (rng_state >> 1) % (MERSENNE_61 - 1) + 1
        rng_state = (rng_state * 6364136223846793005 + 1442695040888963407 + i * 7919) & ((1 << 64) - 1)
        b = rng_state % MERSENNE_61
        funcs.append((a, b))
    return funcs


def sketch(shingles: set, hash_funcs) -> list:
    if not shingles:
        return [MERSENNE_61] * len(hash_funcs)
    base_hashes = [_stable_hash(s) for s in shingles]
    sig = []
    for a, b in hash_funcs:
        m = min((a * h + b) % MERSENNE_61 for h in base_hashes)
        sig.append(m)
    return sig


def estimate_jaccard(sig_a: list, sig_b: list) -> float:
    agree = sum(1 for x, y in zip(sig_a, sig_b) if x == y)
    return agree / len(sig_a)


def required_k(epsilon: float, delta: float) -> int:
    """Hoeffding bound for the average of k iid Bernoulli(J) MinHash
    agreement indicators: P(|Jhat - J| >= eps) <= 2*exp(-2*k*eps^2).
    Solve for the smallest k meeting a target (epsilon, delta)."""
    return math.ceil(math.log(2 / delta) / (2 * epsilon ** 2))
