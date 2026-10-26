# EC-551group_project
Sequestered Encryption

## RVX hello world on the Nexys A7

1. Clone with the submodule: `git clone --recursive -b Lohit https://github.com/ritwick-arch/EC-551group_project.git`
   (or run `git submodule update --init` in an existing clone).
2. In Vivado's Tcl console: `source <repo>/boards/nexys_a7/hello_world/create_project.tcl`
3. Generate Bitstream, then program the board from Hardware Manager.
4. Open a serial terminal on the board's COM port at 9600 baud, 8N1.
5. Press CPU RESET: the terminal prints `Hello World from RVX!`
