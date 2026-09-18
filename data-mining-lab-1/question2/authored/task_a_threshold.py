"""
Turns the Task A score gap into a single threshold, using an explicit,
numeric cost ratio -- not an adjective.
"""
from load import load_notices, load_labelled_pairs
from reduce import represent, jaccard

# A false merge (two different tenders shown as one card) risks a bidder
# missing a deadline and suing SetuBid. A false split (one tender shown
# twice) costs a grumble and, at worst, a support ticket. We price a false
# merge at 25x a false split: a single missed-deadline lawsuit plausibly
# costs more than a support team resolves in twenty-five duplicate-card
# complaints combined (legal exposure + reputational vs. an annoyed click).
# This ratio is a judgment call, not a corpus fact -- it is recorded here,
# as a number, so it can be argued with and revised.
COST_FALSE_MERGE = 25
COST_FALSE_SPLIT = 1


def find_gap():
    notices = load_notices()
    pairs = load_labelled_pairs()
    same, diff = [], []
    for p in pairs:
        a = represent(notices[p["notice_id_a"]], "signal_word5")
        b = represent(notices[p["notice_id_b"]], "signal_word5")
        s = jaccard(a, b)
        (same if p["label"] == "same" else diff).append(s)
    return min(same), max(diff)


same_min, diff_max = find_gap()
gap_width = same_min - diff_max
assert gap_width > 0, "representation no longer separates the labelled pairs cleanly"

# Place the threshold inside [diff_max, same_min], biased toward same_min
# in proportion to how much costlier a false merge is than a false split:
# the more a false merge is feared, the closer we sit to the safe (high)
# edge, so only very confident matches ever merge.
weight = COST_FALSE_MERGE / (COST_FALSE_MERGE + COST_FALSE_SPLIT)
THRESHOLD = diff_max + gap_width * weight

if __name__ == "__main__":
    print(f"same_min={same_min:.4f}  diff_max={diff_max:.4f}  gap_width={gap_width:.4f}")
    print(f"cost ratio false_merge:false_split = {COST_FALSE_MERGE}:{COST_FALSE_SPLIT}")
    print(f"-> THRESHOLD = {THRESHOLD:.4f}")
    print(f"   margin below same_min: {same_min - THRESHOLD:.4f}")
    print(f"   margin above diff_max: {THRESHOLD - diff_max:.4f}")
