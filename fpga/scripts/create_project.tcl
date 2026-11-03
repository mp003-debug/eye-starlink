# Run from Vivado 2026.1; no board access, no ps7_init or bitstream download.
set repo [file normalize [file join [file dirname [info script]] ../..]]
set build [file join $repo fpga project]
set variant eye_tracker
if {[file exists [file join $build ${variant}.xpr]]} {error "Project already exists; open it or choose a fresh build directory"}
set_param general.maxThreads 4
create_project $variant $build -part xc7z020clg400-1
set_property target_language Verilog [current_project]
set_property ip_cache_permissions {disable} [current_project]
foreach name {mt9v034_dvp_frontend camera_diag_axi dvp_axis_queue axis_video_sink camera_ddr_video rgb565_to_rgb888 camera_i2c_pins audio_aux_axi} {
    add_files -norecurse [file join $repo fpga rtl $name.v]
}
foreach name {clk_gen video_timing hdmi_tx tmds_encoder serializer_10to1} {
    add_files -norecurse [file join $repo fpga rtl $name.v]
}
add_files -fileset constrs_1 -norecurse [file join $repo fpga constraints camera_diag.xdc]
add_files -fileset constrs_1 -norecurse [file join $repo fpga constraints audio_aux.xdc]
add_files -fileset constrs_1 -norecurse [file join $repo fpga constraints ddr_cdc.xdc]
set_property PROCESSING_ORDER LATE [get_files ddr_cdc.xdc]
set_property USED_IN_SYNTHESIS false [get_files ddr_cdc.xdc]
if {[llength [get_files -quiet event_uart.xdc]] == 0} {add_files -fileset constrs_1 -norecurse [file join $repo fpga constraints event_uart.xdc]}
update_compile_order -fileset sources_1
create_bd_design eye_tracker_bd
set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps7]
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 -config {make_external "FIXED_IO, DDR" apply_board_preset "0" Master "Disable" Slave "Disable"} $ps
# PL overlay only. Do not run generated ps7_init; Linux owns DDR/MIO setup.
set_property -dict [list CONFIG.PCW_EN_CLK0_PORT {1} CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {50} CONFIG.PCW_EN_RST0_PORT {1} CONFIG.PCW_USE_M_AXI_GP0 {1} CONFIG.PCW_USE_S_AXI_HP0 {1} CONFIG.PCW_EN_CLK1_PORT {1} CONFIG.PCW_FPGA1_PERIPHERAL_FREQMHZ {100} CONFIG.PCW_S_AXI_HP0_DATA_WIDTH {64}] $ps
create_bd_cell -type module -reference camera_ddr_video video_0
# ctrl_clk deliberately avoids the generic 'aclk' inference heuristic.
# AXIS clock associations come from explicit HDL attributes.
create_bd_cell -type module -reference camera_diag_axi camera_diag_0
set vdma [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_vdma:6.3 vdma_0]
set_property -dict [list CONFIG.c_num_fstores {3} CONFIG.c_include_sg {0} CONFIG.c_include_mm2s {1} CONFIG.c_include_s2mm {1} CONFIG.c_m_axi_mm2s_data_width {64} CONFIG.c_m_axi_s2mm_data_width {64} CONFIG.c_m_axis_mm2s_tdata_width {16} CONFIG.c_mm2s_linebuffer_depth {8192} CONFIG.c_s2mm_linebuffer_depth {8192} CONFIG.c_mm2s_genlock_mode {3} CONFIG.c_s2mm_genlock_mode {2} CONFIG.c_include_internal_genlock {1} CONFIG.c_use_mm2s_fsync {0} CONFIG.c_use_s2mm_fsync {0} CONFIG.c_include_mm2s_dre {0} CONFIG.c_include_s2mm_dre {0} CONFIG.c_mm2s_max_burst_length {16} CONFIG.c_s2mm_max_burst_length {16}] $vdma
# Reassert dependent values after customization to avoid implicit default resets.
set_property CONFIG.c_mm2s_linebuffer_depth 8192 $vdma
set_property CONFIG.c_s2mm_linebuffer_depth 8192 $vdma
set gpio [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 video_control]
set_property -dict [list CONFIG.C_IS_DUAL {1} CONFIG.C_GPIO_WIDTH {4} CONFIG.C_ALL_OUTPUTS {1} CONFIG.C_GPIO2_WIDTH {7} CONFIG.C_ALL_INPUTS_2 {1} CONFIG.C_DOUT_DEFAULT {0x00000000}] $gpio
# Match the single- and three-slave probes verified on the board on 2026-09-25.
apply_bd_automation -rule xilinx.com:bd_rule:axi4 -config {Master "/ps7/M_AXI_GP0" Clk_master "/ps7/FCLK_CLK0 (50 MHz)" Clk_slave "/ps7/FCLK_CLK0 (50 MHz)" Clk_xbar "/ps7/FCLK_CLK0 (50 MHz)" intc_ip "New AXI Interconnect" master_apm "0"} [get_bd_intf_pins camera_diag_0/s_axi]
set ctrl [get_bd_cells ps7_axi_periph]
set_property CONFIG.NUM_MI 3 $ctrl
set mem [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 memory_bus]
set_property -dict [list CONFIG.NUM_SI {2} CONFIG.NUM_MI {1}] $mem
set one [create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 one]
set_property CONFIG.CONST_VAL 1 $one
set zero [create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 zero]
set_property CONFIG.CONST_VAL 0 $zero
foreach {name clk} {rst_ps7_50M ps7/FCLK_CLK0 reset100 ps7/FCLK_CLK1} {
    if {$name eq "reset100"} {
        create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 $name
        connect_bd_net [get_bd_pins $clk] [get_bd_pins $name/slowest_sync_clk]
        connect_bd_net [get_bd_pins ps7/FCLK_RESET0_N] [get_bd_pins $name/ext_reset_in]
    }
    # C_EXT_RESET_HIGH is inferred from FCLK_RESET0_N and read-only after connection.
    set_property CONFIG.C_AUX_RESET_HIGH 0 [get_bd_cells $name]
    # aux_reset_in is ACTIVE LOW: tying it to zero held the old design in reset.
    connect_bd_net [get_bd_pins one/dout] [get_bd_pins $name/dcm_locked] [get_bd_pins $name/aux_reset_in]
    connect_bd_net [get_bd_pins zero/dout] [get_bd_pins $name/mb_debug_sys_rst]
}
foreach pin {video_0/ctrl_clk vdma_0/s_axi_lite_aclk video_control/s_axi_aclk ps7_axi_periph/M01_ACLK ps7_axi_periph/M02_ACLK} {
    connect_bd_net [get_bd_pins ps7/FCLK_CLK0] [get_bd_pins $pin]
}
foreach pin {ps7/S_AXI_HP0_ACLK vdma_0/m_axi_mm2s_aclk vdma_0/m_axi_s2mm_aclk memory_bus/ACLK memory_bus/S00_ACLK memory_bus/S01_ACLK memory_bus/M00_ACLK} {
    connect_bd_net [get_bd_pins ps7/FCLK_CLK1] [get_bd_pins $pin]
}
foreach pin {video_0/aresetn video_control/s_axi_aresetn vdma_0/axi_resetn ps7_axi_periph/M01_ARESETN ps7_axi_periph/M02_ARESETN} {
    connect_bd_net [get_bd_pins rst_ps7_50M/peripheral_aresetn] [get_bd_pins $pin]
}
foreach pin {memory_bus/ARESETN memory_bus/S00_ARESETN memory_bus/S01_ARESETN memory_bus/M00_ARESETN} {
    connect_bd_net [get_bd_pins reset100/peripheral_aresetn] [get_bd_pins $pin]
}
foreach {a b} {ps7_axi_periph/M01_AXI vdma_0/S_AXI_LITE ps7_axi_periph/M02_AXI video_control/S_AXI vdma_0/M_AXI_MM2S memory_bus/S00_AXI vdma_0/M_AXI_S2MM memory_bus/S01_AXI memory_bus/M00_AXI ps7/S_AXI_HP0 video_0/m_axis vdma_0/S_AXIS_S2MM vdma_0/M_AXIS_MM2S video_0/s_axis} {
    connect_bd_intf_net [get_bd_intf_pins $a] [get_bd_intf_pins $b]
}
connect_bd_net [get_bd_pins video_0/capture_clk] [get_bd_pins vdma_0/s_axis_s2mm_aclk] [get_bd_pins camera_diag_0/pclk]
connect_bd_net [get_bd_pins video_0/capture_resetn] [get_bd_pins camera_diag_0/cam_rst_n]
connect_bd_net [get_bd_pins video_0/display_clk] [get_bd_pins vdma_0/m_axis_mm2s_aclk]
connect_bd_net [get_bd_pins video_control/gpio_io_o] [get_bd_pins video_0/control]
connect_bd_net [get_bd_pins video_0/status] [get_bd_pins video_control/gpio2_io_i]
foreach name {frame_count frame_period frame_pixels frame_lines line_pixels bad_lines bad_frames} {
    connect_bd_net [get_bd_pins video_0/$name] [get_bd_pins camera_diag_0/$name]
}
foreach name {cam_data cam_pclk cam_frame_valid cam_line_valid cam_sda cam_scl sw0 led hdmi_out_clk_p hdmi_out_clk_n hdmi_out_data_p hdmi_out_data_n} {
    make_bd_pins_external [get_bd_pins video_0/$name]
    set_property name $name [get_bd_ports ${name}_0]
}
set_property CONFIG.FREQ_HZ 24000000 [get_bd_ports cam_pclk]
assign_bd_address
foreach {pattern base size} {*camera_diag_0* 0x43C00000 4K *vdma_0* 0x43000000 64K *video_control* 0x41200000 64K} {
    set seg [get_bd_addr_segs -of_objects [get_bd_addr_spaces ps7/Data] -filter "NAME =~ $pattern"]
    if {[llength $seg]!=1} {error "Ambiguous address segment: $pattern / $seg"}
    set_property offset $base $seg
    set_property range $size $seg
}
source [file join $repo fpga scripts add_audio_aux.tcl]
source [file join $repo fpga scripts add_event_uart.tcl]
validate_bd_design
foreach {p value} {c_num_fstores 3 c_mm2s_genlock_mode 3 c_s2mm_genlock_mode 2 c_include_internal_genlock 1 c_prmry_is_aclk_async 1 c_s_axis_s2mm_tdata_width 8 c_m_axis_mm2s_tdata_width 16 c_mm2s_linebuffer_depth 8192 c_s2mm_linebuffer_depth 8192 c_use_s2mm_fsync 0 c_use_mm2s_fsync 0} {
    if {[get_property CONFIG.$p $vdma] != $value} {error "Incorrect propagated VDMA property $p"}
}
foreach name {rst_ps7_50M reset100} {
    if {[get_property CONFIG.C_EXT_RESET_HIGH [get_bd_cells $name]] != 0} {error "Reset polarity mismatch: $name"}
    if {[get_property CONFIG.C_AUX_RESET_HIGH [get_bd_cells $name]] != 0} {error "Aux reset polarity mismatch: $name"}
    foreach pin {aux_reset_in dcm_locked} {
        if {[get_bd_nets -of_objects [get_bd_pins $name/$pin]] ne [get_bd_nets -of_objects [get_bd_pins one/dout]]} {error "Reset tie-off mismatch: $name/$pin must be 1"}
    }
    if {[get_bd_nets -of_objects [get_bd_pins $name/mb_debug_sys_rst]] ne [get_bd_nets -of_objects [get_bd_pins zero/dout]]} {error "Debug reset must be 0: $name"}
}
save_bd_design
set reports [file join $repo build fpga reports]
file mkdir $reports
set f [open [file join $reports vdma_configuration.txt] w]
foreach p [lsort [list_property $vdma]] {if {[string match CONFIG.* $p]} {puts $f "$p=[get_property $p $vdma]"}}
close $f
set_property synth_checkpoint_mode None [get_files eye_tracker_bd.bd]
generate_target all [get_files eye_tracker_bd.bd]
add_files -norecurse [make_wrapper -files [get_files eye_tracker_bd.bd] -top]
set_property top eye_tracker_bd_wrapper [current_fileset]
update_compile_order -fileset sources_1

write_bd_tcl -force [file join $repo fpga scripts exported_bd.tcl]
puts "EYE_TRACKER_PROJECT_CREATED: [file join $build ${variant}.xpr]"
close_project
exit 0
