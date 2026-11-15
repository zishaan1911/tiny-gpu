// The whole board, seen from its pins. Plays the laptop: sends two frames of commands over the
// UART at 1 Mbaud, waiting for the GPU's acknowledgement in between. Then captures one VGA frame
// from the colour and sync pins exactly as a monitor would, checks every one of its 640x480
// pixels against the framebuffer, and writes it to sim/vga_frame.bmp.
`timescale 1ns / 1ps
`define SIM

module tb_board;
  reg clk = 0;
  always #19.9 clk = ~clk;  // 25.125 MHz

  reg rx = 1;  // the FPGA's uart_rx, driven by the "laptop"
  wire tx;
  wire [3:0] r, g, b;
  wire hs, vs, led_n;

  board_top dut (
      .clk_12m(clk), .uart_rx(rx), .uart_tx(tx),
      .vga_r(r), .vga_g(g), .vga_b(b), .vga_hs(hs), .vga_vs(vs), .led_n(led_n)
  );

  // The laptop's side of the UART ------------------------------------------------------
  localparam BIT = 1000.0;  // ns per bit at 1 Mbaud

  task send_byte(input [7:0] d);
    integer i;
    begin
      rx = 0; #(BIT);
      for (i = 0; i < 8; i = i + 1) begin rx = d[i]; #(BIT); end
      rx = 1; #(BIT);
    end
  endtask

  task send_cmd(input [1:0] op, input [3:0] color, input integer ax, input integer ay,
                input integer bx, input integer by, input integer cx, input integer cy);
    begin
      send_byte(8'h55); send_byte({2'b00, op, color});
      send_byte(ax); send_byte(ay); send_byte(bx); send_byte(by); send_byte(cx); send_byte(cy);
    end
  endtask

  // Waits for one byte from the FPGA and checks it is the frame acknowledgement.
  task expect_ack;
    reg [7:0] d;
    integer i;
    begin
      @(negedge tx);
      #(BIT * 1.5);
      for (i = 0; i < 8; i = i + 1) begin d[i] = tx; #(BIT); end
      if (d !== 8'h06) begin $display("FAIL: expected ack 06, got %h", d); $finish; end
      $display("%0t ns: ack", $time);
    end
  endtask

  function integer rnd(input real v);
    rnd = $rtoi($floor(v + 0.5));
  endfunction
  function integer vx(input real rad, input real turn, input integer k, input integer n);
    vx = rnd(32.0 + rad * $cos(turn + 6.283185307 * k / n));
  endfunction
  function integer vy(input real rad, input real turn, input integer k, input integer n);
    vy = rnd(32.0 + rad * $sin(turn + 6.283185307 * k / n));
  endfunction

  task send_frame(input real t);
    real w, u;
    begin
      w = 11.0 * (1.0 + 0.25 * $sin(2.0 * t));
      u = -2.0 * t + 0.5;
      send_cmd(0, 1, 0, 0, 0, 0, 0, 0);
      send_cmd(1, 2, vx(30.0, t, 0, 3), vy(30.0, t, 0, 3), vx(30.0, t, 1, 3), vy(30.0, t, 1, 3), vx(30.0, t, 2, 3), vy(30.0, t, 2, 3));
      send_cmd(1, 6, vx(21.0, u, 0, 3), vy(21.0, u, 0, 3), vx(21.0, u, 1, 3), vy(21.0, u, 1, 3), vx(21.0, u, 2, 3), vy(21.0, u, 2, 3));
      send_cmd(1, 10, vx(w, t, 0, 4), vy(w, t, 0, 4), vx(w, t, 1, 4), vy(w, t, 1, 4), vx(w, t, 2, 4), vy(w, t, 2, 4));
      send_cmd(1, 10, vx(w, t, 0, 4), vy(w, t, 0, 4), vx(w, t, 2, 4), vy(w, t, 2, 4), vx(w, t, 3, 4), vy(w, t, 3, 4));
      send_cmd(2, 0, 0, 0, 0, 0, 0, 0);
    end
  endtask

  // The monitor's side: capture from the pins ------------------------------------------
  // After the vsync pulse starts, row v's pixels follow the (v + 35)th hsync pulse, starting
  // 144 clocks after it (the sync pulse and back porch).
  reg [11:0] screen[0:640 * 480 - 1];
  reg capturing = 0;
  reg hs_d = 1, vs_d = 1;
  integer nline = 0, hpos = 0, row, col;

  always @(posedge clk) begin
    hs_d <= hs;
    vs_d <= vs;
    if (vs_d && !vs) nline = 0;
    if (hs_d && !hs) begin nline = nline + 1; hpos = 0; end
    else hpos = hpos + 1;
    row = nline - 35;
    col = hpos - 144;
    if (capturing && row >= 0 && row < 480 && col >= 0 && col < 640) screen[row * 640 + col] = {r, g, b};
  end

  function [11:0] palette(input [3:0] i);
    case (i)
      0: palette = 12'h000; 1: palette = 12'h112; 2: palette = 12'hF61; 3: palette = 12'hFB4;
      4: palette = 12'hFDA; 5: palette = 12'h2DB; 6: palette = 12'h3BF; 7: palette = 12'hA8F;
      8: palette = 12'hF7B; 9: palette = 12'hF35; 10: palette = 12'hFFF; 11: palette = 12'h8C1;
      12: palette = 12'hFC1; 13: palette = 12'h678; 14: palette = 12'h345; default: palette = 12'hFFF;
    endcase
  endfunction

  integer x, y, bad, lit, f, i;
  reg [11:0] want, got;

  initial begin
    for (i = 0; i < 640 * 480; i = i + 1) screen[i] = 12'hBAD;

    #(20000);
    send_frame(6.283185307 * 3 / 48);
    expect_ack;
    // Straight after the ack the beam is in the vertical blank: draw the next frame now.
    send_frame(6.283185307 * 9 / 48);

    // Capture the frame that follows.
    @(negedge vs);
    capturing = 1;
    wait (nline == 480 + 35);
    @(posedge clk);
    capturing = 0;
    if (led_n !== 1'b1 && led_n !== 1'b0) $display("FAIL: led_n undriven");

    // Every pixel against the framebuffer, scaled 7x and centred.
    bad = 0;
    lit = 0;
    for (y = 0; y < 480; y = y + 1)
      for (x = 0; x < 640; x = x + 1) begin
        if (x >= 96 && x < 544 && y >= 16 && y < 464)
          want = palette(dut.gpu.fb.mem[((y - 16) / 7) * 64 + (x - 96) / 7]);
        else want = 12'h000;
        got = screen[y * 640 + x];
        if (got !== want) begin
          if (bad < 5) $display("mismatch at (%0d, %0d): got %h, want %h", x, y, got, want);
          bad = bad + 1;
        end
        if (got == 12'hF61) lit = lit + 1;
      end

    // Write what the monitor saw: 24-bit BMP, rows bottom-up.
    f = $fopen("sim/vga_frame.bmp", "wb");
    $fwrite(f, "BM%c%c%c%c%c%c%c%c%c%c%c%c", 8'h36, 8'h10, 8'h0E, 8'h00, 0, 0, 0, 0, 8'h36, 0, 0, 0);
    $fwrite(f, "%c%c%c%c%c%c%c%c%c%c%c%c", 40, 0, 0, 0, 8'h80, 8'h02, 0, 0, 8'hE0, 8'h01, 0, 0);
    $fwrite(f, "%c%c%c%c%c%c%c%c", 1, 0, 24, 0, 0, 0, 0, 0);
    $fwrite(f, "%c%c%c%c%c%c%c%c%c%c%c%c%c%c%c%c%c%c%c%c", 0, 8'h10, 8'h0E, 0, 8'h13, 8'h0B, 0, 0, 8'h13, 8'h0B, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
    for (y = 479; y >= 0; y = y - 1)
      for (x = 0; x < 640; x = x + 1) begin
        got = screen[y * 640 + x];
        $fwrite(f, "%c%c%c", got[3:0] * 17, got[7:4] * 17, got[11:8] * 17);
      end
    $fclose(f);

    if (bad == 0 && lit > 1000) $display("PASS: all 307200 pixels match the framebuffer (%0d orange)", lit);
    else $display("FAIL: %0d pixels differ, %0d orange", bad, lit);
    $finish;
  end

  initial begin
    #(80_000_000);
    $display("FAIL: timed out");
    $finish;
  end
endmodule
