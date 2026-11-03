`timescale 1ns/1ps
module tb_neural_mac;
    reg clk=0;always #10 clk=~clk;
    reg resetn=0;
    reg [17:0] awaddr=0,araddr=0;
    reg [31:0] wdata=0;
    reg [3:0] wstrb=15;
    reg awvalid=0,wvalid=0,bready=0,arvalid=0,rready=0;
    wire awready,wready,bvalid,arready,rvalid;
    wire [1:0] bresp,rresp;
    wire [31:0] rdata;
    neural_mac_axi dut(.aclk(clk),.aresetn(resetn),
        .s_axi_awaddr(awaddr),.s_axi_awprot(3'b0),.s_axi_awvalid(awvalid),.s_axi_awready(awready),
        .s_axi_wdata(wdata),.s_axi_wstrb(wstrb),.s_axi_wvalid(wvalid),.s_axi_wready(wready),
        .s_axi_bresp(bresp),.s_axi_bvalid(bvalid),.s_axi_bready(bready),
        .s_axi_araddr(araddr),.s_axi_arprot(3'b0),.s_axi_arvalid(arvalid),.s_axi_arready(arready),
        .s_axi_rdata(rdata),.s_axi_rresp(rresp),.s_axi_rvalid(rvalid),.s_axi_rready(rready));
    integer count=0;
    task send_aw(input [17:0] a);
        begin @(negedge clk);awaddr=a;awvalid=1;
            do @(posedge clk);while(!awready);
            @(negedge clk);awvalid=0;
        end
    endtask
    task send_w(input [31:0] d,input [3:0] s);
        begin @(negedge clk);wdata=d;wstrb=s;wvalid=1;
            do @(posedge clk);while(!wready);
            @(negedge clk);wvalid=0;
        end
    endtask
    task write_word(input [17:0] a,input [31:0] d,input [1:0] expected,input [3:0] s);
        reg [1:0] held;
        begin
            if(count%3==0)begin send_aw(a);repeat(2)@(negedge clk);send_w(d,s);end
            else if(count%3==1)begin send_w(d,s);repeat(2)@(negedge clk);send_aw(a);end
            else fork send_aw(a);send_w(d,s);join
            while(!bvalid)@(negedge clk);
            if(bresp!==expected)$fatal(1,"write %0d address %h data %h response %d != %d",count,a,d,bresp,expected);
            held=bresp;
            repeat(3)begin @(negedge clk);if(!bvalid || bresp!==held || awready || wready)$fatal(1,"write backpressure");end
            bready=1;@(negedge clk);bready=0;
        end
    endtask
    task read_word(input [17:0] a,output [31:0] value,output [1:0] response);
        begin
            @(negedge clk);araddr=a;arvalid=1;
            do @(posedge clk);while(!arready);
            @(negedge clk);arvalid=0;
            while(!rvalid)@(negedge clk);
            value=rdata;response=rresp;
            repeat(3)begin @(negedge clk);if(!rvalid || rdata!==value || rresp!==response || arready)$fatal(1,"read backpressure");end
            rready=1;@(negedge clk);rready=0;
        end
    endtask
    integer fd,n,code,a,data,resp,strobe,loops,out;
    reg [31:0] value;
    reg [1:0] response;
    initial begin
        repeat(6)@(negedge clk);resetn=1;
        fd=$fopen("commands.hex","r");if(fd==0)$fatal(1,"commands missing");
        while(!$feof(fd))begin
            n=$fscanf(fd,"%h %h %h %h %h\n",code,a,data,resp,strobe);
            if(n!=5)$fatal(1,"command malformed");
            case(code)
                0:write_word(a,data,resp,strobe);
                1:begin read_word(a,value,response);
                    if(response!==resp[1:0] || value!==data)$fatal(1,"read %0d address %h: value %h expected %h resp %d expected %d",count,a,value,data,response,resp);
                end
                2:begin
                    loops=0;value=1;
                    while(value[0] || !value[1])begin
                        read_word('hc,value,response);loops=loops+1;
                        if(value[2] || loops>1000 || response!=0)$fatal(1,"poll failed");
                    end
                end
                4:begin
                    // Reset also cancels a partially received AXI write.
                    send_aw('h10);@(negedge clk);resetn=0;
                    repeat(4)@(negedge clk);resetn=1;
                end
                5:begin
                    @(negedge clk);force dut.cycles=4095;
                    @(negedge clk);release dut.cycles;
                end
                default:$fatal(1,"unknown opcode");
            endcase
            count=count+1;
        end
        $fclose(fd);out=$fopen("PASS.txt","w");$fdisplay(out,"PASS");$fclose(out);
        $display("NN32_PASS commands=%0d",count);$finish;
    end
    initial begin #100000000;$fatal(1,"test watchdog");end
endmodule
