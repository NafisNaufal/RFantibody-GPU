#!/bin/bash
# Run rfdiffusion across multiple parallel processes on a single GPU.
#
# Each process handles a chunk of designs independently. Since each design
# uses ~6GB VRAM on an A100 (80GB), you can safely run up to ~10 processes
# in parallel before hitting memory limits.
#
# Usage:
#   bash scripts/rfdiffusion_parallel.sh \
#       --total-designs 1000 \
#       --parallel 10 \
#       --target path/to/target.pdb \
#       --framework path/to/framework.pdb \
#       --output path/to/output_prefix \
#       [any other rfdiffusion flags...]
#
# The output files will be named: output_prefix_0.pdb, output_prefix_1.pdb, ...
# Each chunk writes to its own --design-startnum offset so filenames never collide.

set -euo pipefail

TOTAL_DESIGNS=100
PARALLEL=10
EXTRA_ARGS=()

# Parse our flags, pass everything else through to rfdiffusion
while [[ $# -gt 0 ]]; do
    case "$1" in
        --total-designs) TOTAL_DESIGNS="$2"; shift 2 ;;
        --parallel)      PARALLEL="$2";      shift 2 ;;
        *)               EXTRA_ARGS+=("$1"); shift ;;
    esac
done

CHUNK=$(( (TOTAL_DESIGNS + PARALLEL - 1) / PARALLEL ))

echo "Launching $PARALLEL workers, $CHUNK designs each (total: $((CHUNK * PARALLEL)))..."

PIDS=()
for i in $(seq 0 $((PARALLEL - 1))); do
    START=$(( i * CHUNK ))
    uv run rfdiffusion \
        --num-designs "$CHUNK" \
        --design-startnum "$START" \
        "${EXTRA_ARGS[@]}" &
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

if [[ $FAILED -eq 0 ]]; then
    echo "All workers finished successfully."
else
    echo "One or more workers failed." >&2
    exit 1
fi
