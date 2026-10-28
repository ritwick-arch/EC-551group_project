// Board-level simulation: drives the 100 MHz clock and bridges the design's UART (8N1, baud
// from $BAUD, default 9600). With a file argument it prints what the design sends and sends
// the file once "ready" appears; with --pty it bridges the UART to a pseudo-terminal instead.
#include VTOP_H
#include "verilated.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <string>
#include <termios.h>
#include <unistd.h>

int main(int argc, char **argv) {
  Verilated::commandArgs(argc, argv);
  const char *arg = argc > 1 && argv[1][0] != '+' ? argv[1] : nullptr;
  bool pty = arg && !strcmp(arg, "--pty");
  const char *in_path = pty ? nullptr : arg;
  std::string input;
  if (in_path) {
    FILE *f = fopen(in_path, "rb");
    if (!f) { fprintf(stderr, "cannot open %s\n", in_path); return 1; }
    for (int ch; (ch = fgetc(f)) != EOF;) input += (char)ch;
    fclose(f);
  }

  // The slave end stays open in raw mode so nothing is echoed back. A client may discard output
  // sent before it opened the pty, so it should prompt the board rather than wait for the banner.
  int master = -1;
  if (pty) {
    master = posix_openpt(O_RDWR | O_NOCTTY | O_NONBLOCK);
    if (master < 0 || grantpt(master) || unlockpt(master)) { perror("pty"); return 1; }
    int slave = open(ptsname(master), O_RDWR | O_NOCTTY);
    struct termios t;
    tcgetattr(slave, &t);
    cfmakeraw(&t);
    tcsetattr(slave, TCSANOW, &t);
    printf("pty %s\n", ptsname(master));
    fflush(stdout);
  }

  VTOP top;
  const char *baud = getenv("BAUD");
  const double bit = 100e6 / (baud ? atof(baud) : 9600.0);
  top.clock = 0; top.cpu_resetn = 0; top.uart_rx = 1;
  std::string out, to_pty;
  long rx_next = -1; int rx_bit = -1, rx_byte = 0, prev = 1;
  size_t tx_pos = 0; long tx_next = -1; int tx_bit = -1;
  bool sending = pty;

  for (long cyc = 0; pty || cyc < 2000000000L; ++cyc) {
    if (cyc == 100) top.cpu_resetn = 1;
    top.clock = 1; top.eval(); top.clock = 0; top.eval();

    // Decode the design's transmit line.
    int tx = top.uart_tx;
    if (rx_bit < 0 && prev == 1 && tx == 0) { rx_next = cyc + (long)(1.5 * bit); rx_bit = 0; rx_byte = 0; }
    else if (rx_bit >= 0 && cyc == rx_next) {
      if (rx_bit < 8) { rx_byte |= tx << rx_bit; ++rx_bit; rx_next = cyc + (long)bit; }
      else {
        rx_bit = -1;
        if (pty) to_pty += (char)rx_byte;
        else {
          out += (char)rx_byte;
          if (rx_byte != '\r') { putchar(rx_byte); fflush(stdout); }
          if (in_path && !sending && out.find("ready") != std::string::npos) { sending = true; tx_next = cyc + (long)bit; }
          if (out.size() >= 6 && out.compare(out.size() - 6, 6, "done\r\n") == 0) return 0;
        }
      }
    }
    prev = tx;

    // Move bytes between the pty and the UART buffers.
    if (pty && cyc % 1000 == 0) {
      if (!to_pty.empty()) {
        ssize_t n = write(master, to_pty.data(), to_pty.size());
        if (n > 0) to_pty.erase(0, n);
      }
      char buf[256];
      ssize_t n = read(master, buf, sizeof buf);
      if (n > 0) input.append(buf, n);
    }

    // Send the input on the design's receive line.
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
