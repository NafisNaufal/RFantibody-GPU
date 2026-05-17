"""
Plot RF2 pAE vs CDR RMSD scatter plot from a scored Quiver file.

Usage:
    uv run python scripts/plot_rf2_scores.py <rf2.qv> [--output plot.png]
"""

import argparse
import re
import sys

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np


def parse_scores(qv_path: str) -> tuple[list[float], list[float]]:
    paes, rmsds = [], []
    with open(qv_path) as f:
        for line in f:
            if not line.startswith("QV_SCORE"):
                continue
            # Parse key=value pairs
            scores = {}
            for kv in line.split()[2:]:
                parts = kv.split("=")
                if len(parts) == 2:
                    try:
                        scores[parts[0]] = float(parts[1])
                    except ValueError:
                        pass
            pae  = scores.get("interaction_pae")
            rmsd = scores.get("framework_aligned_cdr_rmsd")
            if pae is not None and rmsd is not None and not np.isnan(rmsd):
                paes.append(pae)
                rmsds.append(rmsd)
    return paes, rmsds


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("qv", help="Path to RF2 scored Quiver file")
    parser.add_argument("--output", "-o", default="rf2_pae_vs_rmsd.png")
    args = parser.parse_args()

    paes, rmsds = parse_scores(args.qv)
    if not paes:
        print("No valid scores found in file.")
        sys.exit(1)

    paes  = np.array(paes)
    rmsds = np.array(rmsds)

    # Compute annotation: % with RMSD < 2 Å among those with pAE < 10
    pae_thresh  = 10.0
    rmsd_thresh = 2.0
    low_pae_mask = paes < pae_thresh
    n_low_pae    = low_pae_mask.sum()
    if n_low_pae > 0:
        pct = 100 * (rmsds[low_pae_mask] < rmsd_thresh).sum() / n_low_pae
        annotation = f"with pAE < {pae_thresh:.0f}\n{pct:.1f}% < {rmsd_thresh:.0f}Å"
    else:
        annotation = f"no designs\nwith pAE < {pae_thresh:.0f}"

    fig, ax = plt.subplots(figsize=(6, 5))

    ax.scatter(paes, rmsds, alpha=0.5, s=40, color="steelblue", edgecolors="none")

    # Dashed vertical line at pAE = 10
    ax.axvline(x=pae_thresh, color="gray", linestyle="--", linewidth=1.2)

    # Annotation (top-left, red like the reference figure)
    ax.text(0.04, 0.97, annotation,
            transform=ax.transAxes,
            va="top", ha="left",
            color="red", fontsize=9, fontweight="bold")

    ax.set_xlabel("RF2 pAE (interaction)", fontsize=11)
    ax.set_ylabel("CDR RMSD — framework aligned (Å)", fontsize=11)
    ax.set_title("RF2 pAE vs CDR RMSD\nInlA Antibody Designs", fontsize=11)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)
    ax.xaxis.set_minor_locator(ticker.AutoMinorLocator())
    ax.yaxis.set_minor_locator(ticker.AutoMinorLocator())
    ax.grid(True, alpha=0.2)

    plt.tight_layout()
    plt.savefig(args.output, dpi=150)
    print(f"Saved: {args.output}  ({len(paes)} designs)")
    print(f"  pAE range:  {paes.min():.1f} – {paes.max():.1f}")
    print(f"  RMSD range: {rmsds.min():.2f} – {rmsds.max():.2f} Å")
    print(f"  Designs with pAE < 10: {n_low_pae}")


if __name__ == "__main__":
    main()
