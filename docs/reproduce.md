# Reproduce EyeStarlink

## Host-only checks

Use Python 3.10+ in a virtual environment and execute commands from the repository
root. Install `requirements-dev.txt`. `tools/prepare_test_assets.py` creates 16 kHz
mono PCM test tones using the published duration metadata; they are not speech.
Then run `tools/build_ui_assets.py` and `tools/verify_software.py`.

With GCC on PATH:

```bash
python tools/verify_receiver_sharing.py
python tools/verify_sharing_chain.py
python tools/rebuild.py native_eye --label native_check
python tools/rebuild.py tiny_runtime --label tiny_check
```

Use `--cc /path/to/gcc` or environment `CC`; add `--arm` with an ARM hard-float
cross-compiler, or compile on the ARMv7 target. Rebuilds use a new output label and
never load hardware. `tiny_runtime` copies the supplied Q8 model and tokenizer into
its output folder. Generated short text requires user review.

Regenerate public OFL graphics from source:

```bash
python tools/build_preview.py
python tools/build_preview.py --eye-region
python tools/build_ui_assets.py
python tools/build_text_assets.py
python tools/build_receiver_assets.py
python tools/build_share_font.py
```

## FPGA build and simulation

Archived results use Vivado 2026.1, part `xc7z020clg400-1`. Install Zynq-7000
device support. Public RTL, XDC and Tcl reconstruct the project; caches are omitted.

```bash
python tools/rebuild.py fpga_base --label base_build --vivado /path/to/vivado
python tools/rebuild.py fpga_neural --label neural_build --vivado /path/to/vivado
vivado -mode batch -source fpga/scripts/simulate_audio.tcl
vivado -mode batch -source fpga/scripts/simulate_capture.tcl
vivado -mode batch -source fpga/scripts/simulate_i2c.tcl
```

Neural candidate and baseline bit/HWH remain separate. Match hashes and hardware
contracts before deployment. Do not replace an overlay while applications own
DMA/display/audio. Another board needs its own constraints and interface contract.

## Four-node communication

Use HiSpark `fbb_ws63` tag 1.10.106, commit
`7cda10e7476d8df35f0ac1a4013eb395874247e0`, and its supported RISC-V toolchain.
The 18-file fingerprint is in `comm/receiver_upgrade/sdk_lock.json`. Obtain the
SDK from the vendor under its terms. The helper checks it and copies it into an
isolated build folder before applying the application and configuration.

```bash
python -m pip install cmake ninja
python tools/rebuild.py receiver --label node03_build --node 03 --sdk /path/to/sdk/src
```

Repeat with 01/02/04 and distinct labels. Vendor-generated `mconfig.h` is regenerated
by the SDK. The public CMake source selection excludes unused vendor UART demos.
Public OFL assets differ typographically from installed firmware; host checks are
included, not a new physical-board acceptance.

See `board/wiring/`: for 03/04, CS GPIO0 has an external 10 kΩ pull-up to 3V3;
GPIO13/14 each goes through 1 kΩ to a normally open button to ground; GPIO2 drives
a red LED through 1 kΩ. Confirm/clear stays local. The 02 HMI protocol and generated
480×272 image sources are included. Import those images into the vendor screen
editor following `care_hmi.c` command/touch contracts; editor binaries are external.

## Personal calibration and normal application

The repository omits a user's eye images and calibrated models. Capture commands
are exposed by `python -m eye_tracker.board --help`; candidate construction uses
`tools/build_fixed_camera_candidate.py --help`. Separate fitting and held-out data;
verify positive and invalid-input cases before enabling actions. Neural training
and native export code is in `train_neural_candidate.py` and `build_neural_native.py`.
Research scripts expect the stage paths documented in their source and
`docs/neural_upgrade.md`; these are not pretrained user-independent models.

Create a private profile following `src/eye_tracker/launch.py`: model/evidence paths,
bit/HWH/model hashes, duration and audio settings. Keep it in ignored `data/private/`.
A copied profile without matching artifacts must fail preflight. Import licensed
or personally recorded PCM speech and update `assets/speech/manifest.json` before
enabling actual speech. Generated test tones must not serve as care prompts.

Install with `python -m pip install -e .`. Review `python -m eye_tracker.launch --help`
and `python -m eye_tracker.board --help`. Board operation needs exclusive ownership,
verified wiring and power. No quick-start command connects or flashes automatically.

## Optional AI writing bundle

`assets/ai` includes Q8 model data/tokenizer with licenses. The adapted runtime is
in `build/edge_ai_v2_20261103/tiny`. ARMv7 flags are
`-O3 -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard`.
Use `tools/tiny_language_cli.py --help` for bounded local generation.

For speech obtain eSpeak NG ARMhf and data under its upstream/distribution terms.
Historical CPU checks used Ubuntu Jammy 1.50+dfsg-10. Put `espeak-ng` in
`assets/ai/tts/bin`, data in `tts/espeak-ng-data`, libraries in `tts/lib`.
Build `native/audio_file_only.c` as shared `libpcaudio.so.0` to prevent system playback.
Preserve upstream notices/source obligations. Generate the SHA-256 manifest required
by `src/eye_tracker/ai_bundle.py`; identify the file-only adapter in `audio_backend`.
Copy `tiny_run` from the ARM build. Do not bypass bundle verification.

Enable `--ai-writing` explicitly after CPU checks. Candidate adoption, speech and
64-character wireless sharing retain separate confirmation. Cancel background jobs
on help, relocation or exit. The public repository does not relabel offline tests
as new board/clinical measurements.
