"""Multi-format tile renderer, to identify how this ROM stores graphics/charset."""
import os
import struct

SRC = os.environ.get("ROM", "xqgwz.md")   # 原版 ROM 路径，用环境变量 ROM 覆盖
R16 = [255, 238, 221, 204, 187, 170, 153, 136, 119, 102, 85, 68, 51, 34, 17, 0]


def write_bmp(path, w, h, rows):
    row_size = (w * 3 + 3) & ~3
    pad = row_size - w * 3
    data = bytearray()
    for r in rows:
        data += r + b'\x00' * pad
    hdr = bytearray()
    hdr += b'BM' + struct.pack('<IHHI', 54 + len(data), 0, 0, 54)
    hdr += struct.pack('<IiiHHIIiiII', 40, w, h, 1, 24, 0, len(data), 2835, 2835, 0, 0)
    open(path, 'wb').write(bytes(hdr) + bytes(data))


def tile_md4(b):
    """Mega Drive 4bpp: 4 bytes per row = plane0,1,2,3."""
    out = []
    for r in range(8):
        p0, p1, p2, p3 = b[r * 4:r * 4 + 4]
        out.append([((p0 >> (7 - i)) & 1) | (((p1 >> (7 - i)) & 1) << 1) |
                    (((p2 >> (7 - i)) & 1) << 2) | (((p3 >> (7 - i)) & 1) << 3) for i in range(8)])
    return out


def tile_snes4(b):
    """SNES/GBA 4bpp: rows 0-7 use planes 0,1 (2 bytes/row); rows 8-15 use planes 2,3."""
    out = []
    for r in range(8):
        a, c = b[r * 2:r * 2 + 2]
        d, e = b[16 + r * 2:16 + r * 2 + 2]
        out.append([((a >> (7 - i)) & 1) | (((c >> (7 - i)) & 1) << 1) |
                    (((d >> (7 - i)) & 1) << 2) | (((e >> (7 - i)) & 1) << 3) for i in range(8)])
    return out


def tile_2bpp(b):
    out = []
    for r in range(8):
        a, c = b[r * 2:r * 2 + 2]
        out.append([((a >> (7 - i)) & 1) | (((c >> (7 - i)) & 1) << 1) for i in range(8)])
    return out


def tile_1bpp(b):
    return [[(b[r] >> (7 - i)) & 1 for i in range(8)] for r in range(8)]


MODES = {
    'md4': (tile_md4, 32, 4),
    'snes4': (tile_snes4, 32, 4),
    'g2': (tile_2bpp, 16, 2),
    'g1': (tile_1bpp, 8, 1),
}


def render(data, off, tiles, cols, out, mode='md4', scale=1):
    fn, tsize, depth = MODES[mode]
    rows = (tiles + cols - 1) // cols
    W, H = cols * 8 * scale, rows * 8 * scale
    img = [bytearray(W * 3) for _ in range(H)]
    for t in range(tiles):
        px = fn(data[off + t * tsize: off + t * tsize + tsize])
        if len(px) < 8:
            break
        tx, ty = (t % cols) * 8 * scale, (t // cols) * 8 * scale
        for y in range(8):
            for x in range(8):
                v = px[y][x]
                g = R16[v] if depth == 4 else (255 if v == 0 else 0) if depth == 1 else [255, 170, 85, 0][v]
                for sy in range(scale):
                    for sx in range(scale):
                        o = ((ty + y * scale + sy) * W + tx + x * scale + sx) * 3
                        img[ty + y * scale + sy][o:o + 3] = bytes((g, g, g))
    write_bmp(out, W, H, img)
    return out, W, H


if __name__ == '__main__':
    d = open(SRC, 'rb').read()
    res = []
    for mode in MODES:
        for off in (0x140000, 0x180000):
            o, w, h = render(d, off, 1024, 64, f'm_{mode}_{off:06x}.bmp', mode)
            res.append((o, w, h))
            print(f'{o}  {w}x{h}  mode={mode} rom={off:#08x}')
