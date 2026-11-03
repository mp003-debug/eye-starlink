`timescale 1ns/1ps
module tb_display;
    reg clk=0; always #5 clk=~clk;
    reg rst_n=0, enable=0, de=0;
    reg [9:0] x=0,y=0;
    reg [15:0] data=0;
    reg user=0,last=0,valid=0;
    wire ready,locked,underflow,format_error;
    wire [15:0] pixel;
    wire [7:0] red,green,blue;
    reg [15:0] probe=0;
    wire [7:0] pr,pg,pb;
    integer i, result_file;
    function automatic integer absolute(input integer value);
      absolute = value < 0 ? -value : value;
    endfunction
    axis_video_sink #(.WIDTH(4),.HEIGHT(2)) dut (.clk(clk),.rst_n(rst_n),.enable(enable),
       .x(x),.y(y),.de(de),.s_axis_tdata(data),.s_axis_tuser(user),.s_axis_tlast(last),
       .s_axis_tvalid(valid),.s_axis_tready(ready),.pixel(pixel),.locked(locked),
       .underflow(underflow),.format_error(format_error));
    rgb565_to_rgb888 color (.pixel(pixel),.red(red),.green(green),.blue(blue));
    rgb565_to_rgb888 exhaustive (.pixel(probe),.red(pr),.green(pg),.blue(pb));
    task reset_sink;
      begin
        @(negedge clk);rst_n=0;enable=0;de=0;valid=0;
        repeat(2) @(negedge clk);
        rst_n=1;enable=1;
      end
    endtask
    task send_pixel(input integer px, input integer py, input [15:0] value,
                    input bit sof, input bit eol, input bit present);
      begin
        @(negedge clk);x=px;y=py;de=1;data=value;user=sof;last=eol;valid=present;
        @(posedge clk);#1;
      end
    endtask
    initial begin
      // Every codeword reaches the corresponding 8-bit endpoints with <=1 LSB
      // error relative to ideal full-range rescaling (independent arithmetic oracle).
      for(i=0;i<65536;i=i+1) begin
        probe=i;#1;
        if (absolute(integer'(pr)-((i/2048)*255/31))>1 ||
            absolute(integer'(pg)-(((i/32)%64)*255/63))>1 ||
            absolute(integer'(pb)-((i%32)*255/31))>1) $fatal(1,"RGB expansion mismatch");
      end
      reset_sink();
      send_pixel(0,0,16'hFFFF,1,0,0);
      if(locked || underflow || format_error || pixel!==0) $fatal(1,"late acquisition fault");
      send_pixel(0,0,16'hF800,1,0,1);
      if(!locked || pixel!==16'hF800 || red!==255 || green!==0 || blue!==0) $fatal(1,"red first pixel");
      send_pixel(1,0,16'h07E0,0,0,1);
      if(red!==0 || green!==255 || blue!==0) $fatal(1,"green packing");
      send_pixel(2,0,16'h001F,0,0,1);
      if(red!==0 || green!==0 || blue!==255) $fatal(1,"blue packing");
      send_pixel(3,0,16'hFFFF,0,1,1);
      @(negedge clk);de=0;#1;if(ready) $fatal(1,"consumed blanking");
      send_pixel(0,1,16'h1234,0,0,1);
      if(pixel!==16'h1234) $fatal(1,"second row corrupt");
      send_pixel(1,1,16'hABCD,0,0,1);
      send_pixel(2,1,16'h6789,0,0,1);
      send_pixel(3,1,16'h8410,0,1,1);
      if(underflow || format_error || pixel!==16'h8410) $fatal(1,"frame failed");
      send_pixel(0,0,16'hFFFF,1,0,1);
      send_pixel(1,0,16'hFFFF,0,0,0);
      if(!underflow || locked || pixel!==0) $fatal(1,"underflow not blacked out");
      send_pixel(2,0,16'hFFFF,0,0,1);
      if(ready || pixel!==0) $fatal(1,"fault did not latch");
      reset_sink();
      send_pixel(0,0,16'hFFFF,0,0,1);
      if(!format_error || pixel!==0) $fatal(1,"missing SOF accepted");
      reset_sink();
      send_pixel(0,0,16'hFFFF,1,1,1);
      if(!format_error || pixel!==0) $fatal(1,"early EOL accepted");
      reset_sink();
      send_pixel(0,0,16'hFFFF,1,0,1);
      @(negedge clk);enable=0;
      @(posedge clk);#1;
      if(ready || locked || pixel!==0) $fatal(1,"disable not blacked out");
      result_file=$fopen("display_test_result.txt","w");
      if(result_file==0) $fatal(1,"cannot write simulation result");
      $fdisplay(result_file,"PASS");$fclose(result_file);
      $display("DISPLAY_TEST_PASS: 65536 RGB565 codes; framing, blanking, acquisition and faults");
      $finish;
    end
    initial begin #1000000;$fatal(1,"simulation timeout");end
endmodule
