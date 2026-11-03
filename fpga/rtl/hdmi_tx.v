// =============================================================
// hdmi_tx.v —— HDMI(DVI) 发送 PHY
// 3 个 TMDS 编码器(RGB) + 4 个 10:1 串行器(3数据+1时钟) + OBUFDS
// 灰度输入时 R=G=B=gray。蓝通道(通道0)在消隐期携带 {vsync,hsync}。
// =============================================================
`timescale 1ns/1ps
module hdmi_tx (
    input  wire        clk_pix,
    input  wire        clk_ser,
    input  wire        rst_n,
    input  wire        de,
    input  wire        hsync,       // 已按 DVI 极性(负)给入
    input  wire        vsync,
    input  wire [7:0]  red,
    input  wire [7:0]  green,
    input  wire [7:0]  blue,
    output wire        tmds_clk_p,  tmds_clk_n,
    output wire [2:0]  tmds_data_p, tmds_data_n
);
    wire rst = ~rst_n;
    wire [9:0] enc0, enc1, enc2;

    // 通道 0 = 蓝, 消隐期发 {vsync,hsync}
    tmds_encoder u_enc0 (.clk(clk_pix), .rst_n(rst_n), .din(blue),
                         .ctrl({vsync,hsync}), .de(de), .dout(enc0));
    // 通道 1 = 绿
    tmds_encoder u_enc1 (.clk(clk_pix), .rst_n(rst_n), .din(green),
                         .ctrl(2'b00), .de(de), .dout(enc1));
    // 通道 2 = 红
    tmds_encoder u_enc2 (.clk(clk_pix), .rst_n(rst_n), .din(red),
                         .ctrl(2'b00), .de(de), .dout(enc2));

    wire ser0, ser1, ser2, serc;
    serializer_10to1 u_s0 (.clk(clk_ser), .clk_div(clk_pix), .rst(rst), .data(enc0),        .ser_out(ser0));
    serializer_10to1 u_s1 (.clk(clk_ser), .clk_div(clk_pix), .rst(rst), .data(enc1),        .ser_out(ser1));
    serializer_10to1 u_s2 (.clk(clk_ser), .clk_div(clk_pix), .rst(rst), .data(enc2),        .ser_out(ser2));
    // 时钟通道: 串出固定 10'b1111100000 图案, 得到与像素同频的 TMDS 时钟
    serializer_10to1 u_sc (.clk(clk_ser), .clk_div(clk_pix), .rst(rst), .data(10'b1111100000), .ser_out(serc));

    OBUFDS obuf_d0 (.I(ser0), .O(tmds_data_p[0]), .OB(tmds_data_n[0]));
    OBUFDS obuf_d1 (.I(ser1), .O(tmds_data_p[1]), .OB(tmds_data_n[1]));
    OBUFDS obuf_d2 (.I(ser2), .O(tmds_data_p[2]), .OB(tmds_data_n[2]));
    OBUFDS obuf_ck (.I(serc), .O(tmds_clk_p),     .OB(tmds_clk_n));
endmodule
