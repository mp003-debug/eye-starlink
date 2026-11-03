#!/usr/bin/env bash
# Keep the board's PYNQ interpreter and only the required environment under sudo.
set -euo pipefail
eye_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
eye_python="$(command -v python3)"
cd -- "$eye_root"
if [[ $# -eq 0 || "$1" == inspect ]]; then
    exec env "PYTHONPATH=$eye_root/src" "$eye_python" -m eye_tracker.board "$@"
fi
: "${XILINX_XRT:?Source the existing PYNQ login environment first}"
: "${BOARD:?Source the existing PYNQ login environment first}"
exec sudo -- env "PYTHONPATH=$eye_root/src" "XILINX_XRT=$XILINX_XRT" "BOARD=$BOARD" "$eye_python" -m eye_tracker.board "$@"
