#!/bin/bash

# ============================================================================
# Resume interrupted RF2 validation from where it left off.
#
# Usage:
#   bash scripts/resume_rf2.sh <pipeline_dir> [pipeline_dir2 ...]
#
# Examples:
#   bash scripts/resume_rf2.sh designs/ace_pipeline
#   bash scripts/resume_rf2.sh designs/ace_pipeline designs/ace_pipeline_2
#
# Each pipeline dir must already contain:
#   2_proteinmpnn.qv  — full MPNN output (source of truth)
#   3_rf2.qv          — partial RF2 output to resume from
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

if [ $# -eq 0 ]; then
    echo "Usage: bash scripts/resume_rf2.sh <pipeline_dir> [pipeline_dir2 ...]"
    echo ""
    echo "Available pipeline dirs:"
    ls -d designs/*/  2>/dev/null || echo "  (none found under designs/)"
    exit 1
fi

resume_rf2() {
    local DIR=$1

    echo ""
    echo "=============================================="
    echo "Resuming RF2: $DIR"
    echo "=============================================="

    # Validate inputs
    if [ ! -f "$DIR/2_proteinmpnn.qv" ]; then
        echo "  ERROR: $DIR/2_proteinmpnn.qv not found — skipping"
        return 1
    fi
    if [ ! -f "$DIR/3_rf2.qv" ]; then
        echo "  ERROR: $DIR/3_rf2.qv not found — nothing to resume"
        echo "  Tip: run the full pipeline script instead"
        return 1
    fi

    local TOTAL DONE REMAINING
    TOTAL=$(uv run qvls "$DIR/2_proteinmpnn.qv" | wc -l)
    DONE=$(uv run qvls "$DIR/3_rf2.qv" | wc -l)
    REMAINING=$((TOTAL - DONE))

    echo "  Total    : $TOTAL"
    echo "  Done     : $DONE"
    echo "  Remaining: $REMAINING"

    if [ "$REMAINING" -le 0 ]; then
        echo "  Status   : Already complete — nothing to do"
        return 0
    fi

    # Find unprocessed tags
    uv run qvls "$DIR/3_rf2.qv"         | sort > /tmp/rf2_done.txt
    uv run qvls "$DIR/2_proteinmpnn.qv" | sort > /tmp/rf2_all.txt
    comm -23 /tmp/rf2_all.txt /tmp/rf2_done.txt > /tmp/rf2_remaining.txt

    # Slice only the unprocessed entries from the MPNN quiver
    echo "  Slicing remaining entries..."
    cat /tmp/rf2_remaining.txt | uv run qvslice "$DIR/2_proteinmpnn.qv" > "$DIR/2_mpnn_remaining.qv"

    # Run RF2 on just the remaining entries
    echo "  Running RF2 on $REMAINING remaining designs..."
    uv run rf2 \
        --input-quiver "$DIR/2_mpnn_remaining.qv" \
        --output-quiver "$DIR/3_rf2_remaining.qv" \
        --hotspot-show-prop 0.0 \
        --num-recycles 10

    # Merge partial + new output
    echo "  Merging results..."
    cat "$DIR/3_rf2.qv" "$DIR/3_rf2_remaining.qv" > "$DIR/3_rf2_complete.qv"
    mv "$DIR/3_rf2_complete.qv" "$DIR/3_rf2.qv"

    # Cleanup temp files
    rm -f "$DIR/2_mpnn_remaining.qv" "$DIR/3_rf2_remaining.qv"
    rm -f /tmp/rf2_done.txt /tmp/rf2_all.txt /tmp/rf2_remaining.txt

    FINAL=$(uv run qvls "$DIR/3_rf2.qv" | wc -l)
    echo ""
    echo "  Done: $FINAL/$TOTAL designs in $DIR/3_rf2.qv"
    echo "=============================================="
}

for DIR in "$@"; do
    # Strip trailing slash
    DIR="${DIR%/}"
    resume_rf2 "$DIR"
done

echo ""
echo "All done. Check results with:"
for DIR in "$@"; do
    DIR="${DIR%/}"
    echo "  uv run qvls $DIR/3_rf2.qv | wc -l"
done
