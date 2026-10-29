# EC-551group_project
Sequestered Encryption

## RVX hello world on the Nexys A7

1. Clone with the submodule: `git clone --recursive -b Lohit https://github.com/ritwick-arch/EC-551group_project.git`
   (or run `git submodule update --init` in an existing clone).
2. In Vivado's Tcl console: `source <repo>/boards/nexys_a7/hello_world/create_project.tcl`
3. Generate Bitstream, then program the board from Hardware Manager.
4. Open a serial terminal on the board's COM port at 9600 baud, 8N1.
5. Press CPU RESET: the terminal prints `Hello World from RVX!`

For the sort demo, source `boards/nexys_a7/sort/create_project.tcl` instead; after reset the
terminal prints the 16-element vector before and after sorting.

## Sequestered Encryption (SE) demos

The SE unit (`hw/se_unit.v`) sits on RVX's bus at `0x80040000` (`hw/rvx_se.v`). For every
operation it decrypts the operands with SIMON-128/128 (`hw/simon128.v`), computes, and
re-encrypts the result with a fresh salt. The RISC-V program only ever handles ciphertext.
Ops: ADD, SUB, MUL, LT, EQ, CMOV (`sw/common/se.h`). The data owner's side is
`host/owner.py`, built on the Python reference model `host/se.py`.

**Encrypted sort** (`boards/nexys_a7/enc_sort`, lab commands in `LAB_STEPS.md` there): an interactive demo that sorts the same
numbers twice while showing the element slots as they sit in board RAM (`0x1800`, one
16-byte slot per element). Program the board, close any serial terminal, then on the laptop
(`pip install pyserial`): `python host/owner.py demo --port COM5`. It asks for 2 to 16
numbers, then press Enter for each compare-and-swap step or `a` to auto-play
(`--auto 0.5` auto-plays from the start).
1. Plaintext mode: the slots hold the numbers in the clear, and step timing depends on
   whether elements swapped.
2. SE mode: the laptop encrypts the numbers (equal numbers get different ciphertexts), and
   the same slots only ever hold ciphertext. Both compared slots are rewritten at every step,
   so memory does not even show whether a swap happened, and every step takes the same
   number of cycles. The laptop's last column decrypts the slots with the key to show the
   sort progressing.
3. After each mode, the whole 8 KB of RAM is dumped and searched for the numbers (and, in SE
   mode, for the key), and the SE unit's operand registers are read back (always zero).

The board talks at 115200 baud and also answers typed commands: `load plain N` / `load se N`
followed by N values or ciphertexts, `step`, `show`, `dump`, `peek <hex address>`.

**Sealed-bid auction** (`boards/nexys_a7/auction`): program the board, close any serial
terminal, then on the laptop (`pip install pyserial`):
`python host/owner.py auction --port COM5 120 340 275` and press CPU RESET when asked.
It prints what the board sees (ciphertext only), then e.g. `bidder 2 wins at 340`.

**Rebuilding firmware** (on SCC, with the RISC-V GCC), e.g. for enc_sort:
```
cmake -S sw/enc_sort -B build/enc_sort -DTOOLCHAIN_PREFIX=<gcc dir>/bin/riscv-none-elf-
make -C build/enc_sort && cp build/enc_sort/enc_sort.hex boards/nexys_a7/enc_sort/
```

**Tests** (on SCC):
```
python3 -m pytest host
tests/run.sh simon128_tb tests/simon128_tb.v hw/simon128.v
python3 tests/gen_se_vectors.py && tests/run.sh se_unit_tb tests/se_unit_tb.v hw/se_unit.v hw/simon128.v
tests/run_demo.sh 31337 -4242 999 4242
python3 host/owner.py auction 120 340 275 --save build/sim/bids.txt
tests/run_board.sh auction build/sim/bids.txt > build/sim/auction.log && python3 host/owner.py auction-result build/sim/auction.log
```

The SE boards run RVX at 25 MHz; at 50 MHz the SE unit's bus decode missed timing.

**Limitations:** the key is a fixed constant (`KEY` in `hw/se_unit.v` and `host/se.py`), so
anyone with the bitstream can extract it; key exchange is the stretch goal. Salts come from
an LFSR, which is fine for a demo but not cryptographically random. Like the paper, SE
protects confidentiality, not integrity.
