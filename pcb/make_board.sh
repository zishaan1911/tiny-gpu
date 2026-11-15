#!/usr/bin/env bash
# Regenerates the schematic and the board from gen/design.py, routes it and checks it.
#   1. schematic + ERC          4. leftover connections: maze router with rip-up (finish_routes.py)
#   2. placement, plane fan-out 5. ground pours, stitching vias, zone fill (fixup.py)
#   3. Freerouting              6. DRC with schematic parity -> drc.rpt, schematic PDF
set -uo pipefail
cd "$(dirname "$0")/gen"
K=/c/Users/Zishaan/Tools/kicad/bin/python.exe
CLI=/c/Users/Zishaan/Tools/kicad/bin/kicad-cli.exe
quiet() { grep -v "image handler\|memory leak\|ctor found"; }

python schematic.py
"$CLI" sch erc --severity-all --format report -o ../erc.rpt ../tiny_gpu.kicad_sch | tail -1
$K board.py 2>&1 | quiet | tail -2
$K route.py --finish 2>&1 | quiet | tail -1
$K cleanup.py 2>&1 | quiet | tail -1
$K fixup.py 2>&1 | quiet | tail -1
python outputs.py | grep unconnected
for pass in 1 2 3 4 5 6 7 8 9 10; do
  grep -A2 "^\[unconnected_items\]" ../drc.rpt | grep -q "Pad \|Track \|Via " || break
  echo "-- finishing pass $pass"
  $K finish_routes.py 2>&1 | quiet | tail -6
  $K fixup.py 2>&1 | quiet | tail -1
  python outputs.py | grep unconnected
done
# Stubs the DRC still calls dangling (it is stricter about track ends than cleanup.py's own check).
for pass in 1 2 3; do
  grep -q "^\[track_dangling" ../drc.rpt || break
  $K cleanup.py --drc 2>&1 | quiet | tail -1
  $K fixup.py 2>&1 | quiet | tail -1
  python outputs.py > /dev/null
done
python outputs.py
grep -E "^\[" ../drc.rpt | sed 's/:.*//' | sort | uniq -c | sort -rn
"$CLI" sch export pdf -o ../tiny_gpu_schematic.pdf ../tiny_gpu.kicad_sch > /dev/null
