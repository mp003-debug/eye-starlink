foreach name {audio_aux_axi.v} {
    if {[llength [get_files -quiet $name]] == 0} {add_files -norecurse [file join $repo fpga rtl $name]}
}
if {[llength [get_files -quiet audio_aux.xdc]] == 0} {add_files -fileset constrs_1 -norecurse [file join $repo fpga constraints audio_aux.xdc]}
# Sourced after open_project. Keep the existing real project in sync with sources.
if {[llength [get_files -quiet rgb565_to_rgb888.v]] == 0} {
    add_files -norecurse [file join $repo fpga rtl rgb565_to_rgb888.v]
}
if {[llength [get_files -quiet camera_i2c_pins.v]] == 0} {
    add_files -norecurse [file join $repo fpga rtl camera_i2c_pins.v]
}
if {[llength [get_files -quiet event_uart.xdc]] == 0} {add_files -fileset constrs_1 -norecurse [file join $repo fpga constraints event_uart.xdc]}
update_compile_order -fileset sources_1
open_bd_design [get_files eye_tracker_bd.bd]
update_module_reference [get_ips eye_tracker_bd_video_0_0]
update_module_reference [get_ips eye_tracker_bd_camera_diag_0_0]
set_property -dict [list CONFIG.C_GPIO_WIDTH 4 CONFIG.C_GPIO2_WIDTH 7] [get_bd_cells video_control]
set vdma [get_bd_cells vdma_0]
set_property CONFIG.c_m_axis_mm2s_tdata_width 16 $vdma
# PL supplies one SOF-aligned frame; complete on VSIZE, without requiring a later SOF.
set_property CONFIG.c_use_s2mm_fsync 0 $vdma
# Width customization can reset dependent line-buffer settings to 512.
set_property CONFIG.c_mm2s_linebuffer_depth 8192 $vdma
set_property CONFIG.c_s2mm_linebuffer_depth 8192 $vdma
source [file join $repo fpga scripts add_audio_aux.tcl]
source [file join $repo fpga scripts add_event_uart.tcl]
validate_bd_design
foreach {p wanted} {c_use_s2mm_fsync 0 c_use_mm2s_fsync 0 c_s_axis_s2mm_tdata_width 8 c_m_axis_mm2s_tdata_width 16 c_m_axi_mm2s_data_width 64 c_m_axi_s2mm_data_width 64 c_mm2s_linebuffer_depth 8192 c_s2mm_linebuffer_depth 8192} {
    if {[get_property CONFIG.$p $vdma] != $wanted} {error "Width mismatch: $p"}
}
save_bd_design
generate_target all [get_files eye_tracker_bd.bd]
make_wrapper -files [get_files eye_tracker_bd.bd] -top -force
write_bd_tcl -force [file join $repo fpga scripts exported_bd.tcl]
set f [open [file join $reports vdma_configuration.txt] w]
foreach p [lsort [list_property $vdma]] {if {[string match CONFIG.* $p]} {puts $f "$p=[get_property $p $vdma]"}}
close $f
reset_run synth_1
