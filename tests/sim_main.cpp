// Generic Verilator driver: toggles `clock` until the testbench calls $finish.
#include VTOP_H
#include "verilated.h"
#include <cstdio>

int main(int argc, char **argv) {
  Verilated::commandArgs(argc, argv);
  VTOP top;
  for (long i = 0; i < 200000000L && !Verilated::gotFinish(); i++) {
    top.clock = 0;
    top.eval();
    top.clock = 1;
    top.eval();
  }
  if (!Verilated::gotFinish()) {
    printf("FAIL: timeout\n");
    return 1;
  }
  top.final();
  return 0;
}
