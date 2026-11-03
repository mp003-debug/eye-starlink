# Shared by fresh creation and synchronization of the real project.
if {[llength [get_bd_cells -quiet audio_aux_0]] == 0} {
    create_bd_cell -type module -reference audio_aux_axi audio_aux_0
    set_property CONFIG.NUM_MI 4 [get_bd_cells ps7_axi_periph]
    connect_bd_intf_net [get_bd_intf_pins ps7_axi_periph/M03_AXI] [get_bd_intf_pins audio_aux_0/s_axi]
    connect_bd_net [get_bd_pins ps7/FCLK_CLK0] [get_bd_pins audio_aux_0/aclk] [get_bd_pins ps7_axi_periph/M03_ACLK]
    connect_bd_net [get_bd_pins rst_ps7_50M/peripheral_aresetn] [get_bd_pins audio_aux_0/aresetn] [get_bd_pins ps7_axi_periph/M03_ARESETN]
    create_bd_cell -type ip -vlnv xilinx.com:ip:clk_wiz:6.0 audio_clock
    set_property -dict [list CONFIG.PRIM_IN_FREQ {50.000} CONFIG.CLKOUT1_REQUESTED_OUT_FREQ {10.000} CONFIG.RESET_TYPE {ACTIVE_LOW}] [get_bd_cells audio_clock]
    connect_bd_net [get_bd_pins ps7/FCLK_CLK0] [get_bd_pins audio_clock/clk_in1]
    connect_bd_net [get_bd_pins ps7/FCLK_RESET0_N] [get_bd_pins audio_clock/resetn]
    connect_bd_net [get_bd_pins audio_clock/locked] [get_bd_pins audio_aux_0/mclk_locked]
    foreach name {au_bclk au_lrclk au_sdata au_sda au_scl buttons} {
        make_bd_pins_external [get_bd_pins audio_aux_0/$name]
        set_property name $name [get_bd_ports ${name}_0]
    }
    make_bd_pins_external [get_bd_pins audio_clock/clk_out1]
    set_property name au_mclk [get_bd_ports clk_out1_0]
} else {update_module_reference [get_ips eye_tracker_bd_audio_aux_0_0]}
assign_bd_address
set seg [get_bd_addr_segs -of_objects [get_bd_addr_spaces ps7/Data] -filter {NAME =~ *audio_aux_0*}]
if {[llength $seg]!=1} {error "Ambiguous audio address"}
set_property offset 0x43C20000 $seg
set_property range 128K $seg
