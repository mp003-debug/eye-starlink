// =============================================================
// video_timing.v —— 640x480@60 (25MHz) VGA/DVI 时序发生器
// H: 640 + 16(FP) + 96(SYNC) + 48(BP) = 800
// V: 480 + 10(FP) +  2(SYNC) + 33(BP) = 525
// hsync/vsync 均为负极性。x,y 为当前扫描坐标(寄存器输出),
// de/hsync/vsync 由 x,y 组合产生, 与 x,y 表示同一像素时刻。
// =============================================================
`timescale 1ns/1ps
module video_timing (
    input  wire       clk_pix,
    input  wire       rst_n,
    output reg  [9:0] x,      // 0..799
    output reg  [9:0] y,      // 0..524
    output wire       de,     // 1=有效像素区
    output wire       hsync,  // 负极性
    output wire       vsync   // 负极性
);
    localparam H_ACT=640, H_FP=16, H_SYNC=96, H_TOT=800;
    localparam V_ACT=480, V_FP=10, V_SYNC=2,  V_TOT=525;

    always @(posedge clk_pix or negedge rst_n) begin
        if (!rst_n) begin
            x <= 10'd0; y <= 10'd0;
        end else begin
            if (x == H_TOT-1) begin
                x <= 10'd0;
                y <= (y == V_TOT-1) ? 10'd0 : y + 1'b1;
            end else begin
                x <= x + 1'b1;
            end
        end
    end

    assign de    = (x < H_ACT) && (y < V_ACT);
    assign hsync = ~((x >= H_ACT+H_FP) && (x < H_ACT+H_FP+H_SYNC));
    assign vsync = ~((y >= V_ACT+V_FP) && (y < V_ACT+V_FP+V_SYNC));
endmodule
