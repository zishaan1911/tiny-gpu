// 640x480 @ 60 Hz VGA scanout of the 64x64 framebuffer, each pixel drawn as a 7x7 block
// (448x448, centred), black around it. 12-bit colour through a 16-entry palette.
//
// Pipeline: the counters address the framebuffer, its data comes back a clock later, and the
// colour is registered a clock after that. The syncs are delayed to match, so the picture and
// the sync pulses stay aligned.
module vga (
    input  wire        clk,          // 25.125 MHz pixel clock
    input  wire        rst,
    output wire [11:0] fb_addr,
    input  wire [3:0]  fb_data,
    output reg  [3:0]  r, g, b,
    output reg         hsync, vsync,  // active low
    output reg         vblank_start   // one clock at the start of the first blank line
);
  localparam H_VIS = 640, H_FP = 16, H_SYNC = 96, H_BP = 48, H_TOT = 800;
  localparam V_VIS = 480, V_FP = 10, V_SYNC = 2, V_BP = 33, V_TOT = 525;
  localparam X0 = 96, Y0 = 16, SIZE = 448;

  reg [9:0] hc, vc;
  // Framebuffer pixel and the position inside its 7x7 block.
  reg [5:0] fx, fy;
  reg [2:0] sx, sy;

  always @(posedge clk) begin
    if (rst) begin
      hc <= 0; vc <= 0; sx <= 0; sy <= 0; fx <= 0; fy <= 0;
    end else begin
      hc <= (hc == H_TOT - 1) ? 10'd0 : hc + 10'd1;
      if (hc == H_TOT - 1) vc <= (vc == V_TOT - 1) ? 10'd0 : vc + 10'd1;

      // Columns: start at X0, advance every 7 pixels.
      if (hc == X0 - 1) begin
        sx <= 0; fx <= 0;
      end else if (sx == 3'd6) begin
        sx <= 0; fx <= fx + 6'd1;
      end else sx <= sx + 3'd1;

      // Rows: the same at the end of each line, for the line about to start.
      if (hc == H_TOT - 1) begin
        if (vc == Y0 - 1) begin
          sy <= 0; fy <= 0;
        end else if (sy == 3'd6) begin
          sy <= 0; fy <= fy + 6'd1;
        end else sy <= sy + 3'd1;
      end
    end
  end

  assign fb_addr = {fy, fx};

  wire in_img = (hc >= X0) && (hc < X0 + SIZE) && (vc >= Y0) && (vc < Y0 + SIZE);
  wire hs = !((hc >= H_VIS + H_FP) && (hc < H_VIS + H_FP + H_SYNC));
  wire vs = !((vc >= V_VIS + V_FP) && (vc < V_VIS + V_FP + V_SYNC));

  // One clock behind the counters, in step with fb_data.
  reg d_img, d_hs, d_vs;

  function [11:0] palette(input [3:0] i);
    case (i)
      4'd0:  palette = 12'h000;
      4'd1:  palette = 12'h112;
      4'd2:  palette = 12'hF61;
      4'd3:  palette = 12'hFB4;
      4'd4:  palette = 12'hFDA;
      4'd5:  palette = 12'h2DB;
      4'd6:  palette = 12'h3BF;
      4'd7:  palette = 12'hA8F;
      4'd8:  palette = 12'hF7B;
      4'd9:  palette = 12'hF35;
      4'd10: palette = 12'hFFF;
      4'd11: palette = 12'h8C1;
      4'd12: palette = 12'hFC1;
      4'd13: palette = 12'h678;
      4'd14: palette = 12'h345;
      default: palette = 12'hFFF;
    endcase
  endfunction

  wire [11:0] rgb = d_img ? palette(fb_data) : 12'h000;

  always @(posedge clk) begin
    if (rst) begin
      d_img <= 0; d_hs <= 1; d_vs <= 1;
      hsync <= 1; vsync <= 1; {r, g, b} <= 12'h000; vblank_start <= 0;
    end else begin
      d_img <= in_img;
      d_hs <= hs;
      d_vs <= vs;
      {r, g, b} <= rgb;
      hsync <= d_hs;
      vsync <= d_vs;
      vblank_start <= (hc == 0) && (vc == V_VIS);
    end
  end
endmodule
