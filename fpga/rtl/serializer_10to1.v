// =============================================================
// serializer_10to1.v —— 10:1 DDR 串行化器 (Zynq-7000 / 7 系列)
// 用两片级联的 OSERDESE2 (MASTER+SLAVE) 把 10 位并行数据
// 按 DDR 方式串出。clk=5x像素时钟(125MHz), clk_div=1x(25MHz),
// 每个像素时钟串出 10 bit -> 250 Mbps, 正好等于 25M*10。
// 输出 ser_out 再接 OBUFDS 变差分。
// =============================================================
`timescale 1ns/1ps
module serializer_10to1 (
    input  wire       clk,      // 125 MHz (串行位时钟, DDR)
    input  wire       clk_div,  // 25 MHz  (像素/并行时钟)
    input  wire       rst,      // 高有效
    input  wire [9:0] data,     // 待串出的 10 位 (data[0] 先出)
    output wire       ser_out
);
    wire shift1, shift2;

    OSERDESE2 #(
        .DATA_RATE_OQ ("DDR"),
        .DATA_RATE_TQ ("SDR"),
        .DATA_WIDTH   (10),
        .SERDES_MODE  ("MASTER"),
        .TRISTATE_WIDTH(1)
    ) oserdes_m (
        .OQ       (ser_out),
        .OFB      (), .TQ(), .TFB(),
        .SHIFTOUT1(), .SHIFTOUT2(),
        .CLK      (clk),
        .CLKDIV   (clk_div),
        .D1(data[0]), .D2(data[1]), .D3(data[2]), .D4(data[3]),
        .D5(data[4]), .D6(data[5]), .D7(data[6]), .D8(data[7]),
        .SHIFTIN1 (shift1), .SHIFTIN2(shift2),
        .OCE(1'b1), .RST(rst),
        .TCE(1'b0), .T1(1'b0), .T2(1'b0), .T3(1'b0), .T4(1'b0), .TBYTEIN(1'b0)
    );

    OSERDESE2 #(
        .DATA_RATE_OQ ("DDR"),
        .DATA_RATE_TQ ("SDR"),
        .DATA_WIDTH   (10),
        .SERDES_MODE  ("SLAVE"),
        .TRISTATE_WIDTH(1)
    ) oserdes_s (
        .OQ(), .OFB(), .TQ(), .TFB(),
        .SHIFTOUT1(shift1), .SHIFTOUT2(shift2),
        .CLK      (clk),
        .CLKDIV   (clk_div),
        .D1(1'b0), .D2(1'b0), .D3(data[8]), .D4(data[9]),
        .D5(1'b0), .D6(1'b0), .D7(1'b0), .D8(1'b0),
        .SHIFTIN1 (1'b0), .SHIFTIN2(1'b0),
        .OCE(1'b1), .RST(rst),
        .TCE(1'b0), .T1(1'b0), .T2(1'b0), .T3(1'b0), .T4(1'b0), .TBYTEIN(1'b0)
    );
endmodule
