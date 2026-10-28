#!/bin/bash
# Usage: tests/run_demo.sh [numbers...]
# Runs host/owner.py demo (auto-play) against the simulated enc_sort board over a pty.
set -e
ROOT=$(cd "$(dirname "$0")/.." && pwd)
LOG=$ROOT/build/sim/demo_pty.txt
mkdir -p "$ROOT/build/sim"
rm -f "$LOG"
BAUD=115200 "$ROOT/tests/run_board.sh" enc_sort --pty > "$LOG" 2>&1 &
SIM=$!
trap 'kill $SIM 2>/dev/null' EXIT
until grep -q '^pty' "$LOG" 2>/dev/null; do
  kill -0 $SIM 2>/dev/null || { cat "$LOG"; exit 1; }
  sleep 1
done
python3 "$ROOT/host/owner.py" demo --port "$(awk '/^pty/{print $2}' "$LOG")" --auto 0 ${*:-4242 -17 999 4242 31337}
