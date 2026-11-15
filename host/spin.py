"""Drive the Tiny GPU board from the laptop: a spinning scene at the monitor's 60 Hz.

    pip install pyserial
    python host/spin.py            # finds the board's serial port (FT2232H channel B)
    python host/spin.py COM7       # or name it

Every command is 8 bytes: 0x55, op << 4 | colour, x0, y0, x1, y1, x2, y2.
The GPU answers each PRESENT with 0x06 once the frame is on screen.
"""

import math
import sys
import time

import serial
from serial.tools import list_ports

CLEAR, TRIANGLE, PRESENT = 0, 1, 2
BAUD = 1_000_000


def cmd(op, colour, *xy):
    xy = list(xy) + [0] * (6 - len(xy))
    return bytes([0x55, (op << 4) | colour] + [v & 0xFF for v in xy])


def polygon(r, turn, n):
    return [(round(32 + r * math.cos(turn + 2 * math.pi * k / n)), round(32 + r * math.sin(turn + 2 * math.pi * k / n))) for k in range(n)]


def frame(t):
    big = polygon(30, t, 3)
    small = polygon(21, -2 * t + 0.5, 3)
    sq = polygon(11 * (1 + 0.25 * math.sin(2 * t)), t, 4)
    out = cmd(CLEAR, 1)
    out += cmd(TRIANGLE, 2, *big[0], *big[1], *big[2])
    out += cmd(TRIANGLE, 6, *small[0], *small[1], *small[2])
    out += cmd(TRIANGLE, 10, *sq[0], *sq[1], *sq[2])
    out += cmd(TRIANGLE, 10, *sq[0], *sq[2], *sq[3])
    return out + cmd(PRESENT, 0)


def find_port():
    # The FT2232H shows up as two ports; the GPU listens on the second (channel B).
    ftdi = sorted((p for p in list_ports.comports() if p.vid == 0x0403 and p.pid == 0x6010), key=lambda p: p.device)
    if not ftdi:
        sys.exit("No FT2232H found. Is the board plugged in? Or pass the port, e.g. COM7.")
    return ftdi[-1].device


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else find_port()
    with serial.Serial(port, BAUD, timeout=0.5) as link:
        print(f"Drawing on {port}. Ctrl+C to stop.")
        t, frames, since = 0.0, 0, time.monotonic()
        while True:
            link.write(frame(t))
            if link.read(1) != b"\x06":
                sys.exit("The board didn't acknowledge the frame. Is the bitstream loaded?")
            t += 2 * math.pi / 240
            frames += 1
            if time.monotonic() - since >= 2:
                print(f"{frames / (time.monotonic() - since):.0f} frames/s")
                frames, since = 0, time.monotonic()


if __name__ == "__main__":
    main()
