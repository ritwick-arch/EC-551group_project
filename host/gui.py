#!/usr/bin/env python3
"""Demo GUI for the encrypted sort: watch the board's RAM slots while it sorts.

    python host/gui.py --port COM5     # real Nexys A7 running boards/nexys_a7/enc_sort
    python host/gui.py                 # no board: built-in simulated board, same protocol

Only needs the standard library (Tkinter) plus pyserial for a real board.
The left panel runs the insecure plaintext baseline, the right panel runs SE mode.
"""
import argparse
import contextlib
import io
import random
import sys

import owner
import se

SLOT_BASE = 0x1800   # element slots in board RAM, see sw/enc_sort/link.ld
RAM_SIZE = 0x2000
MAX_N = 16
SIM_PLAIN_CYCLES = (45, 60)   # simulated: no swap / swap
SIM_SE_CYCLES = 1131          # simulated: same for every step


# ---------------------------------------------------------------- simulated board
class SimBoard:
    """Speaks the same line protocol as sw/enc_sort/main.c, with no hardware."""

    def __init__(self):
        self.ram = [0] * (RAM_SIZE // 4)
        for i in range(10):  # a few firmware-like constants so the RAM scan has something to skip
            self.ram[0x1000 // 4 + i] = 10 ** i
        self.n = self.i = self.j = 0
        self.mode = "plain"

    def sync(self):
        pass

    def _base(self, k):
        return SLOT_BASE // 4 + 4 * k

    def _words(self, k):
        return self.ram[self._base(k):self._base(k) + 4]

    def _ct(self, k):
        return owner.words_ct(self._words(k))

    def _set_ct(self, k, ct):
        for w in range(4):
            self.ram[self._base(k) + w] = (ct >> (32 * w)) & 0xFFFFFFFF

    def _show(self):
        return [f"m {SLOT_BASE + 16 * k:08x} " + " ".join(f"{w:08x}" for w in self._words(k))
                for k in range(self.n)]

    def cmd(self, line, data=()):
        if line.startswith("load "):
            self.mode = "se" if line.startswith("load se ") else "plain"
            self.n = int(line.split()[2])
            for k in range(4 * MAX_N):
                self.ram[SLOT_BASE // 4 + k] = 0
            for k, text in enumerate(data):
                if self.mode == "se":
                    self._set_ct(k, int(text, 16))
                else:
                    self.ram[self._base(k)] = int(text) & 0xFFFFFFFF
            self.i = self.j = 0
            return []
        if line == "show":
            return self._show()
        if line == "step":
            return self._step()
        if line == "dump":
            return [f"d {a:08x} " + " ".join(f"{w:08x}" for w in self.ram[a // 4:a // 4 + 8])
                    for a in range(0, RAM_SIZE, 32)]
        if line.startswith("peek "):
            addr = int(line.split()[1], 16) & ~3
            word = self.ram[addr // 4] if addr < RAM_SIZE else 0
            return [f"p {addr:08x} {word:08x}"]
        return ["?"]

    def _step(self):
        if self.i >= self.n - 1:
            return ["sorted"]
        j = self.j
        if self.mode == "plain":
            a, b = owner.signed32(self.ram[self._base(j)]), owner.signed32(self.ram[self._base(j + 1)])
            swap = b < a
            if swap:
                self.ram[self._base(j)], self.ram[self._base(j + 1)] = b & 0xFFFFFFFF, a & 0xFFFFFFFF
            cycles = SIM_PLAIN_CYCLES[swap]
        else:
            lo_ct, hi_ct = self._ct(j), self._ct(j + 1)
            gt = se.se_op(se.OPS["LT"], hi_ct, lo_ct, lo_ct)
            lo = se.se_op(se.OPS["CMOV"], hi_ct, lo_ct, gt)
            hi = se.se_op(se.OPS["CMOV"], lo_ct, hi_ct, gt)
            self._set_ct(j, lo)
            self._set_ct(j + 1, hi)
            cycles = SIM_SE_CYCLES
        self.j += 1
        if self.j >= self.n - 1 - self.i:
            self.j = 0
            self.i += 1
        return [f"step {j} {cycles}"] + self._show()


# ---------------------------------------------------------------- demo logic (no widgets)
class Session:
    """One sort run on the board. Kept separate from Tk so it can be tested without a display."""

    def __init__(self, board):
        self.board = board
        self.mode = None
        self.values = []
        self.rows = []
        self.prev = None
        self.compared = None
        self.k = 0
        self.total = 0
        self.cycles = []
        self.log = []

    def start(self, mode, values):
        self.mode, self.values = mode, list(values)
        n = len(values)
        if mode == "se":
            cts = [se.encrypt(v) for v in values]
            self.log = ["Laptop encrypts the numbers. The board only ever receives:"]
            seen = set()
            for v, ct in zip(values, cts):
                same = "   (same value as above, different ciphertext)" if v in seen else ""
                seen.add(v)
                self.log.append(f"  {v:>11} -> {ct:032x}{same}")
            self.board.cmd(f"load se {n}", [f"{c:032x}" for c in cts])
        else:
            self.log = [f"Laptop sends plaintext: {' '.join(map(str, values))}"]
            self.board.cmd(f"load plain {n}", values)
        self.rows = owner.mem_rows(self.board.cmd("show"), "m")
        self.prev = self.compared = None
        self.k, self.total, self.cycles = 0, n * (n - 1) // 2, []

    @property
    def done(self):
        return self.k >= self.total

    def step(self):
        out = self.board.cmd("step")
        _, j, c = out[0].split()
        self.cycles.append(int(c))
        self.prev, self.rows = self.rows, owner.mem_rows(out[1:], "m")
        self.compared = (int(j), int(j) + 1)
        self.k += 1
        return int(j), int(c)

    def changed(self, i):
        return self.prev is not None and self.prev[i][1] != self.rows[i][1]

    def value(self, i):
        return owner.slot_value(self.mode, self.rows[i][1])

    def result_ok(self):
        return [self.value(i) for i in range(len(self.rows))] == sorted(self.values)

    def timing_note(self):
        if min(self.cycles) == max(self.cycles):
            return f"every step took exactly {self.cycles[0]} cycles"
        return f"steps took {min(self.cycles)} to {max(self.cycles)} cycles (timing leaks swaps)"

    def scan_ram(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            owner.check_memory(self.board, self.mode, self.values)
        return buf.getvalue()


# ---------------------------------------------------------------- Tk front end
def run_gui(board, title):
    import tkinter as tk
    from tkinter import messagebox, scrolledtext

    mono = ("Courier New", 10)
    bold = ("Courier New", 10, "bold")
    YELLOW, GREY, RED = "#fff2a8", "#9a9a9a", "#c62828"

    root = tk.Tk()
    root.title(title)

    class Panel:
        def __init__(self, parent, heading, col):
            self.frame = tk.LabelFrame(parent, text=heading, font=("TkDefaultFont", 11, "bold"), padx=6, pady=6)
            self.frame.grid(row=1, column=col, padx=8, pady=4, sticky="n")
            head = ("slot", "RAM words at 0x1800 (address order)", "", "value")
            for c, text in enumerate(head):
                tk.Label(self.frame, text=text, font=bold, anchor="w").grid(row=0, column=c, sticky="w", padx=3)
            self.rows = []
            for r in range(MAX_N):
                cells = [tk.Label(self.frame, font=mono, anchor="w") for _ in range(4)]
                for c, w in enumerate(cells):
                    w.grid(row=r + 1, column=c, sticky="w", padx=3)
                self.rows.append(cells)
            self.clear()

        def clear(self):
            for r, cells in enumerate(self.rows):
                cells[0].config(text=f"{r:>2}", fg=GREY, bg=root.cget("bg"))
                cells[1].config(text="-", fg=GREY, bg=root.cget("bg"))
                cells[2].config(text="", bg=root.cget("bg"))
                cells[3].config(text="", bg=root.cget("bg"))

        def draw(self, s, reveal):
            for r, cells in enumerate(self.rows):
                if r >= len(s.rows):
                    cells[0].config(fg=GREY, bg=root.cget("bg"))
                    cells[1].config(text="", bg=root.cget("bg"))
                    cells[2].config(text="", bg=root.cget("bg"))
                    cells[3].config(text="", bg=root.cget("bg"))
                    continue
                hot = s.compared is not None and r in s.compared
                bg = YELLOW if hot else root.cget("bg")
                changed = s.changed(r)
                cells[0].config(text=f"{r:>2}", fg="black", bg=bg)
                cells[1].config(text=" ".join(f"{w:08x}" for w in s.rows[r][1]),
                                fg=RED if changed else "black", font=bold if changed else mono, bg=bg)
                cells[2].config(text="rewritten" if changed else "", fg=RED, bg=bg)
                if s.mode == "se" and not reveal:
                    cells[3].config(text="(encrypted)", fg=GREY, bg=bg)
                else:
                    cells[3].config(text=f"{s.value(r):>12}", fg="black", bg=bg)

    # --- controls
    top = tk.Frame(root)
    top.grid(row=0, column=0, columnspan=2, sticky="we", padx=8, pady=6)
    tk.Label(top, text="Numbers (2-16):").pack(side="left")
    entry = tk.Entry(top, width=34, font=mono)
    entry.insert(0, "4242 -17 999 4242 31337")
    entry.pack(side="left", padx=4)
    reveal = tk.BooleanVar(value=False)

    panels = {"plain": Panel(root, "PLAINTEXT baseline (insecure)", 0),
              "se": Panel(root, "SEQUESTERED ENCRYPTION", 1)}
    state = {"s": None, "auto": False, "after": None}

    bottom = tk.Frame(root)
    bottom.grid(row=2, column=0, columnspan=2, sticky="we", padx=8, pady=4)
    status = tk.Label(bottom, text="Pick numbers, then start a mode.", font=("TkDefaultFont", 11), anchor="w")
    status.pack(fill="x")
    log = scrolledtext.ScrolledText(bottom, height=9, font=("Courier New", 9))
    log.pack(fill="x", pady=4)

    def say(text):
        log.insert("end", text + "\n")
        log.see("end")

    def fail(exc):
        stop_auto()
        messagebox.showerror("Board error", f"{exc}\n\nCheck the COM port, close other serial terminals, press CPU RESET.")

    def parse_numbers():
        try:
            vals = [int(t) for t in entry.get().replace(",", " ").split()]
        except ValueError:
            vals = []
        if not 2 <= len(vals) <= MAX_N or any(not -2 ** 31 <= v < 2 ** 31 for v in vals):
            messagebox.showwarning("Numbers", "Enter 2 to 16 whole numbers that fit in 32 bits.")
            return None
        return vals

    def redraw():
        s = state["s"]
        if s:
            panels[s.mode].draw(s, reveal.get())

    def start(mode):
        vals = parse_numbers()
        if vals is None:
            return
        stop_auto()
        try:
            s = Session(board)
            s.start(mode, vals)
        except Exception as exc:  # serial errors etc.
            return fail(exc)
        state["s"] = s
        panels[mode].clear()
        log.delete("1.0", "end")
        for line in s.log:
            say(line)
        redraw()
        status.config(text=f"{mode.upper()} loaded. Step 0/{s.total}. Press Step or Auto.")

    def step():
        s = state["s"]
        if s is None or s.done:
            return
        try:
            j, c = s.step()
        except Exception as exc:
            return fail(exc)
        redraw()
        text = f"step {s.k}/{s.total}: compared slots {j} and {j + 1} in {c} cycles"
        if s.done:
            stop_auto()
            verdict = "CORRECT" if s.result_ok() else "WRONG"
            text += f"   |   DONE, owner check with key: {verdict}"
            say(f"\nSort finished: {s.timing_note()}.")
        status.config(text=text)

    def tick():
        state["after"] = None
        if state["auto"]:
            step()
            s = state["s"]
            if state["auto"] and s and not s.done:
                state["after"] = root.after(int(speed.get()), tick)

    def stop_auto():
        state["auto"] = False
        auto_btn.config(text="Auto-play")
        if state["after"]:
            root.after_cancel(state["after"])
            state["after"] = None

    def toggle_auto():
        if state["auto"]:
            return stop_auto()
        if state["s"] is None or state["s"].done:
            return
        state["auto"] = True
        auto_btn.config(text="Pause")
        tick()

    def scan():
        s = state["s"]
        if s is None:
            return
        root.config(cursor="watch")
        root.update()
        try:
            text = s.scan_ram()
        except Exception as exc:
            return fail(exc)
        finally:
            root.config(cursor="")
        say(text.rstrip())

    tk.Button(top, text="Random", command=lambda: (entry.delete(0, "end"), entry.insert(
        0, " ".join(str(random.randint(-9999, 99999)) for _ in range(8))))).pack(side="left", padx=2)
    tk.Button(top, text="Start plaintext", command=lambda: start("plain")).pack(side="left", padx=(12, 2))
    tk.Button(top, text="Start SE", command=lambda: start("se")).pack(side="left", padx=2)
    tk.Button(top, text="Step", command=step, width=7).pack(side="left", padx=(12, 2))
    auto_btn = tk.Button(top, text="Auto-play", command=toggle_auto, width=9)
    auto_btn.pack(side="left", padx=2)
    speed = tk.Scale(top, from_=100, to=1500, orient="horizontal", length=90, showvalue=False)
    speed.set(500)
    speed.pack(side="left")
    tk.Button(top, text="Scan board RAM", command=scan).pack(side="left", padx=(12, 2))
    tk.Checkbutton(top, text="Show decrypted values (owner view)", variable=reveal,
                   command=redraw).pack(side="left", padx=(12, 0))

    root.bind("<Return>", lambda e: step() if root.focus_get() is not entry else None)
    root.bind("<space>", lambda e: step() if root.focus_get() is not entry else None)
    root.mainloop()


def main():
    p = argparse.ArgumentParser(description="Encrypted-sort demo GUI")
    p.add_argument("--port", help="board serial port, e.g. COM5 or /dev/ttyUSB1 (omit to use the simulated board)")
    p.add_argument("--baud", type=int, default=115200)
    args = p.parse_args()
    if args.port:
        board = owner.Board(args.port, args.baud)
        print("Connecting... press CPU RESET on the board if nothing happens.")
        board.sync()
        title = f"Sequestered Encryption sort demo - board on {args.port}"
    else:
        board = SimBoard()
        title = "Sequestered Encryption sort demo - SIMULATED board"
    run_gui(board, title)


if __name__ == "__main__":
    sys.exit(main())
