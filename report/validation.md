# Validation and evidence map

## Existing project measurements

| Item | Recorded result | Interpretation |
|---|---|---|
| Base independent demonstration | 3600.038 s; 28,950 frames; 272 choices; normal stop | Existing fixed-camera application run, not population accuracy |
| Latest integrated software regression | 559 tests in the private engineering package | Offline behavior checks; public rerun is recorded separately below |
| Native MLP CPU | Median 6.284 → 0.537 ms (11.70×); 50 inputs repeated 1,000 times | PYNQ CPU benchmark, frozen model; not improved gaze accuracy |
| MiniMind2-Small Q8 | 25.83M parameters; 26.20 MiB; 6 CPU generation runs | PYNQ-local CPU inference; short-text capability is limited |
| Neural FPGA candidate | LUT 5,328; FF 6,682; BRAM 72.5; DSP 64; WNS 2.177 ns | Routed candidate on xc7z020clg400-1, Vivado 2026.1; separate from live application acceptance |
| AI writing integration | Offline state/chain tests; silent CPU generation and WAV synthesis | New human UI/listening/wireless mixed-load acceptance remains separate |

Full implementation reports are in `build/fpga/reports/` and
`build/neural_upgrade_20261103/fpga/reports/`. Reports retain their actual warnings;
WNS alone does not establish unconstrained paths, CDC correctness or user-facing rate.
The independent strict MiniMind NumPy comparison did not pass its tolerance;
cross-host agreement of the C implementation is a distinct result.

## Public-source verification

The public export replaces non-redistributable system-font dependencies with
Noto CJK OFL assets and uses generated test tones for offline audio fixtures.
The font's taller bounding boxes required a small header-layout adjustment;
target rectangles, dwell thresholds and original runtime files are unchanged.

Fresh results are published as:
- `software_result.json` / `software_tests.txt`: public application regression.
- `skill_tests.txt`: reusable contract/DMA/golden helper tests.
- `sharing_chain.json`: Python sender through compiled C bridge/endpoints.
- `receiver_host.json`: C receiver display/protocol checks with fake HAL.
- `public_verification.json`: commands, environment and artifact checks.

Three private-profile/optional-full-runtime tests are explicitly gated when those
inputs are absent. The remaining tests retain their assertions, including pixel
comparisons, input rejection, stale confirmations, audio priority and cleanup.
No camera images or personal calibration are needed for the public checks.

The generic Skill uses two fictional board contracts and injected DMA failures.
This verifies portable helpers offline; it is not a claim of physical testing on
two boards. No hardware was accessed while preparing this public release.
