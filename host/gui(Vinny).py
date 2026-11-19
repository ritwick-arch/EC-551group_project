#!/usr/bin/env python3
"""Demo GUI for the encrypted sort: watch the board's RAM slots while it sorts.

    python host/gui.py                 # opens with the built-in simulated board (no hardware)
    python host/gui.py --port COM5     # connects to a Nexys A7 running boards/nexys_a7/enc_sort

The board can also be picked inside the window (Board dropdown, then Connect).
Only needs the standard library (Tkinter) plus pyserial for a real board.
The left panel runs the insecure plaintext baseline, the right panel runs SE mode.
Under each panel a bar chart shows the cycles each step took, which is what a
timing attacker sees: uneven bars in plaintext mode, flat bars in SE mode.
"""
import argparse
import contextlib
import io
import queue
import random
import sys
import threading
import time

import owner
import se

SLOT_BASE = 0x1800   # element slots in board RAM, see sw/enc_sort/link.ld
RAM_SIZE = 0x2000
MAX_N = 16
# Simulated cycle counts, set to what LAB_STEPS.md reports for the real board.
SIM_PLAIN_CYCLES = (27, 31)   # no swap / swap
SIM_SE_CYCLES = 1327          # same for every step
SIM_LABEL = "Simulated board (no hardware)"
CONNECT_TIMEOUT = 15          # seconds to wait for "ready" when connecting
MAX_BAR = 26                  # widest a chart bar gets, in pixels


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
        self.pairs = []   # left slot of each step's compare
        self.swaps = []   # plaintext mode only: did that step change the slots?
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
        self.pairs, self.swaps = [], []

    @property
    def done(self):
        return self.k >= self.total

    def step(self):
        out = self.board.cmd("step")
        parts = out[0].split() if out else []
        if len(parts) != 3 or parts[0] != "step":
            raise RuntimeError(f"unexpected reply to \"step\": {out[:1]} (was the board reset?)")
        j, c = int(parts[1]), int(parts[2])
        self.cycles.append(c)
        self.pairs.append(j)
        self.prev, self.rows = self.rows, owner.mem_rows(out[1:], "m")
        if self.mode == "plain":
            self.swaps.append(self.changed(j))
        self.compared = (j, j + 1)
        self.k += 1
        return j, c

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

    def timing_leak(self):
        """Plaintext mode: guess "slow step = swap" from the timings alone and count the hits.

        Returns (steps guessed right, steps), or None when there is nothing to tell apart.
        """
        if self.mode != "plain" or not self.cycles or min(self.cycles) == max(self.cycles):
            return None
        fast = min(self.cycles)
        right = sum((c > fast) == swapped for c, swapped in zip(self.cycles, self.swaps))
        return right, len(self.swaps)

    def scan_ram(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            owner.check_memory(self.board, self.mode, self.values)
        return buf.getvalue()


# ---------------------------------------------------------------- helpers (no widgets)
class Worker:
    """Runs board calls on a background thread, one at a time, so the window never freezes.

    submit() and poll() are called from the Tk thread; the callbacks run inside poll().
    """

    def __init__(self):
        self.jobs, self.finished = queue.Queue(), queue.Queue()
        self.pending, self.since = 0, 0.0
        threading.Thread(target=self._run, daemon=True).start()

    @property
    def busy(self):
        return self.pending > 0

    def busy_for(self):
        return time.monotonic() - self.since if self.pending else 0.0

    def submit(self, job, on_done, on_error):
        if not self.pending:
            self.since = time.monotonic()
        self.pending += 1
        self.jobs.put((job, on_done, on_error))

    def _run(self):
        while True:
            job, on_done, on_error = self.jobs.get()
            try:
                self.finished.put((on_done, job()))
            except Exception as exc:  # serial errors, timeouts, bad replies
                self.finished.put((on_error, exc))

    def poll(self):
        while True:
            try:
                callback, value = self.finished.get_nowait()
            except queue.Empty:
                return
            self.pending -= 1
            callback(value)


def serial_ports():
    """Serial ports on this machine as "device - description"; empty without pyserial."""
    try:
        from serial.tools import list_ports
    except ImportError:
        return []
    return [f"{p.device} - {p.description}" for p in sorted(list_ports.comports())]


def random_values(count=8):
    """Random numbers that do not also occur in the firmware, so the RAM scan stays clean."""
    values = []
    while len(values) < count:
        v = random.randint(-9999, 99999)
        if not owner.looks_common(v):
            values.append(v)
    return values


def bar_slot(total, width):
    """Horizontal space one step gets in the timing chart."""
    return min(width / max(total, 1), MAX_BAR)


def bar_layout(cycles, total, width, height):
    """Timing-chart bars as (x0, y0, x1, y1, slow) inside a width x height plot.

    The y scale starts at zero. A bar is "slow" when its step took longer than the fastest one.
    """
    if not cycles:
        return []
    slot = bar_slot(total, width)
    gap = 2 if slot >= 6 else 1 if slot >= 3 else 0
    fast, top = min(cycles), max(cycles)
    return [(i * slot, height - height * c / top, (i + 1) * slot - gap, height, c > fast)
            for i, c in enumerate(cycles)]


def chart_keys(mode, cycles):
    """Legend entries (slow, text) for the timing chart."""
    fast, top = min(cycles), max(cycles)
    if fast == top:
        return [(False, f"every step so far: {fast} cycles")]
    upto = "up to " if len(set(cycles)) > 2 else ""
    plain = mode == "plain"
    return [(False, f"fast step: {fast} cycles" + (", no swap" if plain else "")),
            (True, f"slow step: {upto}{top} cycles" + (", a swap happened" if plain else ""))]


# ---------------------------------------------------------------- Tk front end
def run_gui(port=None, baud=115200, timeout=5.0):
    import tkinter as tk
    from tkinter import messagebox, scrolledtext, ttk

    mono = ("Courier New", 10)
    bold = ("Courier New", 10, "bold")
    small = ("TkDefaultFont", 9)
    YELLOW, GREY, RED = "#fff2a8", "#9a9a9a", "#c62828"
    # Timing chart colours: blue = fastest step, orange = slower step (checked for colour-blind contrast).
    FAST, SLOW = "#2a78d6", "#eb6834"
    SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#dddcd6"

    root = tk.Tk()
    root.title("Sequestered Encryption sort demo")
    worker = Worker()

    class Chart:
        """Bar chart of the cycles each step took. Hover a bar to read that step."""
        W, H, LEFT, RIGHT, TOP, BOTTOM = 470, 84, 46, 10, 10, 18

        def __init__(self, parent, row):
            tk.Label(parent, text="Cycles per step (what someone timing the board sees)",
                     font=("TkDefaultFont", 9, "bold"), anchor="w").grid(
                         row=row, column=0, columnspan=4, sticky="w", pady=(8, 2))
            self.canvas = tk.Canvas(parent, width=self.W, height=self.H, bg=SURFACE,
                                    highlightthickness=1, highlightbackground=GRID)
            self.canvas.grid(row=row + 1, column=0, columnspan=4, sticky="w")
            legend = tk.Frame(parent)
            legend.grid(row=row + 2, column=0, columnspan=4, sticky="w")
            self.keys = [(tk.Label(legend, width=2, font=("TkDefaultFont", 6)),
                          tk.Label(legend, font=small, fg=INK2)) for _ in range(2)]
            self.readout = tk.Label(parent, font=small, fg=INK2, anchor="w")
            self.readout.grid(row=row + 3, column=0, columnspan=4, sticky="w")
            self.canvas.bind("<Motion>", self.hover)
            self.canvas.bind("<Leave>", lambda e: self.point(None))
            self.s, self.bars, self.hot = None, [], None
            self.draw(None)

        def plot_size(self):
            return self.W - self.LEFT - self.RIGHT, self.H - self.TOP - self.BOTTOM

        def draw(self, s):
            c = self.canvas
            c.delete("all")
            self.s, self.bars, self.hot = s, [], None
            pw, ph = self.plot_size()
            x0, y0, base = self.LEFT, self.TOP, self.TOP + ph
            for swatch, text in self.keys:
                swatch.pack_forget()
                text.pack_forget()
            cycles = s.cycles if s else []
            if not cycles:
                c.create_line(x0, base, x0 + pw, base, fill=INK2)
                c.create_text(x0 + pw / 2, y0 + ph / 2, text="No steps yet", fill=GREY, font=small)
                self.readout.config(text=" ")
                return
            c.create_line(x0, y0, x0 + pw, y0, fill=GRID)
            c.create_text(x0 - 6, y0, text=str(max(cycles)), anchor="e", fill=INK2, font=small)
            c.create_text(x0 - 6, base, text="0", anchor="e", fill=INK2, font=small)
            for bx0, by0, bx1, _, slow in bar_layout(cycles, s.total, pw, ph):
                self.bars.append(c.create_rectangle(x0 + bx0, y0 + by0, x0 + bx1, base,
                                                    fill=SLOW if slow else FAST, width=0))
            c.create_line(x0, base, x0 + pw, base, fill=INK2)
            c.create_text(x0, base + 9, text="step 1", anchor="w", fill=INK2, font=small)
            c.create_text(x0 + pw, base + 9, text=f"step {s.total}", anchor="e", fill=INK2, font=small)
            for (swatch, text), (slow, label) in zip(self.keys, chart_keys(s.mode, cycles)):
                swatch.config(bg=SLOW if slow else FAST)
                text.config(text=label)
                swatch.pack(side="left", padx=(0, 4))
                text.pack(side="left", padx=(0, 14))
            self.readout.config(text="Move the mouse over a bar to see that step.")

        def hover(self, event):
            i = None
            if self.bars:
                k = int((event.x - self.LEFT) // bar_slot(self.s.total, self.plot_size()[0]))
                if 0 <= k < len(self.bars):
                    i = k
            self.point(i)

        def point(self, i):
            if i == self.hot or not self.bars:
                return
            if self.hot is not None:
                self.canvas.itemconfig(self.bars[self.hot], width=0)
            self.hot = i
            if i is None:
                self.readout.config(text="Move the mouse over a bar to see that step.")
                return
            self.canvas.itemconfig(self.bars[i], width=1, outline=INK)
            j = self.s.pairs[i]
            self.readout.config(text=f"step {i + 1}: compared slots {j} and {j + 1}, {self.s.cycles[i]} cycles")

    class Panel:
        def __init__(self, parent, heading, col):
            self.frame = tk.LabelFrame(parent, text=heading, font=("TkDefaultFont", 11, "bold"), padx=6, pady=6)
            self.frame.grid(row=2, column=col, padx=8, pady=4, sticky="n")
            head = ("slot", "RAM words at 0x1800 (address order)", "", "value")
            for c, text in enumerate(head):
                tk.Label(self.frame, text=text, font=bold, anchor="w").grid(row=0, column=c, sticky="w", padx=3)
            self.rows = []
            for r in range(MAX_N):
                cells = [tk.Label(self.frame, font=mono, anchor="w") for _ in range(4)]
                for c, w in enumerate(cells):
                    w.grid(row=r + 1, column=c, sticky="w", padx=3)
                self.rows.append(cells)
            self.chart = Chart(self.frame, MAX_N + 1)
            self.clear()

        def clear(self):
            for r, cells in enumerate(self.rows):
                cells[0].config(text=f"{r:>2}", fg=GREY, bg=root.cget("bg"))
                cells[1].config(text="-", fg=GREY, bg=root.cget("bg"))
                cells[2].config(text="", bg=root.cget("bg"))
                cells[3].config(text="", bg=root.cget("bg"))
            self.chart.draw(None)

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
            self.chart.draw(s)

    # --- board picker
    link = tk.Frame(root)
    link.grid(row=0, column=0, columnspan=2, sticky="we", padx=8, pady=(6, 0))
    tk.Label(link, text="Board:").pack(side="left")
    port_box = ttk.Combobox(link, width=44)
    port_box.pack(side="left", padx=4)
    conn = tk.Label(link, text="Not connected", fg=GREY, anchor="w")

    # --- controls
    top = tk.Frame(root)
    top.grid(row=1, column=0, columnspan=2, sticky="we", padx=8, pady=6)
    tk.Label(top, text="Numbers (2-16):").pack(side="left")
    entry = tk.Entry(top, width=34, font=mono)
    entry.insert(0, "4242 -17 999 4242 31337")
    entry.pack(side="left", padx=4)
    reveal = tk.BooleanVar(value=False)

    panels = {"plain": Panel(root, "PLAINTEXT baseline (insecure)", 0),
              "se": Panel(root, "SEQUESTERED ENCRYPTION", 1)}
    state = {"board": None, "s": None, "auto": False, "after": None}

    bottom = tk.Frame(root)
    bottom.grid(row=3, column=0, columnspan=2, sticky="we", padx=8, pady=4)
    status = tk.Label(bottom, text="Connecting...", font=("TkDefaultFont", 11), anchor="w")
    status.pack(fill="x")
    log = scrolledtext.ScrolledText(bottom, height=6, font=("Courier New", 9))
    log.pack(fill="x", pady=4)

    def say(text):
        log.insert("end", text + "\n")
        log.see("end")

    def fail(exc):
        stop_auto()
        state["s"] = None
        status.config(text="Run stopped. Press Connect, then start again.")
        messagebox.showerror("Board error", f"{exc}\n\nCheck the COM port, close other serial terminals, "
                                            "press CPU RESET, then press Connect.")

    # --- connecting
    def refresh_ports():
        port_box.config(values=[SIM_LABEL] + serial_ports())

    def connect():
        choice = port_box.get().strip() or SIM_LABEL
        device = None if choice == SIM_LABEL else choice.split(" - ")[0]
        old = state["board"]
        stop_auto()
        state["board"] = state["s"] = None
        conn.config(text="Connecting...", fg=GREY)
        status.config(text="Using the simulated board." if device is None else
                      f"Connecting to {device}... press CPU RESET on the board if this takes a while.")

        def job():
            if hasattr(old, "close"):
                old.close()
            if device is None:
                return SimBoard()
            board = owner.Board(device, baud, idle_timeout=timeout or None)
            try:
                board.sync(timeout=CONNECT_TIMEOUT if timeout else None)
            except Exception:
                board.close()
                raise
            return board

        def connected(board):
            state["board"] = board
            name = "simulated board" if device is None else f"board on {device}"
            conn.config(text=f"Connected: {name}", fg="black")
            root.title(f"Sequestered Encryption sort demo - {name}")
            for panel in panels.values():
                panel.clear()
            status.config(text="Pick numbers, then start a mode.")

        def connect_failed(exc):
            conn.config(text="Not connected", fg=RED)
            status.config(text="Not connected. Pick a board and press Connect.")
            hint = ("Install pyserial first:  python -m pip install pyserial" if isinstance(exc, ImportError) else
                    "Check the COM port, close other serial terminals, press CPU RESET, then press Connect again.")
            messagebox.showerror("Could not connect", f"{exc}\n\n{hint}")

        worker.submit(job, connected, connect_failed)

    # --- running a sort
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
        if s and not worker.busy:  # a running job redraws when it finishes
            panels[s.mode].draw(s, reveal.get())

    def start(mode):
        vals = parse_numbers()
        if vals is None:
            return
        board = state["board"]
        if board is None:
            messagebox.showwarning("Board", "No board connected yet. Pick one and press Connect.")
            return
        stop_auto()
        state["s"] = None

        def job():
            s = Session(board)
            s.start(mode, vals)
            return s

        def loaded(s):
            if state["board"] is not board:
                return
            state["s"] = s
            panels[mode].clear()
            log.delete("1.0", "end")
            for line in s.log:
                say(line)
            common = [v for v in vals if owner.looks_common(v)]
            if common:
                say(f"Tip: small or round numbers ({' '.join(map(str, common))}) also appear in the firmware's "
                    "own code, so the RAM scan finds them in both modes.")
            panels[mode].draw(s, reveal.get())
            status.config(text=f"{mode.upper()} loaded. Step 0/{s.total}. Press Step or Auto.")

        worker.submit(job, loaded, fail)

    def step():
        if state["after"]:  # a manual step replaces the pending auto-play step
            root.after_cancel(state["after"])
            state["after"] = None
        s = state["s"]
        if s is None or s.done:
            return
        if worker.busy:  # another board call is still running; auto-play tries again shortly
            if state["auto"]:
                state["after"] = root.after(50, step)
            return

        def stepped(result):
            if state["s"] is not s:
                return
            j, c = result
            panels[s.mode].draw(s, reveal.get())
            text = f"step {s.k}/{s.total}: compared slots {j} and {j + 1} in {c} cycles"
            if s.done:
                stop_auto()
                verdict = "CORRECT" if s.result_ok() else "WRONG"
                text += f"   |   DONE, owner check with key: {verdict}"
                say(f"\nSort finished: {s.timing_note()}.")
                leak = s.timing_leak()
                if leak:
                    say(f"Timing alone gives the swaps away: guessing \"slow step = swap\" "
                        f"was right for {leak[0]} of {leak[1]} steps.")
            elif state["auto"]:
                state["after"] = root.after(int(speed.get()), step)
            status.config(text=text)

        worker.submit(s.step, stepped, fail)

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
        step()

    def scan():
        s = state["s"]
        if s is None:
            return
        status.config(text="Scanning board RAM...")

        def scanned(text):
            say(text.rstrip())
            status.config(text="RAM scan finished, see the log below.")

        worker.submit(s.scan_ram, scanned, fail)

    def heartbeat():
        """Hands finished board calls back to the window and shows a wait cursor during slow ones."""
        worker.poll()
        root.config(cursor="watch" if worker.busy_for() > 0.6 else "")
        root.after(20, heartbeat)

    def close():
        board = state["board"]
        if hasattr(board, "close") and not worker.busy:
            board.close()
        root.destroy()

    tk.Button(link, text="Refresh", command=refresh_ports).pack(side="left", padx=2)
    tk.Button(link, text="Connect", command=connect).pack(side="left", padx=2)
    conn.pack(side="left", padx=(12, 0))

    tk.Button(top, text="Random", command=lambda: (entry.delete(0, "end"), entry.insert(
        0, " ".join(map(str, random_values()))))).pack(side="left", padx=2)
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

    def typing():
        return root.focus_get() in (entry, port_box)

    root.bind("<Return>", lambda e: None if typing() else step())
    root.bind("<space>", lambda e: None if typing() else step())
    root.protocol("WM_DELETE_WINDOW", close)

    refresh_ports()
    port_box.set(port or SIM_LABEL)
    connect()
    heartbeat()
    root.mainloop()


def main():
    p = argparse.ArgumentParser(description="Encrypted-sort demo GUI")
    p.add_argument("--port", help="serial port to connect to at startup, e.g. COM5 or /dev/ttyUSB1 "
                                  "(omit to start on the simulated board; either can be picked in the window)")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--timeout", type=float, default=5.0,
                   help="seconds of silence before giving up on the board (0 = wait forever, "
                        "for the slow Verilator board from tests/run_board.sh)")
    args = p.parse_args()
    run_gui(args.port, args.baud, args.timeout)


if __name__ == "__main__":
    sys.exit(main())
