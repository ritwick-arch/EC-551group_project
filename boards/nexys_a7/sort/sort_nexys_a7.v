module sort_nexys_a7 (
  input  wire clock,
  input  wire cpu_resetn,
  input  wire uart_rx,
  output wire uart_tx
  );

  // Divide the 100 MHz board clock down to 50 MHz.
  reg clock_50mhz;
  initial clock_50mhz = 1'b0;
  always @(posedge clock) clock_50mhz <= !clock_50mhz;

  // CPU_RESETN is active-low, RVX expects an active-high reset.
  reg reset;
  always @(posedge clock_50mhz) reset <= !cpu_resetn;

  rvx #(
    .CLOCK_FREQUENCY  (50000000         ),
    .MEMORY_INIT_FILE ("sort.hex"       )
  ) rvx_instance (
    .clock            (clock_50mhz      ),
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
