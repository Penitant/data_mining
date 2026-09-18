import pickle
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from lsh import candidate_probability

with open("task_c_mitigation_cache.pkl", "rb") as f:
    m = pickle.load(f)

threshold = m["threshold"]
same_min = m["same_min"]
diff_max = m["diff_max"]
R, B = 3, 200
K = 600

# --- Plot 1: the S-curve for the chosen (r,b), with the operating point ---
xs = [i / 1000 for i in range(1001)]
ys = [candidate_probability(x, B, R) for x in xs]

fig, ax = plt.subplots(figsize=(7, 4.5))
ax.plot(xs, ys, color="#3366cc", lw=2, label=f"P(candidate | s), r={R}, b={B}")
ax.axvline(threshold, color="#cc3333", ls="--", lw=1.5, label=f"chosen threshold s={threshold:.3f}")
ax.axvline(diff_max, color="#888888", ls=":", lw=1, label=f"closest 'different' pair, s={diff_max:.3f}")
ax.axvline(same_min, color="#33aa55", ls=":", lw=1, label=f"weakest 'same' pair, s={same_min:.3f}")
recall_at_threshold = candidate_probability(threshold, B, R)
ax.plot([threshold], [recall_at_threshold], "o", color="#cc3333", zorder=5)
ax.annotate(f"({threshold:.3f}, {recall_at_threshold:.3f})",
            (threshold, recall_at_threshold), textcoords="offset points",
            xytext=(10, -15), fontsize=9, color="#cc3333")
ax.set_xlabel("true similarity s (filtered signal_word5 Jaccard)")
ax.set_ylabel("P(pair survives to candidate stage)")
ax.set_title("LSH retrieval S-curve -- operating point after mitigation")
ax.legend(loc="center right", fontsize=8)
ax.set_xlim(0, 1)
ax.set_ylim(-0.02, 1.02)
fig.tight_layout()
fig.savefig("plot_scurve.png", dpi=150)
print("wrote plot_scurve.png")

# --- Plot 2: the tunable tension -- recall vs candidate volume across r ---
divisors = [r for r in range(1, K + 1) if K % r == 0]
rs, recalls, projs = [], [], []
N = 12000
total_possible = N * (N - 1) // 2
bg_mean = 0.00254  # measured background mean on filtered shingles

for r in divisors:
    b = K // r
    if b < 2:
        continue
    recalls.append(candidate_probability(threshold, b, r))
    # use measured background mean as a rough proxy consistent with task_c_lsh.py's approach
    projs.append(candidate_probability(bg_mean, b, r) * total_possible)
    rs.append(r)

fig2, ax1 = plt.subplots(figsize=(7, 4.5))
ax1.plot(rs, recalls, "o-", color="#3366cc", label="recall @ threshold")
ax1.set_xlabel("r (rows per band; b = 600 / r)")
ax1.set_ylabel("recall @ threshold", color="#3366cc")
ax1.tick_params(axis="y", labelcolor="#3366cc")
ax1.set_xscale("log")
ax1.axvline(R, color="#cc3333", ls="--", lw=1.5)
ax1.annotate(f"chosen r={R}", (R, 0.5), color="#cc3333", fontsize=9,
             textcoords="offset points", xytext=(5, 0))

ax2 = ax1.twinx()
ax2.plot(rs, projs, "s-", color="#dd8800", label="projected candidate pairs")
ax2.set_ylabel("projected candidate pairs (background)", color="#dd8800")
ax2.tick_params(axis="y", labelcolor="#dd8800")
ax2.set_yscale("log")

fig2.suptitle("The tunable tension: retrieval reliability vs. candidate-list cost")
fig2.tight_layout()
fig2.savefig("plot_tension.png", dpi=150)
print("wrote plot_tension.png")
