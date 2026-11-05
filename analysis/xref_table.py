"""Linear-sweep the ROM with capstone (M68K) and collect instructions whose
absolute operands point into the level-up table region (0x40300-0x40600)."""
from capstone import *
from capstone.m68k import *
import struct

SRC = r"E:/BaiduNetdiskDownload/xqgwz/xqgwz.md"
d = open(SRC, 'rb').read()

md = Cs(CS_ARCH_M68K, CS_MODE_BIG_ENDIAN | CS_MODE_M68K_000)

TARGET_LO, TARGET_HI = 0x40300, 0x40620

hits = []
# sweep in 4KB blocks from 0x200 to 0x300000
for blk in range(0x200, 0x300000, 0x1000):
    code = d[blk:blk+0x1000+16]
    for ins in md.disasm(code, blk):
        txt = f"{ins.mnemonic} {ins.op_str}"
        # look for any 0x40xxx hex in the operand string
        import re
        for m in re.finditer(r'0x([0-9a-fA-F]{5,8})', txt):
            v = int(m.group(1), 16)
            if TARGET_LO <= v <= TARGET_HI:
                hits.append((ins.address, txt))

print(f"=== instructions referencing 0x{TARGET_LO:05x}-0x{TARGET_HI:05x}  ({len(hits)} hits) ===")
for a, t in hits[:120]:
    print(f"  {a:07x}  {t}")
