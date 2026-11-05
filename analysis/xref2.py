"""Find real code references to the level table by locating absolute-long
operands and disassembling the instruction that owns them."""
import os
from capstone import *
import struct, re

SRC = os.environ.get("ROM", "xqgwz.md")   # 原版 ROM 路径，用环境变量 ROM 覆盖
d = open(SRC, 'rb').read()
N = len(d)

md = Cs(CS_ARCH_M68K, CS_MODE_BIG_ENDIAN | CS_MODE_M68K_000)

TARGET_LO, TARGET_HI = 0x40420, 0x40460   # table body

print("=== all 32-bit BE values in table range, with owning instruction ===")
seen=set()
for i in range(0, N-4):
    v = int.from_bytes(d[i:i+4], 'big')
    if TARGET_LO <= v <= TARGET_HI:
        found=False
        for back in (2,4,6,8,10):
            s=i-back
            if s<0: continue
            for ins in md.disasm(d[s:s+16], s):
                if ins.address==s:
                    if any(x in ins.op_str for x in (f"0x{v:x}", f"0x{v:05x}")):
                        key=(s,ins.mnemonic,ins.op_str)
                        if key in seen: continue
                        seen.add(key)
                        print(f"  operand@{i:07x}={v:#08x}  ins@{s:07x}  {ins.mnemonic} {ins.op_str}")
                        found=True
                break
        if not found:
            ctx=d[max(0,i-8):i+8]
            print(f"  operand@{i:07x}={v:#08x}  (no clean instr) ctx: {ctx.hex(' ')}")
