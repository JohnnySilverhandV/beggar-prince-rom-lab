"""Brute-force the record layout of the level-up table at ~0x40400.

Strategy: for every (start, stride, field_offset) combination, extract the column
and measure how well it matches the known exp sequence from the GameFAQs guide.
"""
import struct

SRC = r"E:/BaiduNetdiskDownload/xqgwz/xqgwz.md"
d = open(SRC, 'rb').read()

GUIDE = [50,152,232,370,470,580,710,880,920,1000,1240,1510,1950,
         2710,3580,4180,4920,5400,5640,5640,6320,6720,7330,7756]

def col(start, stride, foff, n, width=2):
    out=[]
    for k in range(n):
        o=start+stride*k+foff
        if o+width>len(d): break
        out.append(int.from_bytes(d[o:o+width],'big'))
    return out

def score(vals, guide):
    """longest common prefix match against guide (allowing one guide dup skip)"""
    best=0
    for shift_guide in range(0, len(guide)):
        c=0
        for i,v in enumerate(vals):
            gi=shift_guide+i
            if gi>=len(guide): break
            if v==guide[gi]: c+=1
            else: break
        best=max(best,c)
    return best

results=[]
for start in range(0x403C0, 0x40480):
    for stride in (4,5,6,8,10,12):
        for foff in range(0, stride, 2):
            for n in (30,):
                v=col(start,stride,foff,n)
                s=score(v,GUIDE)
                if s>=6:
                    results.append((s,start,stride,foff,v[:12]))

results.sort(key=lambda x:(-x[0], x[1]))
print("=== best layouts (score = consecutive guide matches) ===")
for s,start,stride,foff,v in results[:15]:
    print(f"score={s:2d} start={start:06x} stride={stride} foff={foff}  vals={v}")

print()
print("=== full column dump for the best layout ===")
if results:
    s,start,stride,foff,v = results[0]
    vv=col(start,stride,foff,40)
    print(f"start={start:06x} stride={stride} foff={foff}")
    for i,x in enumerate(vv):
        g = GUIDE[i] if i<len(GUIDE) else None
        mark = '  <== guide' if g is not None and x==g else ''
        print(f"  idx{i:2d}  lv{i+2:2d}   {x:6d}{mark}")

print()
print("=== all three fields of that record, decoded ===")
s,start,stride,foff,v = results[0]
rec_start = start + foff  # where the matching field begins
base = rec_start - foff
for i in range(0, 32):
    o = base + stride*i
    if o+stride>len(d): break
    w=[int.from_bytes(d[o+j:o+j+2],'big') for j in range(0,stride,2)]
    print(f"  rec{i:2d} @{o:06x}  "+"  ".join(f"{x:6d}" for x in w))
