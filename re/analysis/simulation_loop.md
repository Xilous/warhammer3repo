# WH3 campaign autoresolver: simulation loop and battle phases (from Ghidra pseudo-C, decomp13 + decomp15)

Source: `C:\Users\jaymi\tools\ghidra_quick\decomp13\*.c` (run/post-sim phases) and `decomp15\*.c` (221 functions rooted at FUN_142f0b1c8 / FUN_142f1cd50, the per-step code). No whole-program analysis: argument lists are unreliable, control flow / constants / offsets are reliable. Campaign-variable values from `tww/db/campaign_variables_tables.json`, indices from `re/ar_indices.json`. Engine copy of the variable array: `engine+0x18cd4 + 4*index` (verified on 58 reads, every one semantically consistent).

## Summary

1. The timestep loop is **FUN_142f0b1c8** (called from FUN_142ee33d0): up to 200 steps, `dt = battle_timestep` (4.0 s) for steps 0..149 and `4*dt` (16 s) for steps 150..199 (hard cap 1400 s); exits early when `battle+0x168` (battle finished) is set. **High.**
2. The battle is a **1-D line model**: each army is split into "groups" (one melee line group with `type +8 == 0`, plus ranged/skirmish groups) that have a position on an axis; attacker (side 0) moves toward -x, defender toward +x; melee contact at distance <= 1.0, ranged groups shoot inside their range and are placed/held 0.75*range behind their own line. **High.**
3. Per step (FUN_142f1cd50): movement & reach update -> **melee** (FUN_142ef48e8) -> **ranged** (FUN_142f07190) -> **special abilities/spells** (FUN_142f13fb4, only if front lines are within special_ability_damage_range 100) -> **towers** (FUN_142ec2948, tower_base_kps 0.4) -> two regrouping passes -> reinforcement arrival -> **retreat** (FUN_142ec6450, only once elapsed >= min_battle_time_before_retreat 20). Every damage path ends in FUN_142ebeb0c -> FUN_142f0beec. **High.**
4. Melee pairing is one-to-one by best `kps_dealt/kps_received` ratio from the precomputed pairwise matrix; leftover units become **excess attackers** (FUN_142ebf118) dealing `0.65x` (battle_excess_melee_damage_multiplier) and receiving `0.3x` (`0.2x` vs single-entity targets), at most N per target where N is a rounded campaign value whose load the decompiler dropped (max_attackers_damaging_a_single_target_in_excess_melee = 2 is the only candidate). **High / Medium.**
5. Skirmishers (ranged unit with ammo paired against a non-skirmisher) split the engagement time via the `campaign_autoresolver_skirmish_effectiveness_relative_to_speeds` table (db slot 0xe700) interpolated at `speed_skirmisher/speed_enemy`; flying skirmishers get the whole time when flying_skirmish_units_use_entire_combat_time != 0. Flying vs non-flying melee applies flying_unit_melee_damage_dealt/received_modifier (0 % / -30 %). **High.**
6. Casualties are applied per engagement by interpolating the unit state toward the duel-predicted end state over the engaged time: entity count (+0x14) and hp/entity (+0x18) solve a quadratic so total hp drops linearly, ammo linearly, morale level (+0x10, 0..7) rises at rate `simunit+0x298` with a floor of minimum_morale_loss (0); counts under 1 % of max are zeroed; min_entity_reduction_unary_of_max (0.002) is the forced minimum loss for the "ensured loss" flag. Units with morale 6/7 or count 0 (or a general under 25 % health) leave the battle. **High.**
7. Retreat (FUN_142ec5f08): a side may retreat only while `own_units > enemy_units * num_units_multiplier_vs_enemy_to_allow_retreat (0.75)`; at most 2 units per step and never below 40 % of its starting unit count; a unit retreats when `count <= unit_base_retreat_threshold(0.25)+class offset) * starting entities`. **High.**
8. End of battle: a side whose arrived armies have all been eliminated and has no reinforcements left sets `battle+0x168`; the winner is side 0 iff it still has groups (`battle+0x9c != 0`). **High.**
9. Forced winner (-1/0/1) lands in `sim+8` and only overrides the post-sim winner/KPD step (FUN_142f0f378); stance is read only post-battle (FUN_142f103b8, `+0x4c == 2 -> +0.05, == 3 -> -0.05`). **High.**
10. **No 20 kills/s cap, no bound_* and no max_attackers_* reads exist in any of the 648 dumped functions**; bound_max_ranged_kills_per_second (20) must be applied inside the duel core FUN_142e47084 (other agent's slice). **High (negative result).**

## Loop structure (ordered per-step pseudocode)

### Objects (offsets verified across the functions listed at the end)
- **sim** (FUN_142ea091c): `+0 engine, +8 forced_winner, +0xc annihilate-loser byte (params byte 0x21), +0x1c p = params[0]/(params[0]+params[1]), +0x3c 1-p, +0x50 params[7], +0x54 params byte 0x20, +0x58 setup, +0x60 result, +0x68 attacker alliance, +0x70 defender alliance, +0x78 winner_is_attacker, +0x7c result class, +0x80 battle, +0x88 difficulty, +0x8c int (tower-kill multiplier & duel arg), +0x90 tower level 0..4`.
- **battle** (0x188, FUN_142ea0d48/FUN_142ea124c): `+0 = sim+0x8c, +4 timestep, +8 p, +0xc 1-p, +0x10 side-0 towers (0), +0x14 side-1 towers (3 fortified / 1 unfortified / 0), +0x18 1.0, +0x1c tower level multiplier, +0x78 engine, +0x88 side0 (attacker), +0xf8 side1 (defender), +0x168 finished, +0x16c elapsed, +0x170 engagement list (0x50 records), +0x180 front-group-engaged byte, +0x184 stalemate counter`.
- **side** (0x70): `+0 battle, +8 side index (0 attacker / 1 defender), +0x14/+0x18 active groups sorted by position (front first), +0x24/+0x28 all armies, +0x34/+0x38 arrived armies, +0x44/+0x48 eliminated armies, +0x54/+0x58 abilities (0x30 each: +8 strength, +0xc category, +0x10 target count, +0x20 uses, +0x24 mana cost, +0x28 is-spell), +0x60 spell power (decays by +0x64 per step), +0x68 tower kills, +0x6c mana`.
- **army** (0x30+): `+0 side, +8 id, +0x14 arrived, +0x18 arrival time, +0x1c eliminated, +0x20 elimination time, +0x2c/+0x30 all groups, +0x3c/+0x40 active groups, +0x48 removed groups`.
- **group** (0x68, FUN_142ea0e94): `+0 army, +8 type (0 = melee line, else ranged/skirmish group), +0xc speed (first unit's; 0.5 if 0), +0x10 range (0 for type 0), +0x14 position, +0x18 time spent moving this step, +0x1c engaged-in-melee, +0x20/+0x28 enemy groups in reach, +0x30 eliminated, +0x34 time, +0x38/+0x40 list A, +0x48/+0x50 active units, +0x58/+0x60 routed units`.
- **battle unit**: `+0 group, +8 sim unit, +0xc speed, +0x10 morale level (0..7), +0x14 entity count (float), +0x18 hp/entity, +0x1c, +0x20, +0x24 ammo, +0x28, +0x30 ranged-in-melee-line flag, +0x31 routed, +0x34 rout time, +0x38/+0x3c kills (melee/ranged), +0x40/+0x44 losses (melee/ranged), +0x4c/+0x50 cost weights, +0x54/+0x58 kill totals`.
- **sim unit** (0x2a8): `+0 index, +8 army, +0x10 game record, +0x20 class 0..4 (3 = ability/caster-like), +0x28 stat block, +0x1a8 initial state, +0x1c4 current state (mirrored +0x1e0), +0x204 kills, +0x218 pairwise map, +0x290 retreat threshold, +0x294 ammo multiplier, +0x298 morale rate, +0x2a0 damage-transferred`.
`FUN_142ef4418(sim)` = loser alliance, `FUN_142f27c9c(sim)` = winner, `FUN_142eebb8c(alliance)` = "is winner"; `FUN_142ec22a0(battle)` = p = `+8/(+8+ +0xc)`, `FUN_142ecb538` = 1-p (0.5 when both zero).

### Run: FUN_142f0ba78(sim)
```
if both alliances have units:
    FUN_142f130b0(sim)          # pairwise duel precompute -> simunit+0x218
    FUN_142f0b00c(sim)          # FUN_142ee33d0 builds battle + runs loop; then post-sim phases a..k
    if FUN_142f0b744(sim): FUN_142f103b8(sim)   # post-battle (other agent)
```
FUN_142f0b00c post-sim order (High): a. FUN_142f0f378 winner + KPD class; b. FUN_142f07a98 damage transfer; c. FUN_142f0a388 params[7] recovery; d. FUN_142ec58ec chase-down; e. FUN_142edd084 x2 ensured unit loss; f. FUN_142f27d88 expendables / wipe-out / annihilate; g. FUN_142ec64e4 small-unit revival; h. FUN_142ec628c army & alliance wipe, winning general survives; i. FUN_142ec62e4 dead-general revival; j. FUN_142ebd8b0 kill-credit distribution; k. winner units with `+0x1a2` reset to full. (Details in the Casualty section.)

### FUN_142ee33d0 -> FUN_142f0b1c8(battle): THE TIMESTEP LOOP (High)
```
FUN_142ec6408(battle)                      # bring in armies whose arrival time <= 0 (main armies)
for step in 0..199:
    if battle+0x168: break
    dt = battle+4; if step > 149: dt *= 4.0
    FUN_142f1cd50(battle, dt)
battle+0x50 = (battle+0x9c != 0)           # attacker still has groups -> attacker won
collect results (FUN_142f1c150 / FUN_142f1c1a4) -> FUN_142ec0880 copies into sim units
```
Reinforcement armies (FUN_142f12788 with battle_reinforcement_time 0.0) arrive via FUN_142ec5ec8 when `elapsed >= min(army+0x18)`; FUN_142ecb55c places them: melee line at the side's current rear group position (or the enemy front if none), ranged groups at `front -/+ 0.75*range`.

### FUN_142f1cd50(battle, dt): ONE STEP (order High)
```
battle+0x16c += dt
1. FUN_142ef86c0            movement + reach update:
     battle+0x180 = front group engaged?; reset group+0x18 = 0 for all groups
     2x per side: FUN_142f205d4 (advance groups that FUN_142f137c8 allows: the side's leading
       group when it is not engaged and the enemy main line is not > 2x its unit count; FUN_142ebd904
       moves it toward the enemy front: wanted = |pos-enemy_pos| - range (+1 if >1), capped by
       FUN_142ef7aa4 = dt*speed (ranged groups: not past own melee line minus max(2, 0.25*range)),
       move time = clamp(wanted/speed, 0, dt) -> group+0x18 = time, pos -/+= time*speed)
       FUN_142f0847c re-sorts groups by position; FUN_142f26268 clears engaged flags and recomputes
       reach (FUN_142f24b00: melee group: enemy groups within 1.0 are engaged; ranged group: enemy
       groups within range (+0x10) are targets)
     battle+0x184 = stalemate counter: ++ if neither front group moved > 0.5, else 0
2. FUN_142ef48e8(dt)        MELEE phase (pairing, skirmish, excess melee)   -> FUN_142ebeb0c
3. FUN_142f07190(dt)        RANGED phase for groups not engaged in melee     -> FUN_142ebeb0c
4. FUN_142f13fb4(dt)        ABILITIES/SPELLS if |front0 - front1| <= engine+0x192a0 (special_ability_damage_range 100)
5. FUN_142ec2948(dt)        TOWERS (engine+0x19620 battle_tower_base_kps 0.4)
6. FUN_142ec63c0            regroup: ranged units in non-melee groups that should fall back / join melee (FUN_142eeaeec)
7. FUN_142ec6378            regroup: melee-line units that should split off (FUN_142eeae40)
8. FUN_142ec6408            reinforcement arrival (FUN_142ec5ec8) 
9. if elapsed >= engine+0x192dc (min_battle_time_before_retreat 20): FUN_142ec6450  RETREAT
(each of 2,3,5,6,7,8,9 ends with FUN_142ec7b68 = end-of-battle / elimination check)
```
Evidence: `if (0x95 < uVar2) fVar3 = fVar3 * 4.0; ... while (uVar2 < 200)`; `fVar1 = *(float *)(*(longlong *)(param_1 + 0x78) + 0x192dc); if (fVar1 <= elapsed) FUN_142ec6450(param_1);`; `pfVar1 = (float *)(engine + 0x192a0); if (*pfVar1 < |pos0-pos1|) return;` in FUN_142f13fb4.

### Engagement bookkeeping (FUN_142ec0738 on battle+0x170, High)
Every engagement appends a 0x50 record {unit A, deltas(count, ammo, hp, +0x20), morale delta, is_melee, unit B, ...} (FUN_142ebc660/FUN_142eb1834). At the end of melee/ranged phases FUN_142ec0738 applies them: FUN_142ec1294 writes `count -= lost (>=0)`, `morale = clamp(morale + delta, 0, 7)`, `ammo -= used`, `hp` etc. through FUN_142f0fd28 (which also adds entity losses to the victim's `+0x40` melee / `+0x44` ranged counters), credits the attacker with `+0x38/+0x3c` (melee/ranged) kills, `+0x54 += kills`, `+0x58 += kills * record_cost_ratio` (FUN_142eb17c8 = record+0x608 / FUN_143106320 reference). For hp-based units (record+0x5e3) with hp <= 1 the whole count is removed.

## Target selection & engagement

### Melee phase FUN_142ef48e8 (High for structure)
1. FUN_142f117a0 per side: walk the engaged groups (`+0x1c`) front to back and bucket their active units: list0 = all, list1 = ordinary melee-line units (`+0x30 == 0`), list2 = generals / ability units (FUN_142eeb658), list3 = ranged units standing in the melee line (`+0x30 != 0`). Only melee-line groups (`type == 0`) feed lists 1-3.
2. FUN_142ea10d8 builds the **pair list** for A->B and B->A separately: for each of the three buckets, FUN_142f12400 sorts, for every A unit, the B candidates by `pair[0]/pair[1]` = (melee kps A deals) / (melee kps A receives) (FUN_142e99914; the per-unit rows are then sorted by their average ratio FUN_142e957c4). FUN_142ec1b58 then assigns **one-to-one**: each A unit takes its best-ratio B unit that is not already claimed (hash at +0x60); A units that find nobody go to the **unpaired list** (+0x80).
3. FUN_142ec0284 resolves the paired fights with `combat_time = dt - max(timeMovingA, timeMovingB)` (`param_4 - min(groupA+0x18, groupB+0x18)`):
   - neither unit is a skirmisher (FUN_142eeaec4 = class != 0 AND ammo > 0): plain melee `FUN_142ebeb0c(A, B, combat_time, dt, dt, melee=1, 1)`.
   - exactly one is a skirmisher S vs other O: `f = table(speed_S/speed_O)` from **campaign_autoresolver_skirmish_effectiveness_relative_to_speeds** (FUN_1414d0e14 -> db slot 0xe700, FUN_14169cd30 = piecewise-linear interpolation, clamped to the table ends) when S.class in {1,2}; if S is flying (record flags 0x20/0x21, FUN_142e357f8) with ammo, O is not flying and `round(engine+0x19288)` (flying_skirmish_units_use_entire_combat_time 1.0) != 0 then `f = 1.0`; `f = clamp(f, 0, 1)`; `skirmish_time = clamp(f*combat_time, 0, combat_time)`; `ranged_time = min(skirmish_time, range_S / speed_O)`; if `ranged_time > 0`: ranged exchange `FUN_142ebeb0c(S, O, ranged_time, dt, dt, 0, 0)`; then if both still have entities and `combat_time - skirmish_time > 0`: melee for the remainder.
   - both skirmishers: handled as plain melee with flag 0 (`uVar16 = 0`).
   - afterwards FUN_142ec06b0 adds an extra record scaled by `pair[8]`/`pair[9]` (both written as 0 by FUN_142f130b0; buff/debuff hooks, Low).
4. **Excess melee** (the unpaired list of the side with leftovers): candidates = all enemy units with count >= 1 (FUN_142ee046c). For each unpaired unit (not routed, count > 0): FUN_142f118a8 sorts candidates by `pair[6]` (variant-2 melee value; `pair[7]` ranged variant if the unit still has ammo) and the first candidate is attacked through **FUN_142ebf118**; the per-target attacker count (hash FUN_142eb0628) is incremented and when it exceeds `uVar21 = round(<campaign value, load lost by the decompiler>)` the target is removed from the candidate list. When the candidate list is exhausted and the round counter `< round(<second lost value>)` the list is refilled from the full enemy list and another round starts. By elimination (every other autoresolver_* read is accounted for) these are **max_attackers_damaging_a_single_target_in_excess_melee (2)** and the flanked variant/`num_excess_melee_units_receiving_casualties_from_target` (2 / 100). **Medium.**
   FUN_142ebf118(A, B, ranged?, weight): runs the duel core FUN_142ee381c on copies of both states (mode 3 at `FUN_142ef58ec` range if ranged, else 0), then `FUN_142ebeb0c(A, B, dt, weight*(B is hp-based ? engine+0x197f0 [excess_melee_damage_received_from_single_entity_target 0.2] : engine+0x1930c [excess_melee_damage_received_from_target 0.3]), weight*engine+0x19308 [excess_melee_damage_multiplier 0.65], 1, 0)` -- i.e. the excess attacker deals 65 % and receives 30 % (20 % from single-entity targets). **High.**
5. Unpaired units that still found no target (second block) walk the enemy **groups** instead: `dist = |posUnit - posGroup|`, `reach = speed*timestep*battle+0x184` (stalemate counter); if `dist > reach`: `t_travel = clamp((dist-reach)/speed, 0, (dt - moved)*p)`; remaining `(dt - moved)*p - t_travel` is spent in excess melee against the group's best unit, where `p` = FUN_142ec22a0 (attacker share `+8/(+8+0xc)`, i.e. the Lua/params win-chance) for side 0 and `1-p` for side 1. Then the whole procedure is repeated with the sides swapped. **High** for structure, **Medium** for the role of p.

### Ranged phase FUN_142f07190 -> FUN_142f0ada0 -> FUN_142f0b220 (High)
For every group **not engaged in melee** (`+0x1c == 0`), twice: `FUN_142f0b220(battle, group, dt, p, pickMax=1)` and `(..., 1-p, pickMax=0)`.
FUN_142f0b220: target group = FUN_142edcefc(enemy side) = the enemy main-line group if this group is the side's main line, else the enemy group with the largest `sum(+0x4c)+sum(+0x50)` cost among groups that still have fighting units; candidates = its units not out (FUN_142eeb390). For each shooter with ammo (FUN_142ec43bc: class != 0, `+0x30 == 0`, `round(ammo) != 0`): target = candidate with max (pickMax) / min `pair[3]` (= the target's ranged kps back at the shooter; FUN_142e91c10); run the duel core in mode 3 at `range*0.65` (FUN_142ef58ec: `unit_range * engine+0x19568` battle_missile_range_modifier_used_in_ranged_combat; class 3 units use ability range, 10 if none); `FUN_142ebeb0c(shooter, target, dt, w, w, 0, 0)`; the target is removed from the candidate list (one target per shooter, list refilled when empty). Range gating is done by the group reach lists, not here.

### Damage core FUN_142ebeb0c(battle, A, B, dt, wA, wB, melee, flag) (High for structure, Medium for every slot)
`pair = A.map[B]` (16 floats, see below; created on the fly with zero state if missing). Morale rates: `mA = max(pair[11], minimum_morale_loss_per_second)`, `mB = max(pair[10], ...)` (engine+0x19ad4 = 0). If A is class 3 (caster) or (melee and B has no ammo) the B->A ranged slot is zeroed. FUN_142eb3720 builds the **predicted end state** of each unit: `count' = max(0, count - kps*dt)`, `hp' = count'/initial * hp_per_entity`, `ammo' = max(0, ammo - ammo_rate*dt)`, `morale' = min(7, morale + morale_rate*dt)`. Damage multipliers `FUN_142ed9664(A,B) = mult_mod + add_mod/kps` (>= 0.01) from FUN_142ecad64. **Flying**: if exactly one of A/B is flying and `melee` is set, the flyer's dealt multiplier `*= 1 + engine+0x1967c/100` (flying_unit_melee_damage_dealt_modifier 0 -> x1.0) and the non-flyer's dealt multiplier `*= 1 + engine+0x19680/100` (flying_unit_melee_damage_received_modifier -30 -> x0.7). Then `FUN_142f0beec(battle, outA, A, predA, multB*wA, flag)` and `(outB, B, predB, multA*wB, 1)` interpolate the real states (see Casualty application) and FUN_142ebc660 records the engagement.
Pairwise record (FUN_142f130b0 -> FUN_142ebcfa4, keyed by enemy sim-unit index at `simunit+0x218`): `[0] melee kps A->B, [1] melee kps B->A, [2] ranged kps A->B, [3] ranged kps B->A, [4]/[5] ranged duel durations, [6] variant-2 melee value (excess-melee target sort key), [7] variant-2 ranged value, [8]/[9] 0, [10]/[11] morale rates from the A-shoots-B run scaled by +0x298 (B's, A's), [12]/[13] from the B-shoots-A run, [14]/[15] 0`.

### Abilities / spells FUN_142f13fb4 -> FUN_142f0ae48(side, dt) (Medium)
Gate: both sides have groups and `|front0.pos - front1.pos| <= special_ability_damage_range (100)`. For each ability of the side (0x30 records built by FUN_142ebc994 from special_ability_* variables) with uses left and (not a spell, or `mana cost <= side+0x6c`): FUN_142ee4314/FUN_142ec3080 scores every live enemy unit of every enemy group `score = strength(+8) * (count/initial) * (cost+0x4c + cost+0x50) * (100 - resist)/100` (resist = record stats +0x170/+0x17c clamped by virtual limits; category 4 skips entity units; spells additionally `* side+0x60`), keeps the top `+0x10` (category 3) or 1 target(s). Non-spells fire immediately (FUN_142ec0a34: `dmg = strength * int(dt) [* side+0x60 for spells]`; per target `count -= dmg * weight` (category 4: `dmg / total_hp`), uses--, hp scaled for hp units); the single best-scoring spell is cast and `mana -= cost`. `side+0x60 = max(0, side+0x60 - side+0x64)` per step.

### Towers FUN_142ec2948 -> FUN_142f0a984(battle, side, dt, p/1-p, 1-p/p) (Medium)
If the side has towers (`battle+0x14` for the defender, `battle+0x10 = 0` for the attacker): collect the live units of the **front-most enemy group that has any**; per unit `w = (1 - record->+0x158->+0x20/100) * tower_level_multiplier(battle+0x18/+0x1c) * engine+0x19620 (tower_base_kps 0.4) * battle+0 (sim+0x8c)`, `w *= count/100` when count < 100; sort; towers are spread round-robin (`towers/targets` each, remainder to the first ones); `kills = n_towers * dt * w * weight` (two weights p / 1-p applied to the two halves), `count -= min(count, kills)`, `side+0x68 += kills`. Only the defender has towers (3 for battle type 6, 1 for type 9).

### Regrouping (FUN_142ec63c0 / FUN_142ec6378, Medium)
FUN_142ec5d60: for every non-main-line group not engaged, units for which FUN_142eeaeec is true are moved (FUN_142f09a2c + FUN_142ebced8) into the melee line (or a new group). FUN_142eeaeec says yes for a ranged/skirmish unit when: it has no ammo and `cost+0x50 < 0.5*cost+0x4c`; or its own melee line is gone / weaker (`sum(+0x50) <= enemy sum`) and `2*cost+0x50 < cost+0x4c`; generals/ability units only if the side's melee line still exists and (the enemy has < 2 units, or the unit's cost `>= 0.75 * average line cost` and its health `>= 0.85` (`0.65` when `cost > 1.5*avg` or fewer than `enemy_engaged+3` own units engaged)). FUN_142ec5bd4 (main-line groups): units for which FUN_142eeae40 is true (ranged units in the line when the line is not alone / generals whose line still has melee units) are moved to the appropriate ranged group (FUN_142ee79ac), refreshing `+0x30` via FUN_142f105d4.

## Retreat / stance / forced-winner

- **Forced winner** (High): FUN_142f007f0 maps `setup_obj+0x18` {1 -> 0, 2 -> 1, else -1} -> `ctx+0` -> `sim+8`. FUN_142f0f378: `sim+0x7c = 1; if forced: sim+0x78 = forced_alliance+8 and return`; else `sim+0x78 = battle+0x50 (attacker won)` and KPD class: `kw/kl > 3.0 (winner_kpd_major_win_threshold) or kl == 0 -> 0 (decisive); 0.3 (winner_kpd_minor_win_threshold) <= r <= 3.0 -> 1; r < 0.3 -> 2`. The forced winner does not touch the simulation.
- **Retreat decision** FUN_142ec6450 -> FUN_142ec5f08(battle, side, own, enemy) with `own = FUN_142efc69c(side)` = active unit count, `enemy` = the other side's (High):
  ```
  if enemy * engine+0x19274 (num_units_multiplier_vs_enemy_to_allow_retreat 0.75) < own:        # only while not badly outnumbered
      total = FUN_142efc7e8(side)                 # starting unit count (list A of all groups)
      if int(total*0.4) < own:
          n = min(own - int(total*0.4), 2)        # at most 2 retreats per step, never below 40 % of starting units
          for unit in groups front-to-back while n > 0:
              if FUN_142f138a4(unit):             # count (or count*hp for hp units) <= FUN_142f0b7bc
                  unit+0x31 = 1; unit+0x34 = elapsed; move to routed list; n--
          if any: FUN_142ec7b68 (end check)
  FUN_142f0b7bc(simunit) = clamp(record initial entities (+0x540, or +0x548 for hp units) * simunit+0x290, 0, that value)
  simunit+0x290 = clamp(engine+0x19260 (unit_base_retreat_threshold 0.25) + class_table[+4], 0, 1)   (FUN_142f1147c)
  ```
  Evidence: `if ((float)param_4 * *(float *)(engine + 0x19274) < (float)param_3) { ... if ((int)((float)uVar3 * 0.4) < (int)param_3) { uVar5 = iVar4 - (int)((float)uVar3 * 0.4); uVar3 = 2; if ((2 < uVar5) || ...`.
- **Broken units** (FUN_142eeb390, High): a unit is out of the fight when `round(count) == 0`, or its morale level `int(+0x10)` is 6 or 7, or it is its army's general (first unit of army+0x28) with health fraction (FUN_142ee828c) `< 0.25`. FUN_142ec7bd4 marks such units routed (`+0x31`, time), groups with no active units eliminated (`+0x30`), armies with no active groups eliminated (`+0x1c`, `+0x20 = time`).
- **End of battle** (FUN_142ec7b68 -> FUN_142ec7b20 per side, High): after FUN_142ec7bd4, if the side has no arrived armies left: if `all armies (+0x24) == eliminated (+0x44)` -> `battle+0x168 = 1`; otherwise the next reinforcement armies are placed immediately (FUN_142ecb644). Whenever a side changed, the other side's groups recompute reach (FUN_142f08500). The winner is side 0 iff `battle+0x9c != 0` (it still has active groups).
- **Morale as a state**: `+0x10` (0..7) only increases (FUN_142f0beec `max(.., current)`), at rate `(predicted - current) * t * simunit+0x298` with floor `minimum_morale_loss` (engine+0x19ad0 = 0); per-second floor `minimum_morale_loss_per_second` (engine+0x19ad4 = 0) applies to the pairwise morale rates. Reaching 6 removes the unit.
- **Stance** (High for the read, Low for meaning): only in post-battle FUN_142f103b8: `adj = +0.05 if result_alliance+0x4c == 2; -0.05 if == 3` for the loser; `unit_result+0x1d4 = int((rand16/65536*0.1 + 0.1 + adj) * unit_result+0x154)`. No stance read exists anywhere in the simulation (all 648 dumped functions grepped for `+0x4c) ==`).

## Casualty application

### In the loop: FUN_142f0beec(battle, out, unit, predicted, t, ensure) (High)
Given current state S (`+0x10 morale, +0x14 count, +0x18 hp/entity, +0x20, +0x24 ammo`) and the duel-predicted end state P, with `t = engaged_time * weight`:
- ammo: `out.ammo = S.ammo - (round(S.ammo) - P.ammo) * t` if P.ammo is lower, floor 0.
- count/hp: with `dc = min(P.count, S.count) - S.count`, `dh = min(P.hp, S.hp) - S.hp`: if `dc*dh == 0` -> linear `count = S.count - (S.count - P.count)*t` (if `ensure`: at least `initial_entities * engine+0x19a28` = min_entity_reduction_unary_of_max 0.002), `hp = max(1, S.hp - (S.hp - P.hp)*t)`; else solve the quadratic `dc*dh*x^2 + (S.hp*dc + S.count*dh)*x + (S.hp*S.count - min_hp*min_count)*t = 0` for `x` (total hp decreases linearly in t) and set `count = S.count + dc*x`, `hp = max(1, S.hp + dh*x)`; `count <= 0.01 * max_entities -> 0`. Single-entity hp units (`record+0x5e3 && record+0x5a0 == 1`) are re-normalised so `count*hp` is preserved against `hp_per_entity*max`.
- `+0x20`: linear toward P.
- morale: `out.morale = clamp(S.morale + max((P.morale - S.morale) * t * simunit+0x298, engine+0x19ad0), S.morale, 7)`.
The engagement record then carries `S - out` deltas (FUN_142eb1834) and FUN_142ec0738/FUN_142ec1294 writes them into the battle unit (FUN_142f0fd28), crediting kills.
- Count/hp copy-back after the loop: FUN_142ec0880 writes the 7-word battle-unit state into `simunit+0x1c4` (and +0x1e0), `+0x204 = kills(+0x38 + +0x3c)`, `+0x20c = routed(+0x31)`, `+0x214/+0x215 = flags`.

### Post-sim phases on the sim state (High unless noted)
- **State block**: `simunit+0x1a8` initial `{state, +0x1ac initial count, +0x1b4 hp/entity, +0x1c0 ammo}`, `+0x1c4` current `{state (6/7 = out), +0x1c8 count, +0x1cc max hp/entity, +0x1d0 hp/entity, +0x1dc ammo}`; `record+0x544` max entities, `record+0x5e3` hp-based flag, `record+0x548` alternate full-hp reference.
- **Strength** (FUN_142eabf3c): entity units `count/max`, lost `initial/max - strength`; hp units `(hp*count)/(hp_per_entity*max)`.
- **FUN_142f262a4(entry, f)**: `count = round(max*f)` via FUN_142e76248 (`hp/entity = min(total/count, max)`); returns `new - old`; callers do `other_alliance+0x40 -= delta` (pending kill credit), later spread onto units' `+0x208` in 20 %-of-remaining chunks (FUN_142ebd8b0 / FUN_142ec1c64).
- **Wipe-out count** FUN_142ef57e0 = `max(round(max_entities * 0.2 [unit_wipe_out_threshold]), has_general)`; below it and damaged -> count 0 (FUN_142f27e28); `sim+0xc` zeroes the whole losing alliance.
- **Chase-down** (FUN_142ec56a8, skipped for battle types 3/6): routed (`+0x20c`), non-transferred units: `dmg = clamp((clamp((avg_speed_other+10 - speed)/160, 0, 0.2) + alive_ratio*0.05) * (victim is winner ? 0.1 : 1.0), 0, 0.2)`, `count -= max*dmg`.
- **Damage transfer** (FUN_142f07a98, Medium): if damage_transfer_enabled: loser units sorted, first 50 % (damage_transfer_proportion_of_alliance) healed up to the group-B average lost fraction, the rest pushed down to min_health_remaining 0.2, totals reconciled, `+0x2a0 = 1` on healed units.
- **Override recovery** (FUN_142f0a388): alliance `[sim+0x54 ^ 1]` units get `strength += clamp(lost * params[7], 0, 1)`.
- **Ensured unit loss** (FUN_142edd084, Medium): `n = min(floor(loser_hp_share * winner_cost / battle_size_kill_factor * (type 6 ? siege_attack_kill_multiplier 1.75 : 1)), floor(units*0.5)) - already_wiped` lowest-ranked (weight ensured_unit_loss_cp_weight 0) units destroyed; both directions.
- **Revivals**: FUN_142ec6520 dead units with `< 11` entities, not hp-based: `k = round(n * min(alliance_strength, 0.9))` (halved for the loser) revived with `rand[wipeout_count, max(round(max*0.4), wipeout_count)]`; FUN_142ec60d8 dead general of an army with survivors revives unless `lost >= 0.65` (loser) / `0.8` (winner) and not (`record+0x520 == 1` and >= 2 live units); FUN_142f0b810 winner's main general -> `min(initial, wipeout_count)`.
- **Army / alliance wipe** (FUN_142ec5a6c): army `1 - count/initial > 0.92` (wipe_out_army_force_unary_lost) -> 0 (not the winner's main army); loser alliance wiped if any winner record has flag +0x160, or `winner_count/loser_count >= 7.0` and `loser count/max < 0.3`.
- **Expendables** (FUN_142f27cec): live units with `+0x214` whose faction passes FUN_142ed9608 are zeroed.

## Campaign-variable constants seen (constant -> where)

`engine+0x18cd4 + 4*index`; all 58 reads in both dumps:

| offset | var (value) | read in |
|---|---|---|
| 0x1925c | unit_wipe_out_threshold (0.2) | FUN_142ef57e0 |
| 0x19260 | unit_base_retreat_threshold (0.25) | FUN_142f1147c -> simunit+0x290 -> FUN_142f0b7bc / FUN_142f138a4 (retreat) |
| 0x19264 | wipe_out_army_force_unary_lost (0.92) | FUN_142ec5a6c |
| 0x19270 | battle_reinforcement_time (0.0) | FUN_142f11a90 -> FUN_142f12788 |
| 0x19274 | num_units_multiplier_vs_enemy_to_allow_retreat (0.75) | FUN_142ec5f08 (retreat gate) |
| 0x19278 / 0x1927c | winner_kpd_major/minor_win_threshold (3.0 / 0.3) | FUN_142f0f378 |
| 0x19280 | battle_timestep (4.0) | FUN_142ee33d0 -> battle+4 -> FUN_142f0b1c8 |
| 0x19288 | flying_skirmish_units_use_entire_combat_time (1.0) | FUN_142ec0284 (skirmish split) |
| 0x1928c..0x192b0 | special_ability_cp_to_strength_divider (500), min/max_strength_proportion (0/1), damage_damage_min/max (1/30), buff_kps_min/max (0/0.1), debuff_kps_min/max (0/0.1) | FUN_142ebc994 (ability precompute) |
| 0x192a0 | special_ability_damage_range (100) | FUN_142f13fb4 (ability phase gate) |
| 0x192dc | min_battle_time_before_retreat (20) | FUN_142f1cd50 (gate for FUN_142ec6450) |
| 0x192f0 / 0x192f4 | alliance_wipe_out_winner_loser_strength_multiple (7) / loser_strength_of_max_threshold (0.3) | FUN_142ec5a6c |
| 0x19308 | battle_excess_melee_damage_multiplier (0.65) | FUN_142ebf118 (excess attacker dealt) |
| 0x1930c | battle_excess_melee_damage_received_from_target_multiplier (0.3) | FUN_142ebf118 |
| 0x197f0 | battle_excess_melee_damage_received_from_single_entity_target_multiplier (0.2) | FUN_142ebf118 (hp-based target) |
| 0x19568 | battle_missile_range_modifier_used_in_ranged_combat (0.65) | FUN_142ef58ec (duel range, ranged phase & precompute) |
| 0x19618 / 0x1961c | battle_num_defender_towers_in_(un)fortified_settlement (3 / 1) | FUN_142ee33d0 -> battle+0x14 |
| 0x19620 | battle_tower_base_kps (0.4) | FUN_142f0a984 (tower phase) |
| 0x1967c / 0x19680 | flying_unit_melee_damage_dealt/received_modifier (0 / -30 %) | FUN_142ebeb0c |
| 0x197f8..0x19804 | battle_tower_level_1..4_damage_multiplier (0.2/0.4/0.6/0.8) | FUN_142f194a8(sim+0x90) -> battle+0x1c |
| 0x19808..0x19818 | damage_transfer_* (1, 0.5, 0.2, 0, 0) | FUN_142f07a98 |
| 0x19940..0x19954 | chase_down_* (0.1, 1.0, 0.05, 160, 0.2, 0.2) | FUN_142ec56a8 |
| 0x19a0c / 0x19a10 / 0x19a20 | battle_size_kill_factor (1) / siege_attack_kill_multiplier (1.75) / ensured_unit_loss_cp_weight (0) | FUN_142edd084 |
| 0x19a28 | min_entity_reduction_unary_of_max (0.002) | FUN_142f0beec (ensured minimum loss) |
| 0x19ad0 / 0x19ad4 | minimum_morale_loss / minimum_morale_loss_per_second (0 / 0) | FUN_142f0beec / FUN_142ebeb0c |
| 0x194d4..0x194e4, 0x19768 | building/wall damage percentages | post-battle (other slice) |
| db slot 0xe700 | campaign_autoresolver_skirmish_effectiveness_relative_to_speeds table | FUN_1414d0e14 -> FUN_1416aaa7c -> FUN_14169cd30 (speed-ratio interpolation) |

Literals: `200` steps, `0x95`/`4.0` acceleration, `1.0` melee contact distance, `0.75*range` ranged stand-off, `max(2, 0.25*range)` hold-behind-line distance, `0.5` stalemate movement threshold, `0.4`/`2` retreat budget, `0.25` general-health knockout, `6`/`7` morale knockout, `0.01` count floor, `7.0` morale cap, `0.5`/`0.75`/`0.85`/`0.65`/`1.5`/`2.0` regrouping thresholds, `100` ability/tower count normaliser, `0.1`/`0.9`/`0.65`/`0.8`/`0.4` revival rules, `0.2` kill-credit chunk, `10` chase-down speed offset, `0.05`/`0.1` stance.
**Not read anywhere in decomp13/decomp15** (648 functions): bound_max_ranged_kills_per_second (20) and all other bound_*, max_attackers_damaging_a_(flanked_)single_target_in_excess_melee (2/2), num_excess_melee_units_receiving_casualties_from_target (100), casualty_unary_received_by_excess_melee_units_from_target, chase_down_damage_multiplier, max/min_hp_for_enemy_hp_dps_modifier, mana_pool_per_round_per_mana_cost_reduction, battle_damage_modifier_*_at_sea, naval ramming. The bound_* / hp_dps variables belong to the duel core FUN_142e47084 (other agent); the max_attackers values are consistent only with the two dropped `FUN_1405af474()` loads in FUN_142ef48e8.

## Open questions

1. The two rounded values in FUN_142ef48e8 (`auStackX_18[0] = FUN_1405af474()` round cap, `uVar21 = FUN_1405af474()` per-target cap) lost their arguments; identification as max_attackers_* (2) / num_excess_melee_units_receiving_casualties (100) is by elimination only.
2. Exact meaning of pairwise slots [6]/[7] (variant-2 duel outputs used as the excess-melee sort key) and [8]/[9] (zero at precompute, consumed by FUN_142ec06b0) -- needs the duel core's handling of its last argument (0 vs 2).
3. Sort comparators FUN_142eb1518 / FUN_142e90ee0 / FUN_142e9eddc (pair-list and candidate ordering) are not dumped; the keys above are inferred from the key fields written before sorting.
4. `sim+0x8c` (battle+0) multiplies tower kills and is the first duel argument; NOTES call it difficulty, the ctor argument order suggests the 7th arg of FUN_142ec22c4. Unresolved.
5. Meaning of simunit byte `+0x1a2` (winner units reset to full strength at the end), result flags e+0x48/+0x49, `record+0x520`, `record+0x160`, `record+0x6a8`, `record+0x158->+0x20` (tower resistance %?), and the class table (`alliance+0x48`) source rows.
6. FUN_142ec06b0 / pair[8..9] "buff" path and how the alliance ability lists (+0x68/+0x78/+0x88 from FUN_142ebc994) map onto the side ability records (+0x54/+0x58) -- the conversion function (FUN_142f125bc) is still not on disk.
7. Whether reinforcement groups inherit the `0.75*range` placement from the enemy front when the own line is gone (FUN_142ecb55c falls back to the enemy's front group position; sign conventions assumed).

## Functions read

decomp13: FUN_142f0ba78, FUN_142f0b00c, FUN_142f0b744, FUN_142ee33d0, FUN_142f0f378, FUN_142ef4418, FUN_142f27c9c, FUN_142f07a98, FUN_142f0a388, FUN_142ec58ec, FUN_142ec56a8, FUN_142edd084, FUN_142f27d88, FUN_142f27cec, FUN_142f27e28, FUN_142f27cac, FUN_142f0b810, FUN_142ec64e4, FUN_142ec6520, FUN_142ec628c, FUN_142ec5a6c, FUN_142ec62e4, FUN_142ec60d8, FUN_142ebd8b0, FUN_142ec1c64, FUN_142eabf3c, FUN_142e98818, FUN_142e989c0, FUN_142ebd498, FUN_142f262a4, FUN_142e76248, FUN_142ef57e0, FUN_142f1b750, FUN_142f1b6f0, FUN_142f1bd84, FUN_142f1bb40, FUN_142eebb8c, FUN_142ee80c8, FUN_142efc77c, FUN_142ebe098, FUN_142ed9608, FUN_142ef5e24, FUN_142eeb454, FUN_142eeb658, FUN_142e95a18, FUN_142e95b18, FUN_142e960b4, FUN_142f0b1c8, FUN_142f1cd50, FUN_142ea0d48, FUN_142ea124c, FUN_142f11a90, FUN_142ec0880, FUN_142ec08b0, FUN_142ee30b0, FUN_142f1946c, FUN_142f194a8, FUN_142f26fcc, FUN_142ebb1c0, FUN_142ebc994, FUN_142ea1418, FUN_142ec10c4, FUN_142ec1028, FUN_142ea091c, FUN_142ec0ba4, FUN_142ea0a40, FUN_142ea0bf0, FUN_142ea13c8, FUN_142ea16d4, FUN_142ec22c4, FUN_142f007f0, FUN_142e9fea8 (head), FUN_142ee406c, FUN_142ebb9e4, FUN_142f12540, FUN_142f016ac, FUN_142f12fc0, FUN_142f11958, FUN_142f1147c, FUN_142f130b0, FUN_142f1bebc, FUN_142ebcfa4, FUN_142e972b4, FUN_142ef58ec, FUN_142ef5834, FUN_142eb3a0c, FUN_142e38518 (head), FUN_142ee4280, FUN_142f0ec1c, FUN_142f103b8 (head).

decomp15: FUN_142ef86c0, FUN_142ef48e8, FUN_142f07190, FUN_142f13fb4, FUN_142ec2948, FUN_142ec63c0, FUN_142ec6378, FUN_142ec6408, FUN_142ec5ec8, FUN_142ec7b68, FUN_142ec6450, FUN_142ec5d60, FUN_142ec5bd4, FUN_142efa228, FUN_142ecb644, FUN_142ecb55c, FUN_142ec7b20, FUN_142ec7bd4, FUN_142f08500, FUN_142f24b00, FUN_142ec84ac, FUN_142f205d4, FUN_142f137c8, FUN_142ebd904, FUN_142ebd8d8, FUN_142ef7aa4, FUN_142f0847c, FUN_142f26268, FUN_142f0a87c, FUN_142f117a0, FUN_142ea10d8, FUN_142f12400, FUN_142e99914, FUN_142ec1b58, FUN_142eeb844, FUN_142ec22a0, FUN_142ecb538, FUN_142ec0284, FUN_142eeaec4, FUN_142eea2dc, FUN_142e357f8, FUN_1414d0e14, FUN_1416aaa7c, FUN_14169cd30, FUN_142ec0738, FUN_142ec1294, FUN_142eb17c8, FUN_142f0fd28, FUN_142f0a220, FUN_142f0a250, FUN_142ee046c, FUN_142f118a8, FUN_142ec43bc, FUN_142ebf118, FUN_142ebeb0c, FUN_142eb3720, FUN_142ed9664, FUN_142f0beec, FUN_142ebc660, FUN_142eb1834, FUN_142e98158, FUN_142ec06b0, FUN_142ebc724, FUN_142f02ad8, FUN_142ee0738, FUN_142eb0628, FUN_142edf1d0, FUN_142ead314, FUN_142f0ada0, FUN_142f0b220, FUN_142edcefc, FUN_142eba370, FUN_142e91c10, FUN_142f173a0, FUN_142ee7d70, FUN_142eeb390, FUN_142ee828c, FUN_142f0ae48, FUN_142ee4314, FUN_142ec3080, FUN_142ec0a34, FUN_142e9e2d8, FUN_142f0a984, FUN_142e98abc, FUN_142ec5f08, FUN_142efc69c, FUN_142efc7e8, FUN_142efc848, FUN_142f138a4, FUN_142f0b7bc, FUN_142f08408, FUN_142f082b0, FUN_142f08338, FUN_142ef0ccc, FUN_142f16a6c, FUN_142f16aa8, FUN_142eeaeec, FUN_142eeae40, FUN_142ee7dc0, FUN_142f09a2c, FUN_142ebced8, FUN_142eca324, FUN_142ea0e94, FUN_142ee79ac, FUN_1416e3c54, FUN_142ebaf08, FUN_142f105d4, FUN_142e9f894, FUN_142e9107c, FUN_142e917b8, FUN_142e91988, FUN_142e91ccc, FUN_142e92580, FUN_142e92d64, FUN_1419d3888, FUN_1419374c0, FUN_142f08a38.
