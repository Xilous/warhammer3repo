# WH3 autoresolver: unit stat construction and modifier system

Source: Ghidra quick-decompile (no whole-program analysis) in `C:\Users\jaymi\tools\ghidra_quick\decomp13\` (simulator), `decomp16\` (stat-block fillers, added in revision 2) and `decomp14\` (duel core, cross-checked against `re/analysis/duel_math.md`).
Caveat for everything below: parameter lists at call sites are unreliable (args dropped/shifted, `in_stack_*`), but struct offsets, constants and control flow are trustworthy. Confidence tags: [H]/[M]/[L].

## Summary

1. The 0x17c combat-stat block (sim-unit+0x28) is built by `FUN_142e38518`: default ctor `FUN_142e05974`, then `FUN_142e6836c` fills it from the 0x6b0 game-unit copy (`FUN_141c46e58`) and its DB record aggregate `db = *(*(unit+0)+0x500)`, via sub-fillers `FUN_142e45944` (entity: mass/speed/radius/size), `FUN_142e455f0` (missile weapon block, primary at +0x28 and secondary at +0x6c), `FUN_142e45dc0` (artillery variant summing engine weapons), `FUN_142e459e4` (melee/leadership stats from the unit attribute array), `FUN_142e458d4` (crew divisor / frontage), `FUN_143019990` (ammo) and `FUN_142e2dda0` (ability-phase stat multipliers and HP regen).
2. Resolved stat fields now cover +0x0c..+0x6c, +0xbc..+0x11c, +0x128..+0x17b; the unit attribute array at `unit+0x48` (12-byte stride from +0x68: base, modifier, floor) is read by index; 0x18 leadership, 0x16 missile block, 0x19 reload, 0x25/0x26 melee/missile CP are certain, 0x10/0x14 melee attack/defence and 9 charge bonus are inferred from use.
3. `FUN_142ea0a40` builds an alliance: army-sims (0x30) + sim-units (0x2a8) for every army and reinforcement army, then `FUN_142f12fc0` applies per-class modifier entries to each unit (`FUN_142f1147c`), processes special abilities (`FUN_142ebc994`), and scales ammo.
4. Modifier pipeline: `FUN_142ee172c` scores autoresolver_battle_types rows against the setup; `FUN_142ee406c` walks the lookup rows for that battle type, filters by player_type (`FUN_142f016ac`), and `FUN_142ebfc7c` writes group_to_modifiers values into a 0x20-byte per-side block of 20 per-unit-class 0x58 entries. 10 modifier kinds are decoded; 6 of them form the kps vector copied to sim-unit +0x248..+0x25c.
5. `FUN_142ecad64` returns either `max(1 + sum(multipliers), 0.01)` or `sum(additions)`; the caller applies `kps * mult + add`, clamped at 0.
6. Special-ability buffs/debuffs modify melee/missile multipliers multiplicatively in `FUN_142ec0ba4` (`(m+1)*(1/(debuff_avg+1))*(buff_avg+1)-1`).
7. Combat potential per unit = `(attr#0x25, attr#0x26)` (= melee_cp / missile_cp) + ability CP, scaled by hp ratio and a cost-record adjustment, then `usage_group.multiplier * cp + usage_group.additive_mod` (`FUN_142ef5e24`, table at db+0xba60).
8. Campaign variables live in the "engine"/db object at `engine + 0x18cd4 + 4*index` (index as in `re/ar_indices.json`).

## Stat block field table (sim-unit+0x28, size 0x17c; copied by FUN_142e05b08)

Notation: `unit` = 0x6b0 game-unit copy (`*(sim-unit+0x10)`), `urec` = `*(unit+0)` (unit object), `db` = `*(urec+0x500)` (DB record aggregate).
`attr#i` = `FUN_141480a68(unit+0x48, i)` = `max(round(f[0x68+12i] + f[0x6c+12i]), round(f[0x70+12i]))` (base + modifier, floored by the third value); `attrF#i` = the same triple read unrounded as float (`max(base+mod, floor)`); `battr#i` = boolean attribute `FUN_14146ff40(unit+0x48, i)` (i < 0x5a; bitsets at +0x28/+0x38/+0x48/+0x58 with an override set at +0x20).
`W` = primary missile weapon record (`**(FUN_142e59b20(unit,1,0)+0x28)`), `P = *(W+0x40)` projectile record, `Q = *(W+0xe8)`, `mw = *(db+0x140)` melee weapon record, `E` = entity record (see FUN_142e45944), `T(i)` = multiplier from `FUN_142e44e60(ctx, i, &unit+0x5c0)` (record with `+0x1c == i` and `*(+0x20)+8 == *(unit+0x5c0)`, value `+0x18`, default 1.0; NOT the difficulty handicap: that table has no battle-stat effects).

| Offset | Type | Value / source | Meaning | Conf |
|---|---|---|---|---|
| +0x00 | float | ctor param (call site shows `*(unit+0x604)`) | unit scale factor (same value as +0x15c) | L |
| +0x04 | float | 1.0 (ctor) | post-multiplier applied to melee attack/defence/charge in FUN_142e459e4 | M |
| +0x08 | byte | ctor param (undetermined) | when set, the +0x04 multiplication is skipped (FUN_142e58504/590b4/58908) | M |
| +0x0c | int | 2 (FUN_142e6836c) | morale band / combat state (duel: 0 best .. 6 broken); starts at 2 | H value / M meaning |
| +0x10 | int | `unit+0x540` | number of entities | H |
| +0x14 | uint | `hp / unit+0x544`, hp = `unit+0x548` or recomputed by FUN_143106320 if -1 | hp per entity (max) | H |
| +0x18 | uint | same | hp per entity (current) | H |
| +0x1c | int | `(int)(attr#0x27 * max(unit+0x3c0 + unit+0x3bc, unit+0x3c4) * unit+0x604)` | damage carry (duel subtracts it from incoming damage) | H formula / L meaning |
| +0x20 | int | 0 | fatigue-like counter (duel) | H |
| +0x24 | int | `FUN_143019990`: carriers x `db+0x1a8`; artillery (FUN_142e45dc0): `db+0x1a8/max(1,n-1) + db+0x1a4/max(1,n-1)` | ammunition (`db+0x1a8` = primary_ammo, `db+0x1a4` = secondary_ammo) | H |
| +0x28 | int | `attr#0x21 + attrF#0x32 * W+0x70` | missile damage | H |
| +0x2c | int | `attr#0x22 + attrF#0x33 * W+0x74` | missile AP damage | H |
| +0x30 | int | `attr#0x23 + attrF#0x34 * P+0x2c` (if P) | explosion damage | M |
| +0x34 | int | `attr#0x24 + attrF#0x35 * P+0x58` (if P) | explosion AP damage | M |
| +0x38 | int | `Q+0x30` (if Q) | penetration: max entities hit | M |
| +0x3c | float | `(W+0xf4 / max(4, (100 - attr#0x19) * 0.01 * W+0x80)) * W+0xb8 * W+0x4c`; artillery: `sqrt(sum over weapons)` | fire rate (shots/s per firing weapon); `W+0x80` = base reload time, `attr#0x19` = reload skill % | H |
| +0x40 | int | `W+0x54` (artillery: mean over weapons) | range (also what FUN_142ef58ec reads for the type-3 duel distance) | H |
| +0x48 | float | `W+0x88` (artillery: mean) | unknown projectile scalar copied into the firing situation | L |
| +0x50 | int | `attrF#0x36 * W+0x64` | projectile velocity (> 80 enables penetration) | M |
| +0x54 | float | `W+0x7c` | unknown | L |
| +0x58 | int | `attrF#0x46 * P+0x20` | explosion radius | H |
| +0x5c | float | `W+0xb0` | penetration distance | M |
| +0x60 | int | `Q+8` | penetration max entity-size class | M |
| +0x64 | byte | `FUN_142e3ba7c(W, FUN_1430d5494(ctx, ., W))` = `0xc8 \| (W+0x7b ? 4) \| (shot-type sum != 0 ? 1) \| 2` | projectile flag byte | H |
| +0x68 | byte | `(W+0x20 - 1) > 4` unsigned (shot category not in 1..5) | ignores shields (duel) | M |
| +0x69 | byte | `W+0xc8 != 0` | halves engagement distance (artillery-like trajectory record present) | M |
| +0x6c..+0xac | block | `FUN_142e455bc` -> `FUN_142e455f0(stat+0x6c, ..., secondary weapon = FUN_141670ec8(unit+0x18 list))` | secondary missile weapon, same layout as +0x28 (+0x80 = its fire rate) | H |
| +0xb0 | ptr | db | DB record pointer | M |
| +0xbc | int | `attr#0x18` | leadership (morale) | H |
| +0xc0 | u4 | `db+0xc8` | unknown | L |
| +0xc4 | int | `round(round(attr#0x10 * T(0x10)) * 1.0) * stat+0x04` | melee attack | M |
| +0xc8 | int | `round(attr#0x14 * T(0x14) * 1.0) * stat+0x04` | melee defence (duel cuts it 20% when a single entity is swarmed) | M |
| +0xcc | int | `attr#0x1b` | unknown (armour candidate) | L |
| +0xd0 | int | `attr#3` | unknown (armour candidate) | L |
| +0xd4 | int | `attr#0x1a` | unknown | L |
| +0xd8 | int | `attr#0x16` | missile block chance % | H |
| +0xdc | int | `attr#0x12` | unknown (melee damage AP candidate; pairs with 0x11) | L |
| +0xe0 | int | `attr#0x11` | unknown (melee damage base candidate) | L |
| +0xe4 | u4 | `mw+0x38` | melee splash max attacks (duel: max targets per attack) | M |
| +0xe8 | u4 | `mw+0x4c` | melee collision/charge max targets (nonzero -> charge impact) | M |
| +0xec | int | `round(attr#9 * T(9) * 1.0) * stat+0x04` (`FUN_142e58908`, optional x `engine+0x5cb0`) | charge bonus | M |
| +0xf0 | int | `attr#6` | bonus vs (one of three bonus-vs stats used by the hit roll) | L |
| +0xf4 | int | `attr#4` | bonus vs | L |
| +0xf8 | int | `attr#5` | bonus vs | L |
| +0xfc | uint | `max(1, round(unit+0x66c / (unit+0x684 ? unit+0x684 : unit+0x67c)))` (FUN_142e458d4) | entities per weapon/engine (crew divisor) | H |
| +0x100 | uint | same, forced to 1 when `db+0x110 == 0` or (`unit+0x684 != 0` and `!FUN_142e52e18`) | frontage / contact-count multiplier | H |
| +0x104 | float | `T(0)` | multiplier for attribute #0 | M |
| +0x108 | float | `attr#0 + f` (f = XMM0 leftover of a void call: unreliable) | attribute #0 (accuracy?) | L |
| +0x10c | uint | `0xd0 \| (mw+0x61 ? 4) \| (ctx+4 + (int)mw+0x48 != 0 ? 1) \| (FUN_1430df280(ctx) ? 2)` | flag word | H |
| +0x110 | float | `E+0x68` (+ man entity `(db+0x108)+0x68` when E is a mount) | mass | H |
| +0x114 | float | `X+0x30` (X = mount/articulated entity, else man) | speed | H |
| +0x118 | float | `X+0x20` | charge/run speed (cycle-charge discriminator) | M |
| +0x11c | float | `attrF#0x39` | unknown speed-like | L |
| +0x120 | float | `sum over passive ability phases: (ph+0x78/ph+0x74 - ph+0x80/ph+0x74) * FUN_142e269c4(ab)` | net HP regen per second (duel: incoming-damage reduction) | M |
| +0x128 | uint | `*(db+0xe0)+0x28` | unit category index | H |
| +0x130 | float | `E+0x64 * E+0x5c` | entity radius (x scale) | H |
| +0x134 | int | `E+0x54` | entity size class | H |
| +0x138 / +0x13c | u4 | `*(db+0x168)+0x10` / `+8` | formation spacing (two axes) | H copy / M meaning |
| +0x140 | int | `(int)(float)*(int*)(db+0x150)` | number of ranks (rank_depth) | M |
| +0x144 | float | `attr#0xf + attr#0xb` | unknown | L |
| +0x148 / +0x14c / +0x150 / +0x154 | float | `attr#0xc` / `attr#0xe` / `attr#0xd` / `attr#0xa` | unknown (not used by the duel) | L |
| +0x158 | byte | `unit+0x412` | unknown | L |
| +0x15c | float | `*(unit+0x604)` | per-entity divisor for single-entity normalisation | M |
| +0x160 / +0x161 / +0x162 | byte | `battr#3` / `battr#4` / `battr#0x27` | boolean attributes | H copy |
| +0x164 | int | `battr#0x28 ? 0 : (battr#0x46 ? 1 : 2)` | tri-state from two boolean attributes | H |
| +0x168 | byte | `*(FUN_142e59b20(unit,1,0)+0x18) != 0` | fires while charging (duel) | L |
| +0x16b | byte | `E+0x54 < 2` | small entity | H |
| +0x16c | byte | `battr#0x20 \|\| battr#0x21` (FUN_142e357f8) | envelopment-mode flag (duel) | M |
| +0x16f | byte | category == 2 | category flag (charge multiplier 2.0 in duel) | H |
| +0x170 | byte | `E+0x54 > 1` | | H |
| +0x171 | byte | `E+0x54 > 2` (overwrites the category==3 flag unless category == 5) | large entity | H |
| +0x172 | byte | `E+0x54 < 2` (overwrites the category<2 flag unless category == 5) | small entity (charge-multiplier target) | H |
| +0x173 | byte | category == 5 | count entities individually (bypass +0xfc) | H |
| +0x174 | byte | category == 4 | category flag | H |
| +0x177 | byte | not written by any dumped filler (ctor 0) | 3x frontage (duel) | - |
| +0x178 | byte | `battr#0x15 \|\| 0x16 \|\| 0x1e \|\| 0x1f \|\| 0x3f` | unbreakable | H |
| +0x179 | byte | `battr#0x3a` | boolean attribute | M |
| +0x17a | byte | `battr#0xf` | boolean attribute | H copy |
| +0x17b | byte | `*(urec+0x5e3)` | is single entity | H |

Entity record selection (`FUN_142e45944(stat, X, db+0x108, cat == 5)`): `X = *(db+0x180)+0x68` (mount) if `db+0x180`, else `*(db+0x110)+0x28` (articulated) if `db+0x110`, else `db+0x108` (man); `E = (cat == 5) ? db+0x108 : X`. Size flags +0x16b/+0x170/+0x171/+0x172 are written only when `cat != 5`.

Decisive lines (FUN_142e455f0):
```
*param_1 = (int)((float)iVar6 + fVar10 * (float)iVar8);      // +0x28 = attr#0x21 + attrF#0x32 * W+0x70
param_1[6] = (int)(float)iVar2;                                // +0x40 = W+0x54 (range)
param_1[5] = (int)(((float)*(int *)(param_4 + 0xf4) / fVar10) * (float)*(int *)(param_4 + 0xb8) * (float)*(uint *)(param_4 + 0x4c));
// fVar10 = max(4.0, (100 - attr#0x19) * 0.01 * W+0x80)
```
FUN_142e459e4: `uVar3 = FUN_141480a68(param_3,0x18); *(param_1 + 0xbc) = uVar3;` ... `FUN_142e58504(attr#0x10, T(0x10), 1.0, p5, p6) -> +0xc4`, `FUN_142e590b4(attr#0x14, ...) -> +0xc8`, `FUN_142e58908(attr#9, ...) -> +0xec`.

### Unit attribute array (unit+0x48) index table

| index | read as | lands in | identification | conf | evidence |
|---|---|---|---|---|---|
| 0 | int, T(0) | +0x108, +0x104; `n` in FUN_142ecad64 | unknown (accuracy candidate: pairs with missile kps "per n" modifier kinds 5/8) | L | usage only |
| 3 | int | +0xd0 | unknown (armour candidate) | L | |
| 4 / 5 / 6 | int | +0xf4 / +0xf8 / +0xf0 | the three bonus-vs stats (infantry / large / cavalry order unknown) | L | hit roll adds three target-type-gated bonuses (FUN_142e58560 vf0xe0/e8/f0) |
| 9 | int, T(9) | +0xec | charge bonus | M | cycle-charge 3.5x rule pairs it with run speed +0x118; charge-impact path |
| 0xa, 0xb, 0xc, 0xd, 0xe, 0xf | int | +0x154, +0x144, +0x148, +0x150, +0x14c, +0x144 | unknown | L | not read by duel code |
| 0x10 | int, T(0x10) | +0xc4 | melee attack | M | only attack-sized int on the attacker side of the hit roll; see adapter note |
| 0x11 / 0x12 | int | +0xe0 / +0xdc | melee damage base / AP (candidates) | L | adjacent pair like 0x21/0x22 |
| 0x14 | int, T(0x14) | +0xc8 | melee defence | M | swarm penalty (FUN_142e33420 x0.8) applies to it |
| 0x16 | int | +0xd8 | missile block chance % | H | `(1 - 0xd8*0.01) * p_hit` |
| 0x18 | int | +0xbc | leadership / morale | H | morale bands in duel |
| 0x19 | int | fire-rate formula | reload skill % | H | `(100 - x) * 0.01 * base_reload` |
| 0x1a / 0x1b | int | +0xd4 / +0xcc | unknown | L | |
| 0x1f | int | ability range (FUN_142ebc994) | unknown range bonus | L | |
| 0x21 / 0x22 | int | +0x28 / +0x2c | missile damage / AP flat bonus | M | |
| 0x23 / 0x24 | int | +0x30 / +0x34 | explosion damage / AP flat bonus | M | |
| 0x25 / 0x26 | int | CP pair (FUN_142e317b0) | melee_cp / missile_cp | H | seeds of CP, ability CP added on top |
| 0x27 | int | +0x1c | unknown | L | |
| 0x32 / 0x33 | float | +0x28 / +0x2c | missile damage / AP multiplier | M | |
| 0x34 / 0x35 | float | +0x30 / +0x34 | explosion damage / AP multiplier | M | |
| 0x36 | float | +0x50 | velocity multiplier | M | |
| 0x39 | float | +0x11c | unknown speed-like | L | |
| 0x46 | float | +0x58 | explosion radius multiplier | M | |

Boolean attributes (index space 0..0x59 = 90, cf. 87 keys in unit_attributes_tables): 3, 4, 0x27 -> +0x160..+0x162; 0xf -> +0x17a; {0x15, 0x16, 0x1e, 0x1f, 0x3f} -> unbreakable (+0x178); 0x20 / 0x21 -> +0x16c; 0x28 / 0x46 -> +0x164; 0x3a -> +0x179; 0xd is tested in the damage routine FUN_142e589a4; 0x15 in FUN_142e2a8e8 (skips a CP cost term). The engine enum order is not alphabetical (alphabetical would make 0x15/0x16 executor/expendable), so names cannot be assigned from the DB key list.

Adapter note (hit % / armour): `FUN_142e323c8` builds two wrappers `{vtable UNK_143906018, ctx, stat}` and `FUN_142e58560` reads melee attack via vf0xb0, defence via vf0xb8, bonus-vs via vf0xe0/0xe8/0xf0, shield via vf0x40; `FUN_142e589a4` reads armour/damage via vf0xa0/0xc8/0xd8 (names from role). The vtables UNK_143906018 / UNK_143905f80 / UNK_143906228 / UNK_143905f50 are not in decomp13/14/16, so the slot -> stat-offset mapping cannot be read; the identifications above come from which fields the fillers produce (+0xc4/+0xc8 are the only T-scaled attack/defence-sized ints; +0x28/+0x2c the only missile damage pair). Hit formula (FUN_142e58560): `hit = clamp(vf8(p1) + vf0x20(p1) * (MA + bonus_vs - (MD [+ shield vf0x40 if vf0x58]) * flank(FUN_142e32a04) - vf0xc0(target) if vf0x20(p2)), vf0x10(p1), vf0x18(p1))`.

Other sim-unit (0x2a8 bytes) fields set during construction (FUN_142ea1418, FUN_142ea16d4, FUN_142f1147c):

| Offset | Meaning | Conf |
|---|---|---|
| +0x00 | int global unit index (counter runs across both alliances: defender starts at attacker count) | H |
| +0x08 | ptr army-sim (0x30: +0 alliance, +8 army index, +0xc byte is_reinforcement, +0x10 setup army 0x390, +0x18 result army 0x228, +0x20 vector of sim-units) | H |
| +0x10 | ptr game unit (0x6b0) | H |
| +0x18 | ptr result entry (0x1c8) | H |
| +0x20 | int ar unit category 0..3: `*(db+0x1f0)`; if 4 (unset) derived from `*(*(db+0x4f8)+0x28)` (unit class) / `*(*(db+0x4f0)+0x28)` / `*(*(db+0x1c8)+0x18)&1` by a switch; 3 = artillery (FUN_142ebee8c counts class==3 units with cv `wall_damage_num_artillery_units_percentage`; FUN_142ef58ec gives class 3 full weapon range, others range*0.65) | M |
| +0x28 | stat block (0x17c) | H |
| +0x1a8 / +0x1c4 / +0x1e0 | three copies of a 0x1c state block = stat +0xc..+0x24 plus leading int: {+0 int = 1, +4 entities = unit+0x540, +8 = stat+0x14, +0xc = stat+0x18, +0x10 = stat+0x1c, +0x14 = stat+0x20, +0x18 = ammo = stat+0x24} | H |
| +0x218 | hash map of per-enemy duel results (FUN_142ebcfa4 / FUN_142e972b4) | M |
| +0x240 | float 1.0 | H |
| +0x248..+0x25c | 6 kill-rate modifier floats (see Modifier system) | H |
| +0x260 | map vs-unit-class index -> node with 6 floats at node+0x14..+0x28 | H |
| +0x288 | float 1.0 | H |
| +0x290 | retreat threshold = clamp(cv[355] autoresolver_unit_base_retreat_threshold + entry+4, 0, 1) | H |
| +0x294 | ammo multiplier (entry+8, default 1.0); FUN_142f12fc0: `ammo = round(ammo * m)` (0 if product <= 0) written to +0x4c, +0x1c0, +0x1dc, +0x1f8 | H |
| +0x298 | scale applied in FUN_142f130b0 to duel outputs [3],[4] (deltas of state+0) -> morale-loss scale (entry+0xc, default 1.0) | M |

Game-unit (0x6b0) / DB-aggregate fields identified along the way [M unless noted]: `unit+0x540` entities, `unit+0x544` divisor for hp per entity, `unit+0x548` total hp or -1, `unit+0x604` scale float, `unit+0x5c0` int key for the T() lookup, `unit+0x668/+0x66c` men (max/current), `unit+0x678/+0x67c` mounts, `unit+0x680/+0x684` engines, `unit+0x688/+0x68c` and `unit+0x670/+0x674` further hp components (FUN_143106320), `unit+0x450/+0x454/+0x458` ability list (0x190 stride), `urec+0x5c0/+0x5c4` floats summed to pick the "best" unit for buff_unit abilities, `urec+0x5e0 -> +0x40` CP cost-adjust record; `db+0xe0` category, `db+0xe8` class, `db+0x108` man entity, `db+0x110` articulated, `db+0x140` melee weapon, `db+0x150` rank depth, `db+0x154` hp per man [H: FUN_14310660c], `db+0x168` spacing record, `db+0x178` engine record (+0x7c = artillery-style fill, +0x58 -> +0x80 hp), `db+0x180` mount record (+0x50 enum in {7,8} tested by FUN_142e52e18), `db+0x1a4/+0x1a8` secondary/primary ammo, `db+0x1c8` ai_usage_group, `db+0x1f0` ar_unit_category, `db+0x1fc` ammo flag.

## Alliance/unit build

`FUN_142ea091c(sim, engine, ctx, setup, result, difficulty, override, handicap)`:
- `sim+0x00` engine; `sim+0x08..` copy of ctx (FUN_142ea13c8: +0x10 and +0x30 = the two 0x20 modifier blocks); `sim+0x58` setup; `sim+0x60` result.
- `sim+0x68` = FUN_142ea0a40(alliance, sim, sim+0x10, *(setup+8) [attacker setup alliance, 0x80 stride], *(result+0x30) [attacker result alliance, 0x60 stride], is_attacker=1, first_index=0)
- `sim+0x70` = same for defender with `+0x80` / `+0x60` and first_index = attacker unit count (`*(sim+0x68 +0x34)`).
- then `+0x80 = 0`, `+0x7c = 0`, `+0x88 = difficulty`, `+0x90 = handicap`, `+0x8c = override`, `+0x78 byte = 1`.
- `FUN_142ec0ba4(att)`, `FUN_142ec0ba4(def, att)` (ability buffs), then `FUN_142f0ba78(sim)` = run (only if both alliances have >= 1 unit).

`FUN_142ea0a40(alliance[0xa0], sim, block, setupAlliance, resultAlliance, is_attacker, first_index)`:
- +0x00 sim, +0x08 byte is_attacker, +0x10 setupAlliance, +0x18 resultAlliance, +0x20 army-sim vector, +0x30 sim-unit vector (count +0x34, ptr +0x38), +0x40 int 0.
- +0x48 = copy of the side's 0x20 modifier block (FUN_142ea0ba4 deep-copies the 20 x 0x58 entries via FUN_142e96a00).
- +0x68 / +0x78 / +0x88: three 0x30-stride vectors (damage / own-side buff / enemy-side debuff ability entries), +0x98 float accumulator.
- Loop over `setupAlliance+0x2c` armies (0x390 stride at +0x30) paired with result armies (0x228 stride at `resultAlliance+8`): `FUN_142f11958(alliance, army, resArmy, &index, is_reinforcement = (i != 0), armyIdx)`; then nested loop over reinforcement armies (`army+0x1f4` count, `army+0x1f8` ptr) paired with `resArmy+8`.
- `FUN_142f11958`: allocates the 0x30 army-sim, pushes it on alliance+0x20; for each unit (`army+0x124` count, `army+0x128`, 0x6b0 stride; result entries `resArmy+0x18`, 0x1c8 stride) allocates 0x2a8 and calls `FUN_142ea1418(simunit, index++, engine, armysim, unit, entry)`, pushing it on alliance+0x30 and armysim+0x20.
- Finally `FUN_142f12fc0(alliance)`:
  1. `FUN_142f1147c(unit, alliance+0x48)`: class = `*(*(db+0xe8)+0x28)`; if class < entry count, copies entry[class]: +0x10..+0x27 -> unit+0x248..+0x25f, map +0x28 -> unit+0x260, `unit+0x290 = clamp(cv355 + entry+4, 0, 1)`, `unit+0x294 = entry+8`, `unit+0x298 = entry+0xc`.
  2. `FUN_142ebc994(alliance, unit+0x450 [unit abilities, 0x190 stride], armysim, 0, unit)` then for each army `FUN_142ebc994(alliance, setupArmy+0x2b8 [army abilities], armysim, 1, 0)`.
  3. ammo scaling by +0x294 (see table).

Special abilities (`FUN_142ebc994`) [M]: for each ability A (0x190 stride, deduped by `FUN_142e55d88(A,0)` key):
- usage = `*(A+0xe8 -> +0x1ed)` (autoresolver_usages enum; 9 = default, 10 = disabled -> skipped), `cp = (*(A+0xe8->+0xc4) + *(A+0xe8->+0xc8)) * (double)*(A+0xe8->+0x1f8)`.
- strength `t = clamp(cp / max(1, cv366), cv367, cv368)` (cp_to_strength_divider=500, min/max strength proportion 0..1).
- range = `FUN_142e583c8(A)` = round(max(w+0x70 * A+0x48 + A+0x44, w>0 ? 1 : 0)); `alliance+0x98 += max(range + attr#0x1f, 0)`.
- usage < 3, == 8, or (9 with buff-like flags): value = `lerp(cv372, cv373, t) * (range>0 ? A+0x34 : 1) * F1 * F2` -> list alliance+0x78 (own-side).
- usage 3, 5, or 9-with-damage-components: `lerp(cv369, cv370, t) * n * F1 * F2` -> damage list alliance+0x68; usage 4: raw cp value.
- else (6, 7, 9 otherwise): `lerp(cv374, cv375, t) * ...` -> enemy-side list alliance+0x88.
- F1 = `*(setupArmy+0x15c)` if range>0 else 1.0; F2 = `*(setup+0x100)` (both unresolved floats).
- Inferred usage enum order [M]: 0 buff_army, 1 buff_self, 2 buff_unit, 3/4/5 damage_*, 6 debuff_army, 7 debuff_unit, 8 debuff_self, 9 default, 10 disabled (from how FUN_142eb2598 routes 1/8 to "own unit by index", 2/7 to "best-CP unit", 0/6/9 to the army-wide sum).

`FUN_142ec0ba4(A, B)` (ability buff application) [H on math, M on list semantics]:
```
n = A.unitCount; buff = FUN_142eb2598(sorted copy of A+0x78); debuff = FUN_142eb2598(sorted copy of B+0x88)
fb = n ? buff/n + 1 : 1;   fd = n ? 1/(debuff/n + 1) : 1
for each unit u in A: u+0x248 = (u+0x248 + 1)*fd*fb - 1;  u+0x250 = (u+0x250 + 1)*fd*fb - 1
```
Decisive line: `*(float *)(lVar3 + 0x248) = (*(float *)(lVar3 + 0x248) + 1.0) * fVar7 * fVar5 - 1.0;`
Inside FUN_142eb2598, entries of usage 1/8 are applied directly to the named unit (`FUN_142ec0cf0`: factor `1+v` if usage<3 else `1-v`, on +0x248/+0x250), usage 2/7 to the not-yet-buffed unit with the highest `*(urec+0x5c0) + *(urec+0x5c4)` (two floats on the unit object, urec = `*unit`) [M]; only the first flagged (+0x28 != 0) entry is counted.

Combat potential / strength per unit (`FUN_142eabf3c`, used in run/result phases) [M]:
- `FUN_142e317b0(out, unit, hpRatio)`: `out = (attr#0x25, attr#0x26)` + `FUN_142e38c7c` (adds FUN_142e29d0c/29d30 terms when positive) + up to 10 abilities (FUN_142e38ad8: ability `+0xe8->+0xc4` to melee, `+0xc8` to missile, ranged ones weighted `1 - j*0.9/(n-1)`), then `* hpRatio` (FUN_143121788 of FUN_143106320(unit, 1.0)), then `FUN_142e2a8e8`: with cost record `R = *(*(urec+0x5e0)+0x40)`: `melee = melee * (1 + R+0x54 [+ R+0x5c if an ability with +0x178 == 0 exists] [+ R+0x64 if !battr#0x15]) + (R+0x50 [+ R+0x58] [+ R+0x60])`, missile likewise with `R+0x6c/+0x74/+0x7c` and `R+0x68/+0x70/+0x78`.
- `FUN_142ef5e24(engine, unit, cp)`: `FUN_14162afe0(db+0xba60 table [autoresolver_ai_usage_group_combat_potential_modifiers], *(db+0x1c8) [ai_usage_group record], &add, &mult)` -> row `+0x10 = additive_mod`, `+0x14 = multiplier`, defaults (0, 1.0); returns `mult * cp + add`.
- Strength record (0x20): +0 unit, +8 cp', +0x10 max entities (`unit+0x544`), +0xc total hp = state+0xc * max entities, +0x18 current fraction (entities/max, or hp fraction for single-entity), +0x14 lost fraction.

## Modifier system

### Data flow
`FUN_142ec22c4` -> `FUN_142ee46c0(setup, &A, &B)`: scans `setup+0x388` (0x48 stride, count `setup+0x384`): entries with byte +0x10 set are human players; A/B (per side 0/1) get `.found=1` and `.difficulty = entry+0x34`.
`FUN_142ee406c(ctx, engine, setup, difficulty, &A, &B)`:
1. `bt = FUN_142ee172c(engine, setup, difficulty)`: best-scoring autoresolver_battle_types row (table db+0xc978). Row fields: +8 battle_type enum (0x17 = wildcard), +0xc is_encampment tri-state, +0x10 is_night_battle tri-state, +0x18 difficulty string ("" = wildcard), +0x38 autoresolver_stance ptr (null = wildcard). Tri-state encoding (from FUN_142f016ac): 0 = true, 1 = false, 2 = any. Match against `setup+0xf0` (battle type), `setup+0x125 == 0` (encampment), `setup+0xc8 == 1` (night), `*(setup+0x180)+0x108` (stance), difficulty string = `FUN_142ee4280()+0x30` or `FUN_14058dc30()` when difficulty != 0. Score = 1 + 0x20 (stance) + 0x10 (encampment) + 8 (battle type) + 4 (night) + 2 (difficulty); highest wins, ties keep the first.
2. `rows = FUN_14162af60(FUN_1414b31ec(engine) [db+0xc860 lookups index], bt)+0x18` = vector of autoresolver_modifier_group_lookups rows (+0x10 group key, +0x18 mechanic enum, +0x20 player_type row).
3. Per side: `FUN_142f12540(side, setup+0x380, &X)` -> 8-byte player descriptor {byte0 side (1 attacker), byte1 human found, int4 difficulty = clamp(2 - raw, 0, 5) or 2 if not found}. General level `gl = *(FUN_142d52a2c(army)+0x40)` (first unit with `+0x4d8+0x44 in {1,2}`), siege strength `ss = FUN_142ec3034(army+0x1c8)` = sum of `+0xb0` floats.
4. For each row: `FUN_142f016ac(row+0x20, &A, &B)` (player_type match: +0x18/+0x19 if_player_is_attacker/defender vs side, +0x14 player_is_human, +0xc enemy_is_human, +0x10 player difficulty (0 = any), +8 enemy difficulty) -> `FUN_142ebfc7c(engine, ctx+8, row, glA, ssA)`; swapped -> `ctx+0x28` with B's values.

### FUN_142ebfc7c (write one group into a side block)
scale = `(float)gl` if mechanic == 1, `ss` if mechanic == 2, else 1.0. For each group_to_modifiers row M (`FUN_14162afa0(db+0xc898, row+0x10)`): `v = scale * *(M+0x28)`, kind = `*(M+0x10)`, target T = `*(M+0x18)` (autoresolver_modifier_targets row: +8 target_unit_class ptr, +0x10 vs_unit_class ptr; class index = `*(cls+0x28)`).

Side block (0x20): {+0 u8 player info, +8 u4, +0xc float (init = win-chance share p0/(p0+p1) for A, 1-that for B), +0x10 cap, +0x14 count (20), +0x18 entries}. Entry (0x58, one per unit class, FUN_142ea181c): {+0 class idx, +4 retreat mod (0), +8 ammo mult (1.0), +0xc morale-loss scale (1.0), +0x10..+0x24 six kps floats (0), +0x28 map vs-class -> node(+0x14..+0x28 six floats), +0x50 float 1.0}.

| kind | effect | likely DB name | Conf |
|---|---|---|---|
| 1 | `block+0xc += v` | (side-level, unnamed) | H effect |
| 2 | `entry[T.target]+4 += v` or all entries | unit_retreat_mod | M |
| 3 | vec[0] -> unit+0x248 (melee multiplier) | unit_melee_kps_multiplier | M |
| 4 | vec[2] -> unit+0x250 (missile multiplier) | unit_missile_kps_multiplier | M |
| 5 | vec[4] -> unit+0x258 (missile multiplier per attr#0) | (unnamed) | H effect |
| 6 | vec[1] -> unit+0x24c (melee addition) | unit_melee_kps_addition | M |
| 7 | vec[3] -> unit+0x254 (missile addition) | (unnamed; unit_missile_kps_addition?) | L name |
| 8 | vec[5] -> unit+0x25c (missile addition per attr#0) | (unnamed) | H effect |
| 9 | `entry+8 += v` or all | (ammo multiplier, unnamed) | M |
| 10 | `entry+0xc += v` or all | unit_morale_loss_scale | M |

Vector routing (`FUN_142ebee38(block, T, vec)`): T.target != null -> entry[T.target]; then T.vs != null -> `entry.map[T.vs].floats += vec` (node created on miss, FUN_142e97d30) else `entry+0x10.. += vec`. T.target == null -> all entries (per-vs via FUN_142ebba68 if T.vs set, else `entry+0x10..`).
Also `FUN_142ebb9e4(block, vec)` (called from FUN_142ec22c4 with vec = {p4+p5, 0, p4+p5, 0, 0, 0} for A and {p3+p6, 0, p3+p6, 0, 0, 0} for B) adds the result params' kps bonus to melee and missile multipliers of every class.

### FUN_142ecad64(u, vs, is_melee, want_multiplier) exact combination
```
n   = attr#0 of u                                      // FUN_141480a68(*(u+0x10)+0x48, 0)
if is_melee: M = u+0x248;                   A = u+0x24c
else:        M = u+0x250 + n*u+0x258;       A = u+0x254 + n*u+0x25c
node = map(u+0x260).find(*(*(*(vs+0x10)+0x500)+0xe8)+0x28)   // vs unit class index
if node:
  if is_melee: M += node+0x14;                 A += node+0x18
  else:        M += node+0x1c + n*node+0x24;   A += node+0x20 + n*node+0x28
  M += node[0x14 + (is_melee^1)*8];  A += node[0x18 + (is_melee^1)*8]   // appears to re-add the same base term (see Open questions)
return want_multiplier ? max(M + 1.0, 0.01) : A
```
Decisive lines:
```
fVar5 = (float)iVar2 * *(float *)(param_1 + 0x25c) + *(float *)(param_1 + 0x254);
fVar4 = (float)iVar2 * *(float *)(param_1 + 600) + *(float *)(param_1 + 0x250);
...
if ((param_4 != '\0') && (fVar5 = fVar4 + 1.0, fVar5 <= 0.01)) { fVar5 = 0.01; }
```
Caller (`FUN_142f130b0`): `kps' = max(kps * FUN_142ecad64(u,vs,k,1) + FUN_142ecad64(u,vs,k,0), 0)` for melee (k=1) and missile (k=0), for both directions and for the "duel type 2" variants; morale-ish deltas `*= vs+0x298`.

## Campaign-variable constants seen

The engine/db object holds the campaign_variables array at `engine + 0x18cd4 + 4*index` (index per `re/ar_indices.json`; verified by 0x19260 = idx 355 and the whole 0x1928c..0x192b0 run matching the special_ability_* names in order) [H]. Note: NOTES.md says the values live at "campaign-model holder +0x5be8"; this is a different base (open question).

| engine offset | idx | variable (value) | used in |
|---|---|---|---|
| 0x1925c | 354 | autoresolver_unit_wipe_out_threshold (0.2) | FUN_142ef57e0 |
| 0x19260 | 355 | autoresolver_unit_base_retreat_threshold (0.25) | FUN_142f1147c (+ kind 2 mod, clamp 0..1) |
| 0x19264 | 356 | autoresolver_wipe_out_army_force_unary_lost (0.92) | FUN_142ec5a6c |
| 0x19270 | 359 | autoresolver_battle_reinforcement_time (0) | FUN_142f11a90 |
| 0x19278/0x1927c | 361/362 | winner_kpd_major/minor_win_threshold (3.0 / 0.3) | FUN_142f0f378 |
| 0x19280 | 363 | autoresolver_battle_timestep (4.0) | FUN_142ee33d0 |
| 0x1928c | 366 | special_ability_cp_to_strength_divider (500) | FUN_142ebc994 |
| 0x19290/0x19294 | 367/368 | special_ability_min/max_strength_proportion (0 / 1) | FUN_142ebc994 |
| 0x19298/0x1929c | 369/370 | special_ability_damage_damage_min/max (1 / 30) | FUN_142ebc994 |
| 0x192a4/0x192a8 | 372/373 | special_ability_buff_kps_modifier_min/max (0 / 0.1) | FUN_142ebc994 |
| 0x192ac/0x192b0 | 374/375 | special_ability_debuff_kps_modifier_min/max (0 / 0.1) | FUN_142ebc994 |
| 0x192dc | 386 | autoresolver_min_battle_time_before_retreat (20) | FUN_142f1cd50 |
| 0x192f0/0x192f4 | 391/392 | alliance_wipe_out_winner_loser_strength_multiple (7) / loser_strength_of_max_threshold (0.3) | FUN_142ec5a6c |
| 0x194d4..0x194e4 | 512..516 | building/wall damage percentages (0.2, 0.2, 0.2, 0.01, 0.01) | FUN_142ebee8c |
| 0x19568 | 549 | battle_missile_range_modifier_used_in_ranged_combat (0.65) | FUN_142ef58ec (range * 0.65 for non-artillery) |
| 0x19618/0x1961c | 593/594 | num_defender_towers fortified/unfortified (3 / 1) | FUN_142ee33d0 |
| 0x19768 | 677 | winner_additional_wall_damage_per_wall_breach (5) | FUN_142ebee8c |
| 0x197f8..0x19804 | 713..716 | tower_level_1..4_damage_multiplier | FUN_142f194a8 |
| 0x19808..0x19818 | 717..721 | damage_transfer_* | FUN_142f07a98, FUN_142edd084 |
| 0x19940..0x19954 | 795..800 | chase_down_* | FUN_142ec56a8 |
| 0x19a0c/0x19a10/0x19a20 | 846/847/851 | battle_size_kill_factor, siege_attack_kill_multiplier, ensured_unit_loss_cp_weight | FUN_142edd084 |

Literal constants in this slice: 0.01 (multiplier floor), 1.0 defaults, 0.9 (ability weight decay in FUN_142e38ad8), 10.0 (fallback range for class-3 units with abilities, FUN_142ef58ec; fallback duel time in FUN_142f1bebc), 4.0 (minimum reload time in the fire-rate formula, FUN_142e455f0), 100 (reload skill percent base), 0x14 = 20 unit classes, 0x17 = battle-type wildcard. Other engine floats touched by the fillers: `engine+0x5cb0` (charge-bonus scale in FUN_142e58908 when a mode flag is 1..3), `engine+0x40a8/+0x4110` (bonus scaling in the hit roll), `engine+0x66d8` (threshold in FUN_142e589a4) - not campaign_variables by offset.

## Open questions

- Unit attribute enum: 0x47+ numeric and 0x5a boolean indices; only the entries in the index table are identified. Indices 0, 3, 0xa..0xf, 0x11/0x12, 0x1a/0x1b, 0x27, 0x39 and which of +0xcc/+0xd0/+0xd4 is armour need either the vtables of UNK_143906018/UNK_143905f80 (stat wrappers) or the campaign-side code that fills `unit+0x48` from land_units columns.
- Fields never written by the dumped fillers: +0x44, +0x4c, +0xb8, +0xc0 (copied raw), +0x124, +0x177 (3x frontage flag), +0x16a (runtime). +0x108's second term is an XMM0 leftover of a void call and cannot be trusted.
- `T(i)` multiplier table (FUN_142e44e60 / FUN_1415eae64: record `+0x1c == stat`, `*(+0x20)+8 == *(unit+0x5c0)`, value `+0x18`): not the campaign difficulty handicap (no battle-stat effects in that table); candidate: an experience-rank or unit-set stat multiplier table. `unit+0x5c0` (int) is its key.
- `FUN_142ecad64` appears to add the base vs-class term twice (`node[0x14 + (is_melee^1)*8]` after the branch). Could be a real double-count or a quick-decompile phi artifact; needs the full-analysis decompile or a disassembly check.
- Call-site argument loss: `FUN_142ec0ba4(attacker)` shows one argument (second presumably the defender), `FUN_142ef5e24` takes a single CP float although `FUN_142e31768` produces a (melee, missile) pair; `FUN_142e05974` call in FUN_142e38518 shows shifted args; `FUN_142e455f0`/`FUN_142e45dc0` are void but their caller consumes a float return.
- Which enum value of autoresolver_usages maps to 3/4/5 (damage_aoe/single/unit) and the exact 7/8 order.
- Where `block+0xc` (win-chance share +/- kind-1 modifiers; copied to alliance+0x54) is consumed (run phase, not in this slice).
- Engine campaign-variable base 0x18cd4 vs NOTES.md "holder +0x5be8": different object or stale note.
- `F1 = *(setupArmy+0x15c)` and `F2 = *(setup+0x100)` multiplying ability values are unidentified.
- Weapon record fields W+0x7c (-> +0x54), W+0x88 (-> +0x48), W+0xb8, W+0x4c, W+0xf4 (fire-rate factors: shots per volley / barrels), and the Q record behind W+0xe8 are named only by role.

## Functions read

decomp13 core: FUN_142ec22c4, FUN_142ee46c0, FUN_142ea0bf0, FUN_142ea181c, FUN_142e98cc0, FUN_142ea1750, FUN_142ebb9e4, FUN_142eb385c, FUN_142ee406c, FUN_142ee172c, FUN_142e96630, FUN_142ee4280, FUN_14058dc30, FUN_1414b2dec, FUN_1414b31ec, FUN_1414b3414, FUN_1414b2bcc, FUN_14162af60, FUN_14162afa0, FUN_14162afe0, FUN_142f12540, FUN_142f016ac, FUN_142d52a2c, FUN_142ec3034, FUN_142ebfc7c, FUN_142ebee38, FUN_142ebc77c, FUN_142ebbd44, FUN_142ebbf60, FUN_142ea091c, FUN_142ea13c8, FUN_142ea0a40, FUN_142ea0ba4, FUN_142f11958, FUN_142ea1418, FUN_142ea16d4, FUN_142e38518, FUN_142e05974, FUN_142e05b08, FUN_142e6836c, FUN_141c46e58, FUN_142e2df2c, FUN_143106320, FUN_141480a68, FUN_142f12fc0, FUN_142f1147c, FUN_142eae8a0, FUN_142ebc994, FUN_142e97f98, FUN_142e58988, FUN_142e594f8, FUN_142e583c8, FUN_142e55d88, FUN_142ec0ba4, FUN_142eb2598, FUN_142e9f8c8, FUN_142e9ed9c, FUN_142ec0e58, FUN_142ec0d4c, FUN_142ec0cf0, FUN_142eeb658, FUN_142ef58ec, FUN_142ef5834, FUN_1416703cc, FUN_142ecad64, FUN_142f130b0, FUN_142f1bebc, FUN_142ee381c, FUN_142e7403c, FUN_142e47084, FUN_142ebcfa4, FUN_142f0ba78, FUN_142eabf3c, FUN_142ef5e24, FUN_142e31768, FUN_142e317b0, FUN_142e38ad8, FUN_142ebee8c (head only).
decomp16 (stat fillers): FUN_142e45944, FUN_142e455f0, FUN_142e455bc, FUN_142e45dc0, FUN_142e7a904, FUN_142e459e4, FUN_142e458d4, FUN_143019990, FUN_142e59b20, FUN_142e59bbc, FUN_142e357f8, FUN_142e52e18, FUN_14146ff40, FUN_1430c6bc8, FUN_1430c6db4, FUN_142e2dda0, FUN_142e269c4, FUN_142e38c7c, FUN_142e2a8e8, FUN_142e58504, FUN_142e590b4, FUN_142e58908, FUN_142e44e60, FUN_1415eae64, FUN_142dfa594, FUN_142e3ba7c, FUN_1430d5494, FUN_141670ec8, FUN_1430df280, FUN_14310660c, FUN_14310656c, FUN_143103bc0, FUN_143104498.
decomp14 (cross-check): FUN_142e58560, FUN_142e338c0, FUN_142e323c8, FUN_142e324bc, FUN_142e32a04, FUN_142e2e9e0, FUN_142e52c20, FUN_142e589a4, FUN_142e590f8, FUN_142e59328, FUN_142e5955c, FUN_142e59a3c, FUN_142e33420, FUN_142e32330.
Triaged and ruled out as stat builders (sort/hash/vector templates): FUN_142e935e4, FUN_142e93198, FUN_142e9140c, FUN_142e912a0, FUN_142e96f94, FUN_142e972b4, FUN_142e95d68, FUN_142e95a18, FUN_142e95b18, FUN_142e95390, FUN_142e952ac, FUN_142e989c0, FUN_142e98818, FUN_142ea0d48.
