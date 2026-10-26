set_property -dict { PACKAGE_PIN E3  IOSTANDARD LVCMOS33 } [get_ports clock]
set_property -dict { PACKAGE_PIN C12 IOSTANDARD LVCMOS33 } [get_ports cpu_resetn]
set_property -dict { PACKAGE_PIN C4  IOSTANDARD LVCMOS33 } [get_ports uart_rx]
set_property -dict { PACKAGE_PIN D4  IOSTANDARD LVCMOS33 } [get_ports uart_tx]

create_clock -period 10.000 -name clock -waveform {0.000 5.000} [get_ports clock]
create_generated_clock -name clock_50mhz -source [get_pins clock_50mhz_reg/C] -divide_by 2 [get_pins clock_50mhz_reg/Q]

set_property CONFIG_VOLTAGE 3.3 [current_design]
set_property CFGBVS VCCO [current_design]
