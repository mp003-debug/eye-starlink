set repo [file normalize [file join [file dirname [info script]] ../..]]
set reports [file join $repo build fpga reports]
file mkdir $reports
set_param general.maxThreads 4
open_project [file join $repo fpga project eye_tracker.xpr]
source [file join $repo fpga scripts sync_project.tcl]
launch_runs synth_1 -jobs 4
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {error "Synthesis failed"}
launch_runs impl_1 -to_step route_design -jobs 4
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {error "Implementation failed"}
close_project
source [file join $repo fpga scripts export_bitstream.tcl]
