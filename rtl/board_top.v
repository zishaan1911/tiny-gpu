// The whole chip on the board: the PLL, the laptop link through the FT2232H, the GPU and the
// VGA output. Pin numbers are in board.pcf.
module board_top (
    input  wire       clk_12m,   // 12 MHz oscillator
    input  wire       uart_rx,   // from the FT2232H (its TXD)
    output wire       uart_tx,   // to the FT2232H (its RXD)
    output wire [3:0] vga_r,
    output wire [3:0] vga_g,
    output wire [3:0] vga_b,
    output wire       vga_hs,
    output wire       vga_vs,
    output wire       led_n      // lit (low) for a moment every 32 frames
);
  wire clk;
  wire locked;
`ifdef SIM
  // The testbench drives clk_12m at the pixel clock itself.
  assign clk = clk_12m;
  assign locked = 1'b1;
`else
  // 12 MHz * 67 / 32 = 25.125 MHz, close enough to VGA's 25.175 MHz for any monitor.
  SB_PLL40_PAD #(
      .FEEDBACK_PATH("SIMPLE"),
      .DIVR(4'b0000),
      .DIVF(7'b1000010),
      .DIVQ(3'b101),
      .FILTER_RANGE(3'b001)
  ) pll (
      .PACKAGEPIN(clk_12m),
      .PLLOUTGLOBAL(clk),
      .RESETB(1'b1),
      .BYPASS(1'b0),
      .LOCK(locked)
  );
`endif

  // Hold everything in reset until the PLL is locked, then a little longer.
  reg [7:0] por = 0;
  wire rst = !por[7];
  always @(posedge clk)
    if (!locked) por <= 0;
    else if (!por[7]) por <= por + 8'd1;

  wire rx_valid;
  wire [7:0] rx_byte;
  uart_rx #(.CLKS(25)) rx (.clk(clk), .rst(rst), .rx(uart_rx), .valid(rx_valid), .data(rx_byte));

  wire cmd_valid, cmd_ready, overflow;
  wire [1:0] cmd_op;
  wire [3:0] cmd_color;
  wire signed [7:0] x0, y0, x1, y1, x2, y2;
  cmd_port port (
      .clk(clk), .rst(rst), .in_valid(rx_valid), .in_byte(rx_byte),
      .cmd_valid(cmd_valid), .cmd_op(cmd_op), .cmd_color(cmd_color),
      .x0(x0), .y0(y0), .x1(x1), .y1(y1), .x2(x2), .y2(y2),
      .cmd_ready(cmd_ready), .overflow(overflow)
  );

  wire vblank_start, frame_done;
  wire [11:0] fb_addr;
  wire [3:0] fb_data;
  tiny_gpu gpu (
      .clk(clk), .rst(rst), .vblank_start(vblank_start),
      .cmd_valid(cmd_valid), .cmd_op(cmd_op), .cmd_color(cmd_color),
      .x0(x0), .y0(y0), .x1(x1), .y1(y1), .x2(x2), .y2(y2),
      .cmd_ready(cmd_ready), .frame_done(frame_done),
      .rd_addr(fb_addr), .rd_data(fb_data)
  );

  vga video (
      .clk(clk), .rst(rst), .fb_addr(fb_addr), .fb_data(fb_data),
      .r(vga_r), .g(vga_g), .b(vga_b), .hsync(vga_hs), .vsync(vga_vs),
      .vblank_start(vblank_start)
  );

  // Answer each PRESENT so the laptop knows the frame is on screen.
  uart_tx #(.CLKS(25)) tx (.clk(clk), .rst(rst), .send(frame_done), .data(8'h06), .tx(uart_tx), .busy());

  reg [4:0] frames;
  always @(posedge clk)
    if (rst) frames <= 0;
    else if (frame_done) frames <= frames + 5'd1;
  assign led_n = !(frames == 0 || overflow);
endmodule
