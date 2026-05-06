"""
Validate that optimized RFdiffusion outputs match original repo outputs.

Usage:
    uv run python scripts/validate_optimization.py <original.qv> <optimized.qv>

Compares Cα coordinates of corresponding designs (by index) and reports RMSD.
A RMSD < 0.01 Å indicates numerically identical outputs.
"""

import sys
import numpy as np
from rfantibody.util.quiver import Quiver


def parse_ca_coords(pdb_lines: list) -> np.ndarray:
    coords = []
    for line in pdb_lines:
        if line.startswith("ATOM") and line[12:16].strip() == "CA":
            x = float(line[30:38])
            y = float(line[38:46])
            z = float(line[46:54])
            coords.append([x, y, z])
    return np.array(coords)


def rmsd(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) != len(b):
        return float("nan")
    diff = a - b
    return float(np.sqrt((diff ** 2).sum(axis=1).mean()))


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    orig_path, opt_path = sys.argv[1], sys.argv[2]

    orig_qv = Quiver(orig_path, mode="r")
    opt_qv  = Quiver(opt_path,  mode="r")

    orig_tags = orig_qv.get_tags()
    opt_tags  = opt_qv.get_tags()

    print(f"Original : {len(orig_tags)} designs  ({orig_path})")
    print(f"Optimized: {len(opt_tags)} designs  ({opt_path})")
    print()

    n = min(len(orig_tags), len(opt_tags))
    if n == 0:
        print("No designs to compare.")
        sys.exit(1)

    rmsds = []
    all_pass = True

    print(f"{'#':<4}  {'Original tag':<40}  {'Optimized tag':<40}  {'CA RMSD (Å)'}")
    print("-" * 100)

    for i in range(n):
        ot = orig_tags[i]
        pt = opt_tags[i]

        orig_lines = orig_qv.get_pdblines(ot)
        opt_lines  = opt_qv.get_pdblines(pt)

        ca_orig = parse_ca_coords(orig_lines)
        ca_opt  = parse_ca_coords(opt_lines)

        r = rmsd(ca_orig, ca_opt)
        rmsds.append(r)

        status = "OK" if (np.isnan(r) or r < 0.01) else "MISMATCH"
        if status == "MISMATCH":
            all_pass = False

        print(f"{i:<4}  {ot:<40}  {pt:<40}  {r:.6f} Å  {status}")

    print()
    valid_rmsds = [r for r in rmsds if not np.isnan(r)]
    if valid_rmsds:
        print(f"Mean RMSD : {np.mean(valid_rmsds):.6f} Å")
        print(f"Max RMSD  : {np.max(valid_rmsds):.6f} Å")

    print()
    if all_pass:
        print("RESULT: PASS — outputs are numerically equivalent.")
    else:
        print("RESULT: FAIL — one or more designs differ above 0.01 Å threshold.")
        sys.exit(1)


if __name__ == "__main__":
    main()
