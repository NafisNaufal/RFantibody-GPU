"""
4-Stage Antibody Design Screening Pipeline.

Stages:
  1. Hard Structural Filters  : interaction_pae < 10, pred_lddt > 0.9,
                                framework_aligned_cdr_rmsd < 2, framework_aligned_H3_rmsd < 2
  2. Binding Energy Filter    : dG_kcal_mol < -10  (skipped with warning if not in data)
  3. Composite Score Ranking  : equal-weight min-max normalized sum of
                                interaction_pae + H3_rmsd + cdr_rmsd  (lower = better)
  4. Backbone Diversity Limit : keep top-2 per backbone, then take top N overall

Usage:
    uv run python scripts/screen_designs.py <rf2.qv> [options]

    # Run on all pipelines:
    for f in ace_1st ace_2nd ace_3rd esp_1st esp_2nd esp_3rd; do
        uv run python scripts/screen_designs.py ${f}_rf2.qv -o screening/
    done
"""

import argparse
import re
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import pandas as pd


# ── Score field names ──────────────────────────────────────────────────────────
F_PAE       = "interaction_pae"
F_LDDT      = "pred_lddt"
F_CDR_RMSD  = "framework_aligned_cdr_rmsd"
F_H3_RMSD   = "framework_aligned_H3_rmsd"
F_DG        = "dG_kcal_mol"


# ── Parsing ───────────────────────────────────────────────────────────────────
def parse_qv(path: str) -> pd.DataFrame:
    records = []
    with open(path) as f:
        for line in f:
            if not line.startswith("QV_SCORE"):
                continue
            parts = line.split()
            tag = parts[1]
            raw = parts[2] if len(parts) > 2 else ""
            kvs = raw.split("|") if "|" in raw else parts[2:]
            scores = {"tag": tag}
            for kv in kvs:
                k, _, v = kv.partition("=")
                try:
                    scores[k.strip()] = float(v)
                except ValueError:
                    pass
            records.append(scores)
    if not records:
        print("ERROR: No QV_SCORE lines found. Is the file complete?")
        sys.exit(1)
    return pd.DataFrame(records)


def backbone_id(tag: str) -> str:
    """Extract backbone index from tag, e.g. samples_design_0_dldesign_3_best → samples_design_0"""
    m = re.match(r"^(.*?)_dldesign_\d+", tag)
    return m.group(1) if m else tag


# ── Screening stages ──────────────────────────────────────────────────────────
def stage1_structural(df: pd.DataFrame) -> pd.DataFrame:
    mask = (
        (df[F_PAE]      < 10.0) &
        (df[F_LDDT]     > 0.9)  &
        (df[F_CDR_RMSD] < 2.0)  &
        (df[F_H3_RMSD]  < 2.0)
    )
    return df[mask].copy()


def stage2_binding_energy(df: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    if F_DG not in df.columns or df[F_DG].isna().all():
        print(f"  [Stage 2] WARNING: '{F_DG}' not found in data — "
              "run PRODIGY on extracted PDBs to enable this filter. Skipping.")
        return df.copy(), False
    mask = df[F_DG] < -10.0
    return df[mask].copy(), True


def stage3_composite_rank(df: pd.DataFrame) -> pd.DataFrame:
    """Min-max normalize interaction_pae, H3_rmsd, cdr_rmsd then sum equally."""
    result = df.copy()
    for col in [F_PAE, F_H3_RMSD, F_CDR_RMSD]:
        lo, hi = result[col].min(), result[col].max()
        result[f"_norm_{col}"] = (result[col] - lo) / (hi - lo) if hi > lo else 0.0
    result["composite_score"] = (
        result[f"_norm_{F_PAE}"] +
        result[f"_norm_{F_H3_RMSD}"] +
        result[f"_norm_{F_CDR_RMSD}"]
    ) / 3.0
    return result.sort_values("composite_score").reset_index(drop=True)


def stage4_backbone_diversity(df: pd.DataFrame, max_per_backbone: int = 2) -> pd.DataFrame:
    df = df.copy()
    df["backbone"] = df["tag"].apply(backbone_id)
    keep = []
    counts: dict[str, int] = {}
    for _, row in df.iterrows():
        b = row["backbone"]
        if counts.get(b, 0) < max_per_backbone:
            keep.append(row)
            counts[b] = counts.get(b, 0) + 1
    return pd.DataFrame(keep).reset_index(drop=True)


# ── Visualization ─────────────────────────────────────────────────────────────
def make_figure(
    df_all: pd.DataFrame,
    stage_counts: list[tuple[str, int]],
    df_top: pd.DataFrame,
    out_path: str,
    title: str,
    stage2_ran: bool,
):
    fig = plt.figure(figsize=(14, 10))
    fig.suptitle(title, fontsize=13, fontweight="bold", y=0.98)

    gs = fig.add_gridspec(2, 2, hspace=0.38, wspace=0.32)
    ax_funnel = fig.add_subplot(gs[0, :])   # full-width top
    ax_pae_h3 = fig.add_subplot(gs[1, 0])
    ax_pae_cdr = fig.add_subplot(gs[1, 1])

    # ── Funnel chart ──────────────────────────────────────────────────────────
    labels = [s for s, _ in stage_counts]
    counts = [n for _, n in stage_counts]
    colors = ["#f5e6c8", "#d4e8d4", "#b8d4b8", "#7aad7a", "#2d6a2d"]
    colors = colors[:len(labels)]

    bars = ax_funnel.barh(labels[::-1], counts[::-1], color=colors[::-1],
                          edgecolor="white", height=0.55)
    for bar, n in zip(bars, counts[::-1]):
        ax_funnel.text(bar.get_width() + max(counts) * 0.01, bar.get_y() + bar.get_height() / 2,
                       f"{n:,}", va="center", fontsize=10, fontweight="bold")
    ax_funnel.set_xlabel("Number of designs", fontsize=10)
    ax_funnel.set_title("Screening Funnel", fontsize=11, fontweight="bold")
    ax_funnel.spines[["top", "right"]].set_visible(False)
    ax_funnel.set_xlim(0, max(counts) * 1.15)

    # ── Scatter: pAE vs H3 RMSD ───────────────────────────────────────────────
    all_tags = set(df_top["tag"])
    mask_top = df_all["tag"].isin(all_tags)

    ax_pae_h3.scatter(df_all.loc[~mask_top, F_PAE], df_all.loc[~mask_top, F_H3_RMSD],
                      alpha=0.25, s=18, color="steelblue", edgecolors="none", label="All pass S1")
    ax_pae_h3.scatter(df_all.loc[mask_top, F_PAE], df_all.loc[mask_top, F_H3_RMSD],
                      alpha=0.9, s=60, color="crimson", edgecolors="black", linewidths=0.5,
                      zorder=5, label=f"Top {len(df_top)}")
    ax_pae_h3.axvline(10, color="gray", ls="--", lw=1)
    ax_pae_h3.axhline(2,  color="gray", ls="--", lw=1)
    ax_pae_h3.set_xlabel("interaction_pAE", fontsize=10)
    ax_pae_h3.set_ylabel("H3 RMSD (Å)", fontsize=10)
    ax_pae_h3.set_title("pAE vs H3 RMSD", fontsize=11, fontweight="bold")
    ax_pae_h3.legend(fontsize=8)
    ax_pae_h3.grid(True, alpha=0.2)

    # ── Scatter: pAE vs CDR RMSD ──────────────────────────────────────────────
    ax_pae_cdr.scatter(df_all.loc[~mask_top, F_PAE], df_all.loc[~mask_top, F_CDR_RMSD],
                       alpha=0.25, s=18, color="steelblue", edgecolors="none", label="All pass S1")
    ax_pae_cdr.scatter(df_all.loc[mask_top, F_PAE], df_all.loc[mask_top, F_CDR_RMSD],
                       alpha=0.9, s=60, color="crimson", edgecolors="black", linewidths=0.5,
                       zorder=5, label=f"Top {len(df_top)}")
    ax_pae_cdr.axvline(10, color="gray", ls="--", lw=1)
    ax_pae_cdr.axhline(2,  color="gray", ls="--", lw=1)
    ax_pae_cdr.set_xlabel("interaction_pAE", fontsize=10)
    ax_pae_cdr.set_ylabel("CDR RMSD (Å)", fontsize=10)
    ax_pae_cdr.set_title("pAE vs CDR RMSD", fontsize=11, fontweight="bold")
    ax_pae_cdr.legend(fontsize=8)
    ax_pae_cdr.grid(True, alpha=0.2)

    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"  Saved plot: {out_path}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="4-stage antibody design screener")
    parser.add_argument("qv", help="RF2 scored Quiver file")
    parser.add_argument("--top",        "-n", type=int, default=10,
                        help="Final top N designs (default: 10)")
    parser.add_argument("--output-dir", "-o", default=".",
                        help="Output directory for CSV and PNG (default: current dir)")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(args.qv).stem  # e.g. ace_1st_rf2

    print(f"\n{'='*54}")
    print(f"  Screening: {args.qv}")
    print(f"{'='*54}")

    df = parse_qv(args.qv)
    n_input = len(df)
    print(f"  Input designs   : {n_input}")

    stage_counts = [("Input", n_input)]

    # Stage 1
    print(f"\n[Stage 1] Hard Structural Filters")
    print(f"  interaction_pae < 10  |  pred_lddt > 0.9  |  CDR RMSD < 2Å  |  H3 RMSD < 2Å")
    df_s1 = stage1_structural(df)
    print(f"  Passed: {len(df_s1)} / {n_input}  ({100*len(df_s1)/n_input:.1f}%)")
    stage_counts.append(("Stage 1\nStructural", len(df_s1)))

    if df_s1.empty:
        print("  No designs passed Stage 1. Exiting.")
        sys.exit(0)

    # Stage 2
    print(f"\n[Stage 2] Binding Energy Filter  (dG_kcal_mol < -10)")
    df_s2, s2_ran = stage2_binding_energy(df_s1)
    if s2_ran:
        print(f"  Passed: {len(df_s2)} / {len(df_s1)}  ({100*len(df_s2)/len(df_s1):.1f}%)")
    stage_counts.append(("Stage 2\nBinding ΔG" + (" (skipped)" if not s2_ran else ""), len(df_s2)))

    # Stage 3
    print(f"\n[Stage 3] Composite Score Ranking")
    print(f"  Score = normalized(interaction_pae + H3_rmsd + cdr_rmsd) / 3  [lower = better]")
    df_s3 = stage3_composite_rank(df_s2)
    print(f"  Ranked {len(df_s3)} designs  |  best score: {df_s3['composite_score'].min():.4f}")
    stage_counts.append(("Stage 3\nRanked", len(df_s3)))

    # Stage 4
    print(f"\n[Stage 4] Backbone Diversity Limit  (≤2 per backbone)")
    df_s4 = stage4_backbone_diversity(df_s3, max_per_backbone=2)
    print(f"  After diversity filter: {len(df_s4)} designs")
    stage_counts.append(("Stage 4\nDiversity", len(df_s4)))

    # Top N
    df_top = df_s4.head(args.top)
    stage_counts.append((f"Top {args.top}", len(df_top)))
    print(f"\n  Final top {args.top}: {len(df_top)} designs")

    # ── Output CSV ────────────────────────────────────────────────────────────
    csv_cols = ["tag", "backbone", "composite_score",
                F_PAE, F_LDDT, F_H3_RMSD, F_CDR_RMSD]
    if s2_ran:
        csv_cols.append(F_DG)
    csv_cols = [c for c in csv_cols if c in df_top.columns]

    csv_path = out_dir / f"{stem}_top{args.top}.csv"
    df_top[csv_cols].to_csv(csv_path, index=False)
    print(f"  Saved CSV : {csv_path}")

    print(f"\n  {'Tag':<52} {'Score':>7} {'pAE':>6} {'pLDDT':>7} {'H3':>6} {'CDR':>6}")
    print(f"  {'-'*52} {'-'*7} {'-'*6} {'-'*7} {'-'*6} {'-'*6}")
    for _, row in df_top.iterrows():
        print(f"  {row['tag']:<52} {row['composite_score']:>7.4f} "
              f"{row[F_PAE]:>6.2f} {row[F_LDDT]:>7.3f} "
              f"{row[F_H3_RMSD]:>6.2f} {row[F_CDR_RMSD]:>6.2f}")

    # ── Visualization ─────────────────────────────────────────────────────────
    png_path = str(out_dir / f"{stem}_screening.png")
    make_figure(
        df_s1, stage_counts, df_top,
        out_path=png_path,
        title=f"Screening Pipeline — {stem}",
        stage2_ran=s2_ran,
    )

    print(f"\n{'='*54}\n")


if __name__ == "__main__":
    main()
