# Simple AXI DMA adapter

Prerequisites: simple mode, configured/running channels, responsive MMIO,
exclusive ownership of the engine and buffers, known memory word alignment and
maximum transfer length. Pass exact positive byte lengths. The helper rejects
physical overlap. It does not support SG, cyclic DMA, VDMA or in-place kernels.

The current PYNQ simple driver exposes `running`, `idle`, `error`, and `transfer`.
Its first transfer after `start()` may have idle low; the adapter explicitly checks
`_first_transfer` for that version-specific case. Review this private field on
version upgrades. Do not substitute a fabricated flag to override a busy engine.

Call `transfer(...)` with buffers allocated by `pynq.allocate`. The caller handles
allocation and lifetime. Both buffers are flushed before device ownership; output
is invalidated after completion. `wait()` also performs bookkeeping in PYNQ, so
this helper deliberately returns its own byte counts instead of promising the
driver's `transferred` field is updated. The producer must emit the expected length
and TLAST. Idle alone does not validate output content: compare against a golden
result and check design-specific counters where needed.

On `DmaFailure`, the exception retains both buffers. Never put them in a context
manager that unconditionally frees memory on timeout. `quiesce` must have its own
bounded implementation and must observe the producer and DMA stopped. The stock
driver `stop()` loops without a deadline and is not a suitable generic callback.
If recovery is unknown, keep buffers allocated and do not begin another transfer.
A user-space timer cannot interrupt a kernel or bus access that has hung.

Authoritative references:
- [Buffer allocation and cache maintenance](https://pynq.readthedocs.io/en/latest/pynq_libraries/allocate.html)
- [DMA and TLAST](https://pynq.readthedocs.io/en/latest/pynq_libraries/dma.html)
- [PYNQ DMA implementation](https://pynq.readthedocs.io/en/latest/_modules/pynq/lib/dma.html)
