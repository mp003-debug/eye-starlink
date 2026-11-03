`timescale 1ns/1ps
// AXI4-Lite diagnostic mailbox. One writer must own the snapshot command.
// The camera holds its bundled mailbox until the next accepted request.
// ACK passes two synchronizers, then an extra settle cycle before bus capture.
module camera_diag_axi (
    (* X_INTERFACE_INFO="xilinx.com:signal:clock:1.0 aclk CLK" *)
    (* X_INTERFACE_PARAMETER="ASSOCIATED_BUSIF s_axi, ASSOCIATED_RESET aresetn, FREQ_HZ 50000000" *)
    input wire aclk,
    (* X_INTERFACE_INFO="xilinx.com:signal:reset:1.0 aresetn RST" *)
    (* X_INTERFACE_PARAMETER="POLARITY ACTIVE_LOW" *) input wire aresetn,
    input wire [7:0] s_axi_awaddr, input wire [2:0] s_axi_awprot,
    input wire s_axi_awvalid, output wire s_axi_awready,
    input wire [31:0] s_axi_wdata, input wire [3:0] s_axi_wstrb,
    input wire s_axi_wvalid, output wire s_axi_wready,
    output reg [1:0] s_axi_bresp, output reg s_axi_bvalid,
    input wire s_axi_bready,
    input wire [7:0] s_axi_araddr, input wire [2:0] s_axi_arprot,
    input wire s_axi_arvalid, output wire s_axi_arready,
    output reg [31:0] s_axi_rdata, output reg [1:0] s_axi_rresp,
    output reg s_axi_rvalid, input wire s_axi_rready,
    (* X_INTERFACE_INFO="xilinx.com:signal:clock:1.0 pclk CLK" *)
    (* X_INTERFACE_PARAMETER="ASSOCIATED_RESET cam_rst_n, FREQ_HZ 24000000" *) input wire pclk,
    (* X_INTERFACE_INFO="xilinx.com:signal:reset:1.0 cam_rst_n RST" *)
    (* X_INTERFACE_PARAMETER="POLARITY ACTIVE_LOW" *) input wire cam_rst_n,
    input wire [31:0] frame_count, frame_period, frame_pixels,
    input wire [15:0] frame_lines, line_pixels,
    input wire [31:0] bad_lines, bad_frames
);
    reg request_toggle;
    (* ASYNC_REG = "TRUE" *) reg [1:0] request_sync;
    reg ack_toggle;
    (* ASYNC_REG = "TRUE" *) reg [1:0] ack_sync;
    reg [31:0] camera_ticks;
    (* KEEP = "TRUE" *) reg [223:0] camera_mailbox;
    reg [223:0] snapshot;
    reg busy, valid, settling;
    reg [31:0] sequence_id;

    always @(posedge pclk) begin
        if (!cam_rst_n) begin
            request_sync <= 0;
            ack_toggle <= 0;
            camera_ticks <= 0;
            camera_mailbox <= 0;
        end else begin
            request_sync <= {request_sync[0], request_toggle};
            camera_ticks <= camera_ticks + 1'b1;
            if (request_sync[1] != ack_toggle) begin
                camera_mailbox <= {camera_ticks, bad_frames, bad_lines,
                    frame_lines, line_pixels, frame_pixels, frame_period, frame_count};
                ack_toggle <= request_sync[1];
            end
        end
    end

    reg aw_pending, w_pending;
    reg [7:0] awaddr;
    reg [31:0] wdata;
    reg [3:0] wstrb;
    assign s_axi_awready = !aw_pending && !s_axi_bvalid;
    assign s_axi_wready = !w_pending && !s_axi_bvalid;
    assign s_axi_arready = !s_axi_rvalid;

    always @(posedge aclk) begin
        if (!aresetn) begin
            request_toggle <= 0;
            ack_sync <= 0;
            snapshot <= 0;
            busy <= 0; valid <= 0; settling <= 0; sequence_id <= 0;
            aw_pending <= 0; w_pending <= 0;
            awaddr <= 0; wdata <= 0; wstrb <= 0;
            s_axi_bvalid <= 0; s_axi_bresp <= 0;
            s_axi_rvalid <= 0; s_axi_rresp <= 0; s_axi_rdata <= 0;
        end else begin
            ack_sync <= {ack_sync[0], ack_toggle};
            if (busy && ack_sync[1] == request_toggle) begin
                if (!settling) settling <= 1;
                else begin
                    snapshot <= camera_mailbox;
                    sequence_id <= sequence_id + 1'b1;
                    busy <= 0; valid <= 1; settling <= 0;
                end
            end
            // AW and W may arrive independently, in either order.
            if (s_axi_awvalid && s_axi_awready) begin
                awaddr <= s_axi_awaddr; aw_pending <= 1;
            end
            if (s_axi_wvalid && s_axi_wready) begin
                wdata <= s_axi_wdata; wstrb <= s_axi_wstrb; w_pending <= 1;
            end
            if (s_axi_bvalid && s_axi_bready) s_axi_bvalid <= 0;
            if (aw_pending && w_pending && !s_axi_bvalid) begin
                aw_pending <= 0; w_pending <= 0;
                s_axi_bvalid <= 1;
                s_axi_bresp <= 2'b00;
                if (awaddr != 8'h08) s_axi_bresp <= 2'b10;
                else if (wstrb[0] && wdata[0]) begin
                    if (busy) s_axi_bresp <= 2'b10;
                    else begin
                        request_toggle <= !request_toggle;
                        busy <= 1; settling <= 0;
                    end
                end
            end
            if (s_axi_rvalid && s_axi_rready) s_axi_rvalid <= 0;
            if (s_axi_arvalid && s_axi_arready) begin
                s_axi_rvalid <= 1;
                s_axi_rresp <= 0;
                case (s_axi_araddr)
                    8'h00: s_axi_rdata <= 32'h45594531; // EYE1
                    8'h04: s_axi_rdata <= 32'h00010003;
                    8'h08: s_axi_rdata <= 0;
                    8'h0c: s_axi_rdata <= {30'd0, valid, busy};
                    8'h10: s_axi_rdata <= sequence_id;
                    8'h14: s_axi_rdata <= snapshot[31:0];
                    8'h18: s_axi_rdata <= snapshot[63:32];
                    8'h1c: s_axi_rdata <= snapshot[95:64];
                    8'h20: s_axi_rdata <= snapshot[127:96];
                    8'h24: s_axi_rdata <= snapshot[159:128];
                    8'h28: s_axi_rdata <= snapshot[191:160];
                    8'h2c: s_axi_rdata <= snapshot[223:192];
                    8'h30: s_axi_rdata <= 32'd24000000;
                    default: begin s_axi_rdata <= 0; s_axi_rresp <= 2'b10; end
                endcase
            end
        end
    end
endmodule
