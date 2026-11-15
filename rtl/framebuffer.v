// 64x64 pixels, 4 bits each (a 16-colour palette index). One write port, one read port:
// this is what an FPGA maps onto a block RAM.
module framebuffer (
    input  wire        clk,
    input  wire        we,
    input  wire [11:0] waddr,
    input  wire [3:0]  wdata,
    input  wire [11:0] raddr,
    output reg  [3:0]  rdata
);
  reg [3:0] mem[0:4095];

  always @(posedge clk) begin
    if (we) mem[waddr] <= wdata;
    rdata <= mem[raddr];
  end
endmodule
