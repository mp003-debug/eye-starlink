// =============================================================
// tmds_encoder.v  —— DVI/HDMI TMDS 8b/10b 编码器 (符合 DVI 1.0)
// 每个颜色通道一个。像素区做 8b->10b 最小跳变+直流平衡编码,
// 消隐区发送 4 个固定控制码 (由 ctrl={c1,c0} 选择)。
// =============================================================
`timescale 1ns/1ps
module tmds_encoder (
    input  wire        clk,     // 像素时钟 (25 MHz)
    input  wire        rst_n,
    input  wire [7:0]  din,     // 8 位像素分量
    input  wire [1:0]  ctrl,    // 消隐期控制位 {c1,c0}; 通常蓝通道用 {vsync,hsync}
    input  wire        de,      // 1=像素有效区, 0=消隐区
    output reg  [9:0]  dout
);
    // ---- 第 1 级: 最小化跳变 (选 XOR 或 XNOR) ----
    wire [3:0] n1_din = din[0]+din[1]+din[2]+din[3]+din[4]+din[5]+din[6]+din[7];
    wire use_xnor = (n1_din > 4'd4) || ((n1_din == 4'd4) && (din[0] == 1'b0));

    wire [8:0] q_m;
    assign q_m[0] = din[0];
    assign q_m[1] = use_xnor ? ~(q_m[0]^din[1]) : (q_m[0]^din[1]);
    assign q_m[2] = use_xnor ? ~(q_m[1]^din[2]) : (q_m[1]^din[2]);
    assign q_m[3] = use_xnor ? ~(q_m[2]^din[3]) : (q_m[2]^din[3]);
    assign q_m[4] = use_xnor ? ~(q_m[3]^din[4]) : (q_m[3]^din[4]);
    assign q_m[5] = use_xnor ? ~(q_m[4]^din[5]) : (q_m[4]^din[5]);
    assign q_m[6] = use_xnor ? ~(q_m[5]^din[6]) : (q_m[5]^din[6]);
    assign q_m[7] = use_xnor ? ~(q_m[6]^din[7]) : (q_m[6]^din[7]);
    assign q_m[8] = use_xnor ? 1'b0 : 1'b1;

    // ---- 第 2 级: 直流平衡 ----
    wire [3:0] n1_qm = q_m[0]+q_m[1]+q_m[2]+q_m[3]+q_m[4]+q_m[5]+q_m[6]+q_m[7];
    wire [3:0] n0_qm = 4'd8 - n1_qm;
    wire signed [5:0] diff_qm = $signed({2'b00,n1_qm}) - $signed({2'b00,n0_qm}); // N1-N0
    reg  signed [5:0] cnt;  // 运行视差

    wire [9:0] ctrl_code =
        (ctrl==2'b00) ? 10'b1101010100 :
        (ctrl==2'b01) ? 10'b0010101011 :
        (ctrl==2'b10) ? 10'b0101010100 :
                        10'b1010101011 ;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            dout <= 10'd0;
            cnt  <= 6'sd0;
        end else if (!de) begin
            dout <= ctrl_code;
            cnt  <= 6'sd0;             // 消隐期视差清零
        end else begin
            if ((cnt == 0) || (n1_qm == 4'd4)) begin
                dout[9]   <= ~q_m[8];
                dout[8]   <=  q_m[8];
                dout[7:0] <=  q_m[8] ? q_m[7:0] : ~q_m[7:0];
                cnt <= q_m[8] ? (cnt + diff_qm) : (cnt - diff_qm);
            end else if ((cnt > 0 && diff_qm > 0) || (cnt < 0 && diff_qm < 0)) begin
                dout[9]   <= 1'b1;
                dout[8]   <= q_m[8];
                dout[7:0] <= ~q_m[7:0];
                cnt <= cnt + (q_m[8] ? 6'sd2 : 6'sd0) - diff_qm;
            end else begin
                dout[9]   <= 1'b0;
                dout[8]   <= q_m[8];
                dout[7:0] <= q_m[7:0];
                cnt <= cnt - (q_m[8] ? 6'sd0 : 6'sd2) + diff_qm;
            end
        end
    end
endmodule
