"""Record a successful current Vivado build; never bless a stale or failed run."""
from datetime import date
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def digest(p):
    data=p.read_bytes()
    return {"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()}

def main():
    build=ROOT/"build/fpga"
    log=(build/"build.log").read_text(encoding="utf-8",errors="replace")
    if "EYE_TRACKER_BUILD_PASSED_NOT_BOARD_TESTED" not in log.splitlines():
        raise RuntimeError("no successful final export marker in current build log")
    if "CRITICAL WARNING:" in log or "ERROR:" in log:
        raise RuntimeError("current build log contains critical warnings/errors; resolve before recording")
    sources=list((ROOT/"fpga/rtl").glob("*.v"))+list((ROOT/"fpga/constraints").glob("*.xdc"))+list((ROOT/"fpga/scripts").glob("*.tcl"))
    newest=max(p.stat().st_mtime for p in sources if p.name != "exported_bd.tcl")
    for name in ("eye_tracker.bit","eye_tracker.hwh","reports/timing.rpt","reports/cdc_review.txt"):
        if (build/name).stat().st_mtime < newest:
            raise RuntimeError("build output predates source: "+name)
    lines=(build/"reports/timing.rpt").read_text().splitlines()
    index=next(i for i,line in enumerate(lines) if line.strip().startswith("WNS(ns)"))
    values=lines[index+2].split()
    wns,tns,whs,ths,wpws=[float(values[k]) for k in (0,1,4,5,8)]
    if min(wns,whs,wpws)<0 or tns or ths:raise RuntimeError("timing failed")
    util=(build/"reports/utilization.rpt").read_text()
    def used(label):
        return int(re.search(r"\|\s*"+re.escape(label)+r"\s*\|\s*(\d+)",util).group(1))
    cdc=(build/"reports/cdc.rpt").read_text()
    critical=sum(int(x) for x in re.findall(r"^CDC-\d+\s+Critical\s+(\d+)",cdc,re.M))
    review=(build/"reports/cdc_review.txt").read_text()
    if critical!=6 or "Custom RTL critical CDC: 0" not in review:raise RuntimeError("CDC review missing")
    uart_rx=[line for line in cdc.splitlines() if "event_uart_rx" in line and "INPUT_DOUBLE_REGS3" in line]
    if len(uart_rx)!=1 or "CDC-3" not in uart_rx[0] or "Info" not in uart_rx[0]:
        raise RuntimeError("UART RX synchronizer review missing")
    drc=(build/"reports/drc.rpt").read_text()
    severities={"errors":0,"warnings":0,"advisories":0}
    for severity,count in re.findall(r"\|\s*[\w-]+\s*\|\s*(Error|Warning|Advisory)\s*\|[^|]+\|\s*(\d+)\s*\|",drc):
        severities[{"Error":"errors","Warning":"warnings","Advisory":"advisories"}[severity]]+=int(count)
    if severities["errors"]:raise RuntimeError("DRC error")
    result={"date":date.today().isoformat(),"vivado":"2026.1","part":"xc7z020clg400-1",
        "stage":"upgrade_streaming_audio_uart_video","implementation_completed":True,
        "audio":{"ip_version":"0x00020000","stream_banks":2,"samples_per_bank":16384,"sample_rate":16000,"board_tested":False},
        "final_validation_export_exit_code":0,"final_validation_log":"build.log",
        "uart":{"baud":115200,"format":"8N1","base":"0x42C00000","rx":"Arduino D0/T14","tx":"Arduino D1/U12","rx_cdc":uart_rx[0].strip(),"board_tested":False},
        "formats":{"capture":"GRAY8","display":"RGB565_LE"},
        "diagnostic_version":"0x00010003","gpio_status_width":7,
        "timing":{"wns_ns":wns,"tns_ns":tns,"whs_ns":whs,"ths_ns":ths,"wpws_ns":wpws,
                  "applies_to":"existing constraints; HDMI external timing remains pending"},
        "resources":{"lut":used("Slice LUTs"),"ff":used("Slice Registers"),"bram_tiles":used("Block RAM Tile"),"dsp":used("DSPs")},
        "drc":severities,"cdc":{"raw_critical":critical,"reviewed_vdma_fifo36e1_critical":6,
                "custom_rtl_reported_critical":0,"review":"reports/cdc_review.txt"},
        "pending_review":["HDMI output external timing relationship pending; asynchronous UART TX has no external clock",
            "reset, synchronizer placement and mailbox methodology warnings","DRC warnings PDCN-1569 REQP-1839 RTSTAT-10"],
        "old_repository_runtime_dependency":False,"board_tested_by_build":False,"optics_validated":False,
        "artifacts":{name:digest(ROOT/name) for name in ("fpga/project/eye_tracker.xpr","build/fpga/eye_tracker.bit","build/fpga/eye_tracker.hwh")},
        "source_hashes":{p.relative_to(ROOT).as_posix():digest(p)["sha256"] for p in sorted(sources)}}
    (build/"result.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:result[k] for k in ("stage","timing","resources","drc","cdc")},indent=2))

if __name__=="__main__":main()
