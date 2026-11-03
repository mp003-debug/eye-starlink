"""Verify the bit/HWH pair and exact bring-up register topology before MMIO."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

EXPECTED_VDMA = {
    "C_INCLUDE_SG": 0, "C_NUM_FSTORES": 3,
    "C_INCLUDE_MM2S": 1, "C_INCLUDE_S2MM": 1,
    "C_INCLUDE_MM2S_DRE": 0, "C_INCLUDE_S2MM_DRE": 0,
    "C_M_AXIS_MM2S_TDATA_WIDTH": 16, "C_S_AXIS_S2MM_TDATA_WIDTH": 8,
    "C_M_AXI_MM2S_DATA_WIDTH": 64, "C_M_AXI_S2MM_DATA_WIDTH": 64,
    "C_M_AXI_MM2S_ADDR_WIDTH": 32, "C_M_AXI_S2MM_ADDR_WIDTH": 32,
    "C_USE_MM2S_FSYNC": 0, "C_USE_S2MM_FSYNC": 0,
    "C_MM2S_LINEBUFFER_DEPTH": 8192, "C_S2MM_LINEBUFFER_DEPTH": 8192,
}
ADDRESSES = {"vdma_0": 0x43000000, "video_control": 0x41200000, "camera_diag_0": 0x43C00000, "audio_aux_0": 0x43C20000, "event_uart_0": 0x42C00000}


def verify_artifacts(root):
    root = Path(root)
    build = root / "build/fpga"
    evidence = json.loads((build / "result.json").read_text(encoding="utf-8"))
    digests = {}
    for suffix in ("bit", "hwh"):
        relative = "build/fpga/eye_tracker." + suffix
        actual = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        if actual != evidence["artifacts"][relative]["sha256"]:
            raise ValueError("firmware manifest mismatch: " + relative)
        digests[suffix] = actual
    hwh = ET.parse(str(build / "eye_tracker.hwh")).getroot()
    modules = {m.attrib.get("INSTANCE"): m for m in hwh.findall(".//MODULE")}
    expected = {
        "ps7": {"PCW_FPGA0_PERIPHERAL_FREQMHZ": 50, "PCW_FPGA1_PERIPHERAL_FREQMHZ": 100},
        "vdma_0": EXPECTED_VDMA,
        "event_uart_0": {"C_BAUDRATE":115200, "C_DATA_BITS":8, "C_USE_PARITY":0, "C_S_AXI_ACLK_FREQ_HZ":50000000},
        "video_control": {"C_IS_DUAL": 1, "C_GPIO_WIDTH": 4, "C_GPIO2_WIDTH": 7,
                          "C_ALL_OUTPUTS": 1, "C_ALL_INPUTS_2": 1},
    }
    for name, values in expected.items():
        module = modules[name]
        params = {p.attrib["NAME"]: p.attrib["VALUE"] for p in module.findall("./PARAMETERS/PARAMETER")}
        for key, value in values.items():
            if int(params[key], 0) != value:
                raise ValueError("unsupported hardware configuration: %s.%s" % (name, key))
    ranges = {m.attrib["INSTANCE"]: int(m.attrib["BASEVALUE"], 0)
              for m in hwh.findall(".//MEMRANGE") if m.attrib.get("MEMTYPE") == "REGISTER"}
    for name, address in ADDRESSES.items():
        if ranges.get(name) != address:
            raise ValueError("unexpected register address: " + name)
    audio_ranges=[m for m in hwh.findall(".//MEMRANGE") if m.attrib.get("INSTANCE")=="audio_aux_0"]
    if not audio_ranges or any(int(m.attrib["HIGHVALUE"],0)-int(m.attrib["BASEVALUE"],0)+1 != 0x20000 for m in audio_ranges):
        raise ValueError("unexpected audio RAM/register span")
    return {"artifact_hashes_verified": digests, "register_addresses": ADDRESSES,
            'audio_ip_version':evidence.get('audio',{}).get('ip_version','0x00010000'),
            "hardware_configuration_verified": True, "board_tested_by_this_check": False,
            "remaining_build_review": evidence.get("pending_review", [])}


def configure_overlay_clocks(clocks):
    """Call only immediately after fresh overlay download, before any DMA/MMIO use.

    HWH divisors assume Vivado's nominal PS PLL, while Linux keeps the boot PLL.
    Ask PYNQ to calculate dividers from the running PLL. Never change CPU/DDR PLLs.
    """
    before={"fclk0_mhz":float(clocks.fclk0_mhz),"fclk1_mhz":float(clocks.fclk1_mhz)}
    for index,frequency in ((0,50.),(1,100.)):
        clocks.set_pl_clk(index,clk_mhz=frequency)
    after={"fclk0_mhz":float(clocks.fclk0_mhz),"fclk1_mhz":float(clocks.fclk1_mhz)}
    if any(abs(after[key]-target)>.01 for key,target in (("fclk0_mhz",50.),("fclk1_mhz",100.))):
        raise RuntimeError("PL clock readback differs from timing contract")
    return {"after_overlay_download":before,"configured_and_read_back":after,"cpu_ddr_plls_changed":False}
