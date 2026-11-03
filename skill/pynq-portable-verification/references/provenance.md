# Observation → reusable rule → verification

| EyeStarlink engineering observation | Generalized rule | Package check |
|---|---|---|
| Multiple base/candidate overlays coexist with independent manifests | Pair bit/HWH by hash and verify IP/address/register contracts before use | Wrong hash, missing IP, relocated address, VLNV, register, clock and overlap cases |
| Video/audio/camera work requires explicit DMA and audio cleanup on failure | Transfer ownership remains with hardware until quiescence is established | Stalled/error/partial-start transfers preserve buffers and do not invalidate incomplete output |
| A synchronous alignment helper once delayed BTN0 polling | Keep deadlines and blocking work separate from the interactive loop | Injected monotonic clock proves finite polling exit; no hardware timing claim |
| Independent MiniMind NumPy reference did not meet the strict numerical criterion, despite close cross-host C outputs | Keep independent golden failures visible; report tolerances and provenance | Shape/NaN/rounding/mismatch cases must fail |

These are distilled engineering observations, not copied private logs or personal
eye images. The project uses custom video/audio engines; it does **not** establish
a physical-board test of this new generic AXI DMA adapter. The reusable package
has offline fake-device and fixture validation. Its two board contracts are
illustrations to exercise portability, not measurements on two physical boards.

Use the team's hardware-specific source as a separate example:
`src/eye_tracker/hardware_contract.py`, `fpga/rtl/`, and `tools/verify_audio_rtl.py`.
Review [the published evidence summary](../../../report/validation.md) for actual
project checks and boundaries. No patient/clinical validation is claimed.
