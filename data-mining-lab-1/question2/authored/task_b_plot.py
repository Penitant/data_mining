"""
Task B's own plot: epsilon(k) under Hoeffding at delta=0.10, marking the
adopted k=600 and the margin-anchored (rejected on size) k=14,979.
This is the evidence for "why k=600", separate from Task C's S-curve.
"""
import math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

DELTA = 0.10


def eps_of_k(k):
    return math.sqrt(math.log(2 / DELTA) / (2 * k))


ks = list(range(50, 16000, 10))
epss = [eps_of_k(k) for k in ks]

fig, ax = plt.subplots(figsize=(7.5, 5))
ax.plot(ks, epss, color="#3366cc", lw=2, label=r"$\epsilon(k)=\sqrt{\ln(2/\delta)/(2k)}$, $\delta=0.10$")

# adopted point
k_adopt, eps_adopt = 600, eps_of_k(600)
ax.plot([k_adopt], [eps_adopt], "o", color="#33aa55", zorder=5, markersize=9)
ax.annotate(f"adopted: k=600, eps={eps_adopt:.3f}\n(2,400 B/notice)",
            (k_adopt, eps_adopt), textcoords="offset points", xytext=(15, 15),
            fontsize=9, color="#33aa55")

# margin-anchored point (rejected on size)
k_margin, eps_margin = 14979, eps_of_k(14979)
ax.plot([k_margin], [eps_margin], "o", color="#cc3333", zorder=5, markersize=9)
ax.annotate(f"different-side-margin-anchored:\nk=14,979, eps=0.010\n(59,916 B/notice -- rejected, bigger than raw text)",
            (k_margin, eps_margin), textcoords="offset points", xytext=(-330, 45),
            fontsize=9, color="#cc3333")

# reference lines: the two observed margins from Task A's labelled sample
ax.axhline(0.0273, color="#888888", ls=":", lw=1)
ax.annotate("different-side margin, 900-pair sample\n(T - diff_max = 0.0273)",
            (9500, 0.0273), textcoords="offset points", xytext=(0, -32), fontsize=8, color="#666666")

ax.set_xlabel("k (number of MinHash permutations)")
ax.set_ylabel(r"guaranteed estimation error $\epsilon$ (90% confidence)")
ax.set_title("Task B: sketch size vs. guaranteed estimation error (Hoeffding)")
ax.legend(loc="upper right", fontsize=9)
ax.set_xlim(0, 16000)
ax.set_ylim(0, 0.14)
fig.tight_layout()
fig.savefig("plot_hoeffding.png", dpi=150)
print("wrote plot_hoeffding.png")
