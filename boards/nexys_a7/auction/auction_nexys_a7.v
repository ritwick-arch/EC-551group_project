module auction_nexys_a7 (
  input  wire clock,
  input  wire cpu_resetn,
  input  wire uart_rx,
  output wire uart_tx
  );

  // Divide the 100 MHz board clock down to 25 MHz, which leaves timing slack for the SE unit.
  reg [1:0] clock_div;
  initial clock_div = 2'd0;
  always @(posedge clock) clock_div <= clock_div + 2'd1;
  wire clock_25mhz = clock_div[1];

  // CPU_RESETN is active-low, RVX expects an active-high reset.
  reg reset;
  always @(posedge clock_25mhz) reset <= !cpu_resetn;

  rvx_se #(
    .CLOCK_FREQUENCY  (25000000         ),
    .MEMORY_INIT_FILE ("auction.hex"    )
  ) rvx_instance (
    .clock            (clock_25mhz      ),
    .reset            (reset            ),
    .halt             (1'b0             ),
    .uart_rx          (uart_rx          ),
    .uart_tx          (uart_tx          ),
    .gpio_input       (1'b0             ),
    .gpio_oe          (                 ),
    .gpio_output      (                 ),
    .sclk             (                 ),
    .pico             (                 ),
    .poci             (1'b0             ),
    .cs               (                 )
  );

endmodule
