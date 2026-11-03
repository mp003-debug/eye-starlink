`timescale 1ns/1ps
// Word layout: R[15:11], G[10:5], B[4:0]. No added pipeline latency.
module rgb565_to_rgb888 (
    input wire [15:0] pixel,
    output wire [7:0] red, green, blue
);
    assign red   = {pixel[15:11],pixel[15:13]};
    assign green = {pixel[10:5],pixel[10:9]};
    assign blue  = {pixel[4:0],pixel[4:2]};
endmodule
