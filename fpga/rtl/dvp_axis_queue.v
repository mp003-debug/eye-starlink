`timescale 1ns/1ps
// One complete cropped frame per enable assertion. Drain independently of
// enable; rearm only after a low request AND an empty queue. Faults latch until
// overlay reset. Backpressure must never splice parts of different frames.
module dvp_axis_queue #(parameter LGDEPTH=10) (
    input wire clk, rst_n, enable,
    input wire [7:0] pixel_data,
    input wire pixel_valid, pixel_sof, pixel_eol, pixel_eof, frame_done,
    output wire [7:0] m_axis_tdata,
    output wire m_axis_tuser, m_axis_tlast, m_axis_tvalid,
    input wire m_axis_tready,
    output reg overflow,
    output reg rearm_ready
);
    localparam DEPTH = 1 << LGDEPTH;
    (* ram_style="distributed" *) reg [9:0] queue [0:DEPTH-1];
    reg [LGDEPTH-1:0] wr_ptr, rd_ptr;
    reg [LGDEPTH:0] count;
    reg active, armed;
    wire pop = m_axis_tvalid && m_axis_tready;
    wire start_frame = armed && pixel_sof;
    wire malformed = active && ((pixel_valid && pixel_sof) || frame_done);
    wire offered = enable && !overflow && !malformed && pixel_valid && (active || start_frame);
    wire push = offered && ((count < DEPTH) || pop);
    assign {m_axis_tuser,m_axis_tlast,m_axis_tdata} = queue[rd_ptr];
    assign m_axis_tvalid = count != 0;
    always @(posedge clk) begin
        if (!rst_n) begin
            wr_ptr<=0; rd_ptr<=0; count<=0; active<=0; armed<=0; overflow<=0; rearm_ready<=0;
        end else begin
            // Register the combined condition before its two-flop CDC.
            rearm_ready <= !enable && !active && armed && count == 0 && !overflow;
            if (!enable) begin
                active<=0;
                if (count == 0 && !overflow) armed<=1;
            end
            if (push) begin
                queue[wr_ptr] <= {pixel_sof,pixel_eol,pixel_data};
                wr_ptr <= wr_ptr+1'b1;
                if (start_frame) begin armed<=0; active<=1; end
                if (pixel_eof) active<=0;
            end
            if (malformed || (offered && !push)) begin
                overflow<=1; active<=0; armed<=0;
            end
            if (pop) rd_ptr<=rd_ptr+1'b1;
            case ({push,pop})
                2'b10: count<=count+1'b1;
                2'b01: count<=count-1'b1;
                default: count<=count;
            endcase
        end
    end
endmodule
