// Triangle rasteriser: one pixel per clock, no multipliers in the scan loop.
//
// A triangle is three vertices in a 64x64 framebuffer (signed 8-bit coordinates, so a vertex
// may lie off screen). Each edge has a linear "edge function" E(x, y) that is >= 0 on the
// inside. Stepping one pixel right adds A, stepping one row down adds B, so the whole fill
// is three adders per pixel. The multipliers only run during setup, to start the edges at the
// corner of the bounding box. Setup is pipelined over seven clocks so that no stage chains more
// than one multiply or one compare-and-select, which keeps the design fast enough for 25 MHz.
module raster (
    input  wire              clk,
    input  wire              rst,
    input  wire              start,
    input  wire signed [7:0] x0, y0, x1, y1, x2, y2,
    input  wire        [3:0] color,
    output reg               busy,
    output reg               wr_en,
    output reg         [5:0] wr_x,
    output reg         [5:0] wr_y,
    output reg         [3:0] wr_color
);
  localparam IDLE = 4'd0, DIFF = 4'd1, PROD = 4'd2, AREA = 4'd3, ORDER = 4'd4, BBOX = 4'd5,
             STEP = 4'd6, MUL = 4'd7, SUM = 4'd8, SCAN = 4'd9, FLUSH = 4'd10;

  reg [3:0] state;

  // The vertices as given, then in counter-clockwise order so the inside has every edge >= 0.
  reg signed [7:0] vx0, vy0, vx1, vy1, vx2, vy2;
  reg signed [7:0] ax, ay, bx, by, cx, cy;

  // Twice the signed area, in two steps: differences, then products.
  reg signed [8:0] dx1, dy1, dx2, dy2;
  reg signed [17:0] p1, p2;
  reg signed [18:0] area;

  // Bounding box: unclamped, then on screen.
  reg signed [7:0] minx, maxx, miny, maxy;
  reg [5:0] lox, hix, loy, hiy;
  reg [5:0] px, py;

  // Edge function steps (A per pixel right, B per row down), the distances from each edge's
  // start vertex to the box corner, and their products.
  reg signed [9:0] a0, b0, a1, b1, a2, b2;
  reg signed [8:0] u0, w0, u1, w1, u2, w2;
  reg signed [19:0] m0a, m0b, m1a, m1b, m2a, m2b;

  // Edge functions at the current pixel, and at the start of the current row.
  reg signed [19:0] e0, e1, e2;
  reg signed [19:0] r0, r1, r2;

  wire covered = !e0[19] && !e1[19] && !e2[19];

  function signed [7:0] min3(input signed [7:0] a, input signed [7:0] b, input signed [7:0] c);
    min3 = (a < b) ? ((a < c) ? a : c) : ((b < c) ? b : c);
  endfunction
  function signed [7:0] max3(input signed [7:0] a, input signed [7:0] b, input signed [7:0] c);
    max3 = (a > b) ? ((a > c) ? a : c) : ((b > c) ? b : c);
  endfunction

  always @(posedge clk) begin
    if (rst) begin
      state <= IDLE;
      busy  <= 1'b0;
      wr_en <= 1'b0;
    end else begin
      wr_en <= 1'b0;
      case (state)
        IDLE: if (start) begin
          vx0 <= x0; vy0 <= y0; vx1 <= x1; vy1 <= y1; vx2 <= x2; vy2 <= y2;
          wr_color <= color;
          busy <= 1'b1;
          state <= DIFF;
        end

        DIFF: begin
          dx1 <= vx1 - vx0; dy1 <= vy1 - vy0;
          dx2 <= vx2 - vx0; dy2 <= vy2 - vy0;
          state <= PROD;
        end

        PROD: begin
          p1 <= dx1 * dy2;
          p2 <= dy1 * dx2;
          state <= AREA;
        end

        AREA: begin
          area <= p1 - p2;
          state <= ORDER;
        end

        // Clockwise vertices swap two; a triangle with no area draws nothing.
        ORDER: begin
          if (area == 0) begin
            busy <= 1'b0;
            state <= IDLE;
          end else begin
            ax <= vx0; ay <= vy0;
            if (area > 0) begin
              bx <= vx1; by <= vy1; cx <= vx2; cy <= vy2;
            end else begin
              bx <= vx2; by <= vy2; cx <= vx1; cy <= vy1;
            end
            minx <= min3(vx0, vx1, vx2); maxx <= max3(vx0, vx1, vx2);
            miny <= min3(vy0, vy1, vy2); maxy <= max3(vy0, vy1, vy2);
            state <= BBOX;
          end
        end

        BBOX: begin
          if (maxx < 0 || minx > 63 || maxy < 0 || miny > 63) begin
            busy <= 1'b0;
            state <= IDLE;
          end else begin
            lox <= (minx < 0) ? 6'd0 : minx[5:0];
            loy <= (miny < 0) ? 6'd0 : miny[5:0];
            hix <= (maxx > 63) ? 6'd63 : maxx[5:0];
            hiy <= (maxy > 63) ? 6'd63 : maxy[5:0];
            state <= STEP;
          end
        end

        STEP: begin
          a0 <= ay - by;  b0 <= bx - ax;
          a1 <= by - cy;  b1 <= cx - bx;
          a2 <= cy - ay;  b2 <= ax - cx;
          u0 <= $signed({2'b00, lox}) - ax;  w0 <= $signed({2'b00, loy}) - ay;
          u1 <= $signed({2'b00, lox}) - bx;  w1 <= $signed({2'b00, loy}) - by;
          u2 <= $signed({2'b00, lox}) - cx;  w2 <= $signed({2'b00, loy}) - cy;
          px <= lox;
          py <= loy;
          state <= MUL;
        end

        // E = A * (x - vx) + B * (y - vy) at the bounding box corner.
        MUL: begin
          m0a <= a0 * u0;  m0b <= b0 * w0;
          m1a <= a1 * u1;  m1b <= b1 * w1;
          m2a <= a2 * u2;  m2b <= b2 * w2;
          state <= SUM;
        end

        SUM: begin
          e0 <= m0a + m0b;  r0 <= m0a + m0b;
          e1 <= m1a + m1b;  r1 <= m1a + m1b;
          e2 <= m2a + m2b;  r2 <= m2a + m2b;
          state <= SCAN;
        end

        SCAN: begin
          wr_en <= covered;
          wr_x  <= px;
          wr_y  <= py;
          if (px == hix) begin
            if (py == hiy) state <= FLUSH;
            else begin
              py <= py + 6'd1;
              px <= lox;
              r0 <= r0 + b0;  e0 <= r0 + b0;
              r1 <= r1 + b1;  e1 <= r1 + b1;
              r2 <= r2 + b2;  e2 <= r2 + b2;
            end
          end else begin
            px <= px + 6'd1;
            e0 <= e0 + a0;
            e1 <= e1 + a1;
            e2 <= e2 + a2;
          end
        end

        FLUSH: begin
          busy  <= 1'b0;
          state <= IDLE;
        end

        default: state <= IDLE;
      endcase
    end
  end
endmodule
