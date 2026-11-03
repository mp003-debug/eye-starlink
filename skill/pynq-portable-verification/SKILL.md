---
name: pynq-portable-verification
description: Verify portable PYNQ overlay contracts, DMA ownership and cache handling, and numerical/timing evidence. Use when adapting a Zynq design to another board, diagnosing stale buffers or hung transfers, or preparing a reproducible FPGA validation package.
---

# PYNQ portable verification

Work from the target design's interface contract, not an example board's addresses.
The helpers run offline without PYNQ; they never download a bitstream or open a device.

## 1. Establish the hardware contract

Record part/board, PYNQ version, paired bit/HWH hashes, IP instance names and VLNVs,
address ranges, register offsets, clocks, stream word size, DMA mode and maximum
transfer size. Use `references/contracts.md` and the two example contracts.

Run `scripts/overlay_contract.py CONTRACT OBSERVED --artifacts DIRECTORY`.
`OBSERVED` is a normalized snapshot of an already inspected overlay's `ip_dict`;
`snapshot(overlay, platform)` can collect it without register reads or downloading.
Read metadata first; only load an overlay when the task authorizes hardware changes
and the device is idle. Never replace PS DDR or boot configuration to fix an IP mismatch.

Stop on hash, part, IP, range, register or clock-contract mismatch. Do not guess a
register address from a different board. Hash equality proves pairing to the manifest,
not that hardware was built correctly; check synthesis and simulation separately.

## 2. Establish DMA ownership

For **simple AXI DMA only**, use `scripts/dma_guard.py` after inspecting the driver's
version and stream contract. Allocate with `pynq.allocate`, initialize input, flush
PS writes, arm receive before send, and invalidate output only after both channels
finish. Keep buffers alive until hardware is proven quiescent.

Use a finite deadline for polling. Inspect channel errors and the producer's TLAST,
TKEEP, transfer length, backpressure and reset/clock domain when completion stalls.
Read `references/dma.md` for recovery and ownership rules. The helper never calls
unbounded `wait()`/`stop()` and never frees buffers. A timeout is **not** proof that
DMA stopped. A design-specific bounded `quiesce` callback may prove this; otherwise
retain `DmaFailure.buffers` and recover the hardware before freeing them.

Do not apply this simple-DMA helper to cyclic/SG DMA, AXI VDMA frame rings, custom
video/audio MMIO engines, or partial reconfiguration. Adapt and test their contracts.

## 3. Compare output and implementation evidence

Run `scripts/verify_results.py RESULTS.json` to compare full shape, finite values,
absolute/relative errors, latencies, and optional timing/resource limits. Set tolerances
before examining results. Preserve failed comparisons and input provenance.

For integers use exact comparison unless the algorithm specifies saturation or
rounding. For quantization report maximum error and the reference implementation;
matching the same C kernel on two hosts is not independent numerical validation.
Report LUT/FF/BRAM/DSP with part, tool version and implementation stage. WNS is a
constraint-dependent timing result, not measured application throughput.

## 4. Deliver a reproducible record

Run `python -m unittest discover -s skill/pynq-portable-verification/tests -v`.
Keep contract, commands, tool versions, input/golden hashes, reports and failure
reason in the result. Label offline fixtures, RTL simulation, CPU benchmark and
physical board checks separately. Never infer a board pass from a mocked device.

Read `references/provenance.md` for the actual EyeStarlink observations that motivated
these rules and the boundaries of this reusable package's validation.
