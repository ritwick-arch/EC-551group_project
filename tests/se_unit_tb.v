// Drives se_unit over its bus port with Python-generated vectors, decrypts each
// result with a second SIMON core, and checks every op takes the same cycle count.
module se_unit_tb (input wire clock);

  localparam integer N = 120;
  localparam [127:0] KEY = 128'h2B7E151628AED2A6ABF7158809CF4F3C;

  reg [127:0] vec [0:5*N-1];
  initial $readmemh("build/sim/se_vectors.hex", vec);

  reg         reset = 1'b1;
  reg  [6:0]  addr  = 7'd0;
  reg  [31:0] wdata = 32'd0;
  reg         wreq  = 1'b0;
  reg         rreq  = 1'b0;
  wire [31:0] rdata;
  wire        rresp, wresp;

  se_unit #(.KEY(KEY)) dut (
    .clock          (clock),
    .reset          (reset),
    .rw_address     (addr ),
    .read_data      (rdata),
    .read_request   (rreq ),
    .read_response  (rresp),
    .write_data     (wdata),
    .write_request  (wreq ),
    .write_response (wresp)
  );

  reg          chk_start = 1'b0;
  reg  [127:0] chk_in    = 128'd0;
  wire [127:0] chk_out;
  wire         chk_ready, chk_done;

  simon128 #(.KEY(KEY)) chk (
    .clock     (clock    ),
    .reset     (reset    ),
    .start     (chk_start),
    .decrypt   (1'b1     ),
    .block_in  (chk_in   ),
    .block_out (chk_out  ),
    .ready     (chk_ready),
    .done      (chk_done )
  );

  integer     v = 0;
  reg [3:0]   k = 4'd0;
  reg [3:0]   step = 4'd0;
  reg [31:0]  cycles = 32'd0, t0 = 32'd0, lat = 32'd0, first_lat = 32'd0;
  reg [127:0] r = 128'd0;

  wire [127:0] op_w = vec[5*v];
  wire [127:0] a    = vec[5*v+1];
  wire [127:0] b    = vec[5*v+2];
  wire [127:0] c    = vec[5*v+3];
  wire [127:0] exp  = vec[5*v+4];
  wire [127:0] src  = (k < 4'd4) ? a : (k < 4'd8) ? b : c;

  always @(posedge clock) begin
    cycles    <= cycles + 32'd1;
    wreq      <= 1'b0;
    rreq      <= 1'b0;
    chk_start <= 1'b0;
    case (step)
      4'd0: begin
        if (cycles == 32'd3) reset <= 1'b0;
        else if (!reset && chk_ready && !dut.busy) step <= 4'd1;
      end
      4'd1: begin
        wreq <= 1'b1;
        if (k < 4'd12) begin
          addr  <= {1'b0, k[3:2], k[1:0], 2'b00};
          wdata <= src[32*k[1:0] +: 32];
          k     <= k + 4'd1;
        end else begin
          addr  <= 7'h40;
          wdata <= op_w[31:0];
          step  <= 4'd2;
        end
      end
      4'd2: if (dut.busy) begin t0 <= cycles; step <= 4'd3; end
      4'd3: if (!dut.busy) begin lat <= cycles - t0; addr <= 7'h44; rreq <= 1'b1; step <= 4'd4; end
      4'd4: if (rresp) begin
        if (rdata[0]) begin $display("FAIL: STATUS still busy"); $stop; end
        k <= 4'd0;
        step <= 4'd5;
      end
      4'd5: begin addr <= {3'b011, k[1:0], 2'b00}; rreq <= 1'b1; step <= 4'd6; end
      4'd6: if (rresp) begin
        r[32*k[1:0] +: 32] <= rdata;
        if (k == 4'd3) step <= 4'd7;
        else begin k <= k + 4'd1; step <= 4'd5; end
      end
      4'd7: if (chk_ready) begin chk_in <= r; chk_start <= 1'b1; step <= 4'd8; end
      4'd8: if (chk_done) begin
        if (chk_out[127:64] !== exp[63:0]) begin
          $display("FAIL vector %0d op %0d: got %h expected %h", v, op_w[2:0], chk_out[127:64], exp[63:0]);
          $stop;
        end
        if (v == 0) first_lat <= lat;
        else if (lat != first_lat) begin
          $display("FAIL vector %0d: %0d cycles, first op took %0d", v, lat, first_lat);
          $stop;
        end
        if (v == N - 1) begin
          $display("PASS se_unit: %0d ops correct, every op took %0d cycles", N, first_lat);
          $finish;
        end
        v    <= v + 1;
        k    <= 4'd0;
        step <= 4'd1;
      end
      default: ;
    endcase
  end

endmodule
