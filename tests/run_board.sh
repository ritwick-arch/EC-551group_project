#!/bin/bash
# Usage: tests/run_board.sh <app> [uart input file]   e.g. tests/run_board.sh enc_sort
# Simulates boards/nexys_a7/<app> and prints what the board would send over UART.
set -e
APP=$1
IN=${2:+$(realpath "$2")}
VROOT=${VERILATOR_ROOT:-/share/pkg.7/verilator/4.108/install/share/verilator}
VBIN=${VERILATOR_BIN:-/share/pkg.7/verilator/4.108/install/bin/verilator_bin}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
BOARD=$ROOT/boards/nexys_a7/$APP
TOP=${APP}_nexys_a7
OUT=$ROOT/build/sim/$TOP
export VERILATOR_ROOT=$VROOT
mkdir -p "$OUT"
"$VBIN" --cc --exe -O2 -Wno-fatal -Wno-WIDTH --top-module "$TOP" -Mdir "$OUT" \
  -CFLAGS "-DVTOP=V$TOP -DVTOP_H=\\\"V$TOP.h\\\" -include limits" \
  "$BOARD/$TOP.v" "$ROOT"/rvx/hardware/rvx_*.v "$ROOT"/hw/*.v "$ROOT/tests/board_sim.cpp" > /dev/null
make -s -j8 -C "$OUT" -f "V$TOP.mk" "V$TOP" > /dev/null
cd "$BOARD" && "$OUT/V$TOP" $IN
