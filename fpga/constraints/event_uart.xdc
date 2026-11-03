# PYNQ-Z2 Arduino D0=T14 (RX), D1=U12 (TX), both 3.3V.
# Xilinx/PYNQ boards/Pynq-Z2/base/vivado/constraints/base.xdc.
set_property -dict {PACKAGE_PIN T14 IOSTANDARD LVCMOS33 PULLUP true} [get_ports event_uart_rx]
set_property -dict {PACKAGE_PIN U12 IOSTANDARD LVCMOS33 SLEW SLOW DRIVE 8} [get_ports event_uart_tx]
# RX enters the AMD IP's xpm_cdc_single; its own XDC constrains the synchronizer.
# Asynchronous UART TX has no external clock to specify output delay against.
