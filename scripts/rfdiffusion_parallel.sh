#!/bin/bash
# Run rfdiffusion across multiple parallel processes on a single GPU.
#
# Each process handles a chunk of designs independently. Since each design
# uses ~6GB VRAM on an A100 (80GB), you can safely run up to ~13 processes
# in parallel before hitting memory limits.
#
# Usage:
#   bash scripts/rfdiffusion_parallel.sh \
#       --total-designs 1000 \
#       --parallel 13 \
#       [any other rfdiffusion flags...]
#
# For Quiver output (--output-quiver path/to/out.qv), each worker writes to
# its own shard file, which are merged into the final file at the end.
# For PDB output (--output path/to/prefix), filenames never collide because
# each worker gets its own --design-startnum offset.

set -euo pipefail

TOTAL_DESIGNS=100
PARALLEL=10
EXTRA_ARGS=()
QUIVER_OUT=""

# Parse our flags; detect --output-quiver so we can handle sharding
while [[ $# -gt 0 ]]; do
    case "$1" in
        --total-designs) TOTAL_DESIGNS="$2"; shift 2 ;;
        --parallel)      PARALLEL="$2";      shift 2 ;;
        --output-quiver|-q)
            QUIVER_OUT="$2"
            EXTRA_ARGS+=("$1" "$2")
            shift 2 ;;
        *) EXTRA_ARGS+=("$1"); shift ;;
    esac
done

CHUNK=$(( (TOTAL_DESIGNS + PARALLEL - 1) / PARALLEL ))

echo "Launching $PARALLEL workers, $CHUNK designs each (total: $((CHUNK * PARALLEL)))..."

# If using Quiver output, each worker writes to a shard so they don't collide
SHARD_FILES=()
PIDS=()
for i in $(seq 0 $((PARALLEL - 1))); do
    START=$(( i * CHUNK ))

    WORKER_ARGS=("${EXTRA_ARGS[@]}")

    if [[ -n "$QUIVER_OUT" ]]; then
        # Replace the shared quiver path with a per-worker shard path
        SHARD="${QUIVER_OUT%.qv}_shard${i}.qv"
        SHARD_FILES+=("$SHARD")
        # Rebuild args replacing the quiver value
        WORKER_ARGS=()
        SKIP_NEXT=0
        for arg in "${EXTRA_ARGS[@]}"; do
            if [[ $SKIP_NEXT -eq 1 ]]; then
                WORKER_ARGS+=("$SHARD")
                SKIP_NEXT=0
            elif [[ "$arg" == "--output-quiver" || "$arg" == "-q" ]]; then
                WORKER_ARGS+=("$arg")
                SKIP_NEXT=1
            else
                WORKER_ARGS+=("$arg")
            fi
        done
    fi

    uv run rfdiffusion \
        --num-designs "$CHUNK" \
        --design-startnum "$START" \
        "${WORKER_ARGS[@]}" &
    PIDS+=($!)
    echo "  Worker $i started (PID ${PIDS[-1]}, designs $START–$((START + CHUNK - 1)))"
done

# Wait for all workers and collect exit codes
FAILED=0
for i in "${!PIDS[@]}"; do
    if ! wait "${PIDS[$i]}"; then
        echo "Worker $i (PID ${PIDS[$i]}) failed." >&2
        FAILED=1
    fi
done

if [[ $FAILED -ne 0 ]]; then
    echo "One or more workers failed." >&2
    exit 1
fi

# Merge Quiver shards into the final file
if [[ -n "$QUIVER_OUT" && ${#SHARD_FILES[@]} -gt 0 ]]; then
    echo "Merging ${#SHARD_FILES[@]} Quiver shards into $QUIVER_OUT..."
    uv run python - "$QUIVER_OUT" "${SHARD_FILES[@]}" <<'EOF'
import sys
from rfantibody.util.quiver import Quiver

out_path = sys.argv[1]
shard_paths = sys.argv[2:]

out_qv = Quiver(out_path, mode='w')
for shard_path in shard_paths:
    try:
        shard = Quiver(shard_path, mode='r')
        for tag in shard.get_tags():
            pdblines = shard.get_pdb(tag)
            score = shard.get_score(tag)
            if score:
                out_qv.add_pdb(pdblines, tag, score)
            else:
                out_qv.add_pdb(pdblines, tag)
        import os; os.remove(shard_path)
    except Exception as e:
        print(f"Warning: could not merge {shard_path}: {e}", file=sys.stderr)

print(f"Merged {len(shard_paths)} shards -> {out_path}")
EOF
fi

echo "All workers finished successfully."
