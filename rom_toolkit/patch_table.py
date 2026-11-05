#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_table.py —— 参数化补丁器（用 JSON 描述"改什么、怎么改"）

设计原则:
    1. 原文件永远只读，成品写到 out/
    2. 文件长度必须不变（改数据表不该改变大小）
    3. 打完补丁逐字节 diff，把改动范围打印出来对账
    4. 用同一套描述回读校验，确保补丁落在预期位置

用法:
    python patch_table.py plan.json               # 打补丁
    python patch_table.py plan.json --dry-run     # 只看会改成什么样，不写文件
    python patch_table.py --init plan.json        # 生成一份带注释的模板

plan.json 结构:
{
  "src": "E:/path/to/rom.bin",
  "out": "out/rom_patched.bin",
  "ops": [
    {
      "name": "升级所需经验",
      "base": "0x4043E",
      "stride": 6,
      "count": 27,
      "type": "u16be",
      "expr": "round(v / 10)",
      "clamp": [1, 9999]
    },
    {
      "name": "攻击档位（组内单调递增）",
      "base": "0x3FEE2", "stride": 10, "count": 24, "type": "u16be",
      "expr": "round(v * 2 + 40)",
      "group_sizes": [4, 5, 4, 3, 4, 4],
      "monotonic": "grow"
    },
    { "name": "保底经验", "bytes": "0xD2162", "hex": "0001" }
  ]
}

expr 里可用的变量/函数:
    v  当前值      i  第几个元素(从 0 开始)
    round / int / min / max / abs / floor / ceil / sqrt / pow

type 可选: u8 / u16be / u16le / u32be / u32le
group_sizes: 分组长度表，用于"武器/角色分组"这类表
monotonic  :
    true    → 遇到下降就压平（维持前一个值）
    "grow"  → 遇到下降就继续爬升（前值 + max(2, 前值 × grow_rate)），
              默认 grow_rate=0.08。适用于原版数据里"每组最后一档是个断崖值"的坑
"""

import sys
import os
import json
import math
import hashlib
import argparse

TYPES = {
    'u8': (1, 'big'),
    'u16be': (2, 'big'), 'u16le': (2, 'little'),
    'u32be': (4, 'big'), 'u32le': (4, 'little'),
}

SAFE = {
    'round': round, 'int': int, 'min': min, 'max': max, 'abs': abs,
    'floor': math.floor, 'ceil': math.ceil, 'sqrt': math.sqrt, 'pow': pow,
    'v': 0, 'i': 0,
}

TEMPLATE = {
    "_说明": "把本文件另存后改成你要的数值；expr 里 v=当前值, i=元素序号",
    "src": "E:/path/to/rom.bin",
    "out": "out/rom_patched.bin",
    "ops": [
        {
            "name": "示例：把某张表的每个值除以 10",
            "base": "0x4043E", "stride": 6, "count": 27, "type": "u16be",
            "expr": "round(v / 10)",
            "clamp": [1, 9999]
        },
        {
            "name": "示例：把一段字节原样替换",
            "bytes": "0xD2162", "hex": "0001"
        }
    ]
}


def rd(buf, off, t):
    sz, order = TYPES[t]
    return int.from_bytes(buf[off:off + sz], order)


def wr(buf, off, t, val):
    sz, order = TYPES[t]
    val &= (0xFFFFFFFF if sz == 4 else (0xFFFF if sz == 2 else 0xFF))
    buf[off:off + sz] = val.to_bytes(sz, order)


def ev(expr, v, i):
    ns = dict(SAFE)
    ns['v'] = v
    ns['i'] = i
    return eval(expr, {'__builtins__': {}}, ns)


def apply_op(buf, op):
    """返回 (changed_list, describe)"""
    changes = []
    if 'bytes' in op:
        off = int(op['bytes'], 0) if isinstance(op['bytes'], str) else op['bytes']
        raw = bytes.fromhex(op['hex'].replace(' ', ''))
        if off + len(raw) > len(buf):
            raise ValueError('字节写入越界: %#x + %d' % (off, len(raw)))
        old = buf[off:off + len(raw)]
        buf[off:off + len(raw)] = raw
        if old != raw:
            changes.append((off, off + len(raw) - 1))
        return changes, '%s: %#x <- %s' % (op.get('name', 'bytes'), off, raw.hex(' '))

    base = int(op['base'], 0) if isinstance(op['base'], str) else op['base']
    stride = int(op['stride'])
    count = int(op['count'])
    t = op.get('type', 'u16be')
    if t not in TYPES:
        raise ValueError('未知 type: %s' % t)
    sz = TYPES[t][0]
    expr = op.get('expr', 'v')
    clamp = op.get('clamp')
    monotonic = op.get('monotonic')
    grow_rate = float(op.get('grow_rate', 0.08))
    groups = op.get('group_sizes')

    vals_old = [rd(buf, base + stride * i, t) for i in range(count)]
    vals_new = []
    for i, v in enumerate(vals_old):
        nv = ev(expr, v, i)
        try:
            nv = int(round(nv))
        except Exception:
            raise ValueError('expr 结果不是数字: %r (第 %d 项)' % (nv, i))
        if clamp:
            nv = max(int(clamp[0]), min(int(clamp[1]), nv))
        vals_new.append(nv)

    # 单调化：绝不比前一个值小
    #   monotonic: true     → 压平成平台（= 前一个值）
    #   monotonic: "grow"   → 继续爬升（= 前一个值 + max(2, 前值*grow_rate)）
    # 分组时每组的第一个不受上一组约束（适用于"武器/角色分组表"
    # 里"每组最后一档数值反而下降"这种原始数据坑）
    if monotonic:
        grow = (monotonic == 'grow' or monotonic is True and op.get('grow_rate'))
        if isinstance(monotonic, str):
            grow = monotonic.lower() in ('grow', 'slope', 'continue')
        spans = []
        if groups:
            idx = 0
            for g in groups:
                spans.append(range(idx, min(idx + g, len(vals_new))))
                idx += g
            if idx < len(vals_new):
                spans.append(range(idx, len(vals_new)))
        else:
            spans.append(range(len(vals_new)))
        for sp in spans:
            for k in list(sp)[1:]:
                if vals_new[k] < vals_new[k - 1]:
                    if grow:
                        vals_new[k] = vals_new[k - 1] + max(2, round(vals_new[k - 1] * grow_rate))
                    else:
                        vals_new[k] = vals_new[k - 1]
            if clamp:
                for k in sp:
                    vals_new[k] = max(int(clamp[0]), min(int(clamp[1]), vals_new[k]))

    for i, nv in enumerate(vals_new):
        o = base + stride * i
        if o + sz > len(buf):
            raise ValueError('表越界: 第 %d 项 @%#x' % (i, o))
        if nv != vals_old[i]:
            changes.append((o, o + sz - 1))
        wr(buf, o, t, nv)

    desc = ('%s: base=%#x stride=%d count=%d type=%s\n'
            '        旧值 %s\n        新值 %s'
            % (op.get('name', 'table'), base, stride, count, t,
               vals_old[:14], vals_new[:14]))
    return changes, desc


def merge_ranges(ranges, gap=8):
    ranges = sorted(ranges)
    out = []
    for s, e in ranges:
        if out and s - out[-1][1] <= gap:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def main():
    ap = argparse.ArgumentParser(description='参数化 ROM 补丁器')
    ap.add_argument('plan', nargs='?')
    ap.add_argument('--init', metavar='FILE', help='生成模板 JSON 后退出')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--verbose', action='store_true', help='打印每项旧值/新值全表')
    a = ap.parse_args()

    if a.init:
        with open(a.init, 'w', encoding='utf-8') as f:
            json.dump(TEMPLATE, f, ensure_ascii=False, indent=2)
        print('已生成模板: %s' % a.init)
        return 0

    if not a.plan:
        print('需要 plan.json，或用 --init 生成模板')
        return 2

    with open(a.plan, encoding='utf-8') as f:
        plan = json.load(f)

    src = plan['src']
    if not os.path.isabs(src):
        src = os.path.join(os.path.dirname(os.path.abspath(a.plan)), src)
    orig = open(src, 'rb').read()
    buf = bytearray(orig)

    print('原文件 : %s' % os.path.abspath(src))
    print('大小   : %d 字节' % len(orig))
    print('MD5    : %s' % hashlib.md5(orig).hexdigest())
    print()

    all_changes = []
    for op in plan['ops']:
        ch, desc = apply_op(buf, op)
        all_changes.extend(ch)
        print('  [%s]' % ('改动' if ch else '无变化'))
        print('        %s' % desc)
        print()

    if len(buf) != len(orig):
        print('!! 长度改变了，拒绝写出（%d -> %d）' % (len(orig), len(buf)))
        return 3

    blocks = merge_ranges(all_changes)
    print('改动汇总: %d 处，合并为 %d 个连续区间' % (len(all_changes), len(blocks)))
    for s, e in blocks:
        print('   %#08x - %#08x  (%d 字节)' % (s, e, e - s + 1))
    print()

    if a.dry_run:
        print('--dry-run: 未写出文件')
        return 0

    out = plan.get('out', 'out/rom_patched.bin')
    if not os.path.isabs(out):
        out = os.path.join(os.path.dirname(os.path.abspath(a.plan)), out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'wb') as f:
        f.write(bytes(buf))

    chk = open(out, 'rb').read()
    same_len = len(chk) == len(orig)
    unknown = sum(1 for i in range(len(orig)) if orig[i] != chk[i]
                  and not any(s <= i <= e for s, e in all_changes))
    print('已写出 : %s' % os.path.abspath(out))
    print('MD5    : %s' % hashlib.md5(chk).hexdigest())
    print('长度不变: %s' % ('是' if same_len else '否 —— 异常！'))
    print('越界改动: %d 字节 %s' % (unknown, '(应为 0)' if unknown == 0 else '<-- 有问题！'))
    print()
    print('建议下一步:')
    print('  1) 用 xref.py 确认过"谁读这张表"，确保没连带改到敌人/其他单位')
    print('  2) 模拟器里跑一场战斗，看升级提示与数值跳变是否符合预期')
    print('  3) 原文件保持不动，随时可以换参数重新生成')
    return 0


if __name__ == '__main__':
    sys.exit(main())
