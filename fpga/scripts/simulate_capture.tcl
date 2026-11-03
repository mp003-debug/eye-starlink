set repo [file normalize [file join [file dirname [info script]] ../..]]
open_project [file join $repo fpga project eye_tracker.xpr]
if {[llength [get_files -quiet tb_capture_queue.sv]] == 0} {add_files -fileset sim_1 -norecurse [file join $repo fpga sim tb_capture_queue.sv]}
set_property top tb_capture_queue [get_filesets sim_1]
set_property xsim.simulate.runtime 0ns [get_filesets sim_1]
update_compile_order -fileset sim_1
set marker [file join $repo fpga project eye_tracker.sim sim_1 behav xsim capture_test_result.txt]
file delete -force $marker
launch_simulation -simset sim_1 -mode behavioral
run all
close_sim
if {![file exists $marker]} {error "Capture simulation did not reach PASS"}
set f [open $marker r];set result [string trim [read $f]];close $f
if {$result ne "PASS"} {error "Capture simulation failed"}
set f [open [file join $repo build fpga capture_simulation_result.json] w]
puts $f {{"passed":true,"frame_bounded_rearm":true,"stalled_payload_stability":true,"overflow_and_partial_frame_rejection":true,"board_tested":false}}
close $f
close_project
exit 0
