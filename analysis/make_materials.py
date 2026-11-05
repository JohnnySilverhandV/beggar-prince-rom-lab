# -*- coding: utf-8 -*-
"""生成《新乞丐王子》R0M 逆向视频物料图（全部数据从 ROM 真实提取）。
输出到桌面文件夹：新乞丐王子_视频物料/
依赖：PIL（已装）。无任何第三方绘图库。
"""
import os
import struct, os
from PIL import Image, ImageDraw, ImageFont

ROM = os.environ.get("ROM", "xqgwz.md")   # 原版 ROM 路径，用环境变量 ROM 覆盖
OUT = os.environ.get("OUT", "新乞丐王子_视频物料")   # 输出目录
os.makedirs(OUT, exist_ok=True)

d = open(ROM, "rb").read()
def w(o):  return struct.unpack(">H", d[o:o+2])[0]
def f32(o): return struct.unpack(">f", d[o:o+4])[0]

# ---------- 提取真实数据 ----------
base = 0x4043A
levels = []
for i in range(28):
    o = base + i*6
    levels.append((i+1, w(o), w(o+2), w(o+4)))   # (lv, HP, MP, expToNext)
exp_seq   = [r[3] for r in levels]
hp_seq    = [r[1] for r in levels]
mp_seq    = [r[2] for r in levels]

wb = 0x3FEE0
counts = [0,4,5,4,3,4,4]
weapon_names = ["拳脚","弹弓","长矛","战斧","毒箭","宝剑","圣杖"]
atk = [w(wb+i*10+2) for i in range(24)]
weapons = []
idx = 0
for c in counts:
    weapons.append(atk[idx:idx+c]); idx += c
# 每种武器最后一档（断崖）
cliffs = [(wi, len(ws)-1) for wi, ws in enumerate(weapons) if len(ws) > 1 and ws[-1] < max(ws)]

coeff = [f32(0x3D578 + i*4) for i in range(6)]

# ---------- 主题 ----------
BG=(13,17,23); PANEL=(22,27,34); ROWA=(30,36,44); LINE=(48,54,61)
RED=(248,81,73); BLUE=(88,166,255); GREEN=(63,185,80)
YEL=(240,180,40); PURPLE=(163,113,247); CYAN=(56,200,210)
WHITE=(230,237,243); DIM=(139,148,158)
ACCENT=YEL

_F={}
def font(sz, bold=False):
    k=(sz,bold)
    if k in _F: return _F[k]
    for p in ["C:/Windows/Fonts/msyhbd.ttc","C:/Windows/Fonts/msyh.ttc",
              "C:/Windows/Fonts/simhei.ttf","C:/Windows/Fonts/simsun.ttc"]:
        try: _F[k]=ImageFont.truetype(p,sz); return _F[k]
        except: pass
    _F[k]=ImageFont.load_default(); return _F[k]

def txt(draw,xy,s,size,color,bold=False,anchor="la"):
    draw.text(xy,s,font=font(size,bold),fill=color,anchor=anchor)

def canvas(W=1920,H=1080):
    img=Image.new("RGB",(W,H),BG); return img,ImageDraw.Draw(img)

def panel(draw,box,fill=PANEL,outline=LINE,width=2,radius=16):
    draw.rounded_rectangle(box,radius=radius,fill=fill,outline=outline,width=width)

def header(draw,title,sub,accent=ACCENT):
    draw.rectangle([60,60,72,118],fill=accent)
    txt(draw,(92,58),title,50,WHITE,bold=True)
    if sub: txt(draw,(94,124),sub,24,DIM)
    draw.line([(60,158),(1860,158)],fill=LINE,width=2)

def arrow(draw,x0,y0,x1,y1,color=WHITE,w=4):
    draw.line([(x0,y0),(x1,y1)],fill=color,width=w)
    # arrow head
    import math
    ang=math.atan2(y1-y0,x1-x0); L=14
    for da in (2.6, -2.6):
        a=ang+da
        draw.line([(x1,y1),(x1-L*math.cos(a),y1-L*math.sin(a))],fill=color,width=w)

# ============================================================
# 图1：升级经验曲线
# ============================================================
img,dr=canvas(); header(dr,"升级所需经验曲线（每级 → 下一级）",
    "数据来源：ROM 升级表 @0x4043A · 由 WB 提取", accent=YEL)
box=(150,230,1800,940)
x0,y0,x1,y1=box
ymax=11000
for i in range(5):
    yy=y1-((y1-y0)*i/4)
    dr.line([(x0,yy),(x1,yy)],fill=LINE,width=1)
    txt(dr,(x0-14,yy),str(int(ymax*i/4)),22,DIM,anchor="ra")
n=len(exp_seq)
pts=[]
for i,v in enumerate(exp_seq):
    px=x0+(x1-x0)*i/(n-1); py=y1-(y1-y0)*(v/ymax); pts.append((px,py))
dr.line(pts,fill=YEL,width=4,joint="curve")
for i,(px,py) in enumerate(pts):
    dr.ellipse([px-7,py-7,px+7,py+7],fill=YEL)
    if i in (0,8,27):
        txt(dr,(px,py-28),str(exp_seq[i]),22,WHITE,bold=True,anchor="ma")
# x 轴标签
for i in range(0,n,3):
    txt(dr,(x0+(x1-x0)*i/(n-1),y1+14),str(i+1),20,DIM,anchor="ma")
txt(dr,(x0+(x1-x0)*8/(n-1),pts[8][1]+34),"Lv9 实值720（攻略误记920）",22,RED,bold=True,anchor="ma")
txt(dr,(930,980),"等级",26,DIM,anchor="ma")
img.save(f"{OUT}/01_升级经验曲线.png")

# ============================================================
# 图2：HP / MP 成长曲线（双轴）
# ============================================================
img,dr=canvas(); header(dr,"生命 / 魔法 成长曲线（满级 6300 HP · 2760 MP）",
    "数据来源：ROM 升级表 @0x4043A · 由 WB 提取", accent=RED)
box=(150,230,1800,930)
x0,y0,x1,y1=box
hp_max=7000; mp_max=3000
for i in range(5):
    yy=y1-((y1-y0)*i/4)
    dr.line([(x0,yy),(x1,yy)],fill=LINE,width=1)
    txt(dr,(x0-14,yy),str(int(hp_max*i/4)),22,RED,anchor="ra")
    txt(dr,(x1+14,yy),str(int(mp_max*i/4)),22,BLUE,anchor="la")
def P(i,v,vm):
    return (x0+(x1-x0)*i/(n-1), y1-(y1-y0)*(v/vm))
hp_pts=[P(i,hp_seq[i],hp_max) for i in range(n)]
mp_pts=[P(i,mp_seq[i],mp_max) for i in range(n)]
dr.line(hp_pts,fill=RED,width=4,joint="curve")
dr.line(mp_pts,fill=BLUE,width=4,joint="curve")
for p in hp_pts: dr.ellipse([p[0]-6,p[1]-6,p[0]+6,p[1]+6],fill=RED)
for p in mp_pts: dr.ellipse([p[0]-6,p[1]-6,p[0]+6,p[1]+6],fill=BLUE)
for i in (0,27):
    txt(dr,(hp_pts[i][0],hp_pts[i][1]-26),str(hp_seq[i]),22,RED,bold=True,anchor="ma")
    txt(dr,(mp_pts[i][0],mp_pts[i][1]+30),str(mp_seq[i]),22,BLUE,bold=True,anchor="ma")
for i in range(0,n,3):
    txt(dr,(x0+(x1-x0)*i/(n-1),y1+14),str(i+1),20,DIM,anchor="ma")
txt(dr,(x0+40,y0+10),"HP（红）",24,RED,bold=True)
txt(dr,(x0+160,y0+10),"MP（蓝）",24,BLUE,bold=True)
txt(dr,(930,975),"等级",26,DIM,anchor="ma")
img.save(f"{OUT}/02_HP_MP成长曲线.png")

# ============================================================
# 图3：武器档位表（原版断崖）
# ============================================================
img,dr=canvas(); header(dr,"武器攻击力档位表（原版末档断崖）",
    "数据来源：武器分级表 @0x3FEE0 · 由 WB 提取并理顺", accent=PURPLE)
# 表格
hx=120; hy=250; colw=[150,300,160,160,160,160,160]; rowh=78
maxc=max(len(w) for w in weapons)
# 表头
txt(dr,(hx+colw[0]/2,hy+rowh/2),"武器",28,WHITE,bold=True,anchor="mm")
cx=hx+colw[0]
for j in range(maxc):
    txt(dr,(cx+colw[1+j]/2,hy+rowh/2),f"档{j+1}",26,DIM,bold=True,anchor="mm")
    cx+=colw[1+j]
yy=hy+rowh
for wi,ws in enumerate(weapons):
    if wi==0: continue
    fillc = ROWA if (wi%2==0) else PANEL
    dr.rectangle([hx,yy,hx+sum(colw),yy+rowh],fill=fillc)
    txt(dr,(hx+colw[0]/2,yy+rowh/2),weapon_names[wi],26,WHITE,bold=True,anchor="mm")
    cx=hx+colw[0]
    for j in range(maxc):
        val = ws[j] if j < len(ws) else ""
        is_cliff = (wi,j) in cliffs
        col = RED if is_cliff else WHITE
        txt(dr,(cx+colw[1+j]/2,yy+rowh/2),str(val),26,col,bold=is_cliff,anchor="mm")
        cx+=colw[1+j]
    yy+=rowh
dr.rectangle([hx,hy,hx+sum(colw),yy],outline=LINE,width=2)
txt(dr,(120,yy+30),"红色 = 原版每把武器最后一档反而更低（开发手滑的断崖）。WB 已将其理顺为单调递增，升级不再掉攻击。",24,DIM)
img.save(f"{OUT}/03_武器档位表.png")

# ============================================================
# 图4：魔法分摊系数
# ============================================================
img,dr=canvas(); header(dr,"魔法伤害 · 敌数分摊系数",
    "数据来源：分摊系数表 @0x3D578 · 全 ROM 唯一引用点 @0xD1640", accent=CYAN)
box=(150,250,1700,860)
x0,y0,x1,y1=box
ymax=1.15
labels=["1敌","2敌","3敌","4敌","5敌","6敌"]
for i in range(5):
    yy=y1-((y1-y0)*i/4)
    dr.line([(x0,yy),(x1,yy)],fill=LINE,width=1)
    txt(dr,(x0-14,yy),f"{ymax*i/4:.2f}",22,DIM,anchor="ra")
n=len(coeff); bw=(x1-x0)/n*0.55
for i,v in enumerate(coeff):
    cx=x0+(x1-x0)*(i+0.5)/n
    bh=(y1-y0)*(v/ymax); top=y1-bh
    col=[CYAN,BLUE,GREEN,YEL,PURPLE,RED][i]
    dr.rounded_rectangle([cx-bw/2,top,cx+bw/2,y1],radius=8,fill=col)
    txt(dr,(cx,top-32),f"{v:.2f}",26,WHITE,bold=True,anchor="ma")
    txt(dr,(cx,y1+14),labels[i],26,DIM,anchor="ma")
    # 修改标注
txt(dr,(1650,300),"WB 改为 200",30,RED,bold=True,anchor="la")
txt(dr,(1650,345),"→ 单体 ×200",26,WHITE,anchor="la")
txt(dr,(1650,385),"→ 六敌同屏 ×1000",26,WHITE,anchor="la")
txt(dr,(1650,430),"唯一引用点 →",24,DIM,anchor="la")
txt(dr,(1650,462),"只动魔法伤害",24,GREEN,bold=True,anchor="la")
txt(dr,(930,905),"敌人数量",26,DIM,anchor="ma")
img.save(f"{OUT}/04_魔法分摊系数.png")

# ============================================================
# 图5：魔法伤害公式链路
# ============================================================
img,dr=canvas(); header(dr,"魔法伤害公式链路（WB 反汇编 $0D128E）",
    "一条伤害魔法出口，9 步相乘 → 扣敌 HP", accent=GREEN)
stages=[
    ("数存活敌人","遍历 6 敌位"),
    ("base = power × 等级²","复合基础值"),
    ("× 随机 (4~60)+70","浮动伤害"),
    ("× 魔抗折减","按怪物魔抗"),
    ("× 分摊系数","按敌数 1.0→0.2"),
    ("× 元素相性","≤ ×2.5625"),
    ("float → int","取整"),
    ("× 命中标志","miss 则 0"),
    ("敌 HP -= dmg","扣血结算"),
]
cw,ch=520,150; gx,gy=40,40
sx,sy=150,250
grid_cols=3
for i,(t,s) in enumerate(stages):
    r=i//grid_cols; c=i%grid_cols
    bx=sx+c*(cw+gx); by=sy+r*(ch+gy)
    col=[GREEN,BLUE,CYAN,YEL,PURPLE,RED,WHITE,DIM,RED][i]
    panel(dr,(bx,by,bx+cw,by+ch),fill=PANEL,outline=col,width=3)
    txt(dr,(bx+cw/2,by+50),t,30,WHITE,bold=True,anchor="mm")
    txt(dr,(bx+cw/2,by+100),s,22,DIM,anchor="mm")
    # arrow
    rows=(len(stages)+grid_cols-1)//grid_cols
    if c<grid_cols-1:
        arrow(dr,bx+cw+4,by+ch/2,bx+cw+gx-4,by+ch/2,color=col,w=3)
    elif c==grid_cols-1 and r<rows-1:
        arrow(dr,bx+cw/2,by+ch+4,bx+cw/2,by+ch+gy-4,color=col,w=3)
img.save(f"{OUT}/05_魔法伤害公式.png")

# ============================================================
# 图6：四步撬开老游戏
# ============================================================
img,dr=canvas(); header(dr,"四步撬开任意老游戏（WB 方法论）",
    "攻略数值 → 反查定位 → 反汇编确认 → 查引用范围", accent=YEL)
cards=[
    ("① 攻略数值当指纹","拿攻略里的 exp / 属性表当搜索指纹，\n游戏必把它原样存在 ROM 里。"),
    ("② 文件内反查定位","暴力枚举 偏移 × 步长 × 编码，\n让 WB 把表精确命中。"),
    ("③ 反汇编确认语义","用 capstone(M68K) 读真实查表例程，\n确认这表就是升级/攻击。"),
    ("④ 查引用范围确认安全","xref 找唯一引用点，\n确认改动不会牵连别的系统。"),
]
cw,ch=420,460; gx=40; sx=120; sy=280
cols=[YEL,BLUE,GREEN,PURPLE]
for i,(t,b) in enumerate(cards):
    bx=sx+i*(cw+gx)
    panel(dr,(bx,sy,bx+cw,sy+ch),fill=PANEL,outline=cols[i],width=3)
    txt(dr,(bx+cw/2,sy+70),t,30,WHITE,bold=True,anchor="mm")
    # 编号大圆
    dr.ellipse([bx+cw/2-40,sy+120,bx+cw/2+40,sy+200],outline=cols[i],width=4)
    txt(dr,(bx+cw/2,sy+160),str(i+1),46,cols[i],bold=True,anchor="mm")
    for j,line in enumerate(b.split("\n")):
        txt(dr,(bx+cw/2,sy+270+j*46),line,24,DIM,anchor="mm")
    if i<3:
        arrow(dr,bx+cw+4,sy+ch/2,bx+cw+gx-4,sy+ch/2,color=cols[i],w=4)
img.save(f"{OUT}/06_四步撬开老游戏.png")

# ============================================================
# 图7：原版里的好设计
# ============================================================
img,dr=canvas(); header(dr,"原版里的好设计（WB 逆向时学到的）",
    "30 年前的国产 RPG，藏着不少聪明做法", accent=PURPLE)
cards=[
    ("群攻平衡 · 分摊系数","敌人越多每只分得越少（1.0→0.2），\n总伤恒定，避免 AOE 过强。\n且独立成表、单点引用 = 好模块化。"),
    ("武器分级替代攻击属性","攻击力跟着武器 + 等级走，\n省掉一个独立攻击属性槽，\nROM 资源极度紧凑。"),
    ("魔法按 id 分派","id<29 伤害 / id≥29 治疗辅助，\n一条 cmpi 指令搞定，\n易扩展、好维护。"),
    ("元素相性系统","≤ ×2.5625 倍率，\n石头剪刀布式克制，\n战斗有策略深度。"),
]
cw,ch=820,320; gx,gy=40,40; sx=120; sy=250
cols=[CYAN,BLUE,GREEN,YEL]
for i,(t,b) in enumerate(cards):
    r=i//2; c=i%2
    bx=sx+c*(cw+gx); by=sy+r*(ch+gy)
    panel(dr,(bx,by,bx+cw,by+ch),fill=PANEL,outline=cols[i],width=3)
    dr.rectangle([bx,by,bx+10,by+ch],fill=cols[i])
    txt(dr,(bx+40,by+50),t,32,WHITE,bold=True,anchor="la")
    for j,line in enumerate(b.split("\n")):
        txt(dr,(bx+40,by+120+j*44),line,24,DIM,anchor="la")
txt(dr,(120,sy+2*(ch+gy)-10),"唯一败笔：武器末档断崖（开发手滑），WB 已修。其余设计值得点赞。",24,RED,bold=True)
img.save(f"{OUT}/07_游戏设计亮点.png")

print("DONE ->", OUT)
print("levels:",levels[0],levels[-1])
print("exp:",exp_seq[:10])
print("weapons:",weapons)
print("cliffs:",cliffs)
print("coeff:",coeff)
