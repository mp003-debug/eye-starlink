`timescale 1ns/1ps
module tb_audio_aux;
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
reg prev_lr=1;integer nbits=0,nwords=0;reg [23:0] received=0;reg [23:0] words[0:99];
always @(posedge bclk)begin
    if(prev_lr!=lr)begin prev_lr=lr;nbits=0;received=0;end
    else if(nbits<24)begin
        received={received[22:0],sd};nbits=nbits+1;
        if(nbits==24 && received!=0 && nwords<100)begin words[nwords]=received;nwords=nwords+1;end
    end
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
reg [31:0] value;integer i,fh;
initial begin
    repeat(6)@(negedge clk);rst=1;
    read_reg(0,value);if(value!==32'h41554431)$fatal(1,"identity");
    read_reg('h1c,value);if(value[1:0]!==3)$fatal(1,"I2C not released");
    external_sda=1;repeat(5)@(negedge clk);read_reg('h1c,value);if(value[0]!==0)$fatal(1,"external I2C low");external_sda=0;
    write_reg('h18,3,0);if(sda!==0 || scl!==0)$fatal(1,"I2C low");write_reg('h18,0,0);
    buttons=4'b1010;repeat(5)@(negedge clk);read_reg('h20,value);if(value!==10)$fatal(1,"buttons");
    write_reg('h10,0,2);write_reg('h10,32769,2);
    write_reg('h10000,32'hfedc1234,0);read_reg('h10000,value);if(value!==32'hfedc1234)$fatal(1,"PCM readback");
    write_reg('h10,2,0);write_reg(8,1,0);
    write_reg('h10000,0,2);write_reg('h10,1,2);write_reg(8,1,2);
    #200000;
    read_reg('hc,value);if(value[2:0]!==2)$fatal(1,"not done: %h",value);
    if(nwords!=12)$fatal(1,"wrong I2S word count %d",nwords);
    for(i=0;i<12;i=i+1)if(words[i] !== (i<6 ? 24'h123400 : 24'hfedc00))$fatal(1,"PCM sign/order/repeat error %d %h",i,words[i]);
    write_reg(8,4,0);write_reg('h10,100,0);write_reg(8,1,0);
    #12000;write_reg(8,2,0);repeat(10)@(negedge clk);if(sd!==0)$fatal(1,"stop not silent");
    write_reg(8,1,0);clock_enable=0;#50000;
    read_reg('hc,value);if(value[3:0]!==4)$fatal(1,"clock loss did not stop and latch fault %h",value);
    if(sd!==0)$fatal(1,"clock-loss output not silent");
    write_reg(8,1,2);
    rst=0;repeat(5)@(negedge clk);if(sd!==0 || sda!==1 || scl!==1)$fatal(1,"reset not silent/released");
    fh=$fopen("audio_test_result.txt","w");$fdisplay(fh,"PASS");$fclose(fh);
    $display("PASS audio PCM/I2S AXI ownership timeout and buttons");$finish;
end
initial begin #1000000;$fatal(1,"test timeout");end
endmodule
