"""Disassemble code windows around references to the level-up table."""
from capstone import *
SRC = r"E:/BaiduNetdiskDownload/xqgwz/xqgwz.md"
d = open(SRC, 'rb').read()
md = Cs(CS_ARCH_M68K, CS_MODE_BIG_ENDIAN | CS_MODE_M68K_000)

def show(start, end, label=""):
    print(f"\n===== {label}  {start:#08x} - {end:#08x} =====")
    code = d[start:end]
    for ins in md.disasm(code, start):
        bs = ' '.join(f'{b:02x}' for b in ins.bytes[:8])
        print(f"  {ins.address:07x}  {bs:<24} {ins.mnemonic:<8} {ins.op_str}")

show(0x00D1C60, 0x00D1DA0, "region A (base 0x4043A/0x4043C)")
show(0x00D2120, 0x00D21C0, "region B (base 0x40438)")
show(0x00D4940, 0x00D4A60, "region C (base 0x40438)")
show(0x00E1380, 0x00E1420, "region D (abs 0x40444)")
