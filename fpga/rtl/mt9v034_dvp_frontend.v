`timescale 1ns/1ps

// MT9V034 DVP receiver, cropper, and link-integrity monitor.
//
// The sensor changes DOUT/FV/LV around the falling PIXCLK edge and specifies the
// signals as valid around the rising edge. The first register bank is therefore
// clocked on the rising edge and constrained as a source-synchronous interface.
//
// Coordinates on the output stream are relative to the cropped output window.
// pixel_sof and pixel_eol are asserted with the first and last valid output pixel.
module mt9v034_dvp_frontend #(
    parameter integer SENSOR_WIDTH  = 752,
    parameter integer SENSOR_HEIGHT = 480,
    parameter integer OUTPUT_WIDTH  = 640,
    parameter integer OUTPUT_HEIGHT = 480,
    parameter integer X_OFFSET      = 56,
    parameter integer Y_OFFSET      = 0
) (
    input  wire        pclk,
    input  wire        rst_n,
    input  wire [7:0]  cam_data,
    input  wire        cam_frame_valid,
    input  wire        cam_line_valid,

    output reg  [7:0]  pixel_data,
    output reg         pixel_valid,
    output reg         pixel_sof,
    output reg         pixel_eol,
    output reg  [15:0] pixel_x,
    output reg  [15:0] pixel_y,

    output reg         frame_done,
    output reg  [31:0] frame_count,
    output reg  [31:0] last_frame_period,
    output reg  [31:0] last_frame_pixels,
    output reg  [15:0] last_frame_lines,
    output reg  [15:0] last_line_pixels,
    output reg  [31:0] bad_line_count,
    output reg  [31:0] bad_frame_count
);
    localparam integer EXPECTED_FRAME_PIXELS = SENSOR_WIDTH * SENSOR_HEIGHT;

    // Dedicated input register bank. Vivado should place these registers in IOBs.
    (* IOB = "TRUE" *) reg [7:0] data_iob;
    (* IOB = "TRUE" *) reg       frame_valid_iob;
    (* IOB = "TRUE" *) reg       line_valid_iob;

    always @(posedge pclk) begin
        if (!rst_n) begin
            data_iob        <= 8'd0;
            frame_valid_iob <= 1'b0;
            line_valid_iob  <= 1'b0;
        end else begin
            data_iob        <= cam_data;
            frame_valid_iob <= cam_frame_valid;
            line_valid_iob  <= cam_line_valid;
        end
    end

    reg frame_valid_q;
    reg line_valid_q;
    reg seen_frame;
    reg [15:0] sensor_x;
    reg [15:0] line_count;
    reg [15:0] line_pixels;
    reg [31:0] frame_pixels;
    reg [31:0] frame_period;
    reg frame_bad_line;

    wire frame_rise = frame_valid_iob && !frame_valid_q;
    wire frame_fall = !frame_valid_iob && frame_valid_q;
    wire line_fall  = !line_valid_iob && line_valid_q && frame_valid_q;
    wire [15:0] current_x = frame_rise ? 16'd0 : sensor_x;
    wire [15:0] current_y = frame_rise ? 16'd0 : line_count;
    wire [16:0] completed_line_count =
        {1'b0, line_count} + (line_fall ? 17'd1 : 17'd0);

    wire in_output_window =
        (current_x >= X_OFFSET) &&
        (current_x < X_OFFSET + OUTPUT_WIDTH) &&
        (current_y >= Y_OFFSET) &&
        (current_y < Y_OFFSET + OUTPUT_HEIGHT);

    always @(posedge pclk) begin
        if (!rst_n) begin
            frame_valid_q    <= 1'b0;
            line_valid_q     <= 1'b0;
            seen_frame       <= 1'b0;
            sensor_x         <= 16'd0;
            line_count       <= 16'd0;
            line_pixels      <= 16'd0;
            frame_pixels     <= 32'd0;
            frame_period     <= 32'd0;
            frame_bad_line   <= 1'b0;

            pixel_data       <= 8'd0;
            pixel_valid      <= 1'b0;
            pixel_sof        <= 1'b0;
            pixel_eol        <= 1'b0;
            pixel_x          <= 16'd0;
            pixel_y          <= 16'd0;

            frame_done       <= 1'b0;
            frame_count      <= 32'd0;
            last_frame_period<= 32'd0;
            last_frame_pixels<= 32'd0;
            last_frame_lines <= 16'd0;
            last_line_pixels <= 16'd0;
            bad_line_count   <= 32'd0;
            bad_frame_count  <= 32'd0;
        end else begin
            frame_valid_q <= frame_valid_iob;
            line_valid_q  <= line_valid_iob;
            frame_period  <= frame_period + 1'b1;

            pixel_valid <= 1'b0;
            pixel_sof   <= 1'b0;
            pixel_eol   <= 1'b0;
            frame_done  <= 1'b0;

            if (frame_rise) begin
                if (seen_frame)
                    last_frame_period <= frame_period + 1'b1;
                seen_frame   <= 1'b1;
                frame_period <= 32'd0;
                sensor_x     <= 16'd0;
                line_count   <= 16'd0;
                line_pixels  <= 16'd0;
                frame_pixels <= 32'd0;
                frame_bad_line <= 1'b0;
            end

            if (frame_valid_iob && line_valid_iob) begin
                // FV and LV may rise together, including the first pixel.
                line_pixels  <= frame_rise ? 16'd1 : line_pixels + 1'b1;
                frame_pixels <= frame_rise ? 32'd1 : frame_pixels + 1'b1;

                if (in_output_window) begin
                    pixel_data  <= data_iob;
                    pixel_valid <= 1'b1;
                    pixel_x     <= current_x - X_OFFSET;
                    pixel_y     <= current_y - Y_OFFSET;
                    pixel_sof   <= (current_x == X_OFFSET) &&
                                   (current_y == Y_OFFSET);
                    pixel_eol   <= (current_x == X_OFFSET + OUTPUT_WIDTH - 1);
                end

                sensor_x <= current_x + 1'b1;
            end

            if (line_fall) begin
                last_line_pixels <= line_pixels;
                if (line_pixels != SENSOR_WIDTH) begin
                    bad_line_count <= bad_line_count + 1'b1;
                    frame_bad_line <= 1'b1;
                end
                line_count  <= line_count + 1'b1;
                sensor_x    <= 16'd0;
                line_pixels <= 16'd0;
            end

            if (frame_fall) begin
                frame_done        <= 1'b1;
                frame_count       <= frame_count + 1'b1;
                last_frame_pixels <= frame_pixels;
                // LINE_VALID and FRAME_VALID are allowed to fall together.
                // Include that just-completed line in the frame result.
                last_frame_lines  <= completed_line_count[15:0];
                if (frame_bad_line ||
                    (line_fall && line_pixels != SENSOR_WIDTH) ||
                    (completed_line_count != SENSOR_HEIGHT) ||
                    (frame_pixels != EXPECTED_FRAME_PIXELS))
                    bad_frame_count <= bad_frame_count + 1'b1;
            end

            if (!frame_valid_iob && !frame_rise) begin
                sensor_x    <= 16'd0;
                line_pixels <= 16'd0;
            end
        end
    end
endmodule
