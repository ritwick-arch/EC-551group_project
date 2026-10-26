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

**Encrypted sort** (`boards/nexys_a7/enc_sort`): program the board as above and press
CPU RESET. The terminal shows the 16 input ciphertexts, the 16 sorted ciphertexts, and
the cycle count of every SE op (min equals max). Save the terminal text to a file, then
`python host/owner.py decrypt -f log.txt` shows the plaintext values in sorted order.

**Sealed-bid auction** (`boards/nexys_a7/auction`): program the board, close any serial
terminal, then on the laptop (`pip install pyserial`):
`python host/owner.py auction --port COM5 120 340 275` and press CPU RESET when asked.
It prints what the board sees (ciphertext only), then e.g. `bidder 2 wins at 340`.

**New encrypted inputs** (on SCC, with the RISC-V GCC):
```
python3 host/owner.py header 29 -3 17 8 -o sw/enc_sort/inputs.h
cmake -S sw/enc_sort -B build/enc_sort -DTOOLCHAIN_PREFIX=<gcc dir>/bin/riscv-none-elf-
make -C build/enc_sort && cp build/enc_sort/enc_sort.hex boards/nexys_a7/enc_sort/
```

**Tests** (on SCC):
```
python3 -m pytest host
tests/run.sh simon128_tb tests/simon128_tb.v hw/simon128.v
python3 tests/gen_se_vectors.py && tests/run.sh se_unit_tb tests/se_unit_tb.v hw/se_unit.v hw/simon128.v
tests/run_board.sh enc_sort | python3 host/owner.py decrypt
python3 host/owner.py auction 120 340 275 --save build/sim/bids.txt
tests/run_board.sh auction build/sim/bids.txt > build/sim/auction.log && python3 host/owner.py auction-result build/sim/auction.log
```

**Limitations:** the key is a fixed constant (`KEY` in `hw/se_unit.v` and `host/se.py`), so
anyone with the bitstream can extract it; key exchange is the stretch goal. Salts come from
an LFSR, which is fine for a demo but not cryptographically random. Like the paper, SE
protects confidentiality, not integrity.
