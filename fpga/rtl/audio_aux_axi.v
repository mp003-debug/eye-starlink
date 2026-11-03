`timescale 1ns/1ps
// Mono PCM16, 16 kHz, preloaded BRAM. Each sample is held for three 48 kHz
// stereo I2S frames. Codec is clock master; CPU never services per-sample IRQs.
// v2 adds two owned 16384-sample stream banks. Committed banks are immutable;
// freed banks may be refilled while the other plays. Legacy preloading remains.
module audio_aux_axi #(
    parameter integer WATCHDOG_CYCLES = 50000
)(
    (* X_INTERFACE_INFO="xilinx.com:signal:clock:1.0 aclk CLK" *)
    (* X_INTERFACE_PARAMETER="ASSOCIATED_BUSIF s_axi, ASSOCIATED_RESET aresetn, FREQ_HZ 50000000" *) input wire aclk,
    (* X_INTERFACE_INFO="xilinx.com:signal:reset:1.0 aresetn RST" *)
    (* X_INTERFACE_PARAMETER="POLARITY ACTIVE_LOW" *) input wire aresetn,
    input wire [16:0] s_axi_awaddr, input wire [2:0] s_axi_awprot,
    input wire s_axi_awvalid, output wire s_axi_awready,
    input wire [31:0] s_axi_wdata, input wire [3:0] s_axi_wstrb,
    input wire s_axi_wvalid, output wire s_axi_wready,
    output reg [1:0] s_axi_bresp, output reg s_axi_bvalid, input wire s_axi_bready,
    input wire [16:0] s_axi_araddr, input wire [2:0] s_axi_arprot,
    input wire s_axi_arvalid, output wire s_axi_arready,
    output reg [31:0] s_axi_rdata, output reg [1:0] s_axi_rresp,
    output reg s_axi_rvalid, input wire s_axi_rready,
    input wire au_bclk, au_lrclk, mclk_locked,
    output reg au_sdata,
    inout wire au_sda, au_scl,
    input wire [3:0] buttons
);
    (* ASYNC_REG="TRUE" *) reg [1:0] bclk_sync, lr_sync, sda_sync, scl_sync, lock_sync;
    (* ASYNC_REG="TRUE" *) reg [3:0] btn_meta, btn_sync;
    reg bclk_d,bclk_dd,lr_prev;
    wire bit_fall=bclk_dd && !bclk_d;
    reg [31:0] quiet_cycles,bclk_count,frame_count;
    wire clock_alive=quiet_cycles<WATCHDOG_CYCLES && lock_sync[1];
    reg [1:0] i2c_low;
    assign au_sda=i2c_low[0] ? 1'b0 : 1'bz;
    assign au_scl=i2c_low[1] ? 1'b0 : 1'bz;
    reg busy,done,fault,ending;
    reg stream_mode,paused,pause_pending,underrun,ending_fault;
    reg [1:0] bank_ready,bank_last;
    reg [14:0] bank_length [0:1];
    reg [31:0] consumed;
    reg [15:0] length,sample_index;
    reg [1:0] repeat_index;
    reg [15:0] held_sample;
    reg [23:0] shift;
    reg [5:0] bit_index;
    (* ram_style="block" *) reg [31:0] pcm [0:16383];
    reg [31:0] audio_word,cpu_word;
    reg aw_pending,w_pending,read_pending;
    reg [16:0] awaddr;
    reg [31:0] wdata;
    reg [3:0] wstrb;
    wire write_accept=aw_pending && w_pending && !s_axi_bvalid;
    wire memory_allowed=stream_mode ? !bank_ready[awaddr[15]] : !busy;
    wire memory_write=aresetn && write_accept && awaddr[16] && awaddr[1:0]==0 && memory_allowed && wstrb==4'hf;
    assign s_axi_awready=!aw_pending && !s_axi_bvalid;
    assign s_axi_wready=!w_pending && !s_axi_bvalid;
    assign s_axi_arready=!s_axi_rvalid && !read_pending;
    // Dual-port synchronous RAM. It is deliberately not reset into flip-flops.
    always @(posedge aclk) begin
        if(memory_write) pcm[awaddr[15:2]]<=wdata;
        if(s_axi_arvalid && s_axi_arready && s_axi_araddr[16]) cpu_word<=pcm[s_axi_araddr[15:2]];
        audio_word<=pcm[sample_index[14:1]];
    end
    always @(posedge aclk) begin
        if(!aresetn) begin
            bclk_sync<=0;lr_sync<=0;sda_sync<=3;scl_sync<=3;lock_sync<=0;
            btn_meta<=0;btn_sync<=0;bclk_d<=0;bclk_dd<=0;lr_prev<=0;
            quiet_cycles<=WATCHDOG_CYCLES;bclk_count<=0;frame_count<=0;i2c_low<=0;
            busy<=0;done<=0;fault<=0;ending<=0;length<=0;sample_index<=0;repeat_index<=0;
            stream_mode<=0;paused<=0;pause_pending<=0;underrun<=0;ending_fault<=0;
            bank_ready<=0;bank_last<=0;bank_length[0]<=0;bank_length[1]<=0;consumed<=0;
            held_sample<=0;shift<=0;bit_index<=0;au_sdata<=0;
            aw_pending<=0;w_pending<=0;read_pending<=0;awaddr<=0;wdata<=0;wstrb<=0;
            s_axi_bresp<=0;s_axi_bvalid<=0;s_axi_rdata<=0;s_axi_rresp<=0;s_axi_rvalid<=0;
        end else begin
            bclk_sync<={bclk_sync[0],au_bclk};lr_sync<={lr_sync[0],au_lrclk};
            sda_sync<={sda_sync[0],au_sda};scl_sync<={scl_sync[0],au_scl};
            lock_sync<={lock_sync[0],mclk_locked};btn_meta<=buttons;btn_sync<=btn_meta;
            bclk_d<=bclk_sync[1];bclk_dd<=bclk_d;
            if(bit_fall) begin quiet_cycles<=0;bclk_count<=bclk_count+1'b1;end
            else if(quiet_cycles<WATCHDOG_CYCLES) quiet_cycles<=quiet_cycles+1'b1;
            if(bit_fall) begin
                if(lr_sync[1]!=lr_prev) begin
                    lr_prev<=lr_sync[1];bit_index<=0;au_sdata<=0;
                    if(!lr_sync[1]) begin
                        frame_count<=frame_count+1'b1;
                        if(busy && ending) begin
                            busy<=0;ending<=0;paused<=0;pause_pending<=0;shift<=0;held_sample<=0;
                            if(ending_fault) begin fault<=1;underrun<=1;end
                            else done<=1;
                        end else if(busy && stream_mode && (pause_pending || paused)) begin
                            paused<=1;pause_pending<=0;shift<=0;held_sample<=0;
                        end else if(busy) begin
                            held_sample<=sample_index[0] ? audio_word[31:16] : audio_word[15:0];
                            shift<={sample_index[0] ? audio_word[31:16] : audio_word[15:0],8'b0};
                            if(repeat_index==2) begin
                                repeat_index<=0;
                                if(stream_mode) begin
                                    consumed<=consumed+1'b1;
                                    if({1'b0,sample_index[13:0]}+1==bank_length[sample_index[14]]) begin
                                        bank_ready[sample_index[14]]<=0;
                                        if(bank_last[sample_index[14]]) ending<=1;
                                        else if(bank_ready[!sample_index[14]]) sample_index<={1'b0,!sample_index[14],14'b0};
                                        else begin ending<=1;ending_fault<=1;end
                                    end else sample_index<=sample_index+1'b1;
                                end else if(sample_index+1==length) ending<=1;
                                else sample_index<=sample_index+1'b1;
                            end else repeat_index<=repeat_index+1'b1;
                        end else begin
                            shift<=0;held_sample<=0;
                        end
                    end else shift<=busy && !paused ? {held_sample,8'b0} : 24'b0;
                end else begin
                    if(bit_index<24) begin
                        au_sdata<=busy && !paused ? shift[23] : 1'b0;shift<={shift[22:0],1'b0};
                    end else au_sdata<=0;
                    if(bit_index<63)bit_index<=bit_index+1'b1;
                end
            end
            if(busy && !clock_alive) begin busy<=0;ending<=0;paused<=0;pause_pending<=0;fault<=1;au_sdata<=0;shift<=0;held_sample<=0;end
            if(s_axi_awvalid && s_axi_awready) begin awaddr<=s_axi_awaddr;aw_pending<=1;end
            if(s_axi_wvalid && s_axi_wready) begin wdata<=s_axi_wdata;wstrb<=s_axi_wstrb;w_pending<=1;end
            if(s_axi_bvalid && s_axi_bready)s_axi_bvalid<=0;
            if(write_accept) begin
                aw_pending<=0;w_pending<=0;s_axi_bvalid<=1;s_axi_bresp<=0;
                if(awaddr[1:0]!=0 || wstrb!=4'hf)s_axi_bresp<=2;
                else if(awaddr[16]) begin if(!memory_allowed)s_axi_bresp<=2;end
                else case(awaddr)
                    17'h08: begin
                        if(wdata==2) begin busy<=0;ending<=0;paused<=0;pause_pending<=0;bank_ready<=0;au_sdata<=0;shift<=0;held_sample<=0;end
                        else if(wdata==4 && !busy) begin done<=0;fault<=0;underrun<=0;ending_fault<=0;end
                        else if(wdata==8 && busy && stream_mode && !ending) pause_pending<=1;
                        else if(wdata==16 && busy && stream_mode && paused) begin paused<=0;pause_pending<=0;end
                        else if(wdata==1 && !busy && clock_alive && !fault &&
                                (stream_mode ? bank_ready[0] : (length>0 && length<=32768))) begin
                            busy<=1;done<=0;ending<=0;ending_fault<=0;paused<=0;pause_pending<=0;
                            sample_index<=0;repeat_index<=0;held_sample<=0;shift<=0;consumed<=0;
                        end else s_axi_bresp<=2;
                    end
                    17'h10: if(!busy && wdata>0 && wdata<=32768)length<=wdata[15:0];else s_axi_bresp<=2;
                    17'h18: if(wdata<=3)i2c_low<=wdata[1:0];else s_axi_bresp<=2;
                    17'h30: if(!busy && wdata<=1) begin stream_mode<=wdata[0];bank_ready<=0;bank_last<=0;end else s_axi_bresp<=2;
                    17'h38,17'h3c: begin
                        if(stream_mode && !bank_ready[awaddr[2]] && wdata[30:15]==0 && wdata[14:0]>0 && wdata[14:0]<=16384) begin
                            bank_length[awaddr[2]]<=wdata[14:0];bank_last[awaddr[2]]<=wdata[31];bank_ready[awaddr[2]]<=1;
                        end else s_axi_bresp<=2;
                    end
                    default:s_axi_bresp<=2;
                endcase
            end
            if(s_axi_rvalid && s_axi_rready)s_axi_rvalid<=0;
            if(read_pending) begin s_axi_rvalid<=1;s_axi_rresp<=0;s_axi_rdata<=cpu_word;read_pending<=0;end
            if(s_axi_arvalid && s_axi_arready) begin
                s_axi_rresp<=0;
                if(s_axi_araddr[1:0]!=0) begin s_axi_rvalid<=1;s_axi_rresp<=2;s_axi_rdata<=0;end
                else if(s_axi_araddr[16])read_pending<=1;
                else begin
                    s_axi_rvalid<=1;
                    case(s_axi_araddr)
                        17'h00:s_axi_rdata<=32'h41554431;
                        17'h04:s_axi_rdata<=32'h00020000;
                        17'h08:s_axi_rdata<=0;
                        17'h0c:s_axi_rdata<={25'b0,pause_pending,underrun,paused,clock_alive,fault,done,busy};
                        17'h10:s_axi_rdata<={16'b0,length};
                        17'h14:s_axi_rdata<={16'b0,sample_index};
                        17'h18:s_axi_rdata<={30'b0,i2c_low};
                        17'h1c:s_axi_rdata<={29'b0,lock_sync[1],scl_sync[1],sda_sync[1]};
                        17'h20:s_axi_rdata<={28'b0,btn_sync};
                        17'h24:s_axi_rdata<=frame_count;
                        17'h28:s_axi_rdata<=bclk_count;
                        17'h30:s_axi_rdata<={31'b0,stream_mode};
                        17'h34:s_axi_rdata<={29'b0,sample_index[14],bank_ready};
                        17'h38:s_axi_rdata<={bank_last[0],16'b0,bank_length[0]};
                        17'h3c:s_axi_rdata<={bank_last[1],16'b0,bank_length[1]};
                        17'h40:s_axi_rdata<=consumed;
                        default:begin s_axi_rdata<=0;s_axi_rresp<=2;end
                    endcase
                end
            end
        end
    end
endmodule
