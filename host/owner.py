# Data-owner tool: encrypts inputs for the FPGA and decrypts what it sends back.
import argparse
import os
import re
import sys
import time

import se

HEX_CT = re.compile(r"\b[0-9a-fA-F]{32}\b")


def ct_hex(ct):
    return f"{ct:032x}"


def auction_payload(bids):
    lines = [str(len(bids))]
    for bidder, bid in enumerate(bids, start=1):
        lines += [ct_hex(se.encrypt(bid)), ct_hex(se.encrypt(bidder))]
    return ("\n".join(lines) + "\n").encode()


def report_auction(lines):
    found = {}
    for line in lines:
        parts = line.split()
        if len(parts) == 2 and parts[0] in ("winner", "price") and HEX_CT.fullmatch(parts[1]):
            found[parts[0]] = se.decrypt(int(parts[1], 16))
    if len(found) == 2:
        print(f"\nData owner decrypts: bidder {found['winner']} wins at {found['price']}")
    else:
        print("\nNo winner/price lines found")


def run_auction(bids, port, baud):
    import serial  # pyserial, only needed for the live board

    with serial.Serial(port, baud, timeout=1) as s:
        print("Press CPU RESET on the board...")
        while b"ready" not in s.readline():
            pass
        s.write(auction_payload(bids))
        lines = []
        while True:
            line = s.readline().decode(errors="replace").strip()
            if line:
                print(line)
                lines.append(line)
            if line == "done":
                break
    report_auction(lines)


class Board:
    """Line-based link to the enc_sort demo firmware; every reply ends with "ok"."""

    def __init__(self, port, baud):
        import serial  # pyserial, only needed for the live board

        self.s = serial.Serial(port, baud, timeout=1)

    def sync(self):
        print("Waiting for the board (press CPU RESET if nothing happens)...")
        while True:
            self.s.write(b"\n")
            if b"ready" in self.s.readline():
                return

    def cmd(self, line, data=()):
        self.s.write("".join(f"{x}\n" for x in (line, *data)).encode())
        out = []
        while True:
            reply = self.s.readline().decode(errors="replace").strip()
            if reply == "ok":
                return out
            if reply and reply != "ready":
                out.append(reply)


def mem_rows(lines, tag):
    """Parses "<tag> <addr> <word> ..." lines into (address, words in address order)."""
    rows = []
    for line in lines:
        parts = line.split()
        if parts and parts[0] == tag:
            rows.append((int(parts[1], 16), [int(w, 16) for w in parts[2:]]))
    return rows


def words_ct(words):
    return sum(w << (32 * i) for i, w in enumerate(words))


# The element slots, matching .vec in sw/enc_sort/link.ld.
SLOTS = range(0x1800, 0x1900)


def looks_common(v):
    """Small or round numbers also occur in the firmware itself, e.g. its powers-of-ten table."""
    return abs(v) < 256 or str(abs(v)).rstrip("0") == "1"


def addr_list(addrs):
    return ", ".join(f"0x{a:04x}" for a in addrs[:4]) + (" ..." if len(addrs) > 4 else "")


def signed32(w):
    return w - (1 << 32) if w >> 31 else w


def slot_value(mode, words):
    return se.decrypt(words_ct(words)) if mode == "se" else signed32(words[0])


class Pacer:
    def __init__(self, auto):
        self.auto = auto

    def wait(self):
        if self.auto is not None:
            time.sleep(self.auto)
        elif input("Enter = next step, a = auto-play: ").strip().lower() == "a":
            self.auto = 0.3


def draw(mode, rows, prev, status):
    title = "PLAINTEXT mode (insecure baseline)" if mode == "plain" else "SE mode (Sequestered Encryption)"
    note = "value in RAM" if mode == "plain" else "owner decrypts"
    print("\x1b[H\x1b[2J", end="")
    print(f"{title}   {status}\n")
    print(f"  address  RAM contents, read back from the board      {note:>15}")
    for i, (addr, words) in enumerate(rows):
        changed = "*" if prev and prev[i][1] != words else " "
        mem = " ".join(f"{w:08x}" for w in words)
        print(f"  0x{addr:04x}   {mem} {changed} {slot_value(mode, words):>15}")
    print("\n  * = slot rewritten by this step")
    if mode == "se":
        print("  The last column is computed on the laptop with the key; the board never sees it.")


def sort_on_board(board, mode, values, pacer):
    n = len(values)
    if mode == "se":
        print("\nEncrypting on the laptop. The board only ever receives these ciphertexts:")
        cts, seen = [], set()
        for v in values:
            cts.append(se.encrypt(v))
            again = "   (same value as before, different ciphertext)" if v in seen else ""
            seen.add(v)
            print(f"  {v:>11} -> {cts[-1]:032x}{again}")
        board.cmd(f"load se {n}", [f"{c:032x}" for c in cts])
    else:
        print(f"\nSending plaintext to the board: {' '.join(map(str, values))}")
        board.cmd(f"load plain {n}", values)
    pacer.wait()

    rows = mem_rows(board.cmd("show"), "m")
    total = n * (n - 1) // 2
    draw(mode, rows, None, f"step 0/{total}")
    pacer.wait()
    cycles = []
    for k in range(1, total + 1):
        out = board.cmd("step")
        _, j, c = out[0].split()
        cycles.append(int(c))
        new = mem_rows(out[1:], "m")
        draw(mode, new, rows, f"step {k}/{total}: compared slots {j} and {int(j) + 1} in {c} cycles")
        rows = new
        if k < total:
            pacer.wait()

    result = [slot_value(mode, w) for _, w in rows]
    ok = "correct" if result == sorted(values) else "WRONG"
    print(f"\nResult: {' '.join(map(str, result))}  ({ok})")
    if min(cycles) == max(cycles):
        print(f"Every step took exactly {cycles[0]} cycles, so timing reveals nothing about the data.")
    else:
        print(f"Steps took {min(cycles)} to {max(cycles)} cycles, so timing shows when elements swapped.")


def check_memory(board, mode, values):
    words = {}
    for addr, ws in mem_rows(board.cmd("dump"), "d"):
        for i, w in enumerate(ws):
            words[addr + 4 * i] = w
    print(f"\nSearched all {4 * len(words)} bytes of board RAM for your numbers:")
    for v in sorted(set(values)):
        hits = [a for a, w in words.items() if w == v & 0xFFFFFFFF]
        in_slots = [a for a in hits if a in SLOTS]
        elsewhere = [a for a in hits if a not in SLOTS]
        found = ([f"in the element slots at {addr_list(in_slots)}"] if in_slots else []) + (
            [f"elsewhere at {addr_list(elsewhere)} (firmware constant)"] if elsewhere else [])
        print(f"  {v:>11}: {'; '.join(found) or 'not found'}")
    if mode == "se":
        key_words = {(se.KEY >> (32 * i)) & 0xFFFFFFFF for i in range(4)}
        hits = [a for a, w in words.items() if w in key_words]
        print(f"  {'SE key':>11}: {'FOUND' if hits else 'not found'}")
        regs = [mem_rows(board.cmd(f"peek {0x80040000 + 4 * i:x}"), "p")[0][1][0] for i in range(12)]
        state = "all zero" if not any(regs) else "NOT zero"
        print(f"  SE operand registers A, B, C (0x80040000-0x8004002c) read by the CPU: {state}")


def run_demo(values, port, baud, auto, modes):
    if not values:
        values = [int(v) for v in input("Numbers to sort (2 to 16 of them): ").split()]
    if not 2 <= len(values) <= 16 or any(not -2**31 <= v < 2**31 for v in values):
        sys.exit("Need 2 to 16 numbers that fit in 32 bits")
    common = [v for v in values if looks_common(v)]
    if common:
        print(f"Tip: small or round numbers ({' '.join(map(str, common))}) also appear in the firmware's "
              "own code, so the RAM search finds them in both modes. Other numbers make a cleaner demo.")
    if os.name == "nt":
        os.system("")  # turns on ANSI escape codes in the Windows console
    board = Board(port, baud)
    board.sync()
    pacer = Pacer(auto)
    for mode in modes:
        sort_on_board(board, mode, values, pacer)
        check_memory(board, mode, values)
        if mode != modes[-1] and auto is None:
            input("\nPress Enter for SE mode...")


def main():
    p = argparse.ArgumentParser(description="SE data-owner tool")
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("encrypt", help="print one ciphertext per value")
    e.add_argument("values", type=int, nargs="+")
    d = sub.add_parser("decrypt", help="decrypt every 32-hex-digit ciphertext in the text")
    d.add_argument("cts", nargs="*", help="ciphertexts; reads stdin when empty")
    d.add_argument("-f", "--file")
    a = sub.add_parser("auction", help="run the sealed-bid auction; bidder i gets the i-th bid")
    a.add_argument("bids", type=int, nargs="+")
    a.add_argument("--port", help="board serial port, e.g. COM5 or /dev/ttyUSB1")
    a.add_argument("--baud", type=int, default=9600)
    a.add_argument("--save", help="write the encrypted bids to a file instead (for simulation)")
    r = sub.add_parser("auction-result", help="decrypt winner and price from a saved board log")
    r.add_argument("file")
    m = sub.add_parser("demo", help="sort on the board while watching its memory, plaintext then SE")
    m.add_argument("values", type=int, nargs="*", help="2 to 16 numbers; asks for them when empty")
    m.add_argument("--port", required=True, help="board serial port, e.g. COM5 or /dev/ttyUSB1")
    m.add_argument("--baud", type=int, default=115200)
    m.add_argument("--auto", type=float, metavar="SECONDS", help="step automatically with this delay")
    m.add_argument("--mode", choices=["both", "plain", "se"], default="both")
    args = p.parse_args()

    if args.cmd == "encrypt":
        for v in args.values:
            print(ct_hex(se.encrypt(v)))
    elif args.cmd == "decrypt":
        if args.cts:
            lines = args.cts
        else:
            lines = (open(args.file) if args.file else sys.stdin).read().splitlines()
        for line in lines:
            cts = HEX_CT.findall(line)
            if cts:
                plain = " ".join(str(se.decrypt(int(c, 16))) for c in cts)
                print(f"{line.strip()}  ->  {plain}")
    elif args.cmd == "auction":
        if args.save:
            with open(args.save, "wb") as f:
                f.write(auction_payload(args.bids))
        elif args.port:
            run_auction(args.bids, args.port, args.baud)
        else:
            p.error("auction needs --port or --save")
    elif args.cmd == "auction-result":
        report_auction(open(args.file).read().splitlines())
    elif args.cmd == "demo":
        modes = ["plain", "se"] if args.mode == "both" else [args.mode]
        run_demo(args.values, args.port, args.baud, args.auto, modes)


if __name__ == "__main__":
    main()
