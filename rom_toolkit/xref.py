#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xref.py —— 交叉引用 / 反汇编助手（多平台）

作用：光知道"表在哪"没用，还得知道"谁在读它"才能确定语义。
本工具就是干这个的：给定一个 ROM 地址，把引用它的指令找出来。

依赖: capstone（用于反汇编）。没装也能跑，只是看不到助记符：
    pip install capstone

用法:
    # 1) 找谁引用了某个地址（最常用）
    python xref.py <rom> ref 0x4043A

    # 2) 反汇编一段代码窗口
    python xref.py <rom> dis 0xd4960 --len 0x120

    # 3) 找谁调用了某个函数
    python xref.py <rom> calls 0xd1c74

    # 4) 搜十六进制字节串（不认识地址时用）
    python xref.py <rom> find "20 7c 00 04 04 3a"

通用参数:
    --arch auto|m68k|arm|thumb|6502|65816   （默认 auto 按平台自动选）
    --max N        最多列多少条，默认 40
    --context K    每条引用额外反汇编前后 K 条指令，默认 3

各架构的寻找方式不同，工具已内置:
    m68k  : 4 字节大端绝对地址 / 2 字节短地址；回溯 1..6 字节确认指令边界
    arm   : 4 字节小端（常量池 ldr）
    thumb : 2 字节 + 4 字节小端
    6502  : 3 字节小端操作数，且前一个字节必须是绝对寻址的合法操作码
    65816 : 3 字节小端 / 4 字节长地址
"""

import sys
import os
import re
import argparse

try:
    from capstone import *
    HAVE_CS = True
except Exception:
    HAVE_CS = False

ARCH_ALIAS = {
    '68k': 'm68k', 'm68000': 'm68k', 'genesis': 'm68k', 'md': 'm68k',
    '6502': '6502', 'nes': '6502', 'fc': '6502',
    '65816': '65816', 'snes': '65816', 'sfc': '65816',
    'arm': 'arm', 'gba': 'arm', 'thumb': 'thumb',
}

# 6502 使用 3 字节绝对寻址的官方操作码
OP6502_ABS = {
    0x0D, 0x0E, 0x2C, 0x2D, 0x2E, 0x4C, 0x4D, 0x4E, 0x6C, 0x6D, 0x6E,
    0x8C, 0x8D, 0x8E, 0xAC, 0xAD, 0xAE, 0xCC, 0xCD, 0xCE, 0xEC, 0xED, 0xEE,
    0x20,
}
OP6502_NAMES = {
    0x0D: 'ORA', 0x0E: 'ASL', 0x20: 'JSR', 0x2C: 'BIT', 0x2D: 'AND', 0x2E: 'ROL',
    0x4C: 'JMP', 0x4D: 'EOR', 0x4E: 'LSR', 0x6C: 'JMP()', 0x6D: 'ADC', 0x6E: 'ROR',
    0x8C: 'STY', 0x8D: 'STA', 0x8E: 'STX', 0xAC: 'LDY', 0xAD: 'LDA', 0xAE: 'LDX',
    0xCC: 'CPY', 0xCD: 'CMP', 0xCE: 'DEC', 0xEC: 'CPX', 0xED: 'SBC', 0xEE: 'INC',
}


# ------------------------------------------------------------ 架构选择

def guess_arch(d):
    """按平台指纹给个默认架构，返回 (arch, 平台描述)"""
    if b'NES\x1a' == d[:4]:
        return '6502', 'NES/FC'
    if d[0x04:0x10] == bytes.fromhex('24FFAE51699AA221'):
        return 'thumb', 'GBA'
    ssp = int.from_bytes(d[0:4], 'big')
    vdp = d.count(b'\xc0\x00\x04')
    if 0x00FF0000 <= ssp <= 0x01000000 and vdp > 4:
        return 'm68k', 'Sega MD/Genesis'
    for base in (0x7FC0, 0xFFC0):
        if len(d) >= base + 0x40:
            cs = int.from_bytes(d[base + 0x1E:base + 0x20], 'little')
            csc = int.from_bytes(d[base + 0x1C:base + 0x1E], 'little')
            if (cs ^ csc) == 0xFFFF:
                return '65816', 'SNES/SFC'
    return None, '未知'


def make_md(arch):
    if not HAVE_CS:
        return None
    try:
        if arch == 'm68k':
            md = Cs(CS_ARCH_M68K, CS_MODE_BIG_ENDIAN | CS_MODE_M68K_000)
        elif arch == 'arm':
            md = Cs(CS_ARCH_ARM, CS_MODE_ARM | CS_MODE_LITTLE_ENDIAN)
        elif arch == 'thumb':
            md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
        elif arch == '6502':
            md = Cs(CS_ARCH_MOS65XX, CS_MODE_NONE)
        else:
            return None
        md.detail = False
        return md
    except Exception:
        return None


def disasm_window(md, d, start, length, label=''):
    if not md:
        print('  (未安装 capstone，无法反汇编；pip install capstone)')
        return
    print('--- %s %#x-%#x ---' % (label, start, start + length))
    n = 0
    for ins in md.disasm(d[start:start + length], start):
        raw = ' '.join('%02x' % x for x in ins.bytes[:10])
        print('  %07x  %-24s %-8s %s' % (ins.address, raw, ins.mnemonic, ins.op_str))
        n += 1
    if n == 0:
        print('  (无法解码，可能起始位置不在指令边界上)')


# ------------------------------------------------------------ 引用扫描

def find_refs(d, addr, arch, maxn=40):
    """返回 [(指令起址, 指令长, 助记符, 操作数, 匹配位置)]"""
    out = []
    if arch == 'm68k':
        md = make_md('m68k')
        for width in (4, 2):
            if width == 2 and addr > 0xFFFF:
                continue
            pat = addr.to_bytes(width, 'big')
            i = d.find(pat)
            while i >= 0 and len(out) < maxn * 4:
                for back in range(1, 7):
                    st = i - back
                    if st < 0:
                        continue
                    try:
                        ins = next(md.disasm(d[st:i + width], st))
                    except Exception:
                        continue
                    if ins.address + len(ins.bytes) == i + width:
                        out.append((ins.address, len(ins.bytes),
                                    ins.mnemonic, ins.op_str, i))
                        break
                i = d.find(pat, i + 1)
    elif arch in ('6502', '65816'):
        for width in ((3, 2) if arch == '65816' else (2,)):
            pat = addr.to_bytes(width, 'little')
            i = d.find(pat)
            while i >= 0 and len(out) < maxn * 4:
                if width == 2:
                    op = d[i - 1] if i >= 1 else None
                    if op in OP6502_ABS:
                        out.append((i - 1, 3, OP6502_NAMES.get(op, '?'),
                                    '$%04x' % addr, i))
                else:
                    op = d[i - 1] if i >= 1 else None
                    out.append((i - 1, 3, 'op%02x' % (op or 0),
                                '$%04x' % addr, i))
                i = d.find(pat, i + 1)
    else:  # arm / thumb
        pat = addr.to_bytes(4, 'little')
        md = make_md(arch)
        i = d.find(pat)
        while i >= 0 and len(out) < maxn * 4:
            st = max(0, i - 8)
            note = '常量池/字面量'
            try:
                ins = next(md.disasm(d[st:i], st))
                note = '%s %s' % (ins.mnemonic, ins.op_str)
            except Exception:
                pass
            out.append((i, 4, 'pool', note, i))
            i = d.find(pat, i + 1)
    out.sort(key=lambda x: x[0])
    return out


def find_calls(d, target, arch, maxn=40):
    """找调用/跳转到 target 的指令"""
    out = []
    if arch == 'm68k':
        for pat, name in ((b'\x4e\xb9', 'jsr abs.l'), (b'\x4e\xb8', 'jsr abs.w'),
                          (b'\x4e\xf9', 'jmp abs.l'), (b'\x4e\xf8', 'jmp abs.w')):
            i = d.find(pat)
            while i >= 0:
                v = int.from_bytes(d[i + 2:i + 6], 'big')
                if v == target:
                    out.append((i, 6, name.split()[0], name))
                i = d.find(pat, i + 1)
        # bsr.w / bsr.b 是相对跳转，需要逐个位置算偏移（只扫前 3MB 的可执行区）
        i = 0
        n = min(len(d), 0x300000)
        while i < n - 4:
            if d[i] == 0x61:
                if d[i + 1] == 0x00:
                    disp = int.from_bytes(d[i + 2:i + 4], 'big', signed=True)
                    if i + 2 + disp == target:
                        out.append((i, 4, 'bsr', 'bsr.w'))
                else:
                    disp = d[i + 1]
                    if disp > 127:
                        disp -= 256
                    if i + 2 + disp == target:
                        out.append((i, 2, 'bsr', 'bsr.b'))
            i += 1
    elif arch == '6502':
        pat = target.to_bytes(2, 'little')
        i = d.find(pat)
        while i >= 0:
            if i >= 1 and d[i - 1] == 0x20:
                out.append((i - 1, 3, 'JSR', '$%04x' % target))
            i = d.find(pat, i + 1)
    else:
        print('  该架构暂不支持 calls 模式')
    out.sort(key=lambda x: x[0])
    return out[:maxn]


def main():
    ap = argparse.ArgumentParser(description='交叉引用 / 反汇编助手')
    ap.add_argument('rom')
    ap.add_argument('mode', choices=['ref', 'dis', 'calls', 'find'])
    ap.add_argument('arg', help='地址(如 0x4043A) 或十六进制字节串')
    ap.add_argument('--arch', default='auto')
    ap.add_argument('--len', type=lambda s: int(s, 0), default=0x120,
                    help='dis 模式反汇编长度')
    ap.add_argument('--max', type=int, default=40)
    ap.add_argument('--context', type=int, default=3)
    a = ap.parse_args()

    d = open(a.rom, 'rb').read()
    arch = a.arch
    if arch == 'auto':
        g, plat = guess_arch(d)
        arch = g
        print('自动识别架构: %s (%s)' % (arch or '未知', plat))
    arch = ARCH_ALIAS.get(arch, arch)
    if arch not in ('m68k', 'arm', 'thumb', '6502', '65816'):
        print('无法确定架构，请用 --arch 指定（m68k/arm/thumb/6502/65816）')
        return 2
    if not HAVE_CS:
        print('提示: 未安装 capstone，将看不到助记符。pip install capstone')
    md = make_md(arch)

    if a.mode == 'find':
        pat = bytes.fromhex(re.sub(r'[^0-9a-fA-F]', '', a.arg))
        hits, i = [], d.find(pat)
        while i >= 0:
            hits.append(i)
            i = d.find(pat, i + 1)
        print('字节串 %s 命中 %d 处: %s%s'
              % (pat.hex(' '), len(hits), [hex(x) for x in hits[:30]],
                 ' ...' if len(hits) > 30 else ''))
        return 0

    print('文件 %s  (%d 字节)  架构 %s' % (os.path.abspath(a.rom), len(d), arch))

    if a.mode == 'dis':
        addr = int(a.arg, 0)
        print()
        disasm_window(md, d, addr, a.len, '反汇编')
        return 0

    if a.mode == 'calls':
        target = int(a.arg, 0)
        print()
        print('查找"调用/跳转到 %#x" 的指令' % target)
        res = find_calls(d, target, arch, a.max)
        if not res:
            print('  (无)')
        for st, ln, mn, txt in res[:a.max]:
            print('  %07x  %-6s %s' % (st, mn, txt))
        return 0

    # mode == ref
    addr = int(a.arg, 0)
    print()
    print('查找"引用了 %#x" 的指令' % addr)
    res = find_refs(d, addr, arch, a.max)
    if not res:
        print('  (无) —— 可能: 地址被拆分/间接寻址/表被压缩；')
        print('        试试用 dis 模式看周围代码，或 find 模式搜字节串')
        return 1
    # 相邻位置合并成"引用点"
    groups = []
    for st, ln, mn, txt, at in res:
        if groups and st - groups[-1][0] <= 2:
            continue
        groups.append((st, mn, txt, at))
    print('命中 %d 处:' % len(groups))
    seen_txt = set()
    for st, mn, txt, at in groups[:a.max]:
        print('  %07x  %-8s %s' % (st, mn, txt))
        seen_txt.add(st)
    print()
    print('说明: 同一个地址常被多处引用 —— 状态栏显示、升级计算、伤害计算各一处，')
    print('      把每处的上下文反汇编出来对比，就能给表/变量定语义。')
    if a.context:
        print()
        for st, mn, txt, at in groups[:3]:
            s = max(0, st - 0x10 * a.context)
            disasm_window(md, d, s, 0x30 * a.context, '引用点 %#x 的上下文' % st)
            print()
    return 0


if __name__ == '__main__':
    sys.exit(main())
