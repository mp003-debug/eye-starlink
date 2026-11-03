`timescale 1ns/1ps
module tb_capture_queue;
    reg clk=0; always #5 clk=~clk;
    reg rst_n=0,enable=0,pixel_valid=0,pixel_sof=0,pixel_eol=0,pixel_eof=0,frame_done=0,ready=1;
    reg [7:0] pixel_data=0;
    wire [7:0] data; wire user,last,valid,fault,rearm;
    dvp_axis_queue #(.LGDEPTH(3)) dut(.clk(clk),.rst_n(rst_n),.enable(enable),
      .pixel_data(pixel_data),.pixel_valid(pixel_valid),.pixel_sof(pixel_sof),
      .pixel_eol(pixel_eol),.pixel_eof(pixel_eof),.frame_done(frame_done),
      .m_axis_tdata(data),.m_axis_tuser(user),.m_axis_tlast(last),.m_axis_tvalid(valid),
      .m_axis_tready(ready),.overflow(fault),.rearm_ready(rearm));
    integer n=0,i,f; reg [9:0] received[0:255];
    reg held=0; reg [9:0] held_value;
    always @(posedge clk) begin
        if (!rst_n) held<=0;
        else begin
            if (held && (!valid || {user,last,data} !== held_value)) $fatal(1,"AXIS changed while stalled");
            held<=valid&&!ready; held_value<={user,last,data};
            if (valid&&ready) begin received[n]={user,last,data}; n=n+1; end
        end
    end
    task idle(input integer cycles); begin
        @(negedge clk);pixel_valid=0;pixel_sof=0;pixel_eol=0;pixel_eof=0;frame_done=0;
        repeat(cycles) @(negedge clk);
    end endtask
    task reset; begin
        @(negedge clk);rst_n=0;enable=0;ready=1;pixel_valid=0;frame_done=0;
        repeat(3) @(negedge clk);rst_n=1;n=0;idle(3);
        if(!rearm||fault) $fatal(1,"reset rearm");
    end endtask
    task frame(input integer tag); begin
        for(integer k=0;k<8;k=k+1) begin
            @(negedge clk);pixel_valid=1;pixel_sof=(k==0);pixel_eol=(k%4==3);
            pixel_eof=(k==7);pixel_data=tag+k;
        end
        idle(1);frame_done=1;idle(2);
    end endtask
    task check_frame(input integer start,input integer tag); begin
        for(integer k=0;k<8;k=k+1)
            if(received[start+k] !== {1'(k==0),1'(k%4==3),8'(tag+k)}) $fatal(1,"mixed data/framing at %0d",k);
    end endtask
    initial begin
        reset();enable=1;frame(16);frame(48);idle(12);
        if(n!=8||fault||rearm) $fatal(1,"held enable admitted second frame");check_frame(0,16);
        enable=0;idle(3);if(!rearm)$fatal(1,"cannot rearm");
        enable=1;frame(80);idle(12);if(n!=16||fault)$fatal(1,"second request");check_frame(8,80);
        // A full frame may drain after request is lowered, without truncation.
        reset();ready=0;enable=1;frame(112);enable=0;idle(3);
        if(rearm||fault||n!=0)$fatal(1,"rearmed with pending data");
        ready=1;idle(12);if(!rearm||n!=8)$fatal(1,"drain not acknowledged");check_frame(0,112);
        // Enable in the middle of a frame: ignore until the next SOF.
        reset();pixel_valid=1;pixel_sof=0;pixel_eof=0;pixel_eol=0;enable=1;
        repeat(5) @(negedge clk);idle(3);if(n!=0)$fatal(1,"partial frame accepted");
        frame(144);idle(12);check_frame(0,144);
        // Fatal overflow remains latched across low/high requests.
        reset();ready=0;enable=1;
        for(i=0;i<10;i=i+1)begin
            @(negedge clk);pixel_valid=1;pixel_sof=(i==0);pixel_eol=0;pixel_eof=0;pixel_data=i;
        end
        idle(2);if(!fault)$fatal(1,"overflow not detected");enable=0;ready=1;idle(15);
        if(rearm)$fatal(1,"fault rearmed");i=n;enable=1;frame(176);idle(12);
        if(n!=i||!fault)$fatal(1,"fault permitted new pixels");
        // Incomplete frame and unexpected SOF cannot splice into a later frame.
        reset();enable=1;@(negedge clk);pixel_valid=1;pixel_sof=1;pixel_eof=0;pixel_eol=0;
        idle(1);frame_done=1;idle(2);if(!fault)$fatal(1,"short frame undetected");
        reset();enable=1;@(negedge clk);pixel_valid=1;pixel_sof=1;pixel_eof=0;
        idle(2);@(negedge clk);pixel_valid=1;pixel_sof=1;idle(2);
        if(!fault)$fatal(1,"second SOF undetected");
        f=$fopen("capture_test_result.txt","w");$fdisplay(f,"PASS");$fclose(f);
        $display("PASS: bounded frames, rearm, stall stability, overflow and malformed frame rejection");$finish;
    end
    initial begin #100000; $fatal(1,"simulation watchdog"); end
endmodule
