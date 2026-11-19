"""Tests for the GUI logic that needs no display: the simulated board, Session, Worker and chart maths.

Run with:  python3 -m pytest host
"""
import time

import pytest

import gui
import owner


def run_sort(mode, values):
    s = gui.Session(gui.SimBoard())
    s.start(mode, values)
    while not s.done:
        s.step()
    return s


VALUES = [4242, -17, 999, 4242, 31337, -2147483648, 2147483647]


@pytest.mark.parametrize("mode", ["plain", "se"])
@pytest.mark.parametrize("values", [VALUES, [5, 3], [1, 2, 3, 4], [9, 7, 5, 3], list(range(16, 0, -1))])
def test_both_modes_sort_correctly(mode, values):
    s = run_sort(mode, values)
    assert s.result_ok()
    assert s.k == s.total == len(values) * (len(values) - 1) // 2
    assert len(s.cycles) == len(s.pairs) == s.total


def test_se_mode_rewrites_both_slots_every_step():
    s = gui.Session(gui.SimBoard())
    s.start("se", [1, 2, 3, 4])  # already sorted, so nothing swaps
    while not s.done:
        j, _ = s.step()
        assert s.changed(j) and s.changed(j + 1)
    assert len(set(s.cycles)) == 1  # constant time


def test_se_mode_keeps_plaintext_out_of_ram():
    board = gui.SimBoard()
    s = gui.Session(board)
    s.start("se", [31337, 4242, 777777])
    while not s.done:
        s.step()
    assert not {31337, 4242, 777777} & set(board.ram)


def test_plaintext_timing_leaks_the_swaps():
    s = run_sort("plain", [3, 1, 2, 5, 4])
    assert s.swaps == [c == max(s.cycles) for c in s.cycles]
    assert s.timing_leak() == (s.total, s.total)


def test_timing_leak_is_none_when_nothing_differs():
    assert run_sort("plain", [1, 2, 3]).timing_leak() is None  # no step swapped
    assert run_sort("se", [3, 1, 2]).timing_leak() is None


def test_step_reports_a_reset_board():
    board = gui.SimBoard()
    s = gui.Session(board)
    s.start("plain", [3, 1, 2])
    board.n = 0  # what a CPU RESET does to the firmware's state
    with pytest.raises(RuntimeError, match="reset"):
        s.step()


def test_random_values_avoid_firmware_constants():
    for _ in range(200):
        values = gui.random_values()
        assert len(values) == 8
        assert not any(owner.looks_common(v) for v in values)


def test_bar_layout_starts_at_zero_and_marks_slow_steps():
    bars = gui.bar_layout([27, 31, 27], total=10, width=400, height=100)
    assert [b[4] for b in bars] == [False, True, False]
    assert all(b[3] == 100 for b in bars)                # every bar sits on the baseline
    assert bars[1][1] == 0                               # the slowest step fills the plot
    assert bars[0][1] == pytest.approx(100 - 100 * 27 / 31)
    assert bars[0][2] <= bars[1][0]                      # bars do not overlap
    assert gui.bar_layout([], 10, 400, 100) == []


def test_bars_fit_the_plot_for_the_longest_sort():
    bars = gui.bar_layout([1327] * 120, total=120, width=414, height=72)
    assert bars[-1][2] <= 414
    assert not any(b[4] for b in bars)


def test_chart_keys():
    assert gui.chart_keys("se", [1327, 1327]) == [(False, "every step so far: 1327 cycles")]
    fast, slow = gui.chart_keys("plain", [27, 31, 27])
    assert fast == (False, "fast step: 27 cycles, no swap")
    assert slow == (True, "slow step: 31 cycles, a swap happened")


def wait_for(worker):
    deadline = time.monotonic() + 5
    while worker.busy and time.monotonic() < deadline:
        worker.poll()
        time.sleep(0.01)
    assert not worker.busy


def test_worker_runs_jobs_in_order_and_reports_errors():
    worker, seen = gui.Worker(), []
    worker.submit(lambda: 1, seen.append, seen.append)
    worker.submit(lambda: 1 / 0, seen.append, seen.append)
    worker.submit(lambda: 3, seen.append, seen.append)
    assert worker.busy
    wait_for(worker)
    assert seen[0] == 1 and isinstance(seen[1], ZeroDivisionError) and seen[2] == 3
    assert worker.busy_for() == 0.0


class SilentLink:
    """A serial port whose board never answers."""

    def write(self, data):
        pass

    def readline(self):
        return b""

    def reset_input_buffer(self):
        pass


def silent_board(idle_timeout):
    board = owner.Board.__new__(owner.Board)  # skip opening a real port
    board.s, board.idle_timeout = SilentLink(), idle_timeout
    return board


def test_board_gives_up_on_a_silent_board():
    board = silent_board(idle_timeout=0.05)
    with pytest.raises(TimeoutError):
        board.cmd("step")
    with pytest.raises(TimeoutError):
        board.sync(timeout=0.05)
