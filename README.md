# beggar-prince-rom-lab · 《新乞丐王子》MD 逆向改造工具箱

一套**跨游戏、零依赖**的老游戏 ROM 数值改造工具链，外加在《新乞丐王子》(Beggar Prince，台湾 C&E 1996，世嘉 MD) 上真实跑通的 9 个 IPS 补丁。

> **本仓库不包含、也不分发任何 ROM 文件**——只提供分析脚本、IPS 差量补丁（仅含改动字节）与反汇编证据。

> 📦 **补丁包下载 v1.0**：[Gitee Releases（国内直连，推荐）](https://gitee.com/johnny-silver-hand123/beggar-prince-rom-lab/releases) ｜ [GitHub Releases](https://github.com/JohnnySilverhandV/beggar-prince-rom-lab/releases)
>
> 🛠 **跨游戏工具箱**：[rom_toolkit/](rom_toolkit/) —— 探壳 / 数值表指纹定位 / 交叉引用 / 参数化补丁，支持 MD、SNES、GB、GBA、NES、SMS-GG
>
> 📖 **实战手册**：[rom_toolkit/README.md](rom_toolkit/README.md) —— 四步流程 + 新乞丐王子完整案例

## 源码仓库

| 平台 | 地址 |
|---|---|
| GitHub | https://github.com/JohnnySilverhandV/beggar-prince-rom-lab |
| Gitee（国内直连） | https://gitee.com/johnny-silver-hand123/beggar-prince-rom-lab |

---

## 🆕 更新日志

### v1.0 — 首发：9 个 IPS 补丁 + 跨游戏工具箱（2026-11-05）

- 升级表、武器档位表、魔法表、分摊系数表、怪物表全部定位并交叉验证
- 三个强度档（轻度 / 重度 / 极限）各出「仅成长」与「含攻击力」两版
- 魔法伤害系数改造：全屏秒杀（单体 ×200、六敌同屏 ×1000）
- 魔法必中改造：命中判定 3 字节，只影响玩家施法链路
- 顺手修掉原版埋的「武器断崖」——每把武器最后一档攻击力不升反降
- 沉淀 `rom_toolkit/`：四个脚本换任何老游戏都能用，demo 与实机补丁逐字节一致（232/232）

---

## ✨ 补丁清单

全部为 IPS 格式，**基于汉化版 ROM（MD5 `cda1c5fa4cd72c9188a228b11150440b`）制作**，文件长度保持 4,194,304 字节不变。

| IPS 文件 | 改动字节 | 内容 |
|---|---|---|
| `patch_A_mild_attack.ips` | 211 | ★ **日常推荐**：经验 ÷10 + HP/MP 提升 + 初始攻击 100 + 武器断崖修复 |
| `patch_mild_magic_nuke_alwayshit.ips` | 234 | ★ **最终版**：A 档攻击版 + 魔法全屏秒杀 + 必中 |
| `patch_A_mild.ips` | 168 | A 档仅成长（攻击力原样） |
| `patch_B_heavy.ips` | 169 | B 档重度：基本一仗一级 |
| `patch_B_heavy_attack.ips` | 213 | B 档 + 攻击力 |
| `patch_C_extreme.ips` | 171 | C 档极限：获得 1 点经验就升 1 级 |
| `patch_C_extreme_attack.ips` | 215 | C 档 + 攻击力 |
| `patch_attack_only.ips` | 44 | 只改攻击力，等级表一个字不动（对照组，用来单独验证攻击是否生效） |
| `patch_mild_magic_nuke.ips` | 231 | A 档攻击版 + 魔法伤害系数 ×200（不含必中） |

「改动字节」是补丁实际写入的字节数，不是文件大小——所以九个补丁全加起来也凑不出一个完整 ROM。

## 🚀 使用

### 打补丁

1. 自备你**合法持有**的原版 ROM，先校验：MD5 应为 `cda1c5fa4cd72c9188a228b11150440b`
2. 用任意 IPS 工具应用（网页工具 [ROM Patcher JS](https://www.marcrobledo.com/RomPatcher.js/)、Floating IPS、Lunar IPS 都可以）
3. 打完后文件仍为 4,194,304 字节，直接丢进模拟器跑

> ⚠️ 补丁基于汉化版制作，校验值不一致就会打偏。MD 模拟器推荐 Kega Fusion / Gens / BizHawk / RetroArch（Genesis Plus GX 核心），老 SRAM 存档可以沿用。

### 验证生效

进游戏打一场，看 HP/MP 跳变与升级提示。想更直观就在模拟器里开 Action Replay 观察内存：`FF02EE`（等级）、`FF02F4`（当前 HP）会直接跟着变。

### 自己改别的游戏

```bash
python rom_toolkit/rom_probe.py <rom>                      # 1. 认平台、看熵分布
python rom_toolkit/find_table.py <rom> --seq 370,470,580   # 2. 拿攻略数值当指纹定位
python rom_toolkit/xref.py <rom> ref 0x4043E               # 3. 谁在读这张表（需 capstone）
python rom_toolkit/patch_table.py plan.json --dry-run      # 4. 先看效果再落盘
```

四步的完整说明与范例在 [rom_toolkit/README.md](rom_toolkit/README.md)。

## 🛠 技术要点

### 方法论：四步撬开老游戏

1. **拿攻略数值当指纹** —— 逐级经验值序列独一无二，比字符串搜索可靠得多
2. **在文件里反查定位** —— 暴力枚举 起始偏移 × 步长 × 字段编码
3. **反汇编确认语义** —— capstone M68K 看清「谁在读这张表、怎么用」
4. **查引用范围确认安全** —— 改之前先证明它不牵连别的系统（伤害例程常常敌我共用）

### 关键地址速查（新乞丐王子）

| 表 / 例程 | 地址 | 说明 |
|---|---|---|
| 升级表 | `0x4043A` | 28 级 × 6B：最大 HP / 最大 MP / 升级所需经验 |
| 武器档位表 | `0x3FEE0` | 24 档 × 10B，+2 为 word 攻击力；原版末档有断崖 bug |
| 武器档位计数 | `0x3D590` | `[0,4,5,4,3,4,4]` → 6 把武器共 24 档 |
| 魔法表 | `0x401FA` | 36 条 × 16B：威力 / 系数 / 命中 / 元素 / 处理例程指针 |
| 分摊系数表 | `0x3D578` | 6 × f32BE，全 ROM 仅 `$D1640` 一条指令引用 → 魔法秒杀的开关 |
| 怪物表 | `0x40C00` | 40 条 × 38B |
| 魔法必中 | `$0D1212`、`$0D126C` | 两处 `d4` 赋值点：`78 63` / `38 00` 统一改成 `78 7F`（moveq #$7F,d4），共 3 字节 |

### 两条容易踩的坑

- **没有独立的「攻击力」字段**：攻击力来自武器档位表，改攻击必须改表，不能去搜一个不存在的属性
- **浮点溢出会把扣血变加血**：`$E4DA4` 的 float→int 溢出返回 `0x80000000`，再 `sub.l` 就成了加血。放大系数前先算最坏情况（安全区约 2²⁴ ≈ 1677 万，×200 最坏约 940 万，安全）

反汇编证据片段都在 [evidence/](evidence/)，完整分析过程见 [docs/](docs/)。

## ⚖️ 合规声明

- 本项目为**个人对单机离线游戏的本地修改研究**，不涉及联网对战、不绕过任何付费
- 仓库不含 ROM / 游戏资源本体；IPS 补丁只存与原版的差量字节，需自备合法持有的原版才能使用
- 请支持正版；《新乞丐王子》商标与游戏版权归原权利人（C&E / Super Fighter Team）所有

## 📄 License

代码部分：MIT © 2026 JohnnySilverhandV（见 [LICENSE](LICENSE)）
