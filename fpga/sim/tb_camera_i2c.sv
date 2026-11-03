`timescale 1ns/1ps
module tb_camera_i2c;
 reg clk=0; always #10 clk=~clk;
 reg resetn=0; reg [1:0] low=0; reg slave_sda=0, slave_scl=0;
 tri1 sda,scl; wire [1:0] state;
 assign sda=slave_sda?1'b0:1'bz;
 assign scl=slave_scl?1'b0:1'bz;
 camera_i2c_pins dut(clk,resetn,low,state,sda,scl);
 task check(input [1:0] expected);
  begin repeat(4) @(negedge clk); if ({scl,sda}!==expected || state!==expected) $fatal(1,"I2C pin mismatch"); end
 endtask
 integer f;
 initial begin
  #30; resetn=1; check(3);
  low=1; check(2); low=2; check(1); low=3; check(0);
  low=0; slave_sda=1; check(2); slave_sda=0;
  slave_scl=1; check(1); slave_scl=0; check(3);
  low=3; resetn=0; #1; if ({scl,sda}!==2'b11) $fatal(1,"reset did not release bus");
  low=0; resetn=1; check(3);
  f=$fopen("i2c_test_result.txt","w");$fdisplay(f,"PASS");$fclose(f);$finish;
 end
 initial begin #100000; $fatal(1,"timeout"); end
endmodule
