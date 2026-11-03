# Recheck/export an existing routed run; never accepts stale source/constraint runs.
set repo [file normalize [file join [file dirname [info script]] ../..]]
set reports [file join $repo build fpga reports]
open_project [file join $repo fpga project eye_tracker.xpr]
if {[get_property NEEDS_REFRESH [get_runs impl_1]]} {error "Routed run is stale; run build_project.tcl"}
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {error "Route incomplete"}
set vdma_ip [get_ips eye_tracker_bd_vdma_0_0]
foreach {p wanted} {c_use_s2mm_fsync 0 c_use_mm2s_fsync 0 c_m_axis_mm2s_tdata_width 16 c_s_axis_s2mm_tdata_width 8 c_mm2s_linebuffer_depth 8192 c_s2mm_linebuffer_depth 8192} {
    if {[get_property CONFIG.$p $vdma_ip] != $wanted} {error "Export configuration mismatch: $p"}
}
open_run impl_1
set audio_tx [get_cells -hier -filter {NAME =~ */audio_aux_0/*/au_sdata_reg}]
set audio_first [get_cells -hier -regexp {.*audio_aux_0.*/(bclk_sync_reg|lr_sync_reg|sda_sync_reg|scl_sync_reg)\[0\]$|.*audio_aux_0.*/btn_meta_reg\[[0-3]\]$}]
if {[llength $audio_tx]!=1 || [llength $audio_first]!=8} {error "Audio constraint endpoints missing"}
set audio_path [get_timing_paths -from $audio_tx -to [get_ports au_sdata] -delay_type max -max_paths 1]
if {[llength $audio_path]!=1 || [get_property SLACK $audio_path]<0} {error "I2S output delay failed"}
report_timing -from $audio_tx -to [get_ports au_sdata] -max_paths 1 -file [file join $reports audio_output.rpt]
report_methodology -file [file join $reports methodology.rpt]
check_timing -verbose -file [file join $reports check_timing.rpt]
report_timing_summary -file [file join $reports timing.rpt] -report_unconstrained
report_utilization -file [file join $reports utilization.rpt]
report_cdc -details -file [file join $reports cdc.rpt]
report_drc -file [file join $reports drc.rpt]
report_bus_skew -file [file join $reports bus_skew.rpt]
foreach type {max min} {
    set paths [get_timing_paths -delay_type $type -max_paths 1]
    if {[llength $paths] == 0 || [get_property SLACK $paths] < 0} {error "Timing failed: $type"}
}
if {[llength [get_drc_violations -filter {SEVERITY == Error}]] > 0} {error "DRC errors"}
set f [open [file join $reports cdc.rpt] r];set cdc [read $f];close $f
source [file join $repo fpga scripts review_ddr_cdc.tcl]
review_ddr_cdc $cdc $reports
set f [open [file join $reports bus_skew.rpt] r];set skew [read $f];close $f
if {[string match {*Slack (VIOLATED)*} $skew]} {error "Bus skew failed"}
write_bitstream -force [file join $repo build fpga eye_tracker.bit]
set hwh [file join $repo fpga project eye_tracker.gen sources_1 bd eye_tracker_bd hw_handoff eye_tracker_bd.hwh]
file copy -force $hwh [file join $repo build fpga eye_tracker.hwh]
puts "EYE_TRACKER_BUILD_PASSED_NOT_BOARD_TESTED"
close_project
exit 0
