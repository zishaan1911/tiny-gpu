// Drives the GPU like a host would: a spinning scene of triangles, 48 frames.
// Writes sim/frames.txt (one line of 4096 hex digits per frame), sim/frames_cycles.txt (clock
// cycles each frame took) and sim/trace.txt (the rasteriser, cycle by cycle, for one frame).
`timescale 1ns / 1ps

module tb;
  localparam FRAMES = 48;
  localparam SHOW = 9;  // the frame whose rasteriser is traced cycle by cycle

  reg clk = 0;
  reg rst = 1;
  always #5 clk = ~clk;

  reg cmd_valid = 0;
  reg [1:0] cmd_op = 0;
  reg [3:0] cmd_color = 0;
  reg signed [7:0] x0 = 0, y0 = 0, x1 = 0, y1 = 0, x2 = 0, y2 = 0;
  wire cmd_ready, frame_done;
  reg [11:0] rd_addr = 0;
  wire [3:0] rd_data;

  tiny_gpu dut (
      .clk(clk), .rst(rst), .vblank_start(1'b1), .cmd_valid(cmd_valid), .cmd_op(cmd_op), .cmd_color(cmd_color),
      .x0(x0), .y0(y0), .x1(x1), .y1(y1), .x2(x2), .y2(y2),
      .cmd_ready(cmd_ready), .frame_done(frame_done), .rd_addr(rd_addr), .rd_data(rd_data)
  );

  integer frames_f, cycles_f, trace_f;
  integer cycle = 0;
  integer frame_start = 0;
  integer frame = 0;
  integer tri_no = 0;
  integer i;

  always @(posedge clk) cycle <= cycle + 1;

  task wait_ready;
    begin
      while (!cmd_ready) @(posedge clk);
    end
  endtask

  task send(input [1:0] op, input [3:0] color);
    begin
      wait_ready;
      cmd_op <= op;
      cmd_color <= color;
      cmd_valid <= 1;
      @(posedge clk);
      cmd_valid <= 0;
      @(posedge clk);
    end
  endtask

  // The coordinates must stay put until the triangle is done, so wait for the GPU to be idle
  // again before the next command changes them.
  task triangle(input integer ax, input integer ay, input integer bx, input integer by,
                input integer cx, input integer cy, input [3:0] color);
    begin
      wait_ready;
      x0 <= ax; y0 <= ay; x1 <= bx; y1 <= by; x2 <= cx; y2 <= cy;
      @(posedge clk);
      send(2'd1, color);
      wait_ready;
      tri_no = tri_no + 1;
    end
  endtask

  function integer rnd(input real v);
    begin
      rnd = $rtoi($floor(v + 0.5));
    end
  endfunction

  // A regular polygon's corner k of n, centred on (32, 32), turned by `turn` radians.
  function integer vx(input real r, input real turn, input integer k, input integer n);
    begin
      vx = rnd(32.0 + r * $cos(turn + 6.283185307 * k / n));
    end
  endfunction
  function integer vy(input real r, input real turn, input integer k, input integer n);
    begin
      vy = rnd(32.0 + r * $sin(turn + 6.283185307 * k / n));
    end
  endfunction

  real t, wob;

  // Trace the rasteriser while it scans, in the frame being shown.
  always @(posedge clk)
    if (frame == SHOW && dut.rast.state == 4'd9)
      $fwrite(trace_f, "%0d %0d %0d %0d %0d %0d %0d %0d %0d\n",
              cycle - frame_start, tri_no, dut.rast.px, dut.rast.py,
              dut.rast.e0, dut.rast.e1, dut.rast.e2, dut.rast.covered, dut.rast.wr_color);

  initial begin
    frames_f = $fopen("sim/frames.txt", "w");
    cycles_f = $fopen("sim/frames_cycles.txt", "w");
    trace_f = $fopen("sim/trace.txt", "w");
    repeat (4) @(posedge clk);
    rst <= 0;
    repeat (2) @(posedge clk);

    for (frame = 0; frame < FRAMES; frame = frame + 1) begin
      frame_start = cycle;
      tri_no = 0;
      t = 6.283185307 * frame / FRAMES;
      wob = 1.0 + 0.25 * $sin(2.0 * t);

      send(2'd0, 4'd1);                       // background
      // Outer triangle turning one way, an inner one the other way, a square pulsing in the middle.
      triangle(vx(30.0, t, 0, 3), vy(30.0, t, 0, 3), vx(30.0, t, 1, 3), vy(30.0, t, 1, 3),
               vx(30.0, t, 2, 3), vy(30.0, t, 2, 3), 4'd2);
      triangle(vx(21.0, -2.0 * t + 0.5, 0, 3), vy(21.0, -2.0 * t + 0.5, 0, 3),
               vx(21.0, -2.0 * t + 0.5, 1, 3), vy(21.0, -2.0 * t + 0.5, 1, 3),
               vx(21.0, -2.0 * t + 0.5, 2, 3), vy(21.0, -2.0 * t + 0.5, 2, 3), 4'd6);
      triangle(vx(11.0 * wob, t, 0, 4), vy(11.0 * wob, t, 0, 4), vx(11.0 * wob, t, 1, 4), vy(11.0 * wob, t, 1, 4),
               vx(11.0 * wob, t, 2, 4), vy(11.0 * wob, t, 2, 4), 4'd10);
      triangle(vx(11.0 * wob, t, 0, 4), vy(11.0 * wob, t, 0, 4), vx(11.0 * wob, t, 2, 4), vy(11.0 * wob, t, 2, 4),
               vx(11.0 * wob, t, 3, 4), vy(11.0 * wob, t, 3, 4), 4'd10);
      send(2'd2, 4'd0);                       // present
      wait_ready;

      // Read the finished frame out through the read port.
      $fwrite(cycles_f, "%0d\n", cycle - frame_start);
      for (i = 0; i < 4096; i = i + 1) begin
        rd_addr <= i;
        @(posedge clk);
        @(posedge clk);
        $fwrite(frames_f, "%h", rd_data);
      end
      $fwrite(frames_f, "\n");
    end

    $fclose(frames_f);
    $fclose(cycles_f);
    $fclose(trace_f);
    $display("done: %0d frames", FRAMES);
    $finish;
  end
endmodule
