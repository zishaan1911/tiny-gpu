// Turns bytes from the laptop into GPU commands.
//
// Every command is 8 bytes:  0x55, {2'b0, op[1:0], colour[3:0]}, x0, y0, x1, y1, x2, y2
// (op 0 clear, 1 triangle, 2 present; coordinates are signed bytes). Bytes land in a 512-byte
// FIFO in block RAM, so the laptop can send a whole frame in one USB transfer; the parser takes
// them out as fast as the GPU accepts commands. The GPU answers each PRESENT with one byte, 0x06,
// and the laptop waits for it before sending the next frame, so the FIFO never overflows.
module cmd_port (
    input  wire              clk,
    input  wire              rst,
    input  wire              in_valid,
    input  wire        [7:0] in_byte,
    output reg               cmd_valid,
    output reg         [1:0] cmd_op,
    output reg         [3:0] cmd_color,
    output reg signed  [7:0] x0, y0, x1, y1, x2, y2,
    input  wire              cmd_ready,
    output reg               overflow
);
  // FIFO ------------------------------------------------------------------------------
  reg [7:0] mem[0:511];
  reg [9:0] wptr, rptr;  // one extra bit tells full from empty
  wire empty = (wptr == rptr);
  wire full = (wptr[8:0] == rptr[8:0]) && (wptr[9] != rptr[9]);
  reg [7:0] rdata;
  reg rd;

  always @(posedge clk) begin
    if (in_valid && !full) mem[wptr[8:0]] <= in_byte;
    rdata <= mem[rptr[8:0]];
  end

  always @(posedge clk) begin
    if (rst) begin
      wptr <= 0;
      overflow <= 1'b0;
    end else if (in_valid) begin
      if (full) overflow <= 1'b1;
      else wptr <= wptr + 10'd1;
    end
  end

  // Parser ----------------------------------------------------------------------------
  localparam FETCH = 2'd0, WAIT = 2'd1, TAKE = 2'd2, ISSUE = 2'd3;
  reg [1:0] state;
  reg [2:0] idx;  // which byte of the command comes next
  reg [7:0] p[1:7];

  always @(posedge clk) begin
    cmd_valid <= 1'b0;
    if (rst) begin
      rptr <= 0;
      idx <= 0;
      state <= FETCH;
    end else case (state)
      FETCH: if (!empty) state <= WAIT;
      // The RAM is addressed by rptr; its data is ready on the next clock.
      WAIT: state <= TAKE;
      TAKE: begin
        rptr <= rptr + 10'd1;
        state <= FETCH;
        if (idx == 0) begin
          if (rdata == 8'h55) idx <= 1;  // anything else is skipped until the next sync byte
        end else begin
          p[idx] <= rdata;
          if (idx == 3'd7) begin
            idx <= 0;
            state <= ISSUE;
          end else idx <= idx + 3'd1;
        end
      end
      ISSUE: if (cmd_ready) begin
        cmd_op <= p[1][5:4];
        cmd_color <= p[1][3:0];
        x0 <= p[2]; y0 <= p[3]; x1 <= p[4]; y1 <= p[5]; x2 <= p[6]; y2 <= p[7];
        cmd_valid <= 1'b1;
        state <= FETCH;
      end
    endcase
  end
endmodule
