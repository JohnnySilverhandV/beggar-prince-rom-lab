"""Locate the level-up experience table inside the ROM by searching for the
known numeric sequence (from the GameFAQs Level Up Guide)."""
import struct, sys

SRC = r"E:/BaiduNetdiskDownload/xqgwz/xqgwz.md"
d = open(SRC, 'rb').read()
N = len(d)

# Required exp per level (level 2..25) from the English guide
EXP = [50,152,232,370,470,580,710,880,920,1000,1240,1510,1950,
       2710,3580,4180,4920,5400,5640,5640,6320,6720,7330,7756]

def find_all(needle, limit=200):
    out=[]
    i=0
    while True:
        j=d.find(needle,i)
        if j<0: break
        out.append(j)
        i=j+1
        if len(out)>=limit: break
    return out

print("=== step 1: occurrences of each exp value as 2-byte BE ===")
pos={}
for v in EXP:
    b=struct.pack('>H', v)
    hits=find_all(b, 60)
    pos[v]=hits
    print(f"  {v:6d} ({b.hex(' ')})  hits={len(hits):3d}  {[hex(h) for h in hits[:10]]}")

print()
print("=== step 2: look for the pair (2710,3580) i.e. 0A96 0DFC adjacent ===")
for cand in [struct.pack('>HH',2710,3580), struct.pack('>HH',7330,7756),
             struct.pack('>HH',1950,2710), struct.pack('>HH',4180,4920)]:
    print(f"  {cand.hex(' ')} -> {[hex(h) for h in find_all(cand)]}")

print()
print("=== step 3: stride analysis - do the values appear in a regular table? ===")
# For each candidate base offset found from a 3-value match, check stride
best=[]
for start_idx in range(len(EXP)-3):
    seq=EXP[start_idx:start_idx+4]
    pat=struct.pack('>4H', *seq)
    for off in find_all(pat):
        best.append((off, start_idx, 2))
print("  4-value 2-byte BE matches:", [(hex(o), i) for o,i,w in best])

print()
print("=== step 4: try 4-byte BE storage ===")
for start_idx in range(len(EXP)-3):
    seq=EXP[start_idx:start_idx+4]
    pat=struct.pack('>4I', *seq)
    for off in find_all(pat):
        print(f"  4-byte seq at {hex(off)} starting value index {start_idx}")

print()
print("=== step 5: try 3-byte BE storage ===")
def find3(seq):
    pat=b''.join(v.to_bytes(3,'big') for v in seq)
    return find_all(pat)
for start_idx in range(len(EXP)-3):
    seq=EXP[start_idx:start_idx+4]
    for off in find3(seq):
        print(f"  3-byte seq at {hex(off)} starting value index {start_idx}")

print()
print("=== step 6: single value 7756 (0x1E4C) - all hits scanned for neighbours ===")
for off in find_all(b'\x1e\x4c'):
    ctx=d[max(0,off-8):off+10]
    print(f"  {off:07x}  {ctx.hex(' ')}")
