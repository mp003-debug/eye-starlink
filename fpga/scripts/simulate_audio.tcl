set repo [file normalize [file join [file dirname [info script]] ../..]]
open_project [file join $repo fpga project eye_tracker.xpr]
foreach name {audio_aux_axi.v} {
 if {[llength [get_files -quiet $name]] == 0} {add_files -norecurse [file join $repo fpga rtl $name]}
}
if {[llength [get_files -quiet tb_audio_aux.sv]] == 0} {add_files -fileset sim_1 -norecurse [file join $repo fpga sim tb_audio_aux.sv]}
set_property top tb_audio_aux [get_filesets sim_1]
set_property xsim.simulate.runtime 0ns [get_filesets sim_1]
update_compile_order -fileset sim_1
set marker [file join $repo fpga project eye_tracker.sim sim_1 behav xsim audio_test_result.txt]
if {[file exists $marker]} {file delete $marker}
launch_simulation -simset sim_1 -mode behavioral
run all
close_sim
if {![file exists $marker]} {error "Audio simulation did not reach PASS"}
set f [open $marker r];set result [string trim [read $f]];close $f
if {$result ne "PASS"} {error "Audio simulation failed"}
set f [open [file join $repo build fpga audio_simulation_result.json] w]
puts $f {{"passed":true,"pcm_signed_order_and_three_repeats":true,"axi_independent_channels_and_backpressure":true,"no_live_memory_mutation":true,"stop_and_missing_clock_silence":true,"i2c_open_drain":true,"button_sync":true,"board_tested":false}}
close $f
close_project
exit 0
