# 3.3V UART for the independent BearPi link. No PS console or USB changes.
if {[llength [get_bd_cells -quiet event_uart_0]] == 0} {
    create_bd_cell -type ip -vlnv xilinx.com:ip:axi_uartlite:2.0 event_uart_0
    set_property CONFIG.NUM_MI 5 [get_bd_cells ps7_axi_periph]
    connect_bd_intf_net [get_bd_intf_pins ps7_axi_periph/M04_AXI] [get_bd_intf_pins event_uart_0/S_AXI]
    connect_bd_net [get_bd_pins ps7/FCLK_CLK0] [get_bd_pins event_uart_0/s_axi_aclk] [get_bd_pins ps7_axi_periph/M04_ACLK]
    connect_bd_net [get_bd_pins rst_ps7_50M/peripheral_aresetn] [get_bd_pins event_uart_0/s_axi_aresetn] [get_bd_pins ps7_axi_periph/M04_ARESETN]
    foreach direction {rx tx} {
        make_bd_pins_external [get_bd_pins event_uart_0/$direction]
        set_property name event_uart_$direction [get_bd_ports ${direction}_0]
    }
}
set_property -dict [list CONFIG.C_BAUDRATE {115200} CONFIG.C_DATA_BITS {8} CONFIG.PARITY {No_Parity}] [get_bd_cells event_uart_0]
assign_bd_address
set seg [get_bd_addr_segs -of_objects [get_bd_addr_spaces ps7/Data] -filter {NAME =~ *event_uart_0*}]
if {[llength $seg] != 1} {error "Ambiguous UART address"}
set_property offset 0x42C00000 $seg
set_property range 64K $seg
