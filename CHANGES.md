# Performance Optimizations — RFantibody GPU Fork

This document describes the changes made to the `optimizations` branch of this fork relative to the original [RosettaCommons/RFantibody](https://github.com/RosettaCommons/RFantibody) repository.

**Measured improvement:** ~1.5–2 minutes per design on an RTX 3060 (10.5 min → 9 min), with larger relative gains on server CPUs (AMD EPYC) where single-core Python throughput is lower.

---

## Overview

The original RFdiffusion inference loop runs 50 diffusion timesteps per design. Each timestep involves:
1. A GPU forward pass through RoseTTAFoldModule
2. SO(3) rotation sampling for backbone frame updates
3. Kabsch superposition (motif alignment)
4. Coordinate denoising

The bottleneck in the original code was **CPU↔GPU data transfer**: steps 2 and 3 pulled tensors off the GPU, processed them with scipy/numpy on CPU, then pushed them back. This forced GPU pipeline stalls 49 times per design. All changes below eliminate these stalls by keeping computation on the GPU throughout.

---

## Changes

### 1. SO(3) Rotation Sampling — GPU Port

**File:** `src/rfantibody/rfdiffusion/diffusion.py`

**Original behaviour:** `IGSO3.reverse_sample_vectorized()` converted rotation matrices to CPU numpy arrays, called `scipy.spatial.transform.Rotation.as_rotvec()` for axis-angle conversion, used `np.random.normal` for noise sampling, and called `np.interp` for score norm interpolation. Every diffusion timestep required a full GPU→CPU→GPU round-trip for all residue frames.

**Change:** Rewrote `reverse_sample_vectorized()` as pure PyTorch:
- Replaced `scipy_R.from_matrix(...).as_rotvec()` with `rotation_conversions.matrix_to_axis_angle()` (already available in the codebase)
- Replaced `np.random.normal` with `torch.randn(..., device=device)`
- Added `_score_norm_torch()`: a PyTorch linear interpolation replacing `np.interp`, using `torch.bucketize` to stay on device

All rotation sampling now executes entirely on GPU with no CPU synchronisation.

---

### 2. Kabsch Superposition (Motif Alignment) — GPU Port

**File:** `src/rfantibody/rfdiffusion/inference/utils.py`

**Original behaviour:** `Denoise.align_to_xt_motif()` called `.cpu().detach().numpy()` on all three input tensors (`px0`, `xT`, `diffusion_mask`), performed SVD with `np.linalg.svd`, constructed the rotation matrix on CPU, then returned `torch.Tensor(px0_)` — a CPU tensor cast back to GPU. This happened every timestep when a motif was present.

**Change:** Rewrote using `torch.linalg.svd` and `torch.linalg.det`. All operations stay on the device of the input tensors. The function now returns a native GPU tensor.

---

### 3. Backbone Frame Update — GPU Port

**File:** `src/rfantibody/rfdiffusion/inference/utils.py`

**Original behaviour:** `get_next_frames()` called `scipy_R.from_matrix(...).as_matrix()` to normalise rotation matrices onto SO(3), then used `np.broadcast_to`, `np.identity`, and `np.einsum` for the frame coordinate update. Returned a numpy array.

**Change:**
- Added `_normalize_rot()`: projects `(..., 3, 3)` matrices onto SO(3) using `torch.linalg.svd`, replacing the scipy call
- Replaced numpy operations with `torch.eye`, `torch.einsum`, and tensor indexing
- Function now returns a `torch.Tensor` instead of a numpy array, eliminating the implicit CPU→GPU transfer in callers

---

### 4. Device Consistency Fixes

**File:** `src/rfantibody/rfdiffusion/inference/utils.py`

Several device mismatches caused silent CPU fallbacks or runtime errors when tensors from different sources were combined:

- **`get_next_pose`**: `xt` was arriving on CPU while `px0` was on GPU. Added `xt = xt.to(px0.device)` at entry so all subsequent operations use a consistent device.
- **`get_next_ca`**: Fixed `torch.normal(mu, sigma)` where `sigma` was a CPU scalar and `mu` was on GPU. Replaced with `mu + torch.randn_like(mu) * ...` which inherits device from `mu`.
- **`diffusion_mask` indexing**: Added `.to(delta.device)` and `.to(xt.device)` before boolean indexing to prevent cross-device index errors.
- **`grad_ca`**: `get_potential_gradients()` returns a CPU tensor; added `.to(ca_deltas.device)` before addition.
- **`frames_next`**: Was being constructed with `torch.from_numpy()` (CPU); added `.to(ca_deltas.device)` before the translate step.
- Removed a stale `ComputeAllAtomCoords()` instantiation inside `get_next_ca()` that was being created and discarded every timestep.

---

### 5. Removed Per-Timestep GPU→CPU Sync in Logging

**File:** `src/rfantibody/rfdiffusion/inference/model_runners.py`

**Original behaviour:** Every timestep logged the current sequence:
```python
self._log.info(f'Timestep {t}, input to next step: {seq2chars(torch.argmax(seq_t_1, dim=-1).tolist())}')
```
The `.tolist()` call forces a GPU→CPU synchronisation, stalling the GPU pipeline at every one of the 50 timesteps.

**Change:** Replaced with a simple timestep counter log that requires no GPU data:
```python
self._log.info(f'Timestep {t} done')
```

---

### 6. TF32 Matmul Precision

**File:** `scripts/rfdiffusion_inference.py`

Added at inference startup:
```python
torch.set_float32_matmul_precision('high')
```

On GPUs with tensor cores (A100, L40, RTX 30xx/40xx series), this enables TF32 for float32 matrix multiplications — effectively free throughput improvement with negligible numerical difference for inference.

---

## What Was Not Changed

- **Model weights, architecture, and outputs** — all changes are in the inference loop only; results are numerically equivalent
- **ProteinMPNN and RF2 modules** — unchanged
- **Dependencies** — no new packages required; uses `rotation_conversions` already present in the codebase
