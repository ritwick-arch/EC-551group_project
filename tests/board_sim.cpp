// Board-level simulation: drives the 100 MHz clock, prints what the design sends on
// uart_tx (9600 8N1), and optionally sends a file to uart_rx once "ready" appears.
#include VTOP_H
#include "verilated.h"
#include <cstdio>
#include <string>

int main(int argc, char **argv) {
  Verilated::commandArgs(argc, argv);
  const char *in_path = argc > 1 && argv[1][0] != '+' ? argv[1] : nullptr;
  std::string input;
  if (in_path) {
    FILE *f = fopen(in_path, "rb");
    if (!f) { fprintf(stderr, "cannot open %s\n", in_path); return 1; }
    for (int ch; (ch = fgetc(f)) != EOF;) input += (char)ch;
    fclose(f);
  }

  VTOP top;
  const double bit = 100e6 / 9600.0;
  top.clock = 0; top.cpu_resetn = 0; top.uart_rx = 1;
  std::string out;
  long rx_next = -1; int rx_bit = -1, rx_byte = 0, prev = 1;
  size_t tx_pos = 0; long tx_next = -1; int tx_bit = -1;
  bool sending = false;

  for (long cyc = 0; cyc < 2000000000L; ++cyc) {
    if (cyc == 100) top.cpu_resetn = 1;
    top.clock = 1; top.eval(); top.clock = 0; top.eval();

    // Decode the design's transmit line.
    int tx = top.uart_tx;
    if (rx_bit < 0 && prev == 1 && tx == 0) { rx_next = cyc + (long)(1.5 * bit); rx_bit = 0; rx_byte = 0; }
    else if (rx_bit >= 0 && cyc == rx_next) {
      if (rx_bit < 8) { rx_byte |= tx << rx_bit; ++rx_bit; rx_next = cyc + (long)bit; }
      else {
        out += (char)rx_byte; rx_bit = -1;
        if (rx_byte != '\r') { putchar(rx_byte); fflush(stdout); }
        if (in_path && !sending && out.find("ready") != std::string::npos) { sending = true; tx_next = cyc + (long)bit; }
        if (out.size() >= 6 && out.compare(out.size() - 6, 6, "done\r\n") == 0) return 0;
      }
    }
    prev = tx;

    // Send the input file on the design's receive line.
    if (sending && tx_pos < input.size() && cyc >= tx_next) {
      int b = (unsigned char)input[tx_pos];
      if (tx_bit < 0) { top.uart_rx = 0; tx_bit = 0; }
      else if (tx_bit < 8) { top.uart_rx = (b >> tx_bit) & 1; ++tx_bit; }
      else if (tx_bit == 8) { top.uart_rx = 1; ++tx_bit; }
      else { tx_bit = -1; ++tx_pos; tx_next = cyc + (long)(2 * bit); continue; }
      tx_next = cyc + (long)bit;
    }
  }
  fprintf(stderr, "FAIL: timeout\n");
  return 1;
}
