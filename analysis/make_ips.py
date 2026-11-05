#!/usr/bin/env python3
"""Generate IPS patch files from original ROM <-> patched ROM, with round-trip verification.

Usage: python make_ips.py <original_rom> <out_dir_with_bins> <repo_patches_dir>
Only stores changed bytes (IPS format), so the full copyrighted ROM is never redistributed.
"""
import sys, hashlib, pathlib

MAPPING = {
    "xqgwz_强化A_轻度.bin": "patch_A_mild.ips",
    "xqgwz_强化B_重度.bin": "patch_B_heavy.ips",
    "xqgwz_强化C_极限.bin": "patch_C_extreme.ips",
    "xqgwz_强化A_轻度_攻击版.bin": "patch_A_mild_attack.ips",
    "xqgwz_强化B_重度_攻击版.bin": "patch_B_heavy_attack.ips",
    "xqgwz_强化C_极限_攻击版.bin": "patch_C_extreme_attack.ips",
    "xqgwz_仅攻击力_其余原样.bin": "patch_attack_only.ips",
    "xqgwz_轻度_魔法秒杀版.bin": "patch_mild_magic_nuke.ips",
    "xqgwz_轻度_魔法秒杀必中版.bin": "patch_mild_magic_nuke_alwayshit.ips",
}

def make_ips(orig: bytes, mod: bytes) -> bytes:
    assert len(orig) == len(mod), "length mismatch"
    out = bytearray(b"PATCH")
    i, n = 0, len(orig)
    while i < n:
        if orig[i] == mod[i]:
            i += 1
            continue
        start = i
        while i < n and orig[i] != mod[i]:
            i += 1
        chunk = mod[start:i]
        for j in range(0, len(chunk), 65535):
            seg = chunk[j:j + 65535]
            out += (start + j).to_bytes(3, "big")
            out += len(seg).to_bytes(2, "big")
            out += seg
    out += b"EOF"
    return bytes(out)

def apply_ips(rom: bytes, ips: bytes) -> bytes:
    buf = bytearray(rom)
    assert ips[:5] == b"PATCH"
    i = 5
    while i + 3 <= len(ips):
        if ips[i:i + 3] == b"EOF":
            break
        off = int.from_bytes(ips[i:i + 3], "big"); i += 3
        ln = int.from_bytes(ips[i:i + 2], "big"); i += 2
        if ln == 0:  # RLE
            val = ips[i]; cnt = int.from_bytes(ips[i + 1:i + 3], "big"); i += 3
            buf[off:off + cnt] = bytes([val]) * cnt
        else:
            buf[off:off + ln] = ips[i:i + ln]; i += ln
    return bytes(buf)

def main():
    orig_path, out_dir, dst_dir = (pathlib.Path(p) for p in sys.argv[1:4])
    orig = orig_path.read_bytes()
    print(f"original: {orig_path.name}  size={len(orig)}  md5={hashlib.md5(orig).hexdigest()}")
    ok = True
    for src, dst in MAPPING.items():
        f = out_dir / src
        if not f.exists():
            print(f"  !! missing {src}"); ok = False; continue
        mod = f.read_bytes()
        ips = make_ips(orig, mod)
        (dst_dir / dst).write_bytes(ips)
        # round-trip verify
        back = apply_ips(orig, ips)
        status = "OK" if back == mod else "ROUND-TRIP FAIL"
        if back != mod: ok = False
        nrec = (len(ips) - 8)  # rough
        print(f"  {dst:44s} {len(ips):>7d} B   {status}")
    print("ALL VERIFIED" if ok else "FAILURES PRESENT")
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
