"""Beggar Prince (新乞丐王子) MD ROM patcher.

Two independent data blocks are patched.

(1) LEVEL-UP TABLE   (verified against the game's own code)
    record for level L  ->  0x4043A + (L-1)*6  =  [maxHP][maxMP][expToNextLevel]
    L = 1 .. 28      (level 28's exp value is the 9999 sentinel)
    code base for exp  : 0x40438 + L*6      (routine $0D4960)
    code base for HP   : 0x4043A + (L-1)*6  (routine $0D1C74) -> $FF02F4
    code base for MP   : 0x4043C + (L-1)*6  (routine $0D1CE0) -> $FF02F6
    Also patch the hard-coded 9999 fallback used when level > 28.

(2) WEAPON TIER TABLE = the player's ATTACK POWER
    attack tier = $0D1D4A(weaponId, level)
        base = sum($3D590[0 .. weaponId-1])          (start index of that weapon)
        then walk forward while $3FEE0[tier].level < currentLevel
        (count guarded by $3D590[weaponId], so exactly `count` tiers per weapon)
    $3FEE0 + tier*10 ... one tier, 10 bytes:
        +0  byte  required level
        +2  word  ATTACK POWER          <-- what we patch
        +4  byte  misc / extra
        +5  byte  element  (matched vs the monster's element -> x1.2 damage)
        +6  byte  hit rate (75/80/85/90 %)
    Consumed by the battle damage routine $0D0EBE, which also spends STAMINA
    ($FF038A, max 100, up to 20 per swing -> 5 swings per round).
    $3FEE0 is referenced ONLY from $0D1D4A and $0D0EBE -> only the player's
    physical attack, enemies use a different path.

    $3D590 = [0,4,5,4,3,4,4]  ->  exactly 6 weapons (Slingshot / Spear / Battle Axe
    / Poisonous Arrow / Treasured Sword / Holy Staff) and 24 tiers, the groups tile
    the table with no gap and no overlap.

    NOTE: in the original data the LAST tier row of every weapon group has a much
    lower attack value (30/40/50->25, 120/140/180/200->85, ...).  It is reachable,
    so the unpatched game actually *loses* attack power at those levels.  We keep
    the curve monotonic instead.
"""
import os, struct

SRC = os.environ.get("ROM", "xqgwz.md")   # 原版 ROM 路径，用环境变量 ROM 覆盖
OUTDIR = os.environ.get("OUT", "out")   # 成品输出目录
os.makedirs(OUTDIR, exist_ok=True)

TAB_BASE = 0x4043A        # HP(L) at +0, MP(L) at +2, EXP(L) at +4
NLEVELS  = 28
EXP_FALLBACK_SITES = (0xD2160, 0xD497A, 0xD49FA)   # `3? 3C 27 0F`  move.w #$270f,dx

ATK_BASE = 0x3FEE0        # weapon tier table, 10 bytes per tier
ATK_STR  = 10
ATK_OFF  = 2              # word: attack power
TIERCNT_ADDR = 0x3D590    # int8 tier-count per weapon id

d0 = open(SRC, 'rb').read()

# ---------------------------------------------------------------- readers
def read_table(buf):
    hp, mp, exp = [], [], []
    for i in range(NLEVELS):
        o = TAB_BASE + 6*i
        a, b, c = struct.unpack('>3H', buf[o:o+6])
        hp.append(a); mp.append(b); exp.append(c)
    return hp, mp, exp

def read_atk(buf):
    lvl, atk, hit = [], [], []
    for k in range(24):
        o = ATK_BASE + ATK_STR*k
        lvl.append(buf[o])
        atk.append(struct.unpack('>H', buf[o+2:o+4])[0])
        hit.append(buf[o+6])
    return lvl, atk, hit

def tier_of(buf, weapon_id, level):
    """Exact replica of routine $0D1D4A."""
    if weapon_id == 0:
        return 0
    base = 0
    for i in range(weapon_id):
        base += buf[TIERCNT_ADDR + i]
    cnt = buf[TIERCNT_ADDR + weapon_id]
    d3, d2 = base, 0
    while d2 < cnt - 1:
        if buf[ATK_BASE + ATK_STR*d3] < level:
            d2 += 1; d3 += 1
        else:
            break
    return min(d3, 0x17)

NWEAPONS = 6              # $3D590[0..6] = [0,4,5,4,3,4,4]; byte 7 belongs to the next table

def groups(buf):
    out, base = [], 0
    for w in range(1, NWEAPONS + 1):
        c = buf[TIERCNT_ADDR + w]
        out.append((w, base, c))
        base += c
    assert base == 24, base
    return out

orig_hp, orig_mp, orig_exp = read_table(d0)
orig_lvl, orig_atk, orig_hit = read_atk(d0)
GRP = groups(d0)

print("=== ORIGINAL level table ===")
for i in range(NLEVELS):
    print(f"  Lv{i+1:2d}   HP {orig_hp[i]:5d}   MP {orig_mp[i]:5d}   EXP {orig_exp[i]:5d}")

print("\n=== weapons / attack tiers (original) ===")
for w, base, cnt in GRP:
    print(f"  weapon{w}: tiers {base}..{base+cnt-1}   "
          + "  ".join(f"[{orig_lvl[base+j]}]Lv{orig_lvl[base+j]}:{orig_atk[base+j]}" for j in range(cnt)))

# ---------------------------------------------------------------- attack curve
def reshape_atk(atk_fn):
    """Scale each weapon group, and keep every group strictly increasing."""
    new = [0]*24
    for w, base, cnt in GRP:
        for j in range(cnt):
            new[base+j] = max(1, min(65535, int(atk_fn(orig_atk[base+j], base+j))))
        for j in range(1, cnt):
            if new[base+j] <= new[base+j-1]:
                new[base+j] = min(65535, new[base+j-1] + max(2, round(new[base+j-1]*0.08)))
    return new

# ---------------------------------------------------------------- build
def build(name, note, exp_fn, hp_fn, mp_fn, atk_fn, exp_fallback,
          patch_level=True, patch_atk=True):
    buf = bytearray(d0)

    if patch_level:
        hp, mp, exp = [], [], []
        for i in range(NLEVELS):
            L = i + 1
            e = max(1, min(9999, int(exp_fn(orig_exp[i], L))))
            h = max(1, min(9999, int(hp_fn(orig_hp[i], L))))
            m = max(1, min(9999, int(mp_fn(orig_mp[i], L))))
            exp.append(e); hp.append(h); mp.append(m)
            struct.pack_into('>3H', buf, TAB_BASE + 6*i, h, m, e)
        for off in EXP_FALLBACK_SITES:
            assert buf[off:off+2] in (b'0\x3c', b'6\x3c'), f"unexpected opcode at {off:#x}"
            assert buf[off+2:off+4] == b'\x27\x0f', f"expected 0x270f at {off+2:#x}"
            struct.pack_into('>H', buf, off+2, max(1, min(9999, exp_fallback)))

    new_atk = list(orig_atk)
    if patch_atk:
        new_atk = reshape_atk(atk_fn)
        for k in range(24):
            struct.pack_into('>H', buf, ATK_BASE + ATK_STR*k + ATK_OFF, new_atk[k])

    path = os.path.join(OUTDIR, name)
    open(path, 'wb').write(buf)

    print(f"\n=== {name} ===  ({note})")
    if patch_atk:
        print("   tier  lvlreq   ATK old -> new")
        for k in range(24):
            print(f"   {k:3d}    {orig_lvl[k]:3d}    {orig_atk[k]:5d} -> {new_atk[k]:5d}")
        print("   effective attack by level (starting weapon, weaponId=1):")
        prev = None
        for L in range(1, NLEVELS+1):
            t = tier_of(buf, 1, L)
            a = struct.unpack('>H', buf[ATK_BASE+ATK_STR*t+ATK_OFF:ATK_BASE+ATK_STR*t+ATK_OFF+2])[0]
            if a != prev:
                print(f"      Lv{L:2d}+  ATK {a}")
                prev = a
    if patch_level:
        for i in range(NLEVELS):
            print(f"  Lv{i+1:2d}   HP {orig_hp[i]:5d}->{hp[i]:5d}   "
                  f"MP {orig_mp[i]:5d}->{mp[i]:5d}   EXP {orig_exp[i]:5d}->{exp[i]:5d}")
    return path

# ---------------------------------------------------------------- build set
# every curve is anchored so the starting tier (30) becomes 100
ATK_A = lambda a, k: round(a * 1.5) + 55
ATK_B = lambda a, k: round(a * 2.0) + 40
ATK_C = lambda a, k: round(a * 3.0) + 10

build("xqgwz_强化A_轻度_攻击版.bin",
      "经验÷10 | HP×1.5+200 | MP×1.5+100 | 攻击×1.5+55 (初始100)",
      lambda e, L: round(e/10),
      lambda h, L: round(h*1.5)+200,
      lambda m, L: round(m*1.5)+100,
      ATK_A, exp_fallback=round(9999/10))

build("xqgwz_强化B_重度_攻击版.bin",
      "经验÷50 | HP×2+500 | MP×2+300 | 攻击×2+40 (初始100)",
      lambda e, L: round(e/50),
      lambda h, L: round(h*2)+500,
      lambda m, L: round(m*2)+300,
      ATK_B, exp_fallback=round(9999/50))

build("xqgwz_强化C_极限_攻击版.bin",
      "经验一律=1 | HP=1200+(L-1)*320 | MP=600+(L-1)*160 | 攻击×3+10 (初始100)",
      lambda e, L: 1,
      lambda h, L: min(9999, 1200 + (L-1)*320),
      lambda m, L: min(9999, 600 + (L-1)*160),
      ATK_C, exp_fallback=1)

build("xqgwz_仅攻击力_其余原样.bin",
      "只改攻击力 ×2+40 (初始100)，等级表/经验完全保持原版",
      None, None, None,
      ATK_B, exp_fallback=9999,
      patch_level=False)

print("\nDone. Output dir:", OUTDIR)
