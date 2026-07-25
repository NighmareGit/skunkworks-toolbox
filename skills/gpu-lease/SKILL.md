name: gpu-lease
description: Acquire and release exclusive GPU leases so parallel sub-agents never OOM or contend. Mandatory before any heavy benchmark, profiling, or multi-GPU test.
---

# GPU Lease Manager

## Rules
- Every agent that needs GPUs must call this skill first.
- Leases are exclusive and time-bounded.
- Prefer the smallest set of GPUs that still allows meaningful measurement.

## Protocol
1. List available GPUs (`nvidia-smi -L` or equivalent).
2. Check `.scratch/leases/` for existing active leases.
3. Acquire the required GPUs by writing a lease file:
   `.scratch/leases/<agent-id>-<timestamp>.lease`
   Content:
agent: <id>
gpus: 0,1
acquired: <ISO timestamp>
expires: <ISO timestamp + 90min>
purpose: <short>
4. Export `CUDA_VISIBLE_DEVICES` / `HIP_VISIBLE_DEVICES` accordingly.
5. On finish (or timeout) delete the lease file.

## Safety
If the requested GPUs are already leased, either wait, request a different set, or fail fast and notify the parent. Never force.