// 8N1 UART, one byte at a time. CLKS is clock cycles per bit: 25 for 1 Mbaud at 25.125 MHz.
module uart_rx #(parameter CLKS = 25) (
    input  wire       clk,
    input  wire       rst,
    input  wire       rx,
    output reg        valid,
    output reg  [7:0] data
);
  // Two flops against metastability: rx comes from another chip.
  reg rx1 = 1, rx2 = 1;
  always @(posedge clk) begin
    rx1 <= rx;
    rx2 <= rx1;
  end

  reg [1:0] state;
  reg [7:0] count;
  reg [2:0] bit_no;
  localparam IDLE = 2'd0, START = 2'd1, BITS = 2'd2, STOP = 2'd3;

  always @(posedge clk) begin
    valid <= 1'b0;
    if (rst) state <= IDLE;
    else case (state)
      IDLE: if (!rx2) begin
        count <= CLKS / 2;
        state <= START;
      end
      // Check the start bit in its middle, so a glitch doesn't start a byte.
      START: if (count == 0) begin
        if (!rx2) begin
          count <= CLKS - 1;
          bit_no <= 0;
          state <= BITS;
        end else state <= IDLE;
      end else count <= count - 8'd1;
      BITS: if (count == 0) begin
        data <= {rx2, data[7:1]};
        count <= CLKS - 1;
        if (bit_no == 3'd7) state <= STOP;
        bit_no <= bit_no + 3'd1;
      end else count <= count - 8'd1;
      STOP: if (count == 0) begin
        valid <= rx2;  // a missing stop bit drops the byte
        state <= IDLE;
      end else count <= count - 8'd1;
    endcase
  end
endmodule

module uart_tx #(parameter CLKS = 25) (
    input  wire       clk,
    input  wire       rst,
    input  wire       send,
    input  wire [7:0] data,
    output reg        tx,
    output wire       busy
);
  reg [10:0] shift;
  reg [3:0] left;
  reg [7:0] count;
  assign busy = (left != 0);

  always @(posedge clk) begin
    if (rst) begin
      tx <= 1'b1;
      left <= 0;
    end else if (left == 0) begin
      if (send) begin
        // start, 8 data bits, stop, and one more high bit so the stop bit lasts a full bit time
        shift <= {2'b11, data, 1'b0};
        left <= 4'd11;
        count <= 0;
      end
    end else if (count == 0) begin
      tx <= shift[0];
      shift <= {1'b1, shift[10:1]};
      left <= left - 4'd1;
      count <= CLKS - 1;
    end else count <= count - 8'd1;
  end
endmodule
