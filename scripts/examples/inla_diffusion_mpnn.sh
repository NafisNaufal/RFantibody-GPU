#!/bin/bash

# ============================================================================
# RFdiffusion + ProteinMPNN Pipeline — InlA Target
# ============================================================================
# Usage: CUDA_VISIBLE_DEVICES=1 bash scripts/examples/inla_diffusion_mpnn.sh
# ============================================================================

set -e

# ============================================================================
# EDITABLE PARAMETERS
# ============================================================================

TARGET_PDB="scripts/examples/example_inputs/InlA.pdb"
FRAMEWORK_PDB="scripts/examples/example_inputs/Scaffold.pdb"
OUTPUT_DIR="designs/inla_diffusion_mpnn"

NUM_DESIGNS=100
DESIGN_LOOPS="H1:10,H2:6,H3:16"
HOTSPOTS="A389,A387,A369,A326"
DIFFUSER_T=50

NUM_SEQS=10
SAMPLING_TEMP=0.1

# ============================================================================
# SETUP
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

mkdir -p "$OUTPUT_DIR"

DIFFUSION_OUTPUT="$OUTPUT_DIR/1_rfdiffusion.qv"
MPNN_OUTPUT="$OUTPUT_DIR/2_proteinmpnn.qv"

echo "=============================================="
echo "RFdiffusion + ProteinMPNN — InlA Target"
echo "=============================================="
echo "Target:    $TARGET_PDB"
echo "Framework: $FRAMEWORK_PDB"
echo "Output:    $OUTPUT_DIR"
echo "=============================================="

# ============================================================================
# STEP 1: RFdiffusion
# ============================================================================

echo ""
echo "[Step 1/2] Running RFdiffusion..."
echo "  - Designing $NUM_DESIGNS backbones"
echo "  - Loop lengths: $DESIGN_LOOPS"
echo "  - Hotspots: $HOTSPOTS"

uv run rfdiffusion \
    --target "$TARGET_PDB" \
    --framework "$FRAMEWORK_PDB" \
    --output-quiver "$DIFFUSION_OUTPUT" \
    --num-designs "$NUM_DESIGNS" \
    --design-loops "$DESIGN_LOOPS" \
    --hotspots "$HOTSPOTS" \
    --diffuser-t "$DIFFUSER_T" \
    --deterministic

echo "[Step 1/2] RFdiffusion complete."

# ============================================================================
# STEP 2: ProteinMPNN
# ============================================================================

echo ""
echo "[Step 2/2] Running ProteinMPNN..."
echo "  - Generating $NUM_SEQS sequences per backbone"
echo "  - Sampling temperature: $SAMPLING_TEMP"

uv run proteinmpnn \
    --input-quiver "$DIFFUSION_OUTPUT" \
    --output-quiver "$MPNN_OUTPUT" \
    --seqs-per-struct "$NUM_SEQS" \
    --temperature "$SAMPLING_TEMP"

echo "[Step 2/2] ProteinMPNN complete."

# ============================================================================
# SUMMARY
# ============================================================================

echo ""
echo "=============================================="
echo "Pipeline Complete!"
echo "=============================================="
echo "Outputs:"
echo "  1. RFdiffusion backbones: $DIFFUSION_OUTPUT"
echo "  2. ProteinMPNN sequences: $MPNN_OUTPUT"
echo ""
echo "View results with:  uv run qvls $MPNN_OUTPUT"
echo "Extract PDBs with:  uv run qvextract $MPNN_OUTPUT <output_dir>"
echo "=============================================="
