#!/usr/bin/env bash
# PYNQ-Z2 launcher. Select the verified PYNQ venv even outside an interactive login.
set -euo pipefail
eye_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
eye_python="${EYE_PYTHON:-/usr/local/share/pynq-venv/bin/python3}"
if [[ ! -x "$eye_python" ]]; then
    printf '%s\n' "PYNQ Python is unavailable: $eye_python" >&2
    exit 2
fi
cd -- "$eye_root"
eye_check_only=false
if [[ $# -eq 0 ]]; then eye_check_only=true; fi
for eye_arg in "$@"; do
    case "$eye_arg" in --check-only|-h|--help) eye_check_only=true ;; esac
done
if [[ "$eye_check_only" == true ]]; then
    exec env "PYTHONPATH=$eye_root/src" "$eye_python" -m eye_tracker.launch "$@"
fi
# Match this project's verified board installation; do not depend on shell startup files.
eye_xrt="${XILINX_XRT:-/usr}"
eye_board="${BOARD:-Pynq-Z2}"
if [[ $EUID -eq 0 ]]; then
    exec env "PYTHONPATH=$eye_root/src" "XILINX_XRT=$eye_xrt" "BOARD=$eye_board" "$eye_python" -m eye_tracker.launch "$@"
fi
exec sudo -- env "PYTHONPATH=$eye_root/src" "XILINX_XRT=$eye_xrt" "BOARD=$eye_board" "$eye_python" -m eye_tracker.launch "$@"
