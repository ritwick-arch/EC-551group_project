#!/bin/bash
# Usage: tests/run.sh <testbench> <verilog files...>   (builds into build/sim/<testbench>)
set -e
TB=$1; shift
VROOT=${VERILATOR_ROOT:-/share/pkg.7/verilator/4.108/install/share/verilator}
VBIN=${VERILATOR_BIN:-/share/pkg.7/verilator/4.108/install/bin/verilator_bin}
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=$HERE/../build/sim/$TB
export VERILATOR_ROOT=$VROOT
mkdir -p "$OUT"
"$VBIN" --cc --exe -O2 -Wno-fatal -Wno-WIDTH --top-module "$TB" -Mdir "$OUT" \
  -CFLAGS "-DVTOP=V$TB -DVTOP_H=\\\"V$TB.h\\\" -include limits" "$@" "$HERE/sim_main.cpp" > /dev/null
make -s -j8 -C "$OUT" -f "V$TB.mk" "V$TB" > /dev/null
"$OUT/V$TB"
