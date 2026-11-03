`timescale 1ns/1ps
module tb_audio_stream;
reg clk=0,rst=0;always #10 clk=~clk;
reg [16:0] aw=0,ar=0;reg av=0,wv=0,br=0,arv=0,rr=0;
reg [31:0] wd=0;reg [3:0] ws=15;
wire awr,wr,bv,arr,rv;wire [1:0] bp,rp;wire [31:0] rd;
reg bclk=0,lr=1,locked=1,clock_enable=1;
reg [3:0] buttons=0;
tri1 sda,scl;wire sd;reg external_sda=0;
assign sda=external_sda ? 1'b0:1'bz;
audio_aux_axi #(.WATCHDOG_CYCLES(2000)) dut(
.aclk(clk),.aresetn(rst),.s_axi_awaddr(aw),.s_axi_awprot(3'b0),.s_axi_awvalid(av),.s_axi_awready(awr),
.s_axi_wdata(wd),.s_axi_wstrb(ws),.s_axi_wvalid(wv),.s_axi_wready(wr),.s_axi_bresp(bp),.s_axi_bvalid(bv),.s_axi_bready(br),
.s_axi_araddr(ar),.s_axi_arprot(3'b0),.s_axi_arvalid(arv),.s_axi_arready(arr),.s_axi_rdata(rd),.s_axi_rresp(rp),.s_axi_rvalid(rv),.s_axi_rready(rr),
.au_bclk(bclk),.au_lrclk(lr),.mclk_locked(locked),.au_sdata(sd),.au_sda(sda),.au_scl(scl),.buttons(buttons));
always #163 if(clock_enable)bclk=~bclk;
integer bitpos=0;
always @(negedge bclk)begin
    if(bitpos==0)lr=0;
    if(bitpos==32)lr=1;
    bitpos=(bitpos+1)%64;
end
task write_reg(input [16:0] address,input [31:0] data,input [1:0] expected);
begin
    // Deliberately send W before AW; independently stalled responses.
    @(negedge clk);wd=data;wv=1;
    do @(posedge clk);while(!wr);
    @(negedge clk);wv=0;
    repeat(2)@(negedge clk);aw=address;av=1;
    do @(posedge clk);while(!awr);
    @(negedge clk);av=0;
    while(!bv)@(negedge clk);
    if(bp!==expected)$fatal(1,"bad write response at %h: %b",address,bp);
    repeat(3)begin @(negedge clk);if(!bv || bp!==expected)$fatal(1,"B response not held");end
    br=1;@(negedge clk);br=0;
end endtask
task read_reg(input [16:0] address,output [31:0] data);
begin
    @(negedge clk);ar=address;arv=1;
    do @(posedge clk);while(!arr);
    @(negedge clk);arv=0;
    while(!rv)@(negedge clk);
    if(rp!==0)$fatal(1,"read failed at %h",address);
    data=rd;
    repeat(3)begin @(negedge clk);if(!rv || rd!==data)$fatal(1,"R response not held");end
    rr=1;@(negedge clk);rr=0;
end endtask

integer samples_seen=0,channel_repeats=0,stream_words=0;
reg monitoring=0,allow_silence=0,saw_first=0;
reg prev_lr=1;integer nbits=0;reg [23:0] received=0;
function [15:0] pattern(input integer index);
    pattern=16'h1001+(index%4095);
endfunction
always @(posedge bclk) begin
    if(prev_lr!=lr)begin prev_lr=lr;nbits=0;received=0;end
    else if(nbits<24)begin
        received={received[22:0],sd};nbits=nbits+1;
        if(nbits==24 && monitoring)begin
            if(received!=0 || (saw_first && !allow_silence && dut.busy))begin
                saw_first=1;
                if(received!=={pattern(samples_seen),8'b0})
                    $fatal(1,"stream mismatch sample=%d repeat=%d got=%h",samples_seen,channel_repeats,received);
                stream_words=stream_words+1;
                if(channel_repeats==5)begin samples_seen=samples_seen+1;channel_repeats=0;end
                else channel_repeats=channel_repeats+1;
            end
        end
    end
end

task fill_bank(input integer bank,input integer first,input integer count,input integer last);
integer j;reg [31:0] pair;
begin
    for(j=0;j<count;j=j+2)begin
        pair={pattern(first+j+1),pattern(first+j)};
        write_reg(17'h10000+bank*32768+j*2,pair,0);
    end
    write_reg(17'h38+bank*4,count | (last ? 32'h80000000:0),0);
end endtask
reg [31:0] value,position;integer i,fh;
initial begin
    repeat(6)@(negedge clk);rst=1;
    read_reg(4,value);if(value!==32'h00020000)$fatal(1,"version");
    write_reg('h30,1,0);
    write_reg('h38,0,2);write_reg('h38,16385,2);
    fill_bank(0,0,16384,0);fill_bank(1,16384,16384,0);
    write_reg('h10000,0,2);write_reg('h18000,0,2);write_reg('h38,1,2);
    monitoring=1;write_reg(8,1,0);
    // Pause at a frame boundary, preserve repeat phase, then resume without loss.
    wait(samples_seen>=23);allow_silence=1;write_reg(8,8,0);
    wait(dut.paused);read_reg('h40,position);
    #180000;read_reg('h40,value);if(value!==position || sd!==0)$fatal(1,"pause consumed samples");
    write_reg(8,16,0);wait(samples_seen>=25);allow_silence=0;
    wait(dut.bank_ready[0]==0);fill_bank(0,32768,16384,0);
    wait(dut.bank_ready[1]==0);fill_bank(1,49152,7,1);
    wait(!dut.busy);#15000;
    if(samples_seen!=49159 || channel_repeats!=0 || stream_words!=49159*6)$fatal(1,"length/repeat error %d",samples_seen);
    read_reg('hc,value);if(value[6:0]!==10)$fatal(1,"not clean done %h",value);
    read_reg('h40,value);if(value!=49159)$fatal(1,"consumed count");
    monitoring=0;
    // Missing next bank must drain the last stereo frame then latch underflow.
    write_reg(8,2,0);write_reg(8,4,0);write_reg('h30,1,0);
    fill_bank(0,0,3,0);write_reg(8,1,0);wait(!dut.busy);
    read_reg('hc,value);if(value[5:0]!==44 || sd!==0)$fatal(1,"underflow not fail-closed %h",value);
    write_reg(8,1,2);
    // Clock loss while paused also fails closed, and STOP releases descriptors.
    write_reg(8,2,0);write_reg(8,4,0);fill_bank(0,0,100,1);write_reg(8,1,0);
    write_reg(8,8,0);wait(dut.paused);clock_enable=0;#50000;
    read_reg('hc,value);if(value[4:0]!==4)$fatal(1,"paused clock loss %h",value);
    write_reg(8,2,0);read_reg('h34,value);if(value[1:0]!=0)$fatal(1,"STOP ownership");
    rst=0;repeat(5)@(negedge clk);if(sd!==0 || sda!==1 || scl!==1)$fatal(1,"reset");
    fh=$fopen("audio_stream_result.txt","w");$fdisplay(fh,"PASS");$fclose(fh);
    $display("PASS streaming 49159 samples, bank reuse, pause/resume, underflow and clock loss");$finish;
end
initial begin #4000000000.0;$fatal(1,"stream timeout");end
endmodule
