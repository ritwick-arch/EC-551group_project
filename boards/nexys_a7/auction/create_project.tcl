# Run from the Vivado Tcl console: source create_project.tcl
cd [file normalize [file dirname [info script]]]
create_project auction_nexys_a7 ./vivado -part xc7a100tcsg324-1 -force
set_property simulator_language Verilog [current_project]

add_files -fileset constrs_1 -norecurse { ./auction_nexys_a7.xdc }
add_files -norecurse { ./auction_nexys_a7.v }
add_files -norecurse [glob ../../../rvx/hardware/rvx_*.v]
add_files -norecurse { ../../../hw/rvx_se.v ../../../hw/se_unit.v ../../../hw/simon128.v }
add_files -norecurse { ./auction.hex }
set_property file_type {Memory Initialization Files} [get_files ./auction.hex]
set_property top auction_nexys_a7 [current_fileset]
