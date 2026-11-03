set repo [file normalize [file join [file dirname [info script]] ../..]]
open_project [file join $repo fpga project eye_tracker.xpr]
if {[llength [get_files -quiet rgb565_to_rgb888.v]] == 0} {add_files -norecurse [file join $repo fpga rtl rgb565_to_rgb888.v]}
if {[llength [get_files -quiet tb_display.sv]] == 0} {add_files -fileset sim_1 -norecurse [file join $repo fpga sim tb_display.sv]}
set_property top tb_display [get_filesets sim_1]
set_property xsim.simulate.runtime 0ns [get_filesets sim_1]
update_compile_order -fileset sim_1
set marker [file join $repo fpga project eye_tracker.sim sim_1 behav xsim display_test_result.txt]
# Exact generated result file only; do not accept a stale PASS from an older run.
file delete -force $marker
launch_simulation -simset sim_1 -mode behavioral
run all
close_sim
if {![file exists $marker]} {error "Display simulation did not reach PASS"}
set f [open $marker r];set result [string trim [read $f]];close $f
if {$result ne "PASS"} {error "Display simulation failed"}
set f [open [file join $repo build fpga simulation_result.json] w]
puts $f {{"passed":true,"rgb565_codes":65536,"framing_faults_checked":true,"board_tested":false}}
close $f
close_project
exit 0
