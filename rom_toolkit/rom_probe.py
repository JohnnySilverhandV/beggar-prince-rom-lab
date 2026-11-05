#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rom_probe.py —— 通用 ROM 探壳器（纯标准库，不需要装任何东西）

第一步永远跑这个。它回答三个问题：
    这是什么平台 / 数据是不是压缩或加密的 / 有没有明文线索

用法:
    python rom_probe.py <rom文件>
    python rom_probe.py <rom文件> --block 8192      # 换熵分析块大小
    python rom_probe.py <rom文件> --no-strings      # 跳过字符串提取

输出 6 段:
    [1] 文件基础信息（大小是否为整片 Flash 容量 / 哈希）
    [2] 平台指纹判定（MD/SNES/GB/GBA/NES/SMS-GG）
    [3] 熵分布图（压缩区、未使用区一眼可见）
    [4] 未使用区扫描（连续 0x00 / 0xFF）
    [5] 对齐嗅探（哪个步长下各字节位大量为零 → 位平面/结构体填充线索）
    [6] 字符串提取（ASCII 英文串 + GBK 中文串）
"""

import sys
import os
import re
import math
import hashlib
import argparse
import collections

# ---------------------------------------------------------------- 常量

GB_LOGO = bytes.fromhex(
    'CEED6666CC0D000B03730083000C000D0008111F8889000EDCCC6EE6DDDDD999'
    'BBBB67636E0EECCCDDDC999FBBB9333E')
GBA_LOGO = bytes.fromhex('24FFAE51699AA2213D84820A')

SIZE_HINTS = {
    0x8000: '32 KiB (32KB)', 0x10000: '64 KiB', 0x20000: '128 KiB',
    0x40000: '256 KiB = 2 Mbit', 0x80000: '512 KiB = 4 Mbit',
    0x100000: '1 MiB = 8 Mbit', 0x200000: '2 MiB = 16 Mbit',
    0x400000: '4 MiB = 32 Mbit', 0x800000: '8 MiB = 64 Mbit',
    0x1000000: '16 MiB = 128 Mbit',
}


def u(b, o, n, order='big'):
    return int.from_bytes(b[o:o + n], order)


def hr(title):
    print()
    print('=' * 66)
    print(title)
    print('=' * 66)


# ---------------------------------------------------------------- [2] 平台指纹

def detect_platform(b):
    """返回 [(平台名, 可信度, 证据), ...]，按可信度降序"""
    n = len(b)
    hits = []

    # --- NES / Famicom
    if b[:4] == b'NES\x1a':
        hits.append(('NES / FC', 100, 'iNES 头 magic "NES\\x1a"'))

    # --- GB / GBC
    if n >= 0x150 and b[0x104:0x104 + len(GB_LOGO)] == GB_LOGO:
        title = b[0x134:0x144].split(b'\x00')[0].decode('latin1', 'replace')
        hits.append(('GB / GBC', 100,
                     '任天堂 logo 校验通过  标题=%r  CGB标志=%#04x'
                     % (title, b[0x143])))

    # --- GBA
    if n >= 0xC0 and b[0x04:0x04 + len(GBA_LOGO)] == GBA_LOGO and b[0xB2] == 0x96:
        title = b[0xA0:0xAC].decode('latin1', 'replace')
        hits.append(('GBA', 100, 'logo + 0x96 校验通过  标题=%r' % title))

    # --- SMS / Game Gear
    for base, tag in ((0x7FF0, 'SMS'), (0x3FF0, 'GG')):
        if n >= base + 0x10 and b[base:base + 8] == b'TMR SEGA':
            hits.append(('Sega Master System / Game Gear', 95,
                         '%s 头 "TMR SEGA" @ %#x' % (tag, base)))

    # --- Mega Drive / Genesis
    ssp, entry = u(b, 0, 4), u(b, 4, 4)
    md_ram = 0x00FF0000 <= ssp <= 0x01000000
    vdp = b.count(b'\xc0\x00\x04') + b.count(b'\x00\xc0\x00\x04')
    if b[0x100:0x104] == b'SEGA':
        hits.append(('Sega Mega Drive / Genesis', 99, '0x100 处有 "SEGA" 标准头'))
    if md_ram and vdp > 4:
        note = ('向量表 SSP=%#010x 复位入口=%#06x  VDP($C00004) 出现 %d 次'
                % (ssp, entry, vdp))
        if not b[0x100:0x104] == b'SEGA':
            note += '  (0x100 无 SEGA 头 → 汉化/破解/自制 ROM)'
        hits.append(('Sega Mega Drive / Genesis', 95, note))

    # --- SNES / SFC
    for base, label in ((0x7FC0, 'LoROM'), (0xFFC0, 'HiROM')):
        if n < base + 0x40:
            continue
        title = b[base:base + 21]
        printable = sum(1 for c in title if 32 <= c < 127)
        cs, csc = u(b, base + 0x1E, 2, 'little'), u(b, base + 0x1C, 2, 'little')
        if printable >= 15 and (cs ^ csc) == 0xFFFF:
            hits.append(('SNES / SFC', 97,
                         '%s 头 (标题校验通过)  标题=%r  MAP=%#04x'
                         % (label, title.decode('latin1').strip(), b[base + 0x15])))
        elif printable >= 18 and n % 0x8000 == 0:
            hits.append(('SNES / SFC ?', 55,
                         '%s 位置像标题但校验和不对  标题=%r'
                         % (label, title.decode('latin1').strip())))

    # --- PC-Engine / TurboGrafx
    if n >= 0x2000 and b[0x1FFF] == 0x00:
        pass  # 太弱，不报

    hits.sort(key=lambda x: -x[1])
    return hits


# ---------------------------------------------------------------- [3] 熵

def entropy_profile(b, bs):
    chars = ' .:-=+*#%@'
    ents = []
    for i in range(0, len(b), bs):
        blk = b[i:i + bs]
        c = collections.Counter(blk)
        e = -sum((v / len(blk)) * math.log2(v / len(blk)) for v in c.values())
        ents.append(e)
    print('块大小 %d 字节，共 %d 块；熵值 0=全同字节，8=完全随机' % (bs, len(ents)))
    print('图例: " "=<2(几乎空)  ":#@"=高熵(压缩或加密)')
    print()
    per = 64
    for i in range(0, len(ents), per):
        row = ents[i:i + per]
        print('%08x %s' % (i * bs,
                           ''.join(chars[min(9, int(e / 8.1 * 10))] for e in row)))
    print()
    lo = sum(1 for e in ents if e < 2)
    mid = sum(1 for e in ents if 2 <= e < 6)
    hi = sum(1 for e in ents if e >= 6)
    print('统计: 低熵块(<2) %d (%.0f%%)   中熵 %d (%.0f%%)   高熵(>=6) %d (%.0f%%)'
          % (lo, lo * 100.0 / len(ents), mid, mid * 100.0 / len(ents),
             hi, hi * 100.0 / len(ents), ))
    print('判读: 低熵块多 = 有大量空白/未使用区; 高熵区 = 压缩或加密的素材')
    return ents


# ---------------------------------------------------------------- [4] 未使用区

def unused_regions(b, minrun=8192):
    print('连续相同字节 >= %d 的区域（可能表示"未使用的 Flash 空间"）' % minrun)
    out = []
    i, n = 0, len(b)
    while i < n:
        v = b[i]
        j = i
        while j < n and b[j] == v:
            j += 1
        if j - i >= minrun:
            out.append((i, j, v))
        i = j
    if not out:
        print('  (无)')
    for s, e, v in out:
        print('  %#08x - %#08x  %8d 字节  填充值 %#04x' % (s, e, e - s, v))
    return out


# ---------------------------------------------------------------- [5] 对齐嗅探

def alignment_sniff(b, strides=(2, 4, 8, 16, 32), lo=0, hi=None):
    if hi is None or hi > len(b):
        hi = len(b)
    print('按固定步长切分，统计"每个位置上是 0x00 的比例"  扫描区 %#x-%#x' % (lo, hi))
    print('判读: 某位置接近 100% → 该处是填充/高位平面; 约 50% → 可能是 4bpp 位平面图块')
    print('      某步长下多个位置偏高 → 数据结构/图块按该步长排列')
    print('      整片扫描没信号时，请用 --align-range 缩到疑似图块区再试')
    data = b[lo:hi]
    for st in strides:
        cnt = [0] * st
        tot = 0
        for i in range(0, len(data) - st, st):
            row = data[i:i + st]
            for j, x in enumerate(row):
                if x == 0:
                    cnt[j] += 1
            tot += 1
        if not tot:
            continue
        pct = [c * 100.0 / tot for c in cnt]
        bar = ' '.join('%3.0f%%' % p for p in pct)
        print('  步长%3d : %s' % (st, bar))
    print()


# ---------------------------------------------------------------- [6] 字符串

def strings_report(b, maxshow=40):
    print('--- ASCII 英文语句（带空格，>=8 字符）---')
    pat = re.compile(rb'(?:[A-Za-z][A-Za-z0-9_./:!?()-]*[ ]+){1,}[A-Za-z][A-Za-z0-9_./:!?()-]*')
    seen, shown = set(), 0
    for m in pat.finditer(b):
        t = m.group().decode('latin1')
        if len(t) >= 8 and sum(c.isalpha() for c in t) >= 6 and t not in seen:
            seen.add(t)
            print('  %08x  %s' % (m.start(), t[:96]))
            shown += 1
            if shown >= maxshow:
                break
    print('  小计 %d 条（截断前）' % shown)

    print()
    print('--- ASCII 单词串 / 标识符（无空格，>=8 字符，去重取前 60）---')
    seen, shown = set(), 0
    for m in re.finditer(rb'[ -~]{8,}', b):
        t = m.group().decode('latin1').strip()
        if t in seen or len(t) < 8:
            continue
        if not re.search(r'[A-Za-z]{4}', t):
            continue
        seen.add(t)
        print('  %08x  %s' % (m.start(), t[:96]))
        shown += 1
        if shown >= 60:
            break
    print('  小计 %d 条（截断前）' % shown)

    print()
    print('--- GBK 中文串（>=4 个汉字）---')
    shown = 0
    for m in re.finditer(rb'(?:[\xb0-\xf7][\xa1-\xfe]){4,}', b):
        try:
            t = m.group().decode('gbk')
        except Exception:
            continue
        print('  %08x  %s' % (m.start(), t[:60]))
        shown += 1
        if shown >= 40:
            break
    if not shown:
        print('  (无) —— 若游戏是中文却没命中，说明用的是自定义字库，不是 GBK')
    print('  小计 %d 条（截断前）' % shown)


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description='通用 ROM 探壳器')
    ap.add_argument('rom')
    ap.add_argument('--block', type=int, default=4096, help='熵分析块大小，默认 4096')
    ap.add_argument('--no-strings', action='store_true')
    ap.add_argument('--align-range', default=None,
                    help='对齐嗅探只看这个区间，如 0x140000-0x180000')
    a = ap.parse_args()

    alo, ahi = 0, 0x400000
    if a.align_range:
        s, _, e = a.align_range.partition('-')
        alo, ahi = int(s, 0), int(e, 0)

    if not os.path.isfile(a.rom):
        print('文件不存在: %s' % a.rom)
        return 2
    b = open(a.rom, 'rb').read()
    n = len(b)

    hr('[1] 文件基础信息')
    print('路径   : %s' % os.path.abspath(a.rom))
    print('大小   : %d 字节 = %#x = %.2f MiB' % (n, n, n / 1048576.0))
    if n in SIZE_HINTS:
        print('判读   : 正好是整片 Flash 容量（%s）→ 很可能是编程器读出的完整 dump'
              % SIZE_HINTS[n])
    else:
        for k in sorted(SIZE_HINTS):
            if k > n:
                print('判读   : 不是整片容量; 下一个整片容量是 %s（%#x）' % (SIZE_HINTS[k], k))
                break
    print('MD5    : %s' % hashlib.md5(b).hexdigest())
    print('SHA256 : %s' % hashlib.sha256(b).hexdigest()[:48] + '...')
    print('提示   : 拿 MD5 去 Google 搜一下，能直接查到游戏名就不要自己猜')

    hr('[2] 平台指纹')
    hits = detect_platform(b)
    if not hits:
        print('未命中任何已知平台头。可能是: 被裁剪/加密的固件、非游戏固件、')
        print('或头部被覆盖的自制 ROM。请把 [6] 里的字符串线索发出来人工判断。')
    for name, conf, note in hits:
        print('  [%3d%%] %s' % (conf, name))
        print('         %s' % note)

    hr('[3] 熵分布')
    entropy_profile(b, a.block)

    hr('[4] 未使用区')
    unused_regions(b)

    hr('[5] 对齐嗅探')
    alignment_sniff(b, lo=alo, hi=ahi)

    if not a.no_strings:
        hr('[6] 字符串')
        strings_report(b)

    hr('下一步')
    print('1. 有游戏名 → 去查攻略/数值表/金手指码，拿"数值序列"当指纹')
    print('2. 跑 find_table.py 用指纹把表挖出来：')
    print('     python find_table.py <rom> --seq 50,152,232,370,470,580')
    print('3. 跑 xref.py 确认"谁在读这张表"，语义才算落地：')
    print('     python xref.py <rom> ref 0x4043A')
    print('4. 打补丁 + 逐字节 diff 校验：')
    print('     python patch_table.py plan.json')
    return 0


if __name__ == '__main__':
    sys.exit(main())
