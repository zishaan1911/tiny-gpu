#!/usr/bin/env bash
# Simulate, synthesise, place and route, and pack the bitstream.
#   ./build.sh          everything
#   ./build.sh sim      simulations only
# Programming the board's flash afterwards:  iceprog build/gpu.bin
set -euo pipefail
cd "$(dirname "$0")"
export PATH=/c/msys64/mingw64/bin:$PATH
RTL="rtl/raster.v rtl/framebuffer.v rtl/tiny_gpu.v rtl/vga.v rtl/uart.v rtl/cmd_port.v rtl/board_top.v"
mkdir -p sim build

echo "== GPU core: 48 frames"
iverilog -g2012 -o sim/gpu.vvp rtl/raster.v rtl/framebuffer.v rtl/tiny_gpu.v tb/tb.v
vvp -n sim/gpu.vvp | tail -1

echo "== Whole board from its pins: UART in, VGA out"
iverilog -g2012 -DSIM -o sim/board.vvp $RTL tb/tb_board.v
vvp -n sim/board.vvp | grep -E "PASS|FAIL"

[ "${1:-}" = "sim" ] && exit 0

echo "== Synthesis for iCE40UP5K"
yosys -q -p "read_verilog $RTL; synth_ice40 -dsp -top board_top -json build/gpu.json; tee -q -o build/stat.txt stat"
grep -E "SB_LUT4|SB_RAM40|SB_MAC16|SB_PLL" build/stat.txt

echo "== Place and route"
nextpnr-ice40 -q --up5k --package sg48 --json build/gpu.json --pcf board.pcf --asc build/gpu.asc --freq 25.125 \
  --report build/report.json
node -e "const r=require('./build/report.json');for(const[k,v]of Object.entries(r.fmax))console.log('fmax',k,v.achieved.toFixed(1),'MHz (need',v.constraint.toFixed(3)+')')"
icepack build/gpu.asc build/gpu.bin
ls -l build/gpu.bin
