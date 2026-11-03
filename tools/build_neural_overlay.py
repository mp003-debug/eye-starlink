"""Generate/build an isolated full overlay. No board or baseline project writes."""
from pathlib import Path
import subprocess,hashlib,json
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/neural_upgrade_20261103/fpga'
VIVADO=__import__('os').environ.get('VIVADO_BIN','vivado')

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    create=(ROOT/'fpga/scripts/create_project.tcl').read_text()
    create=create.replace('set repo [file normalize [file join [file dirname [info script]] ../..]]',f'set repo {{{ROOT.as_posix()}}}')
    create=create.replace('set build [file join $repo fpga project]',f'set build {{{(OUT/"project").as_posix()}}}')
    create=create.replace('camera_i2c_pins audio_aux_axi}', 'camera_i2c_pins audio_aux_axi neural_mac_axi}')
    create=create.replace('set reports [file join $repo build fpga reports]',f'set reports {{{(OUT/"reports").as_posix()}}}')
    create=create.replace('[file join $repo fpga scripts exported_bd.tcl]',f'{{{(OUT/"exported_bd.tcl").as_posix()}}}')
    attach='''
create_bd_cell -type module -reference neural_mac_axi neural_mac_0
set_property CONFIG.NUM_MI 6 [get_bd_cells ps7_axi_periph]
connect_bd_intf_net [get_bd_intf_pins ps7_axi_periph/M05_AXI] [get_bd_intf_pins neural_mac_0/s_axi]
connect_bd_net [get_bd_pins ps7/FCLK_CLK0] [get_bd_pins neural_mac_0/aclk] [get_bd_pins ps7_axi_periph/M05_ACLK]
connect_bd_net [get_bd_pins rst_ps7_50M/peripheral_aresetn] [get_bd_pins neural_mac_0/aresetn] [get_bd_pins ps7_axi_periph/M05_ARESETN]
assign_bd_address
set nnseg [get_bd_addr_segs -of_objects [get_bd_addr_spaces ps7/Data] -filter {NAME =~ *neural_mac_0*}]
if {[llength $nnseg]!=1} {error "Missing neural address segment"}
set_property offset 0x43C40000 $nnseg
set_property range 256K $nnseg
'''
    create=create.replace('validate_bd_design',attach+'\nvalidate_bd_design')
    export=(ROOT/'fpga/scripts/export_bitstream.tcl').read_text()
    export=export.replace('set repo [file normalize [file join [file dirname [info script]] ../..]]',f'set repo {{{ROOT.as_posix()}}}')
    export=export.replace('[file join $repo build fpga reports]',f'{{{(OUT/"reports").as_posix()}}}')
    export=export.replace('[file join $repo fpga project eye_tracker.xpr]',f'{{{(OUT/"project/eye_tracker.xpr").as_posix()}}}')
    export=export.replace('[file join $repo build fpga eye_tracker.bit]',f'{{{(OUT/"eye_tracker_neural.bit").as_posix()}}}')
    export=export.replace('[file join $repo build fpga eye_tracker.hwh]',f'{{{(OUT/"eye_tracker_neural.hwh").as_posix()}}}')
    export=export.replace('[file join $repo fpga project eye_tracker.gen sources_1 bd eye_tracker_bd hw_handoff eye_tracker_bd.hwh]',f'{{{(OUT/"project/eye_tracker.gen/sources_1/bd/eye_tracker_bd/hw_handoff/eye_tracker_bd.hwh").as_posix()}}}')
    export=export.replace('report_utilization -file', 'report_utilization -hierarchical -file [file join $reports utilization_hierarchical.rpt]\nreport_utilization -file')
    build=f'''open_project {{{(OUT/'project/eye_tracker.xpr').as_posix()}}}
set_param general.maxThreads 4
launch_runs synth_1 -jobs 4
wait_on_run synth_1
if {{[get_property PROGRESS [get_runs synth_1]] ne "100%"}} {{error "synthesis incomplete"}}
launch_runs impl_1 -to_step route_design -jobs 4
wait_on_run impl_1
if {{[get_property PROGRESS [get_runs impl_1]] ne "100%"}} {{error "implementation incomplete"}}
close_project
source {{{(OUT/'export.tcl').as_posix()}}}
'''
    for name,body in [('create',create),('build',build),('export',export)]:
        (OUT/(name+'.tcl')).write_text(body,encoding='utf-8')
    provenance={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'fpga/rtl/neural_mac_axi.v',ROOT/'fpga/scripts/create_project.tcl',ROOT/'fpga/scripts/export_bitstream.tcl']}
    (OUT/'source_hashes.json').write_text(json.dumps(provenance,indent=2))
    for name in ('create','build'):
        with (OUT/(name+'.stdout.log')).open('w') as f:
            code=subprocess.call([VIVADO,'-mode','batch','-source',str(OUT/(name+'.tcl')),'-log',str(OUT/(name+'.log')),'-journal',str(OUT/(name+'.jou'))],cwd=OUT,stdout=f,stderr=subprocess.STDOUT)
        if code:raise RuntimeError(name+' failed; inspect isolated logs')
    print('NEURAL_FULL_OVERLAY_BUILT_NOT_BOARD_TESTED')

if __name__=='__main__':main()
