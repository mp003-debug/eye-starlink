`timescale 1ns/1ps
// RGB565 display stream; camera capture remains GRAY8.
// VDMA owns the frame buffers. Consume exactly one frame per display period.
// On starvation or bad framing, black out and latch a fault until reset.
module axis_video_sink #(parameter WIDTH=640, HEIGHT=480) (
    input wire clk, rst_n, enable,
    input wire [9:0] x,y,
    input wire de,
    input wire [15:0] s_axis_tdata,
    input wire s_axis_tuser, s_axis_tlast, s_axis_tvalid,
    output wire s_axis_tready,
    output reg [15:0] pixel,
    output reg locked, underflow, format_error
);
    wire first = de && x==0 && y==0;
    wire fault = underflow || format_error;
    assign s_axis_tready = enable && !fault && de && (locked || first);
    always @(posedge clk) begin
        if (!rst_n) begin
            pixel<=0; locked<=0; underflow<=0; format_error<=0;
        end else begin
            pixel<=0;
            if (!enable) locked<=0;
            if (s_axis_tready) begin
                if (!s_axis_tvalid) begin
                    // Before acquisition, a late first frame is not an error.
                    if (locked) begin underflow<=1; locked<=0; end
                end else if (s_axis_tuser != first || s_axis_tlast != (x==WIDTH-1)) begin
                    format_error<=1; locked<=0;
                end else begin
                    pixel<=s_axis_tdata;
                    locked<=1;
                end
            end
        end
    end
endmodule
