// A tiny GPU: a command port, a rasteriser and a framebuffer.
//
// The host waits for cmd_ready, then pulses cmd_valid with one command:
//   CLEAR    fill the framebuffer with cmd_color
//   TRIANGLE fill a triangle with cmd_color
//   PRESENT  wait for the display's vertical blank, then pulse frame_done. The host draws
//            the next frame straight after, while the beam is off screen, so it never tears.
// The display reads the framebuffer on rd_addr / rd_data.
module tiny_gpu (
    input  wire              clk,
    input  wire              rst,
    input  wire              vblank_start,
    input  wire              cmd_valid,
    input  wire        [1:0] cmd_op,
    input  wire        [3:0] cmd_color,
    input  wire signed [7:0] x0, y0, x1, y1, x2, y2,
    output wire              cmd_ready,
    output reg               frame_done,
    input  wire       [11:0] rd_addr,
    output wire        [3:0] rd_data
);
  localparam OP_CLEAR = 2'd0, OP_TRIANGLE = 2'd1, OP_PRESENT = 2'd2;
  localparam IDLE = 3'd0, CLEAR = 3'd1, TRI_START = 3'd2, TRI_WAIT = 3'd3, PRESENT = 3'd4;

  reg [2:0] state;
  reg [11:0] clr_i;
  reg [3:0] clr_color;
  reg r_start;

  wire r_busy, r_we;
  wire [5:0] r_x, r_y;
  wire [3:0] r_color;

  raster rast (
      .clk(clk), .rst(rst), .start(r_start),
      .x0(x0), .y0(y0), .x1(x1), .y1(y1), .x2(x2), .y2(y2),
      .color(cmd_color),
      .busy(r_busy), .wr_en(r_we), .wr_x(r_x), .wr_y(r_y), .wr_color(r_color)
  );

  wire clearing = (state == CLEAR);

  framebuffer fb (
      .clk(clk),
      .we(clearing | r_we),
      .waddr(clearing ? clr_i : {r_y, r_x}),
      .wdata(clearing ? clr_color : r_color),
      .raddr(rd_addr),
      .rdata(rd_data)
  );

  assign cmd_ready = (state == IDLE);

  always @(posedge clk) begin
    if (rst) begin
      state <= IDLE;
      r_start <= 1'b0;
      frame_done <= 1'b0;
    end else begin
      r_start <= 1'b0;
      frame_done <= 1'b0;
      case (state)
        IDLE: if (cmd_valid) begin
          case (cmd_op)
            OP_CLEAR: begin
              clr_i <= 12'd0;
              clr_color <= cmd_color;
              state <= CLEAR;
            end
            OP_TRIANGLE: begin
              r_start <= 1'b1;
              state <= TRI_START;
            end
            OP_PRESENT: state <= PRESENT;
            default: ;
          endcase
        end

        CLEAR: begin
          clr_i <= clr_i + 12'd1;
          if (clr_i == 12'd4095) state <= IDLE;
        end

        // The rasteriser sees start this cycle and raises busy for the next.
        TRI_START: state <= TRI_WAIT;
        TRI_WAIT: if (!r_busy) state <= IDLE;

        PRESENT: if (vblank_start) begin
          frame_done <= 1'b1;
          state <= IDLE;
        end

        default: state <= IDLE;
      endcase
    end
  end
endmodule
