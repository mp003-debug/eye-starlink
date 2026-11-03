`timescale 1ns/1ps
// Video-only shell. Diagnostics remain an independent camera_diag_axi module.
module camera_ddr_video (
    (* X_INTERFACE_INFO="xilinx.com:signal:clock:1.0 ctrl_clk CLK" *)
    (* X_INTERFACE_PARAMETER="ASSOCIATED_RESET aresetn, FREQ_HZ 50000000" *)
    input wire ctrl_clk,
    (* X_INTERFACE_INFO="xilinx.com:signal:reset:1.0 aresetn RST" *)
    (* X_INTERFACE_PARAMETER="POLARITY ACTIVE_LOW" *) input wire aresetn,
    input wire [3:0] control,
    output wire [6:0] status,
    input wire [7:0] cam_data,
    (* X_INTERFACE_INFO="xilinx.com:signal:clock:1.0 cam_pclk CLK" *)
    (* X_INTERFACE_PARAMETER="FREQ_HZ 24000000" *) input wire cam_pclk,
    input wire cam_frame_valid, cam_line_valid,
    inout wire cam_sda, cam_scl,
    input wire sw0,
    output wire [3:0] led,
    (* X_INTERFACE_INFO="xilinx.com:signal:clock:1.0 capture_clk CLK" *)
    (* X_INTERFACE_PARAMETER="ASSOCIATED_BUSIF m_axis, ASSOCIATED_RESET capture_resetn, FREQ_HZ 24000000" *)
    output wire capture_clk,
    (* X_INTERFACE_INFO="xilinx.com:signal:reset:1.0 capture_resetn RST" *)
    (* X_INTERFACE_PARAMETER="POLARITY ACTIVE_LOW" *) output wire capture_resetn,
    (* X_INTERFACE_INFO="xilinx.com:signal:clock:1.0 display_clk CLK" *)
    (* X_INTERFACE_PARAMETER="ASSOCIATED_BUSIF s_axis, ASSOCIATED_RESET display_resetn, FREQ_HZ 25000000" *)
    output wire display_clk,
    (* X_INTERFACE_INFO="xilinx.com:signal:reset:1.0 display_resetn RST" *)
    (* X_INTERFACE_PARAMETER="POLARITY ACTIVE_LOW" *) output wire display_resetn,
    (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 m_axis TDATA" *) output wire [7:0] m_axis_tdata,
    (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 m_axis TUSER" *) output wire m_axis_tuser,
    (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 m_axis TLAST" *) output wire m_axis_tlast,
    (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 m_axis TVALID" *) output wire m_axis_tvalid,
    (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 m_axis TREADY" *) input wire m_axis_tready,
    (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 s_axis TDATA" *) input wire [15:0] s_axis_tdata,
    (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 s_axis TUSER" *) input wire s_axis_tuser,
    (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 s_axis TLAST" *) input wire s_axis_tlast,
    (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 s_axis TVALID" *) input wire s_axis_tvalid,
    (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 s_axis TREADY" *) output wire s_axis_tready,
    output wire [31:0] frame_count, frame_period, frame_pixels, bad_lines, bad_frames,
    output wire [15:0] frame_lines, line_pixels,
    (* X_INTERFACE_INFO="xilinx.com:signal:clock:1.0 hdmi_out_clk_p CLK" *)
    (* X_INTERFACE_PARAMETER="FREQ_HZ 25000000" *) output wire hdmi_out_clk_p,
    (* X_INTERFACE_INFO="xilinx.com:signal:clock:1.0 hdmi_out_clk_n CLK" *)
    (* X_INTERFACE_PARAMETER="FREQ_HZ 25000000" *) output wire hdmi_out_clk_n,
    output wire [2:0] hdmi_out_data_p, hdmi_out_data_n
);
    wire pclk, clk_pix, clk_ser, locked;
    BUFG u_cam_clock (.I(cam_pclk),.O(pclk));
    clk_gen u_clk (.clk_in50(ctrl_clk),.clk_pix(clk_pix),.clk_ser(clk_ser),.locked(locked));
    (* ASYNC_REG="TRUE" *) reg [1:0] lock_sync, cam_reset_sync, pix_reset_sync;
    always @(posedge ctrl_clk or negedge aresetn)
        if (!aresetn) lock_sync<=0; else lock_sync<={lock_sync[0],locked};
    wire pix_reset_source=lock_sync[1];
    always @(posedge pclk or negedge aresetn)
        if (!aresetn) cam_reset_sync<=0; else cam_reset_sync<={cam_reset_sync[0],1'b1};
    always @(posedge clk_pix or negedge pix_reset_source)
        if (!pix_reset_source) pix_reset_sync<=0; else pix_reset_sync<={pix_reset_sync[0],1'b1};
    wire cam_rst_n=cam_reset_sync[1], pix_rst_n=pix_reset_sync[1];
    assign capture_clk=pclk; assign display_clk=clk_pix;
    assign capture_resetn=cam_rst_n; assign display_resetn=pix_rst_n;
    (* ASYNC_REG="TRUE" *) reg [1:0] capture_enable_sync, display_enable_sync, switch_sync;
    always @(posedge pclk) begin
        if (!cam_rst_n) capture_enable_sync<=0;
        else capture_enable_sync<={capture_enable_sync[0],control[0]};
    end
    always @(posedge clk_pix) begin
        if (!pix_rst_n) begin display_enable_sync<=0; switch_sync<=0; end
        else begin
            display_enable_sync<={display_enable_sync[0],control[1]};
            switch_sync<={switch_sync[0],sw0};
        end
    end
    wire [7:0] pixel_data;
    wire pixel_valid,pixel_sof,pixel_eol,frame_done;
    wire [15:0] pixel_x,pixel_y;
    mt9v034_dvp_frontend u_frontend (
        .pclk(pclk),.rst_n(cam_rst_n),.cam_data(cam_data),
        .cam_frame_valid(cam_frame_valid),.cam_line_valid(cam_line_valid),
        .pixel_data(pixel_data),.pixel_valid(pixel_valid),.pixel_sof(pixel_sof),.pixel_eol(pixel_eol),
        .pixel_x(pixel_x),.pixel_y(pixel_y),.frame_done(frame_done),.frame_count(frame_count),
        .last_frame_period(frame_period),.last_frame_pixels(frame_pixels),
        .last_frame_lines(frame_lines),.last_line_pixels(line_pixels),
        .bad_line_count(bad_lines),.bad_frame_count(bad_frames));
    wire capture_rearm_ready;
    wire capture_overflow,display_locked,display_underflow,display_format_error;
    dvp_axis_queue u_queue (.clk(pclk),.rst_n(cam_rst_n),.enable(capture_enable_sync[1]),
        .pixel_data(pixel_data),.pixel_valid(pixel_valid),.pixel_sof(pixel_sof),.pixel_eol(pixel_eol),
        .pixel_eof(pixel_eol && pixel_x==639 && pixel_y==479),.frame_done(frame_done),
        .rearm_ready(capture_rearm_ready),
        .m_axis_tdata(m_axis_tdata),.m_axis_tuser(m_axis_tuser),.m_axis_tlast(m_axis_tlast),
        .m_axis_tvalid(m_axis_tvalid),.m_axis_tready(m_axis_tready),.overflow(capture_overflow));
    wire [9:0] x,y;
    wire de,hs,vs;
    video_timing u_timing (.clk_pix(clk_pix),.rst_n(pix_rst_n),.x(x),.y(y),.de(de),.hsync(hs),.vsync(vs));
    wire [15:0] display_pixel;
    axis_video_sink u_sink (.clk(clk_pix),.rst_n(pix_rst_n),.enable(display_enable_sync[1]),
        .x(x),.y(y),.de(de),.s_axis_tdata(s_axis_tdata),.s_axis_tuser(s_axis_tuser),
        .s_axis_tlast(s_axis_tlast),.s_axis_tvalid(s_axis_tvalid),.s_axis_tready(s_axis_tready),
        .pixel(display_pixel),.locked(display_locked),.underflow(display_underflow),.format_error(display_format_error));
    reg de_d,hs_d,vs_d;
    reg [15:0] test_d;
    always @(posedge clk_pix) begin
        if (!pix_rst_n) begin de_d<=0; hs_d<=1; vs_d<=1; test_d<=0; end
        else begin
            de_d<=de; hs_d<=hs; vs_d<=vs;
            case (x/80)
                0: test_d<=16'hFFFF; 1: test_d<=16'hFFE0;
                2: test_d<=16'h07FF; 3: test_d<=16'h07E0;
                4: test_d<=16'hF81F; 5: test_d<=16'hF800;
                6: test_d<=16'h001F; default: test_d<=16'h0000;
            endcase
        end
    end
    wire [15:0] color_pixel=switch_sync[1]?test_d:display_pixel;
    wire [7:0] red,green,blue;
    rgb565_to_rgb888 u_color (.pixel(color_pixel),.red(red),.green(green),.blue(blue));
    hdmi_tx u_tx (.clk_pix(clk_pix),.clk_ser(clk_ser),.rst_n(pix_rst_n),
        .de(de_d),.hsync(hs_d),.vsync(vs_d),.red(red),.green(green),.blue(blue),
        .tmds_clk_p(hdmi_out_clk_p),.tmds_clk_n(hdmi_out_clk_n),
        .tmds_data_p(hdmi_out_data_p),.tmds_data_n(hdmi_out_data_n));
    (* ASYNC_REG="TRUE" *) reg [1:0] rearm_sync, overflow_sync, underflow_sync, format_sync, display_lock_sync;
    always @(posedge ctrl_clk) begin
        if (!aresetn) begin rearm_sync<=0; overflow_sync<=0; underflow_sync<=0; format_sync<=0; display_lock_sync<=0; end
        else begin
            rearm_sync<={rearm_sync[0],capture_rearm_ready};
            overflow_sync<={overflow_sync[0],capture_overflow};
            underflow_sync<={underflow_sync[0],display_underflow};
            format_sync<={format_sync[0],display_format_error};
            display_lock_sync<={display_lock_sync[0],display_locked};
        end
    end
    assign status={i2c_lines,rearm_sync[1],display_lock_sync[1],format_sync[1],underflow_sync[1],overflow_sync[1]};
    reg [23:0] heartbeat;
    always @(posedge clk_pix) if (!pix_rst_n) heartbeat<=0; else heartbeat<=heartbeat+1'b1;
    assign led={display_underflow|display_format_error,display_locked,locked,heartbeat[23]};
    wire [1:0] i2c_lines;
    camera_i2c_pins u_i2c (.clk(ctrl_clk),.resetn(aresetn),.pull_low(control[3:2]),
        .line_state(i2c_lines),.sda(cam_sda),.scl(cam_scl));
endmodule
