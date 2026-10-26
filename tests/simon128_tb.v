// Checks simon128 against the official SIMON-128/128 test vector, both directions.
module simon128_tb (input wire clock);

  localparam [127:0] KEY = 128'h0f0e0d0c0b0a09080706050403020100;
  localparam [127:0] PT  = 128'h63736564207372656c6c657661727420;
  localparam [127:0] CT  = 128'h49681b1e1e54fe3f65aa832af84e0bbc;

  reg          reset    = 1'b1;
  reg          start    = 1'b0;
  reg          decrypt  = 1'b0;
  reg  [127:0] block_in = 128'h0;
  wire [127:0] block_out;
  wire         ready, done;

  simon128 #(.KEY(KEY)) dut (
    .clock     (clock    ),
    .reset     (reset    ),
    .start     (start    ),
    .decrypt   (decrypt  ),
    .block_in  (block_in ),
    .block_out (block_out),
    .ready     (ready    ),
    .done      (done     )
  );

  reg [2:0]  step   = 3'd0;
  reg [15:0] cycles = 16'd0;
  reg [15:0] t0;

  always @(posedge clock) begin
    cycles <= cycles + 16'd1;
    start  <= 1'b0;
    case (step)
      3'd0: if (cycles == 16'd3) begin reset <= 1'b0; step <= 3'd1; end
      3'd1: if (ready) begin block_in <= PT; decrypt <= 1'b0; start <= 1'b1; t0 <= cycles; step <= 3'd2; end
      3'd2: if (done) begin
        if (block_out !== CT) begin $display("FAIL encrypt: got %h", block_out); $stop; end
        $display("encrypt ok (%0d cycles)", cycles - t0);
        step <= 3'd3;
      end
      3'd3: if (ready) begin block_in <= CT; decrypt <= 1'b1; start <= 1'b1; step <= 3'd4; end
      3'd4: if (done) begin
        if (block_out !== PT) begin $display("FAIL decrypt: got %h", block_out); $stop; end
        $display("PASS simon128");
        $finish;
      end
      default: ;
    endcase
  end

endmodule
