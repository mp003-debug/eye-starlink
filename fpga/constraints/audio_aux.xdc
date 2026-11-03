# PYNQ-Z2 schematic pages 3/7/11. Codec ADR0/1 retain onboard pullups (0x3B).
set_property -dict {PACKAGE_PIN U5 IOSTANDARD LVCMOS33} [get_ports au_mclk]
set_property -dict {PACKAGE_PIN R18 IOSTANDARD LVCMOS33} [get_ports au_bclk]
set_property -dict {PACKAGE_PIN T17 IOSTANDARD LVCMOS33} [get_ports au_lrclk]
set_property -dict {PACKAGE_PIN G18 IOSTANDARD LVCMOS33 SLEW FAST DRIVE 8} [get_ports au_sdata]
set_property -dict {PACKAGE_PIN T9 IOSTANDARD LVCMOS33} [get_ports au_sda]
set_property -dict {PACKAGE_PIN U9 IOSTANDARD LVCMOS33} [get_ports au_scl]
set_property -dict {PACKAGE_PIN D19 IOSTANDARD LVCMOS33} [get_ports {buttons[0]}]
set_property -dict {PACKAGE_PIN D20 IOSTANDARD LVCMOS33} [get_ports {buttons[1]}]
set_property -dict {PACKAGE_PIN L20 IOSTANDARD LVCMOS33} [get_ports {buttons[2]}]
set_property -dict {PACKAGE_PIN L19 IOSTANDARD LVCMOS33} [get_ports {buttons[3]}]
# Asynchronous low-speed inputs go only through their first synchronizer flop.
set audio_first [get_cells -hier -regexp {.*audio_aux_0.*/(bclk_sync_reg|lr_sync_reg|sda_sync_reg|scl_sync_reg)\[0\]$|.*audio_aux_0.*/btn_meta_reg\[[0-3]\]$}]
set_false_path -from [get_ports {au_bclk au_lrclk au_sda au_scl buttons[*]}] -to [get_pins -of_objects $audio_first -filter {REF_PIN_NAME == D}]
set_false_path -to [get_ports {au_sda au_scl}]
# Oversampled I2S: 3-4 50MHz cycles detect the external falling edge (<=80ns),
# then <=25ns registered-output path; 48k*64 BCLK half-period=162.76ns.
# ADAU1761 input setup/hold=5ns. Do not declare the entire I2S path false.
set audio_tx [get_cells -hier -filter {NAME =~ */audio_aux_0/*/au_sdata_reg}]
set_max_delay 25 -datapath_only -from $audio_tx -to [get_ports au_sdata]
set_min_delay 0 -from $audio_tx -to [get_ports au_sdata]
