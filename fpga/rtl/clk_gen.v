// =============================================================
// clk_gen.v —— 由 PS 的 50MHz (FCLK_CLK0) 生成 HDMI 所需两个时钟
//   clk_pix = 25 MHz  (640x480@60 像素时钟, VESA 容差内)
//   clk_ser = 125 MHz (= 5x 像素, 供 OSERDESE2 做 10:1 DDR)
// VCO = 50*20 = 1000 MHz (在 -1 器件 600~1200 范围内)
//   CLKOUT0 = 1000/8  = 125 MHz
//   CLKOUT1 = 1000/40 = 25  MHz
// 用 MMCME2_BASE, 纯原语, 不依赖 Clocking Wizard IP。
// =============================================================
`timescale 1ns/1ps
module clk_gen (
    input  wire clk_in50,    // 来自 Zynq PS FCLK_CLK0
    output wire clk_pix,     // 25 MHz
    output wire clk_ser,     // 125 MHz
    output wire locked
);
    wire clk_fb, clk_fb_bufg;
    wire clkout0_pre, clkout1_pre;

    MMCME2_BASE #(
        .BANDWIDTH        ("OPTIMIZED"),
        .CLKIN1_PERIOD    (20.000),   // 50 MHz
        .DIVCLK_DIVIDE    (1),
        .CLKFBOUT_MULT_F  (20.000),   // VCO = 1000 MHz
        .CLKOUT0_DIVIDE_F (8.000),    // 125 MHz
        .CLKOUT1_DIVIDE   (40),       // 25  MHz
        .CLKOUT0_DUTY_CYCLE(0.5),
        .CLKOUT1_DUTY_CYCLE(0.5),
        .STARTUP_WAIT     ("FALSE")
    ) mmcm_i (
        .CLKIN1   (clk_in50),
        .CLKFBIN  (clk_fb_bufg),
        .CLKFBOUT (clk_fb),
        .CLKOUT0  (clkout0_pre),
        .CLKOUT1  (clkout1_pre),
        .CLKOUT2(), .CLKOUT3(), .CLKOUT4(), .CLKOUT5(), .CLKOUT6(),
        .CLKOUT0B(), .CLKOUT1B(), .CLKOUT2B(), .CLKOUT3B(), .CLKFBOUTB(),
        .LOCKED   (locked),
        .PWRDWN   (1'b0),
        .RST      (1'b0)
    );

    BUFG bufg_fb  (.I(clk_fb),      .O(clk_fb_bufg));
    BUFG bufg_ser (.I(clkout0_pre), .O(clk_ser));
    BUFG bufg_pix (.I(clkout1_pre), .O(clk_pix));
endmodule
