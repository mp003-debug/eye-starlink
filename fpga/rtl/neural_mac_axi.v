`timescale 1ns/1ps
// 32 useful signed int8 MAC lanes. PS performs scaling, bias and activation.
// Weights: 4096 rows x 32 lanes; sequential full-word upload, banked BRAM.
// Inputs: 2048 signed bytes. AXI-Lite AW/W may arrive independently.
module neural_mac_axi #(
    parameter integer WATCHDOG_CYCLES=4096
)(
    (* X_INTERFACE_INFO="xilinx.com:signal:clock:1.0 aclk CLK" *)
    (* X_INTERFACE_PARAMETER="ASSOCIATED_BUSIF s_axi, ASSOCIATED_RESET aresetn, FREQ_HZ 50000000" *) input wire aclk,
    (* X_INTERFACE_INFO="xilinx.com:signal:reset:1.0 aresetn RST" *)
    (* X_INTERFACE_PARAMETER="POLARITY ACTIVE_LOW" *) input wire aresetn,
    input wire [17:0] s_axi_awaddr, input wire [2:0] s_axi_awprot,
    input wire s_axi_awvalid, output wire s_axi_awready,
    input wire [31:0] s_axi_wdata, input wire [3:0] s_axi_wstrb,
    input wire s_axi_wvalid, output wire s_axi_wready,
    output reg [1:0] s_axi_bresp, output reg s_axi_bvalid, input wire s_axi_bready,
    input wire [17:0] s_axi_araddr, input wire [2:0] s_axi_arprot,
    input wire s_axi_arvalid, output wire s_axi_arready,
    output reg [31:0] s_axi_rdata, output reg [1:0] s_axi_rresp,
    output reg s_axi_rvalid, input wire s_axi_rready
);
    reg aw_pending,w_pending;
    reg [17:0] awaddr;
    reg [31:0] wdata;
    reg [3:0] wstrb;
    reg busy,done,fault;
    reg [11:0] length,base;
    reg [5:0] outputs;
    reg [15:0] weight_words;
    reg [9:0] input_words;
    reg [11:0] issued,retired;
    reg [31:0] cycles;
    reg read_valid,product_valid;
    wire accept=aw_pending && w_pending && !s_axi_bvalid;
    wire aligned=awaddr[1:0]==0 && wstrb==4'hf;
    wire [17:0] woffset=awaddr-18'h10000;
    wire wregion=awaddr>=18'h10000 && awaddr<18'h30000;
    wire wsequence=woffset[17:2]==0 || woffset[17:2]==weight_words;
    wire weight_write=aresetn && accept && aligned && !busy && wregion && wsequence;
    wire iregion=awaddr>=18'h01000 && awaddr<18'h01800;
    wire isequence=awaddr[10:2]==0 || {1'b0,awaddr[10:2]}==input_words;
    wire input_write=aresetn && accept && aligned && !busy && iregion && isequence;
    wire issue=busy && issued<length;
    wire [11:0] weight_address=base+issued;
    wire abort_now=accept && aligned && awaddr==18'h8 && wdata==2;
    wire start_ok=!busy && !fault && length>0 && length<=2048 && outputs>0 && outputs<=32 &&
                  ({1'b0,base}+{1'b0,length})<=({1'b0,weight_words}>>3) &&
                  {input_words,2'b00}>={1'b0,length};
    assign s_axi_awready=aresetn && !aw_pending && !s_axi_bvalid;
    assign s_axi_wready=aresetn && !w_pending && !s_axi_bvalid;
    assign s_axi_arready=aresetn && !s_axi_rvalid;
    (* ram_style="block" *) reg [31:0] inputs [0:511];
    reg [31:0] input_read;
    reg [1:0] byte_select;
    wire signed [7:0] activation=input_read >> (8*byte_select);
    wire signed [31:0] accumulator [0:31];
    always @(posedge aclk) begin
        if(input_write) inputs[awaddr[10:2]]<=wdata;
        if(issue) begin input_read<=inputs[issued[10:2]];byte_select<=issued[1:0];end
    end
    genvar lane;
    generate for(lane=0;lane<32;lane=lane+1) begin: lanes
        (* ram_style="block" *) reg signed [7:0] weights [0:4095];
        reg signed [7:0] weight_read;
        (* use_dsp="yes" *) reg signed [15:0] product;
        (* use_dsp="yes" *) reg signed [31:0] accum;
        assign accumulator[lane]=accum;
        always @(posedge aclk) begin
            if(weight_write && woffset[4:2]==lane/4)
                weights[woffset[16:5]]<=wdata[(lane%4)*8+:8];
            if(issue) weight_read<=weights[weight_address];
        end
        always @(posedge aclk) begin
            if(!aresetn) begin product<=0;accum<=0;end
            else if(abort_now || (accept && aligned && awaddr==8 && wdata==1 && start_ok)) begin
                product<=0;accum<=0;
            end else if(busy) begin
                if(read_valid) product<=activation*weight_read;
                if(product_valid) accum<=accum+{{16{product[15]}},product};
            end
        end
    end endgenerate
    always @(posedge aclk) begin
        if(!aresetn) begin
            aw_pending<=0;w_pending<=0;awaddr<=0;wdata<=0;wstrb<=0;
            s_axi_bvalid<=0;s_axi_bresp<=0;s_axi_rvalid<=0;s_axi_rresp<=0;s_axi_rdata<=0;
            busy<=0;done<=0;fault<=0;length<=0;base<=0;outputs<=0;
            weight_words<=0;input_words<=0;issued<=0;retired<=0;cycles<=0;
            read_valid<=0;product_valid<=0;
        end else begin
            read_valid<=issue;product_valid<=read_valid && busy;
            if(issue) issued<=issued+1'b1;
            if(busy) begin
                cycles<=cycles+1'b1;
                if(product_valid) begin
                    retired<=retired+1'b1;
                    if(retired+1==length) begin busy<=0;done<=1;end
                end
                if(cycles>=WATCHDOG_CYCLES-1) begin busy<=0;done<=0;fault<=1;read_valid<=0;product_valid<=0;end
            end
            if(s_axi_awvalid && s_axi_awready) begin awaddr<=s_axi_awaddr;aw_pending<=1;end
            if(s_axi_wvalid && s_axi_wready) begin wdata<=s_axi_wdata;wstrb<=s_axi_wstrb;w_pending<=1;end
            if(s_axi_bvalid && s_axi_bready)s_axi_bvalid<=0;
            if(accept) begin
                aw_pending<=0;w_pending<=0;s_axi_bvalid<=1;s_axi_bresp<=0;
                if(!aligned)s_axi_bresp<=2;
                else if(wregion) begin
                    if(weight_write) begin weight_words<=woffset[17:2]+1'b1;done<=0;end
                    else s_axi_bresp<=2;
                end else if(iregion) begin
                    if(input_write) begin input_words<={1'b0,awaddr[10:2]}+1'b1;done<=0;end
                    else s_axi_bresp<=2;
                end else case(awaddr)
                    18'h08: begin
                        if(wdata==2) begin busy<=0;done<=0;fault<=1;read_valid<=0;product_valid<=0;end
                        else if(wdata==4 && !busy) begin
                            done<=0;fault<=0;weight_words<=0;input_words<=0;length<=0;base<=0;outputs<=0;
                        end else if(wdata==1 && start_ok) begin
                            busy<=1;done<=0;issued<=0;retired<=0;cycles<=0;read_valid<=0;product_valid<=0;
                        end else s_axi_bresp<=2;
                    end
                    18'h10: if(!busy && wdata>0 && wdata<=2048) length<=wdata[11:0];else s_axi_bresp<=2;
                    18'h14: if(!busy && wdata<4096) base<=wdata[11:0];else s_axi_bresp<=2;
                    18'h18: if(!busy && wdata>0 && wdata<=32) outputs<=wdata[5:0];else s_axi_bresp<=2;
                    default:s_axi_bresp<=2;
                endcase
            end
            if(s_axi_rvalid && s_axi_rready)s_axi_rvalid<=0;
            if(s_axi_arvalid && s_axi_arready) begin
                s_axi_rvalid<=1;s_axi_rdata<=0;s_axi_rresp<=0;
                if(s_axi_araddr[1:0]!=0)s_axi_rresp<=2;
                else if(s_axi_araddr>=18'h2000 && s_axi_araddr<18'h2080) begin
                    if(done && !busy && !fault && {1'b0,s_axi_araddr[6:2]}<outputs)
                        s_axi_rdata<=accumulator[s_axi_araddr[6:2]];
                    else s_axi_rresp<=2;
                end else case(s_axi_araddr)
                    18'h00:s_axi_rdata<=32'h4e4e3332;
                    18'h04:s_axi_rdata<=32'h00010000;
                    18'h0c:s_axi_rdata<={29'b0,fault,done,busy};
                    18'h10:s_axi_rdata<={20'b0,length};
                    18'h14:s_axi_rdata<={20'b0,base};
                    18'h18:s_axi_rdata<={26'b0,outputs};
                    18'h1c:s_axi_rdata<={19'b0,weight_words[15:3]};
                    18'h20:s_axi_rdata<={22'b0,input_words};
                    18'h24:s_axi_rdata<=cycles;
                    default:s_axi_rresp<=2;
                endcase
            end
        end
    end
endmodule
