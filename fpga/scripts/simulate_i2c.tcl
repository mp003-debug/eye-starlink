set repo [file normalize [file join [file dirname [info script]] ../..]]
open_project [file join $repo fpga project eye_tracker.xpr]
if {[llength [get_files -quiet camera_i2c_pins.v]] == 0} {add_files -norecurse [file join $repo fpga rtl camera_i2c_pins.v]}
if {[llength [get_files -quiet tb_camera_i2c.sv]] == 0} {add_files -fileset sim_1 -norecurse [file join $repo fpga sim tb_camera_i2c.sv]}
set_property top tb_camera_i2c [get_filesets sim_1]
set_property xsim.simulate.runtime 0ns [get_filesets sim_1]
update_compile_order -fileset sim_1
set marker [file join $repo fpga project eye_tracker.sim sim_1 behav xsim i2c_test_result.txt]
file delete -force $marker
launch_simulation -simset sim_1 -mode behavioral
run all
close_sim
if {![file exists $marker]} {error "I2C simulation did not reach PASS"}
set f [open $marker r];set result [string trim [read $f]];close $f
if {$result ne "PASS"} {error "I2C simulation failed"}
set f [open [file join $repo build fpga i2c_simulation_result.json] w]
puts $f {{"passed":true,"open_drain_release":true,"external_pull_low_and_stretch":true,"reset_release":true,"board_tested":false}}
close $f
close_project
exit 0
