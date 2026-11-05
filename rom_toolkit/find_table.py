#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
find_table.py —— 数值表指纹定位器

核心思路（本次实战验证有效）：
    攻略/资料里抄来的逐级数值序列 = 指纹
    在 ROM 里搜索"以固定步长排列的同一串数字"
    不需要知道表在哪、也不需要知道记录结构 —— 三件事全由暴力枚举算出：
        起始偏移 / 记录步长 / 字段宽度与字节序

用法一（有指纹，最常用）:
    python find_table.py <rom> --seq 50,152,232,370,470,580,710,880

用法二（没有指纹，只能找"单调递增的表"）:
    python find_table.py <rom> --monotonic --min-run 20

常用参数:
    --seq          指纹数值序列，逗号分隔（从攻略抄，越独特越好）
    --types        尝试的编码，默认 u16be,u16le,u8,u32be,u32le
    --strides      尝试的步长，默认 2-32，可写 2,4,6-12
    --top          只显示前 N 个命中，默认 12
    --dump         命中后 dump 多少条完整记录，默认 6
    --min-match    最少要连续匹配几个值才算命中，默认 max(3, len(seq)//3)
    --align        只报告"字段起始地址是 2 的倍数"的命中（表通常按字对齐）

输出:
    每个候选按"匹配数从多到少"排序，并打印匹配率、步长、字段偏移、记录预览
"""

import sys
import os
import argparse

TYPES = {
    'u8': (1, 'big'),
    'u16be': (2, 'big'), 'u16le': (2, 'little'),
    'u32be': (4, 'big'), 'u32le': (4, 'little'),
}


def dec(buf, off, t):
    sz, order = TYPES[t]
    if off < 0 or off + sz > len(buf):
        return None
    return int.from_bytes(buf[off:off + sz], order)


def parse_strides(s):
    out = []
    for part in s.split(','):
        part = part.strip()
        if '-' in part:
            a, b = part.split('-')
            out.extend(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return sorted(set(x for x in out if x >= 1))


def search_fingerprint(d, seq, types, strides, min_match, allow_gap=1):
    """以 seq[0] 为锚点找候选，再沿固定步长验证后续值。

    allow_gap: 允许中间有几个值对不上（攻略和实际 ROM 常有小差异），
               一旦连续不匹配超过 allow_gap 就放弃这条候选，避免误报。
    """
    results = []
    scan_cap = 400000          # 锚点位置上限，防病态输入
    for t in types:
        sz, order = TYPES[t]
        try:
            anchor = int(seq[0]).to_bytes(sz, order)
        except OverflowError:
            continue
        positions = []
        i = d.find(anchor)
        while i >= 0:
            positions.append(i)
            if len(positions) >= scan_cap:
                break
            i = d.find(anchor, i + 1)
        if not positions:
            continue
        for st in strides:
            for p in positions:
                matched = 1
                found = [seq[0]]
                misses = 0
                k = 1
                while k < len(seq):
                    v = dec(d, p + st * k, t)
                    found.append(v)
                    if v == seq[k]:
                        matched += 1
                        misses = 0
                    else:
                        misses += 1
                        if misses > allow_gap:
                            break
                    k += 1
                if matched >= min_match:
                    results.append({'type': t, 'stride': st, 'field': p,
                                    'matched': matched, 'total': len(seq),
                                    'found': found, 'scanned': k})
    # 去掉"同一处被不同步长重复报出"的冗余：保留同一 field 下匹配数最高的
    best = {}
    for r in results:
        k = r['field']
        if k not in best or (r['matched'], -r['stride']) > (best[k]['matched'], -best[k]['stride']):
            best[k] = r
    out = sorted(best.values(), key=lambda r: (-r['matched'], r['stride'], r['field']))
    return out


def dump_records(d, field, stride, count, label=''):
    """按 field 为字段起点、stride 为步长，dump 若干条记录的全部字段"""
    print('  记录预览（字段起点 %#x，步长 %d）%s' % (field, stride, label))
    base = field
    for k in range(count):
        o = base + stride * k
        if o + stride > len(d):
            break
        row = d[o:o + stride]
        print('    #%-3d @%08x  %s   |  %s'
              % (k, o, ' '.join('%02x' % x for x in row),
                 ''.join(chr(x) if 32 <= x < 127 else '.' for x in row)))


def search_monotonic(d, types, strides, min_run, lo=0, hi=None):
    """找固定步长下严格递增的长序列（无需指纹）"""
    if hi is None:
        hi = len(d)
    res = []
    for t in types:
        sz, _ = TYPES[t]
        for st in strides:
            n = (hi - lo) // st
            vals = [dec(d, lo + st * i, t) for i in range(n)]
            i = 0
            while i < n - 1:
                if vals[i] is None:
                    i += 1
                    continue
                j = i + 1
                while j < n and vals[j] is not None and vals[j] > vals[j - 1]:
                    j += 1
                if j - i >= min_run:
                    res.append({'type': t, 'stride': st, 'field': lo + st * i,
                                'matched': j - i, 'total': j - i,
                                'head': vals[i:i + 6], 'tail': vals[j - 3:j]})
                i = max(j, i + 1)
    res.sort(key=lambda r: -r['matched'])
    return res


def main():
    ap = argparse.ArgumentParser(description='数值表指纹定位器')
    ap.add_argument('rom')
    ap.add_argument('--seq', default=None, help='指纹数值序列，逗号分隔')
    ap.add_argument('--monotonic', action='store_true', help='改用"找递增长序列"模式')
    ap.add_argument('--min-run', type=int, default=20)
    ap.add_argument('--types', default='u16be,u16le,u8,u32be,u32le')
    ap.add_argument('--strides', default='2-32')
    ap.add_argument('--top', type=int, default=12)
    ap.add_argument('--dump', type=int, default=6)
    ap.add_argument('--min-match', type=int, default=None)
    ap.add_argument('--allow-gap', type=int, default=1,
                    help='允许中间几个值对不上（攻略与 ROM 常有小差异），默认 1')
    ap.add_argument('--align', type=int, default=None,
                    help='字段起点只接受该数的倍数，如 2')
    a = ap.parse_args()

    d = open(a.rom, 'rb').read()
    types = [t.strip() for t in a.types.split(',') if t.strip()]
    for t in types:
        if t not in TYPES:
            print('未知编码: %s（可选 %s）' % (t, ','.join(TYPES)))
            return 2
    strides = parse_strides(a.strides)

    print('文件 %s  (%d 字节)' % (os.path.abspath(a.rom), len(d)))
    print('编码候选 %s   步长 %s' % (types, strides))

    if a.monotonic:
        print('模式: 查找"固定步长下严格递增"的长序列（无需指纹）')
        print()
        res = search_monotonic(d, types, strides, a.min_run)
        if not res:
            print('没找到。放宽 --min-run，或扩大 --strides 范围。')
            return 1
        for r in res[:a.top]:
            print('  长度 %-5d %-6s 步长 %-3d 起始 %#08x   头 %s  尾 %s'
                  % (r['matched'], r['type'], r['stride'], r['field'],
                     r['head'], r['tail']))
        print()
        dump_records(d, res[0]['field'], res[0]['stride'], a.dump, '（最佳命中）')
        return 0

    if not a.seq:
        print('必须给 --seq，或用 --monotonic 模式')
        return 2

    seq = [int(x, 0) for x in a.seq.replace(' ', '').split(',') if x]
    if len(seq) < 3:
        print('指纹至少给 3 个值（越多越准）')
        return 2
    min_match = a.min_match if a.min_match else max(3, len(seq) // 3)

    print('指纹 %d 个值: %s' % (len(seq), seq[:12]))
    print('要求匹配 >= %d 个（允许中间 %d 个对不上）' % (min_match, a.allow_gap))
    print()

    res = search_fingerprint(d, seq, types, strides, min_match, a.allow_gap)
    if a.align:
        res = [r for r in res if r['field'] % a.align == 0]
    if not res:
        print('没命中。依次尝试：')
        print('  1) 换编码：--types u16le,u8,u32le,u32be')
        print('  2) 放宽步长：--strides 2-64')
        print('  3) 降门槛：--min-match 2 --allow-gap 2')
        print('  4) 攻略数值可能经过换算（如显示值×10），先心算折算再试')
        print('  5) 表可能被压缩/加密 —— 回到 rom_probe.py 看熵图')
        return 1

    print('命中 %d 处（已按字段起点去重，按匹配数排序）' % len(res))
    print()
    print('  %-8s %-6s %-6s %-12s %s' % ('匹配', '编码', '步长', '字段起点', '匹配率'))
    for r in res[:a.top]:
        print('  %-8s %-6s %-6d %#-12x %.0f%%'
              % ('%d/%d' % (r['matched'], r['total']), r['type'], r['stride'],
                 r['field'], r['matched'] * 100.0 / r['total']))

    best = res[0]
    print()
    print('最佳命中逐值对照（★=对得上，×=对不上，. =未扫描到）')
    print('  位置  %-10s %-10s' % ('ROM 实测', '攻略指纹'))
    for k in range(len(seq)):
        if k < len(best['found']):
            v = best['found'][k]
            mark = '★' if v == seq[k] else '×'
            if v is None:
                mark, v = '.', '--'
        else:
            v, mark = '--', '.'
        print('  #%-4d %-10s %-10d %s' % (k, v, seq[k], mark))
    print()
    dump_records(d, best['field'], best['stride'], a.dump, '（最佳命中）')
    print()
    print('下一步：确认"谁在读这张表" —— 把字段起点丢给 xref.py：')
    print('    python xref.py %s ref %#x' % (a.rom, best['field']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
