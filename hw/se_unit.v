// Sequestered Encryption unit: decrypt -> ALU -> re-encrypt, as an RVX bus device.
// Map (byte offsets): 0x00 A, 0x10 B, 0x20 C, 0x30 R (128-bit ciphertexts, word 0 = bits 31:0),
// 0x40 OP (write starts), 0x44 STATUS (bit 0 = busy).
module se_unit #(
  parameter [127:0] KEY = 128'h2B7E151628AED2A6ABF7158809CF4F3C
) (
  input  wire        clock,
  input  wire        reset,
  input  wire [6:0]  rw_address,
  output reg  [31:0] read_data,
  input  wire        read_request,
  output reg         read_response,
  input  wire [31:0] write_data,
  input  wire        write_request,
  output reg         write_response
  );

  localparam OP_ADD  = 3'd0;
  localparam OP_SUB  = 3'd1;
  localparam OP_MUL  = 3'd2;
  localparam OP_LT   = 3'd3;
  localparam OP_EQ   = 3'd4;
  localparam OP_CMOV = 3'd5;

  localparam S_IDLE  = 3'd0;
  localparam S_DEC_A = 3'd1;
  localparam S_DEC_B = 3'd2;
  localparam S_DEC_C = 3'd3;
  localparam S_ALU   = 3'd4;
  localparam S_ENC   = 3'd5;

  // Software-visible state: ciphertext only.
  reg [127:0] ct_a, ct_b, ct_c, ct_r;
  reg [2:0]   op;
  reg [2:0]   state;
  reg         launched;

  // Plaintext lives only here and has no path to read_data.
  reg [63:0] pa, pb, pc;
  reg [63:0] mul_a, mul_b, mul_acc;
  reg [5:0]  mul_count;
  reg [63:0] result;

  // Free-running LFSR supplies the salt (demo quality, not a true RNG).
  reg [63:0] lfsr;
  always @(posedge clock)
    if (reset)
      lfsr <= 64'hACE1_2468_1357_9BDF;
    else
      lfsr <= {lfsr[62:0], lfsr[63] ^ lfsr[62] ^ lfsr[60] ^ lfsr[59]};

  reg          sim_start;
  reg          sim_dec;
  reg  [127:0] sim_in;
  wire [127:0] sim_out;
  wire         sim_ready;
  wire         sim_done;

  simon128 #(.KEY(KEY)) cipher (
    .clock     (clock    ),
    .reset     (reset    ),
    .start     (sim_start),
    .decrypt   (sim_dec  ),
    .block_in  (sim_in   ),
    .block_out (sim_out  ),
    .ready     (sim_ready),
    .done      (sim_done )
  );

  wire busy = (state != S_IDLE) || !sim_ready;

  always @(*) begin
    case (op)
      OP_ADD:  result = pa + pb;
      OP_SUB:  result = pa - pb;
      OP_MUL:  result = mul_acc;
      OP_LT:   result = {63'd0, $signed(pa) < $signed(pb)};
      OP_EQ:   result = {63'd0, pa == pb};
      OP_CMOV: result = (pc != 64'd0) ? pa : pb;
      default: result = 64'd0;
    endcase
  end

  always @(posedge clock) begin
    if (reset) begin
      state     <= S_IDLE;
      op        <= 3'd0;
      launched  <= 1'b0;
      sim_start <= 1'b0;
    end else begin
      sim_start <= 1'b0;
      case (state)
        S_IDLE: begin
          if (write_request) begin
            case (rw_address[6:4])
              3'd0: ct_a[32*rw_address[3:2] +: 32] <= write_data;
              3'd1: ct_b[32*rw_address[3:2] +: 32] <= write_data;
              3'd2: ct_c[32*rw_address[3:2] +: 32] <= write_data;
              3'd4: if (rw_address[3:2] == 2'd0) begin
                op       <= write_data[2:0];
                launched <= 1'b0;
                state    <= S_DEC_A;
              end
              default: ;
            endcase
          end
        end
        S_DEC_A, S_DEC_B, S_DEC_C: begin
          if (!launched && sim_ready) begin
            sim_in    <= (state == S_DEC_A) ? ct_a : (state == S_DEC_B) ? ct_b : ct_c;
            sim_dec   <= 1'b1;
            sim_start <= 1'b1;
            launched  <= 1'b1;
          end else if (launched && sim_done) begin
            if (state == S_DEC_A) pa <= sim_out[127:64];
            if (state == S_DEC_B) pb <= sim_out[127:64];
            if (state == S_DEC_C) begin
              pc        <= sim_out[127:64];
              mul_a     <= pa;
              mul_b     <= pb;
              mul_acc   <= 64'd0;
              mul_count <= 6'd0;
            end
            launched <= 1'b0;
            state    <= state + 3'd1;
          end
        end
        // Shift-and-add multiply: always 64 cycles, whatever the operands.
        S_ALU: begin
          mul_acc   <= mul_acc + (mul_a & {64{mul_b[0]}});
          mul_a     <= mul_a << 1;
          mul_b     <= mul_b >> 1;
          mul_count <= mul_count + 6'd1;
          if (mul_count == 6'd63)
            state <= S_ENC;
        end
        S_ENC: begin
          if (!launched && sim_ready) begin
            sim_in    <= {result, lfsr};
            sim_dec   <= 1'b0;
            sim_start <= 1'b1;
            launched  <= 1'b1;
          end else if (launched && sim_done) begin
            ct_r     <= sim_out;
            launched <= 1'b0;
            state    <= S_IDLE;
          end
        end
        default: state <= S_IDLE;
      endcase
    end
  end

  always @(posedge clock) begin
    if (reset) begin
      read_response  <= 1'b0;
      write_response <= 1'b0;
      read_data      <= 32'd0;
    end else begin
      read_response  <= read_request;
      write_response <= write_request;
      if (read_request) begin
        case (rw_address[6:4])
          3'd3:    read_data <= ct_r[32*rw_address[3:2] +: 32];
          3'd4:    read_data <= (rw_address[3:2] == 2'd1) ? {31'd0, busy} : 32'd0;
          default: read_data <= 32'd0;
        endcase
      end
    end
  end

endmodule
