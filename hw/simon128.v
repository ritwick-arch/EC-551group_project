// SIMON-128/128 block cipher, one round per cycle (68 cycles per block).
module simon128 #(
  parameter [127:0] KEY = 128'h0
) (
  input  wire         clock,
  input  wire         reset,
  input  wire         start,
  input  wire         decrypt,
  input  wire [127:0] block_in,
  output wire [127:0] block_out,
  output wire         ready,
  output reg          done
  );

  localparam [61:0] Z2 = 62'b10101111011100000011010010011000101000010001111110010110110011;

  function [63:0] f;
    input [63:0] v;
    f = ({v[62:0], v[63]} & {v[55:0], v[63:56]}) ^ {v[61:0], v[63:62]};
  endfunction

  // Round keys are expanded once after reset into a small RAM.
  reg [63:0] rk [0:67];
  reg [6:0]  ks_i;
  reg [5:0]  z_i;
  reg [63:0] k_a, k_b;
  reg        ks_busy;

  wire [63:0] ks_t0   = {k_b[2:0], k_b[63:3]};
  wire [63:0] ks_t1   = ks_t0 ^ {ks_t0[0], ks_t0[63:1]};
  wire [63:0] ks_next = ~k_a ^ ks_t1 ^ {63'b0, Z2[61 - z_i]} ^ 64'd3;
  wire [63:0] ks_word = (ks_i == 7'd0) ? KEY[63:0] : (ks_i == 7'd1) ? KEY[127:64] : ks_next;

  always @(posedge clock) begin
    if (reset) begin
      ks_i    <= 7'd0;
      z_i     <= 6'd0;
      ks_busy <= 1'b1;
    end else if (ks_busy) begin
      k_a  <= k_b;
      k_b  <= ks_word;
      ks_i <= ks_i + 7'd1;
      if (ks_i >= 7'd2)
        z_i <= (z_i == 6'd61) ? 6'd0 : z_i + 6'd1;
      if (ks_i == 7'd67)
        ks_busy <= 1'b0;
    end
  end

  always @(posedge clock)
    if (!reset && ks_busy)
      rk[ks_i] <= ks_word;

  reg [63:0] x, y;
  reg [6:0]  r;
  reg        busy;
  reg        dec;

  wire [63:0] k_r = rk[dec ? 7'd67 - r : r];

  assign block_out = {x, y};
  assign ready     = !busy && !ks_busy;

  always @(posedge clock) begin
    done <= 1'b0;
    if (reset) begin
      busy <= 1'b0;
    end else if (start && ready) begin
      x    <= block_in[127:64];
      y    <= block_in[63:0];
      r    <= 7'd0;
      dec  <= decrypt;
      busy <= 1'b1;
    end else if (busy) begin
      if (dec) begin
        x <= y;
        y <= x ^ f(y) ^ k_r;
      end else begin
        x <= y ^ f(x) ^ k_r;
        y <= x;
      end
      r <= r + 7'd1;
      if (r == 7'd67) begin
        busy <= 1'b0;
        done <= 1'b1;
      end
    end
  end

endmodule
