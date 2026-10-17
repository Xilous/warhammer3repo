# WH3 autoresolver: outcome, post-battle casualties, results & prediction noise

Source: Ghidra pseudo-C in `C:\Users\jaymi\tools\ghidra_quick\decomp13|decomp12|decomp10|decomp9|decomp8|decomp5` (9.0 build, ImageBase 0x140000000, no whole-program analysis). Offsets below are cross-checked between at least two functions unless marked otherwise. Confidence: **[H]** high, **[M]** medium, **[L]** low.

## Summary

1. Winner = the alliance the main loop leaves standing (`battle_state+0x50`), unless a forced winner (-1/0/1) is set; KPD class (`sim+0x7c`: 0 decisive / 1 close / 2 pyrrhic) = `winner_kills/loser_kills` vs `winner_kpd_major_win_threshold` (3.0) / `winner_kpd_minor_win_threshold` (0.3).
2. A second, strength-based victory type (close/decisive/heroic/pyrrhic, small vs big battle) is written per alliance into the result tree (`+0x50`, `+0x4c`) using literals 0.5/0.588/0.26/0.4/0.83/1.2 and an 11-unit battle-size split.
3. Post-battle pipeline (FUN_142f0b00c), in order: damage transfer (loser, winner), faction-potential/Lua heal (params[7]), chase-down, ensured unit loss (battle_size_kill_factor, x1.75 on siege attack), loser-destroy flag, survivor return (LCG), force/alliance wipe-out (0.92 / 7x / 0.3), general-survives revive, kill-tally distribution.
4. Campaign variables are read from `engine+0x18cd4 + 4*index` (index from `re/ar_indices.json`); no autoresolver constant appears as a literal.
5. Result object (0xd0) per-side blocks `+0x8c..` / `+0xa4..` = `{true BoP%, noisy BoP%, noisy own-casualty%, victory enum, rank category 0..4, inaccuracy%}`; noise is uniform +/-variation from an LCG seeded by battle totals (deterministic).
6. Variation = battle_result_accuracy_* chosen by best-general level difference (>=7 above: 0.0; 3..6: 0.01; -2..2: 0.05; -6..-3: 0.10; <=-7: 0.15) scaled by min(unit counts)/battle_complexity_max_units_for_scale (10).
7. Defaults: win-chance params are 0; the only default modifier is the faction-potential delta (attacker FP - defender FP, capped by faction_potential_fp_delta_max) -> KPS bonus for the stronger side plus a rounded heal fraction params[7].
8. The effect lookup `FUN_141515aa8(..., 0x155)` on `pending+0xe8` is NOT a handicap: it is the settlement tower level (0..4) selecting `tower_level_N_damage_multiplier`.
9. Lua `modify_next_autoresolve_battle` writes params[0..4] + a bool; the bool kills every surviving loser unit; `win_next_autoresolve_battle` sets `pending+0x138` = 1/2 -> forced winner.
10. The prediction run (slot 1) only happens when the local player's faction has effect 0x5e (human) / 0x58 > 0; `pending+0x270 >= 0` overrides the displayed BoP% of both sides.

## Outcome classification

### Layouts used below [H]
- **sim** (0x110, FUN_142ea091c): `[0] engine`; `+0x08 ctx copy` = `+0x08 int forced_winner`, `+0x0c byte = params byte 0x21`, `+0x10..0x30 side-A modifier block (+0x1c = win chance A)`, `+0x30..0x50 side-B block (+0x3c = win chance B)`, `+0x50 float = params[7]`, `+0x54 byte = params byte 0x20`; `+0x58 setup (0x3a0)`, `+0x60 result (0xd0)`, `+0x68 alliance-A sim`, `+0x70 alliance-B sim`, `+0x78 byte winner_is_A (init 1)`, `+0x7c int kpd_class (init 0)`, `+0x80 battle_state`, `+0x88 difficulty`, `+0x8c campaign setting`, `+0x90 tower level`.
- **alliance sim** (0xa0, FUN_142ea0a40): `+0 sim`, `+8 byte is_A`, `+0x10 setup alliance (0x80)`, `+0x18 result-tree alliance (0x60)`, `+0x24/+0x28 forces`, `+0x34/+0x38 units`, `+0x40 int kill tally`.
- **unit sim**: `+0x10 -> unit desc (** -> record: +0x544 max entities, +0x540, +0x548 initial-men override, +0x5e3 single-entity, +0x5bd, +0x160, +0x6a8)`, `+0x18 -> tree unit node (0x1c8)`, `+0x1ac initial alive`, `+0x1b4 per-entity max HP`, `+0x1c8 alive now`, `+0x1cc per-entity HP`, `+0x1d0 HP/entity now (single entity: HP)`, `+0x204/+0x208 kills`, `+0x20c byte routing`, `+0x214/+0x215 flags`, `+0x2a0 byte received-damage-transfer`.
- **result tree**: alliance node 0x60 (`+8 forces`, `+0x10/+0x18 totals`, `+0x28 = sum(force+0x154)`, `+0x48 = sum(unit+0xc4)`, `+0x4c victory enum`, `+0x50 raw class`, `+0x58 ptr`); force node 0x228 (`+8 reinforcement sub-forces`, `+0x18 units`, `+0x154`, `+0x1d4`); unit node 0x1c8.

### Winner [H]
`FUN_142f0f378(sim)` (decomp13), first step of FUN_142f0b00c:
```c
*(sim+0x7c) = 1;                               // default: close
lVar4 = FUN_142ee30b0(sim);                    // sim+8 == 0 -> alliance A, == 1 -> alliance B, else 0
if (lVar4 == 0) {
   lVar4 = (*(char*)(sim[0x10]+0x50) == 0) ? sim[0xe] : sim[0xd];  // battle_state+0x50: "A still standing"
   cVar6 = *(char*)(lVar4+8); *(char*)(sim+0x78) = cVar6;         // winner_is_A
   ... KPD ...
} else *(sim+0x78) = *(lVar4+8);               // forced winner: KPD class stays 1
```
- Forced winner: `FUN_142f007f0` maps `setup_obj+0x18` 1 -> 0 (attacker/alliance A), 2 -> 1 (defender/alliance B), else `0xffffffff`; passed as 8th arg of FUN_142ec22c4 -> ctx[0] -> sim+8; then `setup_obj+0x18 = 0`. [H]
- `setup_obj+0x18` is set in FUN_1426af3bc: `iStack_98 = (iVar2 != 1) + 1` where `iVar2 = FUN_1426b38f8(pending)` (1 if the attacker force list passes FUN_14263665c, 2 if the defender's does [M]) or, if 0, `pending+0x138` (Lua `win_next_autoresolve_battle`: 1 attacker, 2 defender). [H]
- `FUN_142d5fbd8(result, *(winner_alliance+0x10)+0x68, 0x40, -1.0f)` (from FUN_142f103b8) writes `result+4 = winner alliance id` if still -1 (default set by FUN_142d19b3c), `result+0x10 = 0x40`, `result+0xc = -1.0f`, `result[0] = 1`. [H]

### KPD class (sim+0x7c) [H]
```c
uVar2 = FUN_142f1946c(winner);  uVar3 = FUN_142f1946c(loser);   // sum max(0, unit+0x204 + unit+0x208)
if (uVar2 || uVar3) {
  if (uVar3) { f = uVar2/uVar3;
     if (f <= *(engine+0x19278) /*major 3.0*/) { if (*(engine+0x1927c) /*minor 0.3*/ <= f) return; /*1 close*/
                                                 *(sim+0x7c) = 2; return; } /* pyrrhic */ }
  *(sim+0x7c) = 0;   /* decisive: KPD > 3.0, or loser killed nothing */
}
```
`0x19278 = 0x18cd4 + 0x5a4 (winner_kpd_major_win_threshold)`, `0x1927c = +0x5a8 (minor)`. Enum: **0 decisive, 1 close, 2 pyrrhic**. No reader of sim+0x7c found in the dumps besides FUN_142ea091c's init (open question).

### Strength-based victory type (tree +0x50 / +0x4c) [H]
`FUN_142f0ec1c(sim)` sums, for winner then loser: initial strength `FUN_142e31768(unit_desc)` (two floats a+b) and remaining strength `FUN_142e317b0(unit_desc, hp_frac)` with `hp_frac = (alive*hp_now)/(initial*hp_max)`, and counts units with `unit_desc+0x5bd` set vs not. It builds `stats = {W0, L0, W1, L1, -1, -1, nW_flag, nW_other, nL_flag, nL_other, is_winner, ptr, ptr}` and calls `FUN_142d5ce70(tree_alliance, engine, &stats)` for winner (flag 1) then loser (flag 0).

`FUN_142d5dca8` (writes `tree+0x50`):
```
loss  = (W0 - W1)/W0                  // winner loss fraction
ratio = W0 / L0 (1.0 if L0 <= 0)      // winner/loser initial strength
big   = (nW_flag + nL_flag) > 10      // [M] which flag counts as "unit"
if (loss > 0.5 || ratio > 0.588):
    if loss > 0.26:  loss > 0.4 -> class = big ? 6 : 0 (pyrrhic; small battles never pyrrhic)
                     else       -> class = big ? 3 : 0 (close)
    elif ratio > 0.83: ratio < 1.2 -> class 0 (close); else class = big ? 4 : 1 (decisive)
    else -> class = big ? 5 : 2 (heroic: low losses while outnumbered)
else -> class = big ? 5 : 2 (heroic: won while heavily outnumbered)
```
(The stats[4]/[5] != -1 path using model+0xbd8/+0xc40 is never taken: the autoresolver passes -1/-1.)

`FUN_142d5ce70` maps class -> `tree+0x4c`: winner {0,3}->0, {1,4}->1, {2,5}->2, 6->3; loser {0,3}->5, {1,4}->6, {2,5}->7, 6->8. So `+0x4c`: **0 close victory, 1 decisive victory, 2 heroic victory, 3 pyrrhic victory, 5 close defeat, 6 decisive defeat, 7 valiant defeat, 8 defeat vs pyrrhic winner**. `tree+0x58` = pointer from stats or `FUN_141592cc4(model, enum)` (localised record [L]). This enum is what `FUN_142f103b8` tests (`== 2 -> +0.05`, `== 3 -> -0.05`) and what result block field [3] reports.

### Result object (0xd0) and per-side blocks [H]
`FUN_142e9fea8(result, setup_obj, params, setup, difficulty, side_idx, flag, setting, tower_lvl)`:
- defaults: `+0x8c,+0x90,+0x94 = 50.0`, `+0x98 = 4`, `+0x9c = 2`, `+0xa0 = 0` (side A), same at `+0xa4..+0xb8` (side B), `+0xbc = flag`, `+0x88 = difficulty`, `+0xc0..+0xcc = 0`.
- after the sim, `FUN_142f12f68(result)`: `+0xc0/+0xc4 = sum over winner units of (a,b)`, `+0xc8/+0xcc` same over loser, via `FUN_142f1be40(tree_unit)`: single entity `a = +0xb0 (initial), b = +0xb4 (current HP)`; else `a = +0xb0 (initial men)`, `b = (+0xb0/+0x9c) * +0xa0 (alive)`. **c0/c8 = initial, c4/cc = remaining.**
- then `FUN_142ee3b64(out, engine, &{setup, result, this_idx, other_idx, c0, c4, c8, cc, is_winner, flag, first_call})` twice -> `+0x8c..+0xa0` (side `side_idx`, 0 from campaign) and `+0xa4..+0xb8` (other side).

`FUN_142ee3b64` output (6 dwords, decomp12):

| idx | meaning | formula |
|---|---|---|
| [0] | true balance-of-power % for this side | `v = clamp(KPDm + SR, 0.83, 5)*12 + 40 - clamp(40*WL, 0, 100)`, `v = clamp(v, 50, 100)`; loser gets `100 - v`. `KPDm = (c8-cc)/(c0-c4)` (loser losses / winner losses, 100 if winner lost nothing), `SR = c0/c8` (0 if c8 <= 0), `WL = (c0-c4)/c0`. |
| [1] | **displayed** BoP % | `clamp([0] + U2*2*V - V, 0, 100)` |
| [2] | displayed own casualty % | `base = (own_init - own_rem)/own_init*100` (c0/c4 if winner else c8/cc); `clamp(base + U1*2*V - V, 0, 100)` |
| [3] | victory enum | `*(tree_alliance_this + 0x4c)` |
| [4] | rank category 0..4 | from `d = maxGeneralLevel(this) - maxGeneralLevel(other)` (FUN_142ee85cc -> FUN_142d52a2c(force)+0x40, over forces and reinforcement sub-forces; FUN_142d52a2c picks the character entry with `+0x44 in {1,2}`) |
| [5] | inaccuracy % (int) | `V = round(100 * clamp(var*scale, 0, 1))` |

Noise RNG: `seed = (int)(N * own_init) * 0x45c82be5 + 0xd2f65b55`, `N = FUN_142d6e4c0(setup)` = sum of `unit+0x124` over all setup units; `U1 = (seed>>16)/65536`; `seed2 = seed*0x343fd + 0x269ec3`; `U2 = (seed2>>16)/65536`. **Deterministic from the setup: re-running the same pending battle gives identical numbers.** [H]

Early exit: if `flag` (result+0xbc) and either tree alliance `+0x10 == 0` -> `[0] = [1] = 0`. The campaign always passes `flag = 0` (`auStackX_10 &= 0xffffff00` in FUN_1426af3bc). [H]

## Post-battle casualties

Driver `FUN_142f0b00c(sim)`; winner = `FUN_142f27c9c(sim)`, loser = `FUN_142ef4418(sim)`. The decompiler dropped the arguments of FUN_142f07a98 / FUN_142edd084; the adjacent `FUN_142ef4418/FUN_142f27c9c` calls are those arguments (loser-first for the first pair, winner-first for the second) [M]. Order:
1. `FUN_142ee33d0` main loop (other slice) if both sides have units.
2. `FUN_142f0f378` winner + KPD class.
3. `FUN_142f07a98(sim, loser, winner)` then `(sim, winner, loser)` damage transfer.
4. `FUN_142f0a388(sim, sim+0x54, sim+0x50)` faction-potential / Lua heal.
5. `FUN_142ec58ec(sim)` chase-down (both directions).
6. `FUN_142edd084(sim, winner, loser)` and `(sim, loser, winner)` ensured unit loss.
7. `FUN_142f27d88(sim)` removal of flagged units / Lua destroy-loser.
8. `FUN_142ec64e4` survivor return (LCG), `FUN_142ec628c` wipe-outs, `FUN_142ec62e4` general survives, `FUN_142ebd8b0` kill-tally distribution, then units with `+0x1a2` set are removed (`FUN_142f262a4(unit, 1.0)` subtracted from the winner tally).
`FUN_142f0b744`: the write-out `FUN_142f103b8` runs only if the winner's first force still has an effective unit (`FUN_142ee80c8`) or any unit with `+0x1c8 != 0`. [H]

### Chase-down `FUN_142ec56a8(sim, alliance, other, ratio, enemy_speed)` [H]
From `FUN_142ec58ec`, skipped when battle type `*(setup+0xf0)` is 3 or 6. `FUN_142ebe098(alliance)` -> `(n = #units with alive >= wipe count, avg speed of those via FUN_142f1bd84)`. Call 1 `(A, B, nA/nB, avgSpeed_B)`, call 2 `(B, A, nB/nA, avgSpeed_A)`.
```
if divider (0x1994c speed_comparison_divider, 160) > 0:
  mod   = isWinner(alliance) ? 0x19940 winner_modifier (0.1) : 0x19944 loser_modifier (1.0)
  ratio = ratio * 0x19948 surviver_ratio_multiplier (0.05)        // own surviving units / enemy surviving units
  for unit in alliance with unit+0x2a0 == 0 and unit+0x20c == 1 (routing):
     s = clamp((enemy_avg_speed + 10 - unit_speed) / 160, 0, 0x19950 speed_comparison_cap 0.2)
     d = clamp((s + ratio) * mod, 0, 0x19954 maximum_damage_unary 0.2)
     if d > 0:
        multi-entity: alive = round(max(0, alive - max_entities(+0x544) * d))
        single entity: hp = max(0, alive*hp_now - hp_max*max_entities*d); hp <= 0 -> alive = hp = 0, else rescale (FUN_142e76248)
        other+0x40 += killed
```
`chase_down_damage_multiplier` (0x19284) is not read in this slice.

### Damage transfer `FUN_142f07a98(sim, alliance, other)` [M]
Gated by `engine+0x19808` (damage_transfer_enabled). Per-unit 0x20-byte stat from `FUN_142eabf3c`: `+0x10 max entities`, `+0xc max HP`, `+0x18 = +0x1c = health fraction now`, `+0x14 = fraction lost this battle` (initial/max - now/max; single-entity variant uses +0x548/+0x604). Units included when `unit+0x20 == 0` or lost > 0 or `unit_desc+0x6a8`. Sorted (`FUN_142e95b18`, comparator not recovered); first `round(n * 0x1980c proportion_of_alliance 0.5)` = receivers G1, rest = donors G2:
- pool = sum over G2 of `(health - 0x19810 min_health_remaining 0.2)` where health > 0.2 (target set to 0.2); `avg = mean(lost over G2)`.
- G1 keeps units with `lost > avg + 0x19814 diff_from_average_to_transfer`; `new = health + (lost - (((lost-avg)/(1-avg)) * 0x19818 max_diff_from_average_after_transfer + avg))` clamped `[health, 1]`; gain summed.
- Conservation: if gain < pool donors lose `(health-0.2)*gain/pool`, else receivers gain `*pool/gain`. Receivers get `unit+0x2a0 = 1` (exempt from chase-down). `other+0x40 -= net alive change` (FUN_142f262a4 sets alive = max_entities*health).

### Faction-potential / Lua heal `FUN_142f0a388(sim, byte, f)` [H]
`alliance = sim[(byte ^ 1) + 0xd]` (byte 1 -> A/attacker, 0 -> B/defender). For each unit with `lost > 0`: `health += clamp(lost * f, 0, 1)`; the other side's tally is reduced by the restored count. `f = params[7]`, `byte = params byte 0x20` (default `diff > 0`, 0 under Lua override where params[7] = 0 anyway).

### Ensured unit loss `FUN_142edd084(sim, alliance, other)` [M]
`dead = #units of alliance with alive < FUN_142ef57e0 and HP below full`; the rest are sorted (`FUN_142e95a18`, key `0x19a20 ensured_unit_loss_cp_weight`). `S = strength(alliance)+strength(other)` (>= 0.01); `C = sum over other's units of FUN_143121788(unit+0x1b0)`. `n = floor((C/S * strength(other)) / 0x19a0c battle_size_kill_factor * (battle type 6 ? 0x19a10 siege_attack_kill_multiplier 1.75 : 1))`, capped at `floor(C * 0x1980c (0.5))`, minus `dead`. If `0 < n < count` the last `n` sorted units are killed; kills credited to `other+0x40`.

### Unit wipe-out count `FUN_142ef57e0(unit)` [H]
`max(round(max_entities * 0x1925c unit_wipe_out_threshold), has_general_entry ? 1 : 0)`; a unit with `alive < this` counts as destroyed in the checks above.

### Force / alliance wipe-out `FUN_142ec5a6c(sim, alliance, other, &killed)` [H]
- Per force: if alliance lost or force is not the primary force [M]: `FUN_142f1b6f0(force) = 1 - sum(alive)/sum(initial) > 0x19264 wipe_out_army_force_unary_lost (0.92)` -> every unit alive = 0. Else (winner's primary force) if `FUN_142ee80c8` finds no effective unit -> `FUN_142f0b810` restores the first unit (general) to `min(initial, wipe count)` entities.
- Loser alliance only: `A = sum alive(loser)`; if `A != 0`: any **winner** unit with `unit_desc+0x160` -> wipe the whole loser alliance; else if `sum alive(winner)/A >= 0x192f0 alliance_wipe_out_winner_loser_strength_multiple (7)` and `FUN_142f1b750(loser) = sum alive / sum max_entities < 0x192f4 alliance_wipe_out_loser_strength_of_max_threshold (0.3)` -> wipe every loser unit.
- `FUN_142ec628c` adds the killed counts to the opposing `+0x40`.

### Flagged removals / Lua destroy-loser `FUN_142f27d88(sim)` [H]
`FUN_142f27cec`: units with `+0x214` and `FUN_142ed9608(engine, unit_desc)` true (temporary/summoned [L]) are removed. `FUN_142f27e28(alliance, &n, all)` with `all = (alliance lost) && sim+0xc` (Lua bool): `all = 1` zeroes every surviving loser unit; `all = 0` only removes below-threshold units that `FUN_142f1bb40` approves.

### Survivor return `FUN_142ec6520(alliance)` (second LCG) [M]
Dead (`alive == 0`) multi-entity units with `max_entities < 11`. `k = min(n_dead, round(n_dead * min(0.9, alive_ratio(alliance)) * (loser ? 0.5 : 1)))`. List sorted (`FUN_14242deac`), first k revived: `seed = total_kills(alliance) * unit_count`; per unit `seed = seed*0x343fd + 0x269ec3`, `extra = ((seed>>16) * (span+1)) / 0xffff`, `span = max(wipe, round(unit_desc+0x540 * 0.4)) - wipe`; `alive = min(unit_desc+0x540, wipe + extra)`, HP topped up. Alive total credited against the enemy tally (FUN_142ec64e4).

### General survives `FUN_142ec60d8(force)` [M]
If the first unit (general) is dead: loser forces skip revival when loss >= 0.65 and (`unit_desc+0x520 != 1` or < 2 units alive); winner forces when loss >= 0.8 plus extra checks. Revive: single entity `hp = max(10, min((1-loss)*maxHP*0.5, maxHP))`; multi `alive = clamp((1-loss)*initial*0.5 + wipe, wipe, initial)`.

### LCG + "+/-0.05" term in FUN_142f103b8 [H mechanics / L meaning]
After the write-out, over the **winner's** result-tree forces and reinforcement sub-forces:
```
seed = tree+0x28 * tree+0x18 * 0x343fd + 0x269ec3     // tree+0x28 = sum(force+0x154), tree+0x18 = sum(force+0x140)
bias = tree+0x4c == 2 (heroic victory) ? +0.05 : tree+0x4c == 3 (pyrrhic) ? -0.05 : 0
per force: seed = seed*0x343fd + 0x269ec3; force+0x1d4 = (int)((U*0.1 + 0.1 + bias) * force+0x154), U = (seed>>16)/65536
```
`force+0x1d4 = 10..20% (+/-5%) of force+0x154`. `+0x154` is the count field of a small container created per force (`FUN_14135ce94(.., 2, ..)` in FUN_142d1bf48) and summed into the alliance node (FUN_142d52ef4); its meaning (loot/captives/XP) is not recoverable here. This is **not** a casualty scatter (unit counts are untouched) and the field tested is the victory enum, not a stance.

### Per-unit write-out `FUN_142ec1028 -> FUN_142ec10c4` [H]
`tree_unit+0xa0 = alive`, `+0xb4 = HP total`, `+0xbc/+0xc0 = +0x1d4`, `+0x108 = kills`, `+0xac/+0xb0 = initial men (0x604 table, 0x548 override)`, `+0xb8 = +0x1b8`, flags `+0xde` (routed), `+0xdf/+0xe0` (from +0x214/+0x215), `+0xe2/+0xe4 = 5` if alive on the losing side; `FUN_142d7b694(.., +0x1fc, +0x200, 0, 5, 0)` accumulates `+0xc4/+0xc8`. Force node `+0x138 = 0` when its first unit is dead. `FUN_142ec1968`: alliance `+0x48 = sum(unit+0xc4)`. `FUN_142ebf38c`: per alliance `r = kills(other)/(tree+0x10 - tree+0x18)`, per unit `FUN_142ec1a4c(unit, engine, r)` -> `FUN_142f63480/FUN_142f68794(kills*r, tree_unit+0x9c - +0xa0)` writing `+0xfc,+0x100,+0x104` (experience/rank-up [L]).

### Building / wall / tower damage `FUN_142ebee8c(sim)` [H]
Requires a settlement record (`ctx[0xc]+0x38`) and battle type `t` not in `{4,5,7,8,12,13}` (`(0x31b0 >> t) & 1 == 0`). Only **alliance A (attacker)** counts: `E = FUN_142e95ff0(forces A)` (assault equipment [M]), `U = #units A`, `Art = #units A with unit+0x20 == 3`.
```
bld  = E*0x194d4 building_damage_num_assult_equipment_% + U*0x194e4 building_damage_num_units_%
wall = Art*0x194e0 wall_damage_num_artillery_units_%
if A won: breaches = 5 + round(min(Art*0.1, 1)*5)
          bld  += E*0x194dc winner_additional_..._assult_equipment_% + U*0x194d8 winner_additional_..._num_units_%
          wall += breaches*0x19768 winner_additional_wall_damage_per_wall_breach
clamp 0..100; settlement+0x28 (wall health) -= wall*0.01 (>= 0); +0x30 (breaches) += breaches; +0x10 (building health) -= bld*0.01; FUN_142d7b5b0 applies.
```
Towers (`FUN_142ee33d0`): `sim[0x12]` -> `FUN_142f194a8`: 0 -> 1.0, 1..4 -> `0x197f8..0x19804 tower_level_{1..4}_damage_multiplier`; tower count = round(`0x19618 num_defender_towers_in_fortified_settlement`) for type 6, `0x1961c ..._unfortified_settlement` for type 9; `0x19280 battle_timestep`; win chances `sim+0x1c`/`sim+0x3c` are copied into the battle state.

## Prediction vs actual & noise

- `FUN_1426caba4(pending)` (decomp8): if `pending+0x29d && !pending+0x2a0`: `if (attacker && FUN_1426a99ec(pending, attacker->+0x10)) FUN_1426b0cbc(pending,0,0,1)`; always `FUN_1426b0cbc(pending,0,0,0)`; then a UI/event vcall on `model+0x36f0`. [H]
- `FUN_1426a99ec`: slot 1 is computed only when `pending+0x278 == 0` (no scripted battle), neither force has `+0x430` set, the local player's faction equals `FUN_1426ce6bc(pending)`, and `FUN_141515c24(faction+0x128, 6, 0, eff, 0) > 0` with `eff = 0x5e` if `FUN_14248c610(faction)` (human) else `0x58`. So the prediction slot is gated by a faction effect. [H]
- The 4th argument of FUN_1426b0cbc is the slot passed to `FUN_1426af3bc(pending, slot)` and is also stored in the side descriptor (`FUN_1426932e0: *(param_2+0x30) = flag`), the setup descriptor (`FUN_142d276e4: param_1[0x19] (+0x64) = flag`) and passed to `FUN_1426ae958` / `FUN_142d53520`. **The simulator and the noise seed are identical for both slots**; any difference comes from these setup flags (not resolved). [M]
- Results: 0xd0 object at `pending+0x208 + slot*0x10` (pointer at `+0x210 + slot*0x10`). Afterwards `if (*(float*)(pending+0x270) >= 0) { v = min(v, 100); result+0x90 = v; result+0xa8 = 100 - v; }` overrides the **displayed** BoP% (block [1]) of both sides. No writer of `pending+0x270` in the dumps. [H]
- Variation constants (`FUN_142ee3b64`): `d = bestGeneralLevel(this) - bestGeneralLevel(other)`:
  - `d >= 7` -> `0x19500` very_high (0.0), cat 4; `3..6` -> `0x19510` high (0.01), cat 3; `-2..2` -> `0x1950c` moderate (0.05), cat 2; `-6..-3` -> `0x19508` low (0.10), cat 1; `d <= -7` -> `0x19504` very_low (0.15), cat 0.
  - `scale = clamp(min(unitCount(this), unitCount(other)) / 0x1983c battle_result_battle_complexity_max_units_for_scale (10), 0, 1)` (1.0 if the variable <= 0); `var = clamp(variation*scale, 0, 1)`; `[5] = round(var*100)` = **AutoresolvePredictionInaccuracyPercent** ("larger battles and lower general rankings make this larger").
  - `[1] = clamp([0] + noise, 0, 100)`, `[2]` with independent noise, both uniform in `[-var*100, +var*100]` percentage points from the deterministic LCG. Because each side is clamped separately, `+0x90` and `+0xa8` need not sum to 100.
- Balance of power pre-battle: block [0] true, [1] noisy (`result+0x90` attacker, `+0xa8` defender). Frontend lobby `LocalBalanceOfPowerPercent` (`FUN_141f4afc0`) returns `lobby+0xc`, refreshed at most once per second by `FUN_141f5af3c` via a virtual call (slot 0x1c8) whose target is not in the dumps; `AutoresolveBattleResultsContext` (`FUN_141f2a11c`) wraps `lobby+0x5a0` (result pointer) plus `local_side != winner_side`. [M]

## Handicap & overrides

- **The effect-0x155 lookup is a tower level.** `FUN_1426af3bc`: `lVar3 = vcall+0x30(pending+0xe8); FUN_1423c571c(lVar3+0x18, 0); iVar2 = max(0, FUN_141515aa8(lVar3+0x20, 6, 0, 0x155, ..))` -> 9th arg of FUN_142e9fea8 -> FUN_142f007f0 arg 7 -> FUN_142ec22c4 arg 7 -> FUN_142ea091c arg 8 -> `sim+0x90` -> `FUN_142ee33d0: FUN_142f194a8((int)sim[0x12])` -> `tower_level_{1..4}_damage_multiplier`. `pending+0xe8` is the settlement/garrison object (also used for `+0x390` and vcall `+0x78` garrison checks in FUN_1426b0cbc). `FUN_141515aa8` is a binary search over a sorted (`scope<<40 | effect`) table returning `round(entry+0x1c)`. [H] `nominal_autoresolver_handicap` / `override_autoresolve_handicap` are not referenced anywhere in the dumped chain (open).
- **Defaults `FUN_1426af6a8`** (9 dwords: 8 floats + flag word), all zero except:
  - `fp = FUN_1429ce7a0(attacker, defender)`: AI side -> `FUN_1429ce068` = max faction potential (`FUN_1429cd374(faction+0x10a0)`: sum of 4 ints + `FUN_1426043d4`, only for AI factions with `+0x1bc4 > 1`) over the force's faction and co-belligerents (`+0x438` list); human side -> `FUN_1429c143c(model, FUN_1424750f0(difficulty, flag))` = round of `faction_potential_ai_vs_player_{easy 0x6af8, normal 0x6b04, hard 0x6afc, vhard 0x6b08, legendary 0x6b00}`; both human -> 0/0.
  - `diff = clamp(fp_att - fp_def, -cap, cap)`, `cap = round(model+0x6b24 faction_potential_fp_delta_max)`.
  - `bonus = FUN_1429c86dc(model, diff, !inList)`: if `cap >= 1`: `a = |diff|` (times `model+0x6b38 faction_potential_shroud_multiplier` when `FUN_1426bae7c(model, &pending+0xc8)` is false); if `a >= model+0x6b20 faction_potential_fp_delta_kps_min` then `bonus = a / fp_delta_max * model+0x6b2c faction_potential_kps_multiplier_max`.
  - `diff >= 0` -> `params[5] = bonus` (attacker) else `params[6] = bonus` (defender); `params[7] = FUN_1429c8698(model, diff)` (a rounding; argument lost) = heal fraction; `byte 0x20 = (diff > 0)`.
  - In `FUN_142ec22c4`: `winA = clamp(p0/(p0+p1), 0, 1)` (0.5 when both 0), `winB = 1 - winA`; side-A block gets `max(0,p4) + max(0,p5)`, side-B gets `max(0,p3) + max(0,p6)` (fed to FUN_142ebb9e4/FUN_142ee406c, other slice); `ctx+0x48 = p7`, `ctx+0x4c = byte 0x20`, `ctx+4 = byte 0x21`. `p2` is never read. [H]
- **Lua `modify_next_autoresolve_battle` (`FUN_1427e1110`)**: requires `pending+0xd8 == 1`; reads 1 bool then 4 numbers and writes `pending+0x13c = n4`, `+0x140 = n3`, `+0x144 = 0`, `+0x148 = n2`, `+0x14c = n1`, `+0x150..0x158 = 0`, `+0x15c = bool << 8` (byte 0x21), then `FUN_1426caba4`. Assuming the binding reads Lua arguments last-to-first [M]: `attacker_win_chance -> p0`, `defender_win_chance -> p1`, `attacker_losses_modifier -> p3` (added to the **defender** block), `defender_losses_modifier -> p4` (added to the **attacker** block), `destroy_loser -> byte 0x21`. `FUN_142f27a6c` activates the override when any of p0..p7 != 0 or byte 0x21 == 1; the override **replaces** the defaults (no faction-potential bonus, p7 = 0). The bool zeroes every surviving loser unit (`FUN_142f27d88`). [H]
- **Lua `win_next_autoresolve_battle(faction)` (`FUN_142829800`)**: `pending+0x138 = 1` if the faction is on the attacker side, `2` for defender; recomputes only when the value changed. The forced winner leaves KPD class = 1 and still runs the whole casualty pipeline. [H]
- `sim+0x8c` ("override" in NOTES) is `*(*(*(*(pending+0xc0)+0x90)+0x5bb0)+0xe0)+0x2c`, a campaign-model setting passed to `FUN_142f130b0`'s pairwise strength computation and the battle state; `result+0x88` ("difficulty") receives 0. [M]

## Campaign-variable constants seen (constant -> where)

Engine array: `engine + 0x18cd4 + 4*index` (`re/ar_indices.json`). Model array: `model + 0x5be8 + 4*index` (`re/cv_globals.json`).

| variable | offset | function |
|---|---|---|
| winner_kpd_major_win_threshold (3.0) / minor (0.3) | 0x19278 / 0x1927c | FUN_142f0f378 |
| wipe_out_army_force_unary_lost (0.92) | 0x19264 | FUN_142ec5a6c |
| alliance_wipe_out_winner_loser_strength_multiple (7) / loser_strength_of_max_threshold (0.3) | 0x192f0 / 0x192f4 | FUN_142ec5a6c |
| unit_wipe_out_threshold | 0x1925c | FUN_142ef57e0 |
| chase_down_winner_modifier (0.1) / loser_modifier (1) / surviver_ratio_multiplier (0.05) / speed_comparison_divider (160) / speed_comparison_cap (0.2) / maximum_damage_unary (0.2) | 0x19940 / 0x19944 / 0x19948 / 0x1994c / 0x19950 / 0x19954 | FUN_142ec56a8 |
| chase_down_damage_multiplier (1) | 0x19284 | no reader found |
| damage_transfer_enabled / proportion_of_alliance (0.5) / min_health_remaining (0.2) / diff_from_average_to_transfer / max_diff_from_average_after_transfer | 0x19808 / 0x1980c / 0x19810 / 0x19814 / 0x19818 | FUN_142f07a98 (0x1980c also FUN_142edd084) |
| battle_size_kill_factor / siege_attack_kill_multiplier (1.75) / ensured_unit_loss_cp_weight | 0x19a0c / 0x19a10 / 0x19a20 | FUN_142edd084 |
| building_damage_num_assult_equipment_% / winner_additional_building_damage_num_units_% / winner_additional_..._assult_equipment_% / wall_damage_num_artillery_units_% / building_damage_num_units_% / winner_additional_wall_damage_per_wall_breach | 0x194d4 / 0x194d8 / 0x194dc / 0x194e0 / 0x194e4 / 0x19768 | FUN_142ebee8c |
| battle_result_accuracy_{very_high, very_low, low, moderate, high}_prediction_variation (0, 0.15, 0.10, 0.05, 0.01) | 0x19500 / 0x19504 / 0x19508 / 0x1950c / 0x19510 | FUN_142ee3b64 |
| battle_result_battle_complexity_max_units_for_scale (10) | 0x1983c | FUN_142ee3b64 |
| battle_tower_level_{1..4}_damage_multiplier | 0x197f8 .. 0x19804 | FUN_142f194a8 (from sim+0x90) |
| battle_num_defender_towers_in_{fortified, unfortified}_settlement, battle_timestep | 0x19618 / 0x1961c / 0x19280 | FUN_142ee33d0 |
| faction_potential_ai_vs_player_{easy, hard, legendary, normal, vhard} | model 0x6af8 / 0x6afc / 0x6b00 / 0x6b04 / 0x6b08 | FUN_1429c143c |
| faction_potential_fp_delta_kps_min / fp_delta_max / kps_multiplier_max / shroud_multiplier | model 0x6b20 / 0x6b24 / 0x6b2c / 0x6b38 | FUN_1429c86dc, FUN_1426af6a8 |
| literals 0.5, 0.588, 0.26, 0.4, 0.83, 1.2, 11 units | - | FUN_142d5dca8 (victory type) |
| literals clamp 0.83..5, *12+40, *40, clamp 50..100 | - | FUN_142ee3b64 (BoP%) |
| literals 0.1 + U*0.1, +/-0.05 | - | FUN_142f103b8 |
| literals 0.65, 0.8, 0.5, 10 HP | - | FUN_142ec60d8 (general survives) |
| literals 0.9, 0.5, 0.4, < 11 entities | - | FUN_142ec6520 (survivor return) |

## Open questions

1. Meaning of result-tree force `+0x154` (container count summed into alliance `+0x28`) and `+0x1d4` (10-20% +/-5% of it, FUN_142f103b8): loot / captives / XP? Needs the campaign consumer of the 0x228 force node (FUN_142d1a3f4 copies it to `param_1[0x75]`).
2. Consumer of `sim+0x7c` (KPD class). None found besides the init in FUN_142ea091c.
3. Meaning of `unit_desc+0x5bd` (splits the 11-unit big/small battle test), `+0x160` (winner unit forcing total loser wipe-out), `+0x214/+0x215` (post-battle removals), `+0x6a8`.
4. What the prediction flag (`FUN_1426b0cbc` arg 4 -> setup descriptor `+0x64`, side descriptor `+0x30`) changes inside FUN_142d276e4 / FUN_142d53520 / FUN_1426ae958 — the only possible source of prediction-vs-actual differences.
5. Effect ids 0x5e / 0x58 (prediction gate) and 0x155 (tower level): need the effects-table id mapping.
6. Writer of `pending+0x270` and the campaign consumer of result blocks `+0x8c..+0xb8` (whether the pre-battle panel shows [0] or [1]); lobby getter is a virtual call (slot 0x1c8), target unknown.
7. Body of `FUN_1429c8698` (params[7] heal fraction) — only `round()` survived decompilation.
8. Argument order of the FUN_142f07a98 / FUN_142edd084 calls in FUN_142f0b00c (inferred from the adjacent accessor calls).
9. Sort comparators in damage transfer (FUN_142e95b18) and ensured loss (FUN_142e95a18); the "primary force" test in FUN_142ec5a6c; `FUN_142e95ff0` (assault-equipment count).
10. `chase_down_damage_multiplier` (0x19284) has no reader in the dumped functions.

## Functions read

decomp13: FUN_142ec22c4, FUN_142ea091c, FUN_142ea0a40, FUN_142ec0ba4, FUN_142ea13c8, FUN_142f12fc0, FUN_142ebb9e4, FUN_142ee46c0, FUN_142f0ba78, FUN_142f0b744, FUN_142f0b00c, FUN_142f130b0, FUN_142f0f378, FUN_142ee30b0, FUN_142f1946c, FUN_142f07a98, FUN_142eabf3c, FUN_142e95b18, FUN_142f262a4, FUN_142f27c9c, FUN_142ef4418, FUN_142f0a388, FUN_142ec58ec, FUN_142ebe098, FUN_142ec56a8, FUN_142f1bd84, FUN_142edd084, FUN_142e960b4, FUN_143121788, FUN_142ef57e0, FUN_142f27d88, FUN_142f27cec, FUN_142f27e28, FUN_142ec64e4, FUN_142ec6520, FUN_142ec628c, FUN_142ec5a6c, FUN_142f1b6f0, FUN_142f1b750, FUN_142efc77c, FUN_142f27cac, FUN_142f0b810, FUN_142eebb8c, FUN_142ee80c8, FUN_142ec62e4, FUN_142ec60d8, FUN_142ebd8b0, FUN_142f103b8, FUN_142ec1028, FUN_142ec10c4, FUN_142d7b694, FUN_142d5fbd8, FUN_142d52ea0, FUN_142d52ef4, FUN_142ebf38c, FUN_142ec19bc, FUN_142edf828, FUN_142ec1a4c, FUN_142ec1968, FUN_142ebee8c, FUN_142f0ec1c, FUN_142d5ce70, FUN_142d5dca8, FUN_142e31768, FUN_142f1be40, FUN_142ea0d48, FUN_142ec0880 (head), FUN_142ee33d0 (head), FUN_142f194a8, FUN_142f12f68, FUN_142ebe004, FUN_142eba060.

decomp12/10: FUN_142e9fea8, FUN_142f007f0, FUN_142ee3b64, FUN_142ee85cc, FUN_142d805ec, FUN_142d6e4c0, FUN_142d52a2c, FUN_142d19b3c, FUN_1426af3bc, FUN_1426af6a8, FUN_1426484c4, FUN_142f27a6c, FUN_141515aa8, FUN_1426b38f8, FUN_1429ce7a0, FUN_1429ce068, FUN_1429cd374, FUN_1424750f0, FUN_1429c143c, FUN_1429c86dc, FUN_1429c8698, FUN_1426bae7c, FUN_1426b0cbc, FUN_142d1bf48, FUN_142d1a3f4 (head).

decomp9/8/5: FUN_1426932e0 (head), FUN_142d53520 / FUN_142d276e4 (parameter usage only), FUN_1426caba4, FUN_1426a99ec, FUN_1427e1110, FUN_142829800, FUN_141f2a11c, FUN_141f4afc0, FUN_141f5af3c, FUN_141f2c030.

Data: `re/NOTES.md`, `re/ar_indices.json`, `re/cv_globals.json`.
