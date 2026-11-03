
################################################################
# This is a generated script based on design: eye_tracker_bd
#
# Though there are limitations about the generated script,
# the main purpose of this utility is to make learning
# IP Integrator Tcl commands easier.
################################################################

namespace eval _tcl {
proc get_script_folder {} {
   set script_path [file normalize [info script]]
   set script_folder [file dirname $script_path]
   return $script_folder
}
}
variable script_folder
set script_folder [_tcl::get_script_folder]

################################################################
# Check if script is running in correct Vivado version.
################################################################
set scripts_vivado_version 2026.1
set current_vivado_version [version -short]

if { [string first $scripts_vivado_version $current_vivado_version] == -1 } {
   puts ""
   if { [string compare $scripts_vivado_version $current_vivado_version] > 0 } {
      catch {common::send_gid_msg -ssname BD::TCL -id 2042 -severity "ERROR" " This script was generated using Vivado <$scripts_vivado_version> and is being run in <$current_vivado_version> of Vivado. Sourcing the script failed since it was created with a future version of Vivado."}

   } else {
     catch {common::send_gid_msg -ssname BD::TCL -id 2041 -severity "ERROR" "This script was generated using Vivado <$scripts_vivado_version> and is being run in <$current_vivado_version> of Vivado. Please run the script in Vivado <$scripts_vivado_version> then open the design in Vivado <$current_vivado_version>. Upgrade the design by running \"Tools => Report => Report IP Status...\", then run write_bd_tcl to create an updated script."}

   }

   return 1
}

################################################################
# START
################################################################

# To test this script, run the following commands from Vivado Tcl console:
# source eye_tracker_bd_script.tcl


# The design that will be created by this Tcl script contains the following 
# module references:
# camera_ddr_video, camera_diag_axi, audio_aux_axi

# Please add the sources of those modules before sourcing this Tcl script.

# If there is no project opened, this script will create a
# project, but make sure you do not have an existing project
# <./myproj/project_1.xpr> in the current working folder.

set list_projs [get_projects -quiet]
if { $list_projs eq "" } {
   create_project project_1 myproj -part xc7z020clg400-1
}


# CHANGE DESIGN NAME HERE
variable design_name
set design_name eye_tracker_bd

# If you do not already have an existing IP Integrator design open,
# you can create a design using the following command:
#    create_bd_design $design_name

# Creating design if needed
set errMsg ""
set nRet 0

set cur_design [current_bd_design -quiet]
set list_cells [get_bd_cells -quiet]

if { ${design_name} eq "" } {
   # USE CASES:
   #    1) Design_name not set

   set errMsg "Please set the variable <design_name> to a non-empty value."
   set nRet 1

} elseif { ${cur_design} ne "" && ${list_cells} eq "" } {
   # USE CASES:
   #    2): Current design opened AND is empty AND names same.
   #    3): Current design opened AND is empty AND names diff; design_name NOT in project.
   #    4): Current design opened AND is empty AND names diff; design_name exists in project.

   if { $cur_design ne $design_name } {
      common::send_gid_msg -ssname BD::TCL -id 2001 -severity "INFO" "Changing value of <design_name> from <$design_name> to <$cur_design> since current design is empty."
      set design_name [get_property NAME $cur_design]
   }
   common::send_gid_msg -ssname BD::TCL -id 2002 -severity "INFO" "Constructing design in IPI design <$cur_design>..."

} elseif { ${cur_design} ne "" && $list_cells ne "" && $cur_design eq $design_name } {
   # USE CASES:
   #    5) Current design opened AND has components AND same names.

   set errMsg "Design <$design_name> already exists in your project, please set the variable <design_name> to another value."
   set nRet 1
} elseif { [get_files -quiet ${design_name}.bd] ne "" } {
   # USE CASES: 
   #    6) Current opened design, has components, but diff names, design_name exists in project.
   #    7) No opened design, design_name exists in project.

   set errMsg "Design <$design_name> already exists in your project, please set the variable <design_name> to another value."
   set nRet 2

} else {
   # USE CASES:
   #    8) No opened design, design_name not in project.
   #    9) Current opened design, has components, but diff names, design_name not in project.

   common::send_gid_msg -ssname BD::TCL -id 2003 -severity "INFO" "Currently there is no design <$design_name> in project, so creating one..."

   create_bd_design $design_name

   common::send_gid_msg -ssname BD::TCL -id 2004 -severity "INFO" "Making design <$design_name> as current_bd_design."
   current_bd_design $design_name

}

common::send_gid_msg -ssname BD::TCL -id 2005 -severity "INFO" "Currently the variable <design_name> is equal to \"$design_name\"."

if { $nRet != 0 } {
   catch {common::send_gid_msg -ssname BD::TCL -id 2006 -severity "ERROR" $errMsg}
   return $nRet
}

set bCheckIPsPassed 1
##################################################################
# CHECK IPs
##################################################################
set bCheckIPs 1
if { $bCheckIPs == 1 } {
   set list_check_ips "\ 
xilinx.com:ip:processing_system7:5.5\
xilinx.com:ip:axi_vdma:6.3\
xilinx.com:ip:axi_gpio:2.0\
xilinx.com:ip:proc_sys_reset:5.0\
xilinx.com:ip:xlconstant:1.1\
xilinx.com:ip:clk_wiz:6.0\
xilinx.com:ip:axi_uartlite:2.0\
"

   set list_ips_missing ""
   common::send_gid_msg -ssname BD::TCL -id 2011 -severity "INFO" "Checking if the following IPs exist in the project's IP catalog: $list_check_ips ."

   foreach ip_vlnv $list_check_ips {
      set ip_obj [get_ipdefs -all $ip_vlnv]
      if { $ip_obj eq "" } {
         lappend list_ips_missing $ip_vlnv
      }
   }

   if { $list_ips_missing ne "" } {
      catch {common::send_gid_msg -ssname BD::TCL -id 2012 -severity "ERROR" "The following IPs are not found in the IP Catalog:\n  $list_ips_missing\n\nResolution: Please add the repository containing the IP(s) to the project." }
      set bCheckIPsPassed 0
   }

}

##################################################################
# CHECK Modules
##################################################################
set bCheckModules 1
if { $bCheckModules == 1 } {
   set list_check_mods "\ 
camera_ddr_video\
camera_diag_axi\
audio_aux_axi\
"

   set list_mods_missing ""
   common::send_gid_msg -ssname BD::TCL -id 2020 -severity "INFO" "Checking if the following modules exist in the project's sources: $list_check_mods ."

   foreach mod_vlnv $list_check_mods {
      if { [can_resolve_reference $mod_vlnv] == 0 } {
         lappend list_mods_missing $mod_vlnv
      }
   }

   if { $list_mods_missing ne "" } {
      catch {common::send_gid_msg -ssname BD::TCL -id 2021 -severity "ERROR" "The following module(s) are not found in the project: $list_mods_missing" }
      common::send_gid_msg -ssname BD::TCL -id 2022 -severity "INFO" "Please add source files for the missing module(s) above."
      set bCheckIPsPassed 0
   }
}

if { $bCheckIPsPassed != 1 } {
  common::send_gid_msg -ssname BD::TCL -id 2023 -severity "WARNING" "Will not continue with creation of design due to the error(s) above."
  return 3
}

##################################################################
# DESIGN PROCs
##################################################################



# Procedure to create entire design; Provide argument to make
# procedure reusable. If parentCell is "", will use root.
proc create_root_design { parentCell } {

  variable script_folder
  variable design_name

  if { $parentCell eq "" } {
     set parentCell [get_bd_cells /]
  }

  # Get object for parentCell
  set parentObj [get_bd_cells $parentCell]
  if { $parentObj == "" } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2090 -severity "ERROR" "Unable to find parent cell <$parentCell>!"}
     return
  }

  # Make sure parentObj is hier blk
  set parentType [get_property TYPE $parentObj]
  if { $parentType ne "hier" } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2091 -severity "ERROR" "Parent <$parentObj> has TYPE = <$parentType>. Expected to be <hier>."}
     return
  }

  # Save current instance; Restore later
  set oldCurInst [current_bd_instance .]

  # Set parent object as current
  current_bd_instance $parentObj


  # Create interface ports
  set DDR [ create_bd_intf_port -mode Master -vlnv xilinx.com:interface:ddrx_rtl:1.0 DDR ]

  set FIXED_IO [ create_bd_intf_port -mode Master -vlnv xilinx.com:display_processing_system7:fixedio_rtl:1.0 FIXED_IO ]


  # Create ports
  set cam_data [ create_bd_port -dir I -from 7 -to 0 cam_data ]
  set cam_pclk [ create_bd_port -dir I -type clk -freq_hz 24000000 cam_pclk ]
  set cam_frame_valid [ create_bd_port -dir I cam_frame_valid ]
  set cam_line_valid [ create_bd_port -dir I cam_line_valid ]
  set cam_sda [ create_bd_port -dir IO cam_sda ]
  set cam_scl [ create_bd_port -dir IO cam_scl ]
  set sw0 [ create_bd_port -dir I sw0 ]
  set led [ create_bd_port -dir O -from 3 -to 0 led ]
  set hdmi_out_clk_p [ create_bd_port -dir O -type clk hdmi_out_clk_p ]
  set hdmi_out_clk_n [ create_bd_port -dir O -type clk hdmi_out_clk_n ]
  set hdmi_out_data_p [ create_bd_port -dir O -from 2 -to 0 hdmi_out_data_p ]
  set hdmi_out_data_n [ create_bd_port -dir O -from 2 -to 0 hdmi_out_data_n ]
  set au_bclk [ create_bd_port -dir I au_bclk ]
  set au_lrclk [ create_bd_port -dir I au_lrclk ]
  set au_sdata [ create_bd_port -dir O au_sdata ]
  set au_sda [ create_bd_port -dir IO au_sda ]
  set au_scl [ create_bd_port -dir IO au_scl ]
  set buttons [ create_bd_port -dir I -from 3 -to 0 buttons ]
  set au_mclk [ create_bd_port -dir O -type clk au_mclk ]
  set event_uart_rx [ create_bd_port -dir I event_uart_rx ]
  set event_uart_tx [ create_bd_port -dir O event_uart_tx ]

  # Create instance: ps7, and set properties
  set ps7 [ create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps7 ]
  set_property -dict [list \
    CONFIG.PCW_ACT_APU_PERIPHERAL_FREQMHZ {666.666687} \
    CONFIG.PCW_ACT_CAN_PERIPHERAL_FREQMHZ {10.000000} \
    CONFIG.PCW_ACT_DCI_PERIPHERAL_FREQMHZ {10.158730} \
    CONFIG.PCW_ACT_ENET0_PERIPHERAL_FREQMHZ {10.000000} \
    CONFIG.PCW_ACT_ENET1_PERIPHERAL_FREQMHZ {10.000000} \
    CONFIG.PCW_ACT_FPGA0_PERIPHERAL_FREQMHZ {50.000000} \
    CONFIG.PCW_ACT_FPGA1_PERIPHERAL_FREQMHZ {100.000000} \
    CONFIG.PCW_ACT_FPGA2_PERIPHERAL_FREQMHZ {10.000000} \
    CONFIG.PCW_ACT_FPGA3_PERIPHERAL_FREQMHZ {10.000000} \
    CONFIG.PCW_ACT_PCAP_PERIPHERAL_FREQMHZ {200.000000} \
    CONFIG.PCW_ACT_QSPI_PERIPHERAL_FREQMHZ {10.000000} \
    CONFIG.PCW_ACT_SDIO_PERIPHERAL_FREQMHZ {10.000000} \
    CONFIG.PCW_ACT_SMC_PERIPHERAL_FREQMHZ {10.000000} \
    CONFIG.PCW_ACT_SPI_PERIPHERAL_FREQMHZ {10.000000} \
    CONFIG.PCW_ACT_TPIU_PERIPHERAL_FREQMHZ {200.000000} \
    CONFIG.PCW_ACT_TTC0_CLK0_PERIPHERAL_FREQMHZ {111.111115} \
    CONFIG.PCW_ACT_TTC0_CLK1_PERIPHERAL_FREQMHZ {111.111115} \
    CONFIG.PCW_ACT_TTC0_CLK2_PERIPHERAL_FREQMHZ {111.111115} \
    CONFIG.PCW_ACT_TTC1_CLK0_PERIPHERAL_FREQMHZ {111.111115} \
    CONFIG.PCW_ACT_TTC1_CLK1_PERIPHERAL_FREQMHZ {111.111115} \
    CONFIG.PCW_ACT_TTC1_CLK2_PERIPHERAL_FREQMHZ {111.111115} \
    CONFIG.PCW_ACT_UART_PERIPHERAL_FREQMHZ {10.000000} \
    CONFIG.PCW_ACT_WDT_PERIPHERAL_FREQMHZ {111.111115} \
    CONFIG.PCW_CLK0_FREQ {50000000} \
    CONFIG.PCW_CLK1_FREQ {100000000} \
    CONFIG.PCW_CLK2_FREQ {10000000} \
    CONFIG.PCW_CLK3_FREQ {10000000} \
    CONFIG.PCW_DDR_RAM_HIGHADDR {0x1FFFFFFF} \
    CONFIG.PCW_EN_CLK0_PORT {1} \
    CONFIG.PCW_EN_CLK1_PORT {1} \
    CONFIG.PCW_EN_RST0_PORT {1} \
    CONFIG.PCW_FCLK_CLK0_BUF {TRUE} \
    CONFIG.PCW_FCLK_CLK1_BUF {TRUE} \
    CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {50} \
    CONFIG.PCW_FPGA1_PERIPHERAL_FREQMHZ {100} \
    CONFIG.PCW_FPGA_FCLK0_ENABLE {1} \
    CONFIG.PCW_FPGA_FCLK1_ENABLE {1} \
    CONFIG.PCW_S_AXI_HP0_DATA_WIDTH {64} \
    CONFIG.PCW_UIPARAM_ACT_DDR_FREQ_MHZ {533.333374} \
    CONFIG.PCW_USE_M_AXI_GP0 {1} \
    CONFIG.PCW_USE_S_AXI_HP0 {1} \
  ] $ps7


  # Create instance: video_0, and set properties
  set block_name camera_ddr_video
  set block_cell_name video_0
  if { [catch {set video_0 [create_bd_cell -type module -reference $block_name $block_cell_name] } errmsg] } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2095 -severity "ERROR" "Unable to add referenced block <$block_name>. Please add the files for ${block_name}'s definition into the project."}
     return 1
   } elseif { $video_0 eq "" } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2096 -severity "ERROR" "Unable to referenced block <$block_name>. Please add the files for ${block_name}'s definition into the project."}
     return 1
   }
  
  # Create instance: camera_diag_0, and set properties
  set block_name camera_diag_axi
  set block_cell_name camera_diag_0
  if { [catch {set camera_diag_0 [create_bd_cell -type module -reference $block_name $block_cell_name] } errmsg] } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2095 -severity "ERROR" "Unable to add referenced block <$block_name>. Please add the files for ${block_name}'s definition into the project."}
     return 1
   } elseif { $camera_diag_0 eq "" } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2096 -severity "ERROR" "Unable to referenced block <$block_name>. Please add the files for ${block_name}'s definition into the project."}
     return 1
   }
  
  # Create instance: vdma_0, and set properties
  set vdma_0 [ create_bd_cell -type ip -vlnv xilinx.com:ip:axi_vdma:6.3 vdma_0 ]
  set_property -dict [list \
    CONFIG.c_include_internal_genlock {1} \
    CONFIG.c_include_mm2s {1} \
    CONFIG.c_include_mm2s_dre {0} \
    CONFIG.c_include_s2mm {1} \
    CONFIG.c_include_s2mm_dre {0} \
    CONFIG.c_include_sg {0} \
    CONFIG.c_m_axi_mm2s_data_width {64} \
    CONFIG.c_m_axi_s2mm_data_width {64} \
    CONFIG.c_m_axis_mm2s_tdata_width {16} \
    CONFIG.c_mm2s_genlock_mode {3} \
    CONFIG.c_mm2s_linebuffer_depth {8192} \
    CONFIG.c_mm2s_max_burst_length {16} \
    CONFIG.c_num_fstores {3} \
    CONFIG.c_s2mm_genlock_mode {2} \
    CONFIG.c_s2mm_linebuffer_depth {8192} \
    CONFIG.c_s2mm_max_burst_length {16} \
    CONFIG.c_use_mm2s_fsync {0} \
    CONFIG.c_use_s2mm_fsync {0} \
  ] $vdma_0


  # Create instance: video_control, and set properties
  set video_control [ create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 video_control ]
  set_property -dict [list \
    CONFIG.C_ALL_INPUTS_2 {1} \
    CONFIG.C_ALL_OUTPUTS {1} \
    CONFIG.C_DOUT_DEFAULT {0x00000000} \
    CONFIG.C_GPIO2_WIDTH {7} \
    CONFIG.C_GPIO_WIDTH {4} \
    CONFIG.C_IS_DUAL {1} \
  ] $video_control


  # Create instance: ps7_axi_periph, and set properties
  set ps7_axi_periph [ create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 ps7_axi_periph ]
  set_property CONFIG.NUM_MI {5} $ps7_axi_periph


  # Create instance: rst_ps7_50M, and set properties
  set rst_ps7_50M [ create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst_ps7_50M ]
  set_property CONFIG.C_AUX_RESET_HIGH {0} $rst_ps7_50M


  # Create instance: memory_bus, and set properties
  set memory_bus [ create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 memory_bus ]
  set_property -dict [list \
    CONFIG.NUM_MI {1} \
    CONFIG.NUM_SI {2} \
  ] $memory_bus


  # Create instance: one, and set properties
  set one [ create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 one ]
  set_property CONFIG.CONST_VAL {1} $one


  # Create instance: zero, and set properties
  set zero [ create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 zero ]
  set_property CONFIG.CONST_VAL {0} $zero


  # Create instance: reset100, and set properties
  set reset100 [ create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 reset100 ]
  set_property CONFIG.C_AUX_RESET_HIGH {0} $reset100


  # Create instance: audio_aux_0, and set properties
  set block_name audio_aux_axi
  set block_cell_name audio_aux_0
  if { [catch {set audio_aux_0 [create_bd_cell -type module -reference $block_name $block_cell_name] } errmsg] } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2095 -severity "ERROR" "Unable to add referenced block <$block_name>. Please add the files for ${block_name}'s definition into the project."}
     return 1
   } elseif { $audio_aux_0 eq "" } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2096 -severity "ERROR" "Unable to referenced block <$block_name>. Please add the files for ${block_name}'s definition into the project."}
     return 1
   }
  
  # Create instance: audio_clock, and set properties
  set audio_clock [ create_bd_cell -type ip -vlnv xilinx.com:ip:clk_wiz:6.0 audio_clock ]
  set_property -dict [list \
    CONFIG.CLKOUT1_REQUESTED_OUT_FREQ {10.000} \
    CONFIG.PRIM_IN_FREQ {50.000} \
    CONFIG.RESET_TYPE {ACTIVE_LOW} \
  ] $audio_clock


  # Create instance: event_uart_0, and set properties
  set event_uart_0 [ create_bd_cell -type ip -vlnv xilinx.com:ip:axi_uartlite:2.0 event_uart_0 ]
  set_property -dict [list \
    CONFIG.C_BAUDRATE {115200} \
    CONFIG.C_DATA_BITS {8} \
    CONFIG.PARITY {No_Parity} \
  ] $event_uart_0


  # Create interface connections
  connect_bd_intf_net -intf_net memory_bus_M00_AXI [get_bd_intf_pins memory_bus/M00_AXI] [get_bd_intf_pins ps7/S_AXI_HP0]
  connect_bd_intf_net -intf_net ps7_DDR [get_bd_intf_ports DDR] [get_bd_intf_pins ps7/DDR]
  connect_bd_intf_net -intf_net ps7_FIXED_IO [get_bd_intf_ports FIXED_IO] [get_bd_intf_pins ps7/FIXED_IO]
  connect_bd_intf_net -intf_net ps7_M_AXI_GP0 [get_bd_intf_pins ps7/M_AXI_GP0] [get_bd_intf_pins ps7_axi_periph/S00_AXI]
  connect_bd_intf_net -intf_net ps7_axi_periph_M00_AXI [get_bd_intf_pins ps7_axi_periph/M00_AXI] [get_bd_intf_pins camera_diag_0/s_axi]
  connect_bd_intf_net -intf_net ps7_axi_periph_M01_AXI [get_bd_intf_pins ps7_axi_periph/M01_AXI] [get_bd_intf_pins vdma_0/S_AXI_LITE]
  connect_bd_intf_net -intf_net ps7_axi_periph_M02_AXI [get_bd_intf_pins ps7_axi_periph/M02_AXI] [get_bd_intf_pins video_control/S_AXI]
  connect_bd_intf_net -intf_net ps7_axi_periph_M03_AXI [get_bd_intf_pins ps7_axi_periph/M03_AXI] [get_bd_intf_pins audio_aux_0/s_axi]
  connect_bd_intf_net -intf_net ps7_axi_periph_M04_AXI [get_bd_intf_pins ps7_axi_periph/M04_AXI] [get_bd_intf_pins event_uart_0/S_AXI]
  connect_bd_intf_net -intf_net vdma_0_M_AXIS_MM2S [get_bd_intf_pins vdma_0/M_AXIS_MM2S] [get_bd_intf_pins video_0/s_axis]
  connect_bd_intf_net -intf_net vdma_0_M_AXI_MM2S [get_bd_intf_pins vdma_0/M_AXI_MM2S] [get_bd_intf_pins memory_bus/S00_AXI]
  connect_bd_intf_net -intf_net vdma_0_M_AXI_S2MM [get_bd_intf_pins vdma_0/M_AXI_S2MM] [get_bd_intf_pins memory_bus/S01_AXI]
  connect_bd_intf_net -intf_net video_0_m_axis [get_bd_intf_pins video_0/m_axis] [get_bd_intf_pins vdma_0/S_AXIS_S2MM]

  # Create port connections
  connect_bd_net -net Net  [get_bd_ports cam_sda] \
  [get_bd_pins video_0/cam_sda]
  connect_bd_net -net Net1  [get_bd_ports cam_scl] \
  [get_bd_pins video_0/cam_scl]
  connect_bd_net -net Net2  [get_bd_ports au_sda] \
  [get_bd_pins audio_aux_0/au_sda]
  connect_bd_net -net Net3  [get_bd_ports au_scl] \
  [get_bd_pins audio_aux_0/au_scl]
  connect_bd_net -net au_bclk_0_1  [get_bd_ports au_bclk] \
  [get_bd_pins audio_aux_0/au_bclk]
  connect_bd_net -net au_lrclk_0_1  [get_bd_ports au_lrclk] \
  [get_bd_pins audio_aux_0/au_lrclk]
  connect_bd_net -net audio_aux_0_au_sdata  [get_bd_pins audio_aux_0/au_sdata] \
  [get_bd_ports au_sdata]
  connect_bd_net -net audio_clock_clk_out1  [get_bd_pins audio_clock/clk_out1] \
  [get_bd_ports au_mclk]
  connect_bd_net -net audio_clock_locked  [get_bd_pins audio_clock/locked] \
  [get_bd_pins audio_aux_0/mclk_locked]
  connect_bd_net -net buttons_0_1  [get_bd_ports buttons] \
  [get_bd_pins audio_aux_0/buttons]
  connect_bd_net -net cam_data_0_1  [get_bd_ports cam_data] \
  [get_bd_pins video_0/cam_data]
  connect_bd_net -net cam_frame_valid_0_1  [get_bd_ports cam_frame_valid] \
  [get_bd_pins video_0/cam_frame_valid]
  connect_bd_net -net cam_line_valid_0_1  [get_bd_ports cam_line_valid] \
  [get_bd_pins video_0/cam_line_valid]
  connect_bd_net -net cam_pclk_0_1  [get_bd_ports cam_pclk] \
  [get_bd_pins video_0/cam_pclk]
  connect_bd_net -net event_uart_0_tx  [get_bd_pins event_uart_0/tx] \
  [get_bd_ports event_uart_tx]
  connect_bd_net -net one_dout  [get_bd_pins one/dout] \
  [get_bd_pins rst_ps7_50M/dcm_locked] \
  [get_bd_pins rst_ps7_50M/aux_reset_in] \
  [get_bd_pins reset100/dcm_locked] \
  [get_bd_pins reset100/aux_reset_in]
  connect_bd_net -net ps7_FCLK_CLK0  [get_bd_pins ps7/FCLK_CLK0] \
  [get_bd_pins ps7_axi_periph/ACLK] \
  [get_bd_pins ps7/M_AXI_GP0_ACLK] \
  [get_bd_pins ps7_axi_periph/S00_ACLK] \
  [get_bd_pins rst_ps7_50M/slowest_sync_clk] \
  [get_bd_pins ps7_axi_periph/M00_ACLK] \
  [get_bd_pins vdma_0/s_axi_lite_aclk] \
  [get_bd_pins video_control/s_axi_aclk] \
  [get_bd_pins ps7_axi_periph/M01_ACLK] \
  [get_bd_pins ps7_axi_periph/M02_ACLK] \
  [get_bd_pins ps7_axi_periph/M03_ACLK] \
  [get_bd_pins audio_clock/clk_in1] \
  [get_bd_pins event_uart_0/s_axi_aclk] \
  [get_bd_pins ps7_axi_periph/M04_ACLK] \
  [get_bd_pins video_0/ctrl_clk] \
  [get_bd_pins camera_diag_0/aclk] \
  [get_bd_pins audio_aux_0/aclk]
  connect_bd_net -net ps7_FCLK_CLK1  [get_bd_pins ps7/FCLK_CLK1] \
  [get_bd_pins reset100/slowest_sync_clk] \
  [get_bd_pins ps7/S_AXI_HP0_ACLK] \
  [get_bd_pins vdma_0/m_axi_mm2s_aclk] \
  [get_bd_pins vdma_0/m_axi_s2mm_aclk] \
  [get_bd_pins memory_bus/ACLK] \
  [get_bd_pins memory_bus/S00_ACLK] \
  [get_bd_pins memory_bus/S01_ACLK] \
  [get_bd_pins memory_bus/M00_ACLK]
  connect_bd_net -net ps7_FCLK_RESET0_N  [get_bd_pins ps7/FCLK_RESET0_N] \
  [get_bd_pins rst_ps7_50M/ext_reset_in] \
  [get_bd_pins reset100/ext_reset_in] \
  [get_bd_pins audio_clock/resetn]
  connect_bd_net -net reset100_peripheral_aresetn  [get_bd_pins reset100/peripheral_aresetn] \
  [get_bd_pins memory_bus/ARESETN] \
  [get_bd_pins memory_bus/S00_ARESETN] \
  [get_bd_pins memory_bus/S01_ARESETN] \
  [get_bd_pins memory_bus/M00_ARESETN]
  connect_bd_net -net rst_ps7_50M_peripheral_aresetn  [get_bd_pins rst_ps7_50M/peripheral_aresetn] \
  [get_bd_pins ps7_axi_periph/S00_ARESETN] \
  [get_bd_pins ps7_axi_periph/M00_ARESETN] \
  [get_bd_pins ps7_axi_periph/ARESETN] \
  [get_bd_pins video_control/s_axi_aresetn] \
  [get_bd_pins vdma_0/axi_resetn] \
  [get_bd_pins ps7_axi_periph/M01_ARESETN] \
  [get_bd_pins ps7_axi_periph/M02_ARESETN] \
  [get_bd_pins ps7_axi_periph/M03_ARESETN] \
  [get_bd_pins event_uart_0/s_axi_aresetn] \
  [get_bd_pins ps7_axi_periph/M04_ARESETN] \
  [get_bd_pins video_0/aresetn] \
  [get_bd_pins camera_diag_0/aresetn] \
  [get_bd_pins audio_aux_0/aresetn]
  connect_bd_net -net rx_0_1  [get_bd_ports event_uart_rx] \
  [get_bd_pins event_uart_0/rx]
  connect_bd_net -net sw0_0_1  [get_bd_ports sw0] \
  [get_bd_pins video_0/sw0]
  connect_bd_net -net video_0_bad_frames  [get_bd_pins video_0/bad_frames] \
  [get_bd_pins camera_diag_0/bad_frames]
  connect_bd_net -net video_0_bad_lines  [get_bd_pins video_0/bad_lines] \
  [get_bd_pins camera_diag_0/bad_lines]
  connect_bd_net -net video_0_capture_clk  [get_bd_pins video_0/capture_clk] \
  [get_bd_pins vdma_0/s_axis_s2mm_aclk] \
  [get_bd_pins camera_diag_0/pclk]
  connect_bd_net -net video_0_capture_resetn  [get_bd_pins video_0/capture_resetn] \
  [get_bd_pins camera_diag_0/cam_rst_n]
  connect_bd_net -net video_0_display_clk  [get_bd_pins video_0/display_clk] \
  [get_bd_pins vdma_0/m_axis_mm2s_aclk]
  connect_bd_net -net video_0_frame_count  [get_bd_pins video_0/frame_count] \
  [get_bd_pins camera_diag_0/frame_count]
  connect_bd_net -net video_0_frame_lines  [get_bd_pins video_0/frame_lines] \
  [get_bd_pins camera_diag_0/frame_lines]
  connect_bd_net -net video_0_frame_period  [get_bd_pins video_0/frame_period] \
  [get_bd_pins camera_diag_0/frame_period]
  connect_bd_net -net video_0_frame_pixels  [get_bd_pins video_0/frame_pixels] \
  [get_bd_pins camera_diag_0/frame_pixels]
  connect_bd_net -net video_0_hdmi_out_clk_n  [get_bd_pins video_0/hdmi_out_clk_n] \
  [get_bd_ports hdmi_out_clk_n]
  connect_bd_net -net video_0_hdmi_out_clk_p  [get_bd_pins video_0/hdmi_out_clk_p] \
  [get_bd_ports hdmi_out_clk_p]
  connect_bd_net -net video_0_hdmi_out_data_n  [get_bd_pins video_0/hdmi_out_data_n] \
  [get_bd_ports hdmi_out_data_n]
  connect_bd_net -net video_0_hdmi_out_data_p  [get_bd_pins video_0/hdmi_out_data_p] \
  [get_bd_ports hdmi_out_data_p]
  connect_bd_net -net video_0_led  [get_bd_pins video_0/led] \
  [get_bd_ports led]
  connect_bd_net -net video_0_line_pixels  [get_bd_pins video_0/line_pixels] \
  [get_bd_pins camera_diag_0/line_pixels]
  connect_bd_net -net video_0_status  [get_bd_pins video_0/status] \
  [get_bd_pins video_control/gpio2_io_i]
  connect_bd_net -net video_control_gpio_io_o  [get_bd_pins video_control/gpio_io_o] \
  [get_bd_pins video_0/control]
  connect_bd_net -net zero_dout  [get_bd_pins zero/dout] \
  [get_bd_pins rst_ps7_50M/mb_debug_sys_rst] \
  [get_bd_pins reset100/mb_debug_sys_rst]

  # Create address segments
  assign_bd_address -offset 0x43C20000 -range 0x00020000 -target_address_space [get_bd_addr_spaces ps7/Data] [get_bd_addr_segs audio_aux_0/s_axi/reg0] -force
  assign_bd_address -offset 0x43C00000 -range 0x00001000 -target_address_space [get_bd_addr_spaces ps7/Data] [get_bd_addr_segs camera_diag_0/s_axi/reg0] -force
  assign_bd_address -offset 0x42C00000 -range 0x00010000 -target_address_space [get_bd_addr_spaces ps7/Data] [get_bd_addr_segs event_uart_0/S_AXI/Reg] -force
  assign_bd_address -offset 0x43000000 -range 0x00010000 -target_address_space [get_bd_addr_spaces ps7/Data] [get_bd_addr_segs vdma_0/S_AXI_LITE/Reg] -force
  assign_bd_address -offset 0x41200000 -range 0x00010000 -target_address_space [get_bd_addr_spaces ps7/Data] [get_bd_addr_segs video_control/S_AXI/Reg] -force
  assign_bd_address -offset 0x00000000 -range 0x20000000 -target_address_space [get_bd_addr_spaces vdma_0/Data_MM2S] [get_bd_addr_segs ps7/S_AXI_HP0/HP0_DDR_LOWOCM] -force
  assign_bd_address -offset 0x00000000 -range 0x20000000 -target_address_space [get_bd_addr_spaces vdma_0/Data_S2MM] [get_bd_addr_segs ps7/S_AXI_HP0/HP0_DDR_LOWOCM] -force


  # Restore current instance
  current_bd_instance $oldCurInst

  validate_bd_design
  save_bd_design
}
# End of create_root_design()


##################################################################
# MAIN FLOW
##################################################################

create_root_design ""


