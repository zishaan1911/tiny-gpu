#!/usr/bin/env bash
# Cinematic stills of the board: perspective, floor shadows, low angles, close-ups, then a grading
# pass (gen/grade.py) onto a dark backdrop at 2.39:1.
# Usage: ./render_cinematic.sh [draft]   (draft = quick low-res preview)
set -e
cd "$(dirname "$0")"
K=/c/Users/Zishaan/Tools/kicad/bin/kicad-cli.exe
OUT=renders/cinematic
RAW=$OUT/raw
mkdir -p "$RAW"
if [ "$1" = draft ]; then Q=basic; W=960; H=540; else Q=high; W=3200; H=1800; fi
shot() { # name rotate zoom pivot [extra args...]
  local name=$1 rot=$2 zoom=$3 pivot=$4; shift 4
  [ -n "$ONLY" ] && [[ " $ONLY " != *" $name "* ]] && return 0
  $K pcb render -o "$RAW/$name.png" --quality $Q -w $W -h $H --perspective --floor \
    --background transparent --rotate "$rot" --zoom "$zoom" ${pivot:+--pivot "$pivot"} \
    "$@" tiny_gpu.kicad_pcb >/dev/null && echo "rendered $name"
}
# name       rotate         zoom  pivot (cm from board centre)
shot hero     "-62,0,-28"    1.05  ""           --light-side 0.9 --light-camera 0.2 --light-side-elevation 25
shot fpga     "-50,0,25"     3.2   "0.9,0.8,0"  --light-side 0.8 --light-camera 0.25 --light-side-elevation 35
shot dac      "-72,0,165"    3.3   "2.1,1.9,0"  --light-side 1 --light-camera 0.15 --light-side-elevation 12
shot vga      "-78,0,-115"   2.0   "3.1,0.4,0"  --light-side 1 --light-camera 0.15 --light-side-elevation 15
shot usb      "-72,0,55"     2.6   "-3.4,0.6,0" --light-side 0.9 --light-camera 0.2 --light-side-elevation 20
shot overhead "-15,0,8"      0.85  ""           --light-top 0.5 --light-side 1 --light-camera 0.1 --light-side-elevation 10
python gen/grade.py "$RAW" "$OUT"
