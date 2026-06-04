"""
Extract RF2 scores from a Quiver file to CSV and check completeness.

Usage:
    uv run python scripts/extract_rf2_scores.py <rf2.qv> [--expected N] [--output scores.csv]

Examples:
    uv run python scripts/extract_rf2_scores.py designs/ace_pipeline/3_rf2.qv --expected 1600
    uv run python scripts/extract_rf2_scores.py ace_1st_rf2.qv -e 1600 -o ace_1st_scores.csv
"""

import argparse
import csv
import sys

SCORE_FIELDS = [
    "pae",
    "interaction_pae",
    "pred_lddt",
    "framework_aligned_H1_rmsd",
    "framework_aligned_H2_rmsd",
    "framework_aligned_H3_rmsd",
    "framework_aligned_cdr_rmsd",
    "target_aligned_cdr_rmsd",
    "target_aligned_antibody_rmsd",
    "framework_aligned_antibody_rmsd",
    "dG_kcal_mol",
]


def parse_qv_scores(qv_path: str) -> list[dict]:
    records = []
    with open(qv_path) as f:
        for line in f:
            if not line.startswith("QV_SCORE"):
                continue
            parts = line.split()
            tag = parts[1]
            raw = parts[2] if len(parts) > 2 else ""

            scores = {}
            # Handle both pipe-separated and space-separated key=value formats
            kvs = raw.split("|") if "|" in raw else parts[2:]
            for kv in kvs:
                k, _, v = kv.partition("=")
                k = k.strip()
                try:
                    scores[k] = float(v)
                except ValueError:
                    scores[k] = v
            records.append({"tag": tag, **scores})
    return records


def main():
    parser = argparse.ArgumentParser(description="Extract RF2 scores from a Quiver file")
    parser.add_argument("qv", help="Path to RF2 scored Quiver file")
    parser.add_argument("--expected", "-e", type=int, default=None,
                        help="Expected number of designs (for completeness check)")
    parser.add_argument("--output", "-o", default=None,
                        help="Output CSV path (default: <qv_stem>_scores.csv)")
    args = parser.parse_args()

    qv_path = args.qv
    out_path = args.output or qv_path.replace(".qv", "_scores.csv")

    print(f"Reading: {qv_path}")
    records = parse_qv_scores(qv_path)
    n = len(records)

    # ── Completeness check ───────────────────────────────────────────────────
    print(f"\n── Completeness ────────────────────────────────")
    print(f"  Designs found : {n}")
    if args.expected:
        if n == args.expected:
            print(f"  Status        : COMPLETE ({n}/{args.expected})")
        elif n == 0:
            print(f"  Status        : EMPTY — pipeline may not have started RF2")
        else:
            pct = 100 * n / args.expected
            print(f"  Status        : INCOMPLETE — {n}/{args.expected} ({pct:.1f}%)")
            print(f"  Missing       : {args.expected - n} designs")
    print()

    if n == 0:
        print("No QV_SCORE entries found. File may be incomplete or RF2 hasn't finished.")
        sys.exit(1)

    # ── Score summary ────────────────────────────────────────────────────────
    print(f"── Score Summary ───────────────────────────────")
    for field in SCORE_FIELDS:
        vals = [r[field] for r in records if field in r and r[field] != ""]
        if not vals:
            print(f"  {field:<42} not found")
            continue
        try:
            vals = [float(v) for v in vals]
            print(f"  {field:<42} min={min(vals):.3f}  max={max(vals):.3f}  mean={sum(vals)/len(vals):.3f}  (n={len(vals)})")
        except (TypeError, ValueError):
            print(f"  {field:<42} (non-numeric)")
    print()

    # ── Write CSV ────────────────────────────────────────────────────────────
    all_keys = ["tag"] + SCORE_FIELDS
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
        writer.writeheader()
        for rec in records:
            writer.writerow({k: rec.get(k, "") for k in all_keys})

    print(f"Saved: {out_path}  ({n} rows)")


if __name__ == "__main__":
    main()
