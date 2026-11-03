# Custom two-flop controls and diagnostic held mailbox. VDMA supplies its own XDC.
set first_sync [get_cells -hier -regexp {.*(request_sync|ack_sync|switch_sync|capture_enable_sync|display_enable_sync|overflow_sync|underflow_sync|format_sync|display_lock_sync|rearm_sync|i2c_sda_sync|i2c_scl_sync)_reg\[0\]}]
set_false_path -to [get_pins -of_objects $first_sync -filter {REF_PIN_NAME == D}]
set mailbox_src [get_cells -hier -regexp {.*camera_mailbox_reg\[[0-9]+\]}]
set mailbox_dst [get_cells -hier -regexp {.*snapshot_reg\[[0-9]+\]}]
set_max_delay -datapath_only 20.000 -from $mailbox_src -to $mailbox_dst
set_bus_skew 20.000 -from $mailbox_src -to $mailbox_dst
set reset_regs [get_cells -hier -regexp {.*(cam_reset_sync|pix_reset_sync)_reg\[[01]\]}]
set_false_path -to [get_pins -of_objects $reset_regs -filter {REF_PIN_NAME == CLR || REF_PIN_NAME == PRE}]
