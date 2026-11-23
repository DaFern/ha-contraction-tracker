"""Generate bundled brand PNGs and English translations with the standard library."""

import json
import math
from pathlib import Path
import shutil
import struct
import zlib

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "contraction_tracker"


def chunk(kind, value):
    return struct.pack(">I", len(value)) + kind + value + struct.pack(">I", zlib.crc32(kind + value))


def png(size):
    """Original simple baby mark; no downloaded third-party artwork."""
    navy, teal = (20, 40, 55, 255), (145, 228, 210, 255)
    scale = size / 256
    rows = []
    curl = [(126, 75), (120, 64), (122, 53), (132, 47), (142, 53), (142, 61), (136, 66)]
    smile = [(128 + math.cos(a) * 24, 153 + math.sin(a) * 18)
             for a in [math.radians(25 + index * 5) for index in range(27)]]
    segments = list(zip(curl, curl[1:])) + list(zip(smile, smile[1:]))
    def distance(x, y, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        ratio = max(0, min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / (dx * dx + dy * dy)))
        return math.hypot(x - a[0] - ratio * dx, y - a[1] - ratio * dy)
    for py in range(size):
        row = bytearray([0])
        for px in range(size):
            x, y = (px + .5) / scale, (py + .5) / scale
            rounded = math.hypot(max(40 - x, x - 216, 0), max(40 - y, y - 216, 0)) <= 40
            color = navy if rounded else (0, 0, 0, 0)
            stroke = abs(math.hypot(x - 128, y - 142) - 67) <= 3
            eyes = min(math.hypot(x - 104, y - 136), math.hypot(x - 152, y - 136)) <= 5
            line = any(distance(x, y, a, b) <= 3 for a, b in segments) if 40 < y < 180 else False
            row.extend(teal if stroke or eyes or line else color)
        rows.append(bytes(row))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))


if __name__ == "__main__":
    brand = COMPONENT / "brand"
    brand.mkdir(exist_ok=True)
    (brand / "icon.png").write_bytes(png(256))
    (brand / "icon@2x.png").write_bytes(png(512))
    shutil.copyfile(brand / "icon.png", COMPONENT / "frontend" / "icon.png")
    translations = COMPONENT / "translations"
    translations.mkdir(exist_ok=True)
    source = json.loads((COMPONENT / "strings.json").read_text())
    (translations / "en.json").write_text(json.dumps(source, indent=2) + "\n")
    print("Generated original brand assets, bundled notification icon and English translation.")
