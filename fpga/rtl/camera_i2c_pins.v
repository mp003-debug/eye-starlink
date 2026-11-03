`timescale 1ns/1ps
// Open-drain only: zero drives low, release uses module's external 3.3 V pullups.
// CPU controls low-speed setup between capture/display runs, never per pixel.
module camera_i2c_pins(input wire clk, input wire resetn,
    input wire [1:0] pull_low, output wire [1:0] line_state,
    inout wire sda, inout wire scl);
    assign sda = (resetn && pull_low[0]) ? 1'b0 : 1'bz;
    assign scl = (resetn && pull_low[1]) ? 1'b0 : 1'bz;
    (* ASYNC_REG="TRUE" *) reg [1:0] i2c_sda_sync, i2c_scl_sync;
    always @(posedge clk) begin
        if (!resetn) begin i2c_sda_sync<=0; i2c_scl_sync<=0; end
        else begin i2c_sda_sync<={i2c_sda_sync[0],sda}; i2c_scl_sync<={i2c_scl_sync[0],scl}; end
    end
    assign line_state = {i2c_scl_sync[1],i2c_sda_sync[1]};
endmodule
