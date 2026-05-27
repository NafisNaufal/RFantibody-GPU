#!/bin/bash

# ============================================================================
# Full Antibody Design Pipeline — ACE Target, 2nd Attempt (Enterococcus faecalis)
# ============================================================================
# Hotspots: A206, A300, A301, A304
#
# Usage: CUDA_VISIBLE_DEVICES=0 bash scripts/examples/ace_full_pipeline_2.sh
# ============================================================================

set -e

# ============================================================================
# EDITABLE PARAMETERS
# ============================================================================

TARGET_PDB="scripts/examples/example_inputs/2Z1P.pdb"
FRAMEWORK_PDB="scripts/examples/example_inputs/Scaffold.pdb"
OUTPUT_DIR="designs/ace_pipeline_2"

NUM_DESIGNS=200
DESIGN_LOOPS="H1:10,H2:6,H3:16"
HOTSPOTS="A206,A300,A301,A304"
DIFFUSER_T=50

NUM_SEQS=8
SAMPLING_TEMP=0.1

HOTSPOT_SHOW_PROP=0.0
NUM_RECYCLES=10

# ============================================================================
# SETUP
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

mkdir -p "$OUTPUT_DIR"

DIFFUSION_OUTPUT="$OUTPUT_DIR/1_rfdiffusion.qv"
MPNN_OUTPUT="$OUTPUT_DIR/2_proteinmpnn.qv"
RF2_OUTPUT="$OUTPUT_DIR/3_rf2.qv"

echo "=============================================="
echo "Antibody Design Pipeline — ACE Target (2nd)"
echo "Enterococcus faecalis Collagen Adhesin"
echo "=============================================="
echo "Target:    $TARGET_PDB"
echo "Framework: $FRAMEWORK_PDB"
echo "Output:    $OUTPUT_DIR"
echo "Hotspots:  $HOTSPOTS"
echo "Loops:     $DESIGN_LOOPS"
echo "=============================================="

# ============================================================================
# STEP 1: RFdiffusion
# ============================================================================

echo ""
echo "[Step 1/3] Running RFdiffusion..."
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

echo "[Step 1/3] RFdiffusion complete."

# ============================================================================
# STEP 2: ProteinMPNN
# ============================================================================

echo ""
echo "[Step 2/3] Running ProteinMPNN..."
echo "  - Generating $NUM_SEQS sequences per backbone"
echo "  - Sampling temperature: $SAMPLING_TEMP"

uv run proteinmpnn \
    --input-quiver "$DIFFUSION_OUTPUT" \
    --output-quiver "$MPNN_OUTPUT" \
    --seqs-per-struct "$NUM_SEQS" \
    --temperature "$SAMPLING_TEMP"

echo "[Step 2/3] ProteinMPNN complete."

# ============================================================================
# STEP 3: RF2
# ============================================================================

echo ""
echo "[Step 3/3] Running RF2..."
echo "  - Refining structures with $NUM_RECYCLES recycles"

uv run rf2 \
    --input-quiver "$MPNN_OUTPUT" \
    --output-quiver "$RF2_OUTPUT" \
    --hotspot-show-prop "$HOTSPOT_SHOW_PROP" \
    --num-recycles "$NUM_RECYCLES"

echo "[Step 3/3] RF2 complete."

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
echo "  3. RF2 refined structures: $RF2_OUTPUT"
echo ""
echo "View results with:  uv run qvls $RF2_OUTPUT"
echo "Extract PDBs with:  uv run qvextract $RF2_OUTPUT -o final_designs/"
echo "Score summary with: uv run qvscorefile $RF2_OUTPUT"
echo "=============================================="
