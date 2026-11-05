"""Mega Drive 4bpp planar tile renderer -> 24-bit BMP (no third-party deps)."""
import struct
import sys

SRC = r"E:/BaiduNetdiskDownload/xqgwz/xqgwz.md"

# 16-level grayscale palette (index 0 = white .. 15 = black)
RAMP = [255, 238, 221, 204, 187, 170, 153, 136, 119, 102, 85, 68, 51, 34, 17, 0]


def decode_tile(b):
    """32 bytes MD 4bpp planar -> 8x8 list of indices."""
    if len(b) < 32:
        return None
    px = []
    for row in range(8):
        p0, p1, p2, p3 = b[row * 4:row * 4 + 4]
        line = []
        for i in range(8):
            bit = 7 - i
            line.append(((p0 >> bit) & 1) | (((p1 >> bit) & 1) << 1) |
                        (((p2 >> bit) & 1) << 2) | (((p3 >> bit) & 1) << 3))
        px.append(line)
    return px


def write_bmp(path, w, h, rgb_rows):
    """rgb_rows: list of rows, each a bytearray of BGR triples, top-down."""
    row_size = (w * 3 + 3) & ~3
    pad = row_size - w * 3
    data = bytearray()
    for r in rgb_rows:
        data += r + b'\x00' * pad
    hdr = bytearray()
    hdr += b'BM' + struct.pack('<IHHI', 14 + 40 + len(data), 0, 0, 54)
    hdr += struct.pack('<IiiHHIIiiII', 40, w, h, 1, 24, 0, len(data), 2835, 2835, 0, 0)
    open(path, 'wb').write(bytes(hdr) + bytes(data))


def render(data, off, size, cols, out, scale=1):
    tiles = size // 32
    rows = (tiles + cols - 1) // cols
    W, H = cols * 8 * scale, rows * 8 * scale
    img = []
    for y in range(H):
        img.append(bytearray(W * 3))
    for t in range(tiles):
        px = decode_tile(data[off + t * 32: off + t * 32 + 32])
        if px is None:
            break
        tx, ty = (t % cols) * 8 * scale, (t // cols) * 8 * scale
        for y in range(8):
            for x in range(8):
                g = RAMP[px[y][x]]
                for sy in range(scale):
                    for sx in range(scale):
                        o = ((ty + y * scale + sy) * W + tx + x * scale + sx) * 3
                        img[ty + y * scale + sy][o:o + 3] = bytes((g, g, g))
    write_bmp(out, W, H, img)
    print(f'{out}: {W}x{H}  tiles={tiles}  rom={off:#08x}-{off+size:#08x}')


if __name__ == '__main__':
    d = open(SRC, 'rb').read()
    print('rom size', hex(len(d)))
    jobs = [
        (0x33000, 0x9000, 64, 'r_33000.bmp', 1),
        (0x1000, 0x8000, 64, 'r_01000.bmp', 1),
        (0x20000, 0x8000, 64, 'r_20000.bmp', 1),
        (0xA0000, 0x8000, 64, 'r_A0000.bmp', 1),
        (0xF0000, 0x8000, 64, 'r_F0000.bmp', 1),
        (0x280000, 0x8000, 64, 'r_280000.bmp', 1),
    ]
    for off, size, cols, out, sc in jobs:
        render(d, off, size, cols, out, sc)
