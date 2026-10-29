# Encrypted sort demo: lab steps

Every command needed to build, program and run the sort demo on the Nexys A7-100T.
Assumes the repo is at `C:\Users\daksh\ec551\EC-551group_project` (change the paths if not;
keep it outside OneDrive), Vivado 2025.1 and Python 3.

## 1. Get the latest code (PowerShell)

```powershell
cd C:\Users\daksh\ec551\EC-551group_project
git pull
git submodule update --init
```

On a machine without the repo:

```powershell
git clone --recursive -b Lohit https://github.com/ritwick-arch/EC-551group_project.git
```

## 2. Build the bitstream (Vivado Tcl Console)

Open Vivado without a project and paste into the Tcl Console. Use forward slashes.

```tcl
set REPO C:/Users/daksh/ec551/EC-551group_project
catch {close_project}
source $REPO/boards/nexys_a7/enc_sort/create_project.tcl
launch_runs impl_1 -to_step write_bitstream -jobs 8
wait_on_run impl_1
puts "status: [get_property STATUS [get_runs impl_1]]"
puts "WNS = [get_property STATS.WNS [get_runs impl_1]] ns"
```

Takes 10-15 minutes. Status should read `write_bitstream Complete!` and WNS must be 0 or
positive. If WNS is negative, stop and send the number.

## 3. Program the board (Vivado Tcl Console)

Plug in the USB cable and turn the board on.

```tcl
open_hw_manager
connect_hw_server
open_hw_target
set dev [lindex [get_hw_devices xc7a100t*] 0]
current_hw_device $dev
set_property PROGRAM.FILE [get_property DIRECTORY [current_project]]/enc_sort_nexys_a7.runs/impl_1/enc_sort_nexys_a7.bit $dev
program_hw_devices $dev
```

The DONE LED lights up. If `connect_hw_server` says it is already connected, skip that line.

## 4. Find the board's COM port (PowerShell)

```powershell
[System.IO.Ports.SerialPort]::GetPortNames()
```

If several ports show up, unplug the board, run it again, and see which one disappeared.

## 5. Run the demo (PowerShell, in the repo folder)

```powershell
python -m pip install pyserial
python host\owner.py demo --port COM5
```

Use your COM number. Type 2 to 16 numbers when asked, e.g. `4242 -31337 999 2026 777 31337 5150 -808`.
Press Enter for one compare-and-swap step, or `a` then Enter to auto-play. After plaintext
mode finishes, press Enter to start SE mode.

Other ways to run it:

```powershell
python host\owner.py demo --port COM5 --auto 0.5 4242 -31337 999 2026 777 31337
python host\owner.py demo --port COM5 --mode se 4242 -31337 999 2026
```

The first auto-plays both modes with half a second per step; the second runs only SE mode.

## What you should see

| | Plaintext mode | SE mode |
|---|---|---|
| Slots at `0x1800`... | your numbers, readable | random-looking hex |
| Each step | only swapped slots change | both compared slots change |
| Cycles per step | 27 or 31 (leaks swaps) | always 1327 |
| RAM search | numbers found in the slots | not found; key not found |
| SE registers A, B, C | | all zero |
| Result | sorted | sorted (decrypted on the laptop) |

## If something goes wrong

- **Stuck at "Waiting for the board"**: press CPU RESET (red button), check the COM number,
  and close PuTTY or anything else using the port.
- **`could not open port`**: wrong COM number, or another program has the port open.
- **No output or garbage**: the board still has an older bitstream; program it again (the
  demo needs this build, which talks at 115200 baud).
- **`python` not found**: use `py` instead.
- **Vivado says a file is in use or not writable**: the repo is inside OneDrive; clone it
  somewhere else.
- **100 or 1000 "found" in SE mode**: those are constants in the firmware itself, and the
  script labels them so. Pick less round numbers.
