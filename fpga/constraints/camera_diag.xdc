# Diagnostic overlay: existing DVP wiring only, LVCMOS 3.3 V.

set_property -dict {PACKAGE_PIN Y18 IOSTANDARD LVCMOS33} [get_ports {cam_data[0]}]
set_property -dict {PACKAGE_PIN Y16 IOSTANDARD LVCMOS33} [get_ports {cam_data[1]}]
set_property -dict {PACKAGE_PIN U19 IOSTANDARD LVCMOS33} [get_ports {cam_data[2]}]
set_property -dict {PACKAGE_PIN W18 IOSTANDARD LVCMOS33} [get_ports {cam_data[3]}]
set_property -dict {PACKAGE_PIN W14 IOSTANDARD LVCMOS33} [get_ports {cam_data[4]}]
set_property -dict {PACKAGE_PIN T11 IOSTANDARD LVCMOS33} [get_ports {cam_data[5]}]
set_property -dict {PACKAGE_PIN V16 IOSTANDARD LVCMOS33} [get_ports {cam_data[6]}]
set_property -dict {PACKAGE_PIN V12 IOSTANDARD LVCMOS33} [get_ports {cam_data[7]}]

set_property -dict {PACKAGE_PIN U18 IOSTANDARD LVCMOS33} [get_ports cam_pclk]
set_property -dict {PACKAGE_PIN W19 IOSTANDARD LVCMOS33} [get_ports cam_frame_valid]
set_property -dict {PACKAGE_PIN Y17 IOSTANDARD LVCMOS33} [get_ports cam_line_valid]

set_property -dict {PACKAGE_PIN Y19 IOSTANDARD LVCMOS33} [get_ports cam_sda]
set_property -dict {PACKAGE_PIN Y14 IOSTANDARD LVCMOS33} [get_ports cam_scl]

# Reserved final control pins on the three previously-unused Pmod-B signals.

# The module contains a 24 MHz oscillator. DOUT changes near the falling PCLK
# edge and is captured by FPGA IOB registers on the rising edge.
create_clock -period 41.667 -waveform {0.000 20.833} -name cam_pclk_clk [get_ports cam_pclk]

set_input_delay -clock cam_pclk_clk -clock_fall -max 3.000 \
    [get_ports {cam_data[*]}]
set_input_delay -clock cam_pclk_clk -clock_fall -min -3.000 \
    [get_ports {cam_data[*]}]

set_input_delay -clock cam_pclk_clk -clock_fall -max 9.000 \
    [get_ports {cam_frame_valid cam_line_valid}]
set_input_delay -clock cam_pclk_clk -clock_fall -min 5.000 \
    [get_ports {cam_frame_valid cam_line_valid}]

# I2C and the three mode-control outputs are static/low-speed interfaces. Their
# functional timing is verified by protocol logic rather than the DVP pixel clock.


set_property CFGBVS VCCO [current_design]
set_property CONFIG_VOLTAGE 3.3 [current_design]
set_property -dict {PACKAGE_PIN L16 IOSTANDARD TMDS_33} [get_ports hdmi_out_clk_p]
set_property -dict {PACKAGE_PIN L17 IOSTANDARD TMDS_33} [get_ports hdmi_out_clk_n]
set_property -dict {PACKAGE_PIN K17 IOSTANDARD TMDS_33} [get_ports {hdmi_out_data_p[0]}]
set_property -dict {PACKAGE_PIN K18 IOSTANDARD TMDS_33} [get_ports {hdmi_out_data_n[0]}]
set_property -dict {PACKAGE_PIN K19 IOSTANDARD TMDS_33} [get_ports {hdmi_out_data_p[1]}]
set_property -dict {PACKAGE_PIN J19 IOSTANDARD TMDS_33} [get_ports {hdmi_out_data_n[1]}]
set_property -dict {PACKAGE_PIN J18 IOSTANDARD TMDS_33} [get_ports {hdmi_out_data_p[2]}]
set_property -dict {PACKAGE_PIN H18 IOSTANDARD TMDS_33} [get_ports {hdmi_out_data_n[2]}]
set_property -dict {PACKAGE_PIN M20 IOSTANDARD LVCMOS33} [get_ports sw0]
set_property -dict {PACKAGE_PIN R14 IOSTANDARD LVCMOS33} [get_ports {led[0]}]
set_property -dict {PACKAGE_PIN P14 IOSTANDARD LVCMOS33} [get_ports {led[1]}]
set_property -dict {PACKAGE_PIN N16 IOSTANDARD LVCMOS33} [get_ports {led[2]}]
set_property -dict {PACKAGE_PIN M14 IOSTANDARD LVCMOS33} [get_ports {led[3]}]
set_false_path -from [get_ports sw0]
# No false paths on DVP data/FV/LV. CDC exceptions are in diag_cdc.xdc.

# Human-visible LEDs have no external sampling clock or setup/hold requirement.
# This exception is intentionally restricted to LEDs; HDMI remains under review.
set_false_path -to [get_ports {led[*]}]

# Low-speed I2C output timing is bounded by software delays; input exceptions target first synchronizer D only.
set_false_path -to [get_ports {cam_sda cam_scl}]
