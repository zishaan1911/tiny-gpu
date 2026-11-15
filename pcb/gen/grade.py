"""Turns transparent KiCad renders into graded, letterboxed stills.

Each raw shot is composited onto a dark studio backdrop (a soft pool of warm light behind the
board), then given a gentle filmic curve, teal-shadow / warm-highlight split toning, a little
bloom, a vignette and a 2.39:1 crop with a small caption.

    python gen/grade.py renders/cinematic/raw renders/cinematic
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

CAPTIONS = {
    "hero": "TINY GPU  ·  iCE40UP5K  ·  640×480 VGA",
    "fpga": "U6  ·  RASTERISER, 45 MHz",
    "dac": "4-BIT RESISTOR DAC  ·  R / G / B",
    "vga": "VGA OUT  ·  DE-15",
    "usb": "USB-C  ·  FT2232H HOST LINK",
    "overhead": "4 LAYERS  ·  76 × 56 MM",
}
ASPECT = 2.39


def backdrop(w, h):
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    # Warm pool of light slightly above centre, falling off to near-black graphite.
    d = np.sqrt(((x - w * 0.52) / (w * 0.55)) ** 2 + ((y - h * 0.42) / (h * 0.62)) ** 2)
    t = np.clip(1 - d, 0, 1) ** 1.8
    lo = np.array([10, 11, 14], np.float32)
    hi = np.array([58, 52, 47], np.float32)
    return lo + (hi - lo) * t[..., None]


def filmic(c):
    # Soft S-curve on 0..1 values.
    return np.clip(c * c * (3 - 2 * c) * 0.55 + c * 0.45, 0, 1)


def grade(src, dst, name):
    im = Image.open(src).convert("RGBA")
    rgba = np.asarray(im).astype(np.float32) / 255
    h, w = rgba.shape[:2]
    a = rgba[..., 3:4]
    bg = backdrop(w, h) / 255
    img = rgba[..., :3] * a + bg * (1 - a)

    img = filmic(img)
    lum = img @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    shadow = np.clip(1 - lum * 2, 0, 1)[..., None]
    high = np.clip(lum * 2 - 1, 0, 1)[..., None]
    img = img + shadow * np.array([-0.012, 0.010, 0.030]) + high * np.array([0.040, 0.018, -0.025])

    # Bloom: blur the brightest parts and add them back softly.
    bright = np.clip((img - 0.72) / 0.28, 0, 1)
    glow = Image.fromarray((bright * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(w / 90))
    img = img + np.asarray(glow).astype(np.float32) / 255 * 0.14

    # Vignette.
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.sqrt(((x - w / 2) / (w / 2)) ** 2 + ((y - h / 2) / (h / 2)) ** 2)
    img = img * (1 - 0.45 * np.clip(r - 0.55, 0, 1) ** 1.5)[..., None]

    out = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    # Crop to 2.39:1, centred vertically on the board (opaque pixels) rather than the frame.
    ch = int(w / ASPECT)
    rows = np.where((rgba[..., 3] > 0.9).any(axis=1))[0]
    mid = (rows[0] + rows[-1]) // 2 if len(rows) else h // 2
    top = int(np.clip(mid - ch // 2, 0, max(0, h - ch)))
    out = out.crop((0, top, w, top + min(ch, h)))
    cw, chh = out.size

    # Fine grain keeps the dark gradients from banding.
    rng = np.random.default_rng(7)
    arr = np.asarray(out).astype(np.float32) + rng.normal(0, 2.2, (chh, cw, 1))
    out = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

    caption = CAPTIONS.get(name)
    if caption:
        # Soft dark scrim along the bottom so the caption reads over bright board areas.
        ys = np.linspace(0, 1, chh, dtype=np.float32)[:, None, None]
        scrim = 1 - 0.6 * np.clip((ys - 0.72) / 0.28, 0, 1) ** 1.4
        out = Image.fromarray((np.asarray(out).astype(np.float32) * scrim).astype(np.uint8))
        d = ImageDraw.Draw(out)
        size = max(12, cw // 95)
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", size)
        except OSError:
            font = ImageFont.load_default()
        m = size * 2
        d.text((m, chh - m - size), caption, font=font, fill=(200, 196, 190))
        d.line((m, chh - m - size * 1.6, m + size * 3, chh - m - size * 1.6), fill=(232, 106, 34), width=max(2, size // 8))
    out.save(dst, quality=95)


def main():
    raw, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    for f in sorted(os.listdir(raw)):
        if f.endswith(".png"):
            name = f[:-4]
            grade(os.path.join(raw, f), os.path.join(out, name + ".jpg"), name)
            print("graded", name)


if __name__ == "__main__":
    main()
