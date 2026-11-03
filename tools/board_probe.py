"""Read-only board inventory. No PYNQ import, MMIO, downloads or process control."""
import json
import platform
import os
import sys
from pathlib import Path


def main():
    report = {"python": sys.version, "machine": platform.machine(),
              "system": platform.platform(), "python_executable": sys.executable,
              "pynq_environment": {key:os.environ.get(key) for key in ("BOARD", "XILINX_XRT")},
              "versions": {}, "hardware_touched": False}
    try:
        from importlib.metadata import version, PackageNotFoundError
        for name in ("pynq", "numpy", "Pillow"):
            try:
                report["versions"][name] = version(name)
            except PackageNotFoundError:
                report["versions"][name] = None
    except ImportError:
        report["dependency_note"] = "Python <3.8: inspect existing PYNQ environment before deployment"
    if platform.system() == "Linux":
        report["memory_kb"] = {}
        for line in Path('/proc/meminfo').read_text().splitlines():
            key, value = line.split(':', 1)
            if key in ('MemTotal', 'MemAvailable', 'CmaTotal', 'CmaFree'):
                report["memory_kb"][key] = value.strip()
        processes = []
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():
                continue
            try:
                name = (proc/'comm').read_text().strip()
            except (OSError, UnicodeError):
                continue
            if any(word in name.lower() for word in ('python', 'jupyter', 'eye', 'dma')):
                processes.append({"pid": int(proc.name), "name": name})
        report["processes_to_review_not_proof_of_dma_ownership"] = sorted(processes, key=lambda p:p['pid'])
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
