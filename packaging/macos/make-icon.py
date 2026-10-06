"""Code-native TokenCoach diamond icon; no provider logo or personal artwork."""
from pathlib import Path
import struct
import zlib

size = 1024
rows = bytearray()
for y in range(size):
    rows.append(0)
    for x in range(size):
        diamond = abs(x - 511.5) + abs(y - 511.5)
        inset = max(0, min(1, (280 - diamond) / 2))
        color = tuple(round(a + (b-a)*inset) for a,b in zip((24,29,37), (111,210,177)))
        # Rounded background, transparent outside it.
        dx, dy = max(0, abs(x-511.5)-310), max(0, abs(y-511.5)-310)
        alpha = round(255*max(0,min(1,(192-(dx*dx+dy*dy)**.5)/2)))
        rows.extend((*color, alpha))
def chunk(kind, data):
    return struct.pack('>I',len(data)) + kind + data + struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR',struct.pack('>IIBBBBB',size,size,8,6,0,0,0)) + chunk(b'IDAT',zlib.compress(rows)) + chunk(b'IEND',b'')
icon = b'ic10' + struct.pack('>I',len(png)+8) + png
Path('build/TokenCoach.icns').write_bytes(b'icns'+struct.pack('>I',len(icon)+8)+icon)
