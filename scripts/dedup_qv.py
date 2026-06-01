"""
Remove duplicate tags from a Quiver file, keeping the first occurrence.

Usage:
    uv run python scripts/dedup_qv.py <input.qv> <output.qv>

Example:
    uv run python scripts/dedup_qv.py designs/esp_pipeline_3/3_rf2.qv designs/esp_pipeline_3/3_rf2_clean.qv
"""

import sys


def dedup_qv(input_path: str, output_path: str):
    seen = set()
    kept = 0
    skipped = 0

    with open(input_path, "r") as fin, open(output_path, "w") as fout:
        current_tag = None
        skip_current = False
        buffer = []

        for line in fin:
            if line.startswith("QV_TAG"):
                # Flush previous entry if it wasn't skipped
                if buffer and not skip_current:
                    fout.writelines(buffer)
                    kept += 1
                elif buffer and skip_current:
                    skipped += 1

                # Start new entry
                current_tag = line.split()[1]
                skip_current = current_tag in seen
                if not skip_current:
                    seen.add(current_tag)
                buffer = [line]
            else:
                buffer.append(line)

        # Flush last entry
        if buffer:
            if not skip_current:
                fout.writelines(buffer)
                kept += 1
            else:
                skipped += 1

    print(f"Input : {input_path}")
    print(f"Output: {output_path}")
    print(f"Kept  : {kept}")
    print(f"Removed duplicates: {skipped}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: uv run python scripts/dedup_qv.py <input.qv> <output.qv>")
        sys.exit(1)
    dedup_qv(sys.argv[1], sys.argv[2])
