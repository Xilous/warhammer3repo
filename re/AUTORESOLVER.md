# How Total War: Warhammer III resolves a battle automatically

Reverse-engineered from the 9.0 build of `Warhammer3.exe` on 16 October 2026, using Ghidra pseudo-C and the
game's own data tables. Detailed evidence, offsets and function addresses are in `re/analysis/*.md` and
`re/NOTES.md`. Confidence tags: **H** = arithmetic and constants read directly from the code, **M** = consistent
across several sites but a name was inferred, **L** = single site or inferred by elimination.

The pseudo-C was produced without whole-program analysis, so function parameter lists are frequently wrong,
while control flow, struct offsets, constants and arithmetic are reliable. Everything below rests on the latter.

## 1. The one-paragraph version

The autoresolver is a small one-dimensional battle simulator, not a strength comparison. Every unit is turned into
a combat-stat block derived from its real battle stats (entities, hit points, melee attack and defence, armour,
missile damage, range, fire rate, ammo, speed, mass, leadership, formation). For every attacker unit against every
defender unit the game runs a closed-form "duel" (melee, and each side shooting the other at 65% of range) and
converts the result into kills per second. The campaign modifier tables (battle type, player type, difficulty,
stance) multiply or add to those rates. Then a 200-step timestep loop (4 s per step, 16 s after step 150, so at most
1400 s of simulated time) moves the two lines toward each other, pairs melee units one-to-one by best kill ratio,
lets leftover units pile on as "excess attackers" at 65% effect, has non-engaged ranged groups shoot, fires abilities
and settlement towers, and lets a side retreat units once 20 s have passed. Casualties are interpolated toward the
duel-predicted end state; morale is a 0..7 band that only rises and removes the unit at 6. After the loop a
post-battle pipeline applies damage transfer, chase-down of routing units, "ensured" losses, wipe-outs and general
survival, classifies the victory, and produces the balance-of-power percentage plus a deterministic "noise" term
whose size depends on general rank and battle size. Unit combat potential (`melee_cp`/`missile_cp`) is used only
for ordering and bookkeeping, not for the fight itself.

## 2. Where it lives and how a battle reaches it

| Stage | Function | What it does |
|---|---|---|
| Lua `cm:win_next_autoresolve_battle` | `FUN_142829800` | sets pending battle `+0x138` = 1 (attacker) / 2 (defender) |
| Lua `cm:modify_next_autoresolve_battle` | `FUN_1427e1110` | writes override parameters at pending `+0x13c..0x15c` |
| Regenerate pending result | `FUN_1426caba4` → `FUN_1426b0cbc` | builds the battle setup (armies, units, map, towers), computes the result once for the prediction slot and once for the actual slot |
| Parameters | `FUN_1426af3bc` + `FUN_1426af6a8` | default win-chance parameters are zero; the only default modifier is the faction-potential delta between the sides; the "effect 0x155" lookup is the settlement tower level 0..4 |
| Simulator entry | `FUN_1426484c4` → `FUN_142e9fea8` → `FUN_142f007f0` → `FUN_142ec22c4` | allocates the 0xd0-byte result, normalises win chances, builds the per-side modifier blocks, constructs the simulation object (`FUN_142ea091c`) and runs it (`FUN_142f0ba78`) |
| Precompute | `FUN_142f130b0` | pairwise duel matrix |
| Loop | `FUN_142ee33d0` → `FUN_142f0b1c8` → `FUN_142f1cd50` | the timestep loop and its per-step phases |
| Post-battle | rest of `FUN_142f0b00c`, then `FUN_142f103b8` | casualties, wipe-outs, victory type, result blocks |
| Frontend lobby | CCO getters `0x141f2a11c`, `0x141f4afc0`, `0x141f2c030` | custom-battle lobby autoresolve preview |

The 83 `autoresolver_*` campaign variables are copied verbatim into the simulator's engine object at
`engine + 0x18cd4 + 4 × index` (index = position in the campaign-variable descriptor array, `re/ar_indices.json`);
66 of them are read by the simulator (**H**, every read matches its name). They never appear as literals, which is
why string, index and hash scans of the binary found nothing.

## 3. Unit preparation

### 3.1 Combat-stat block (0x17c bytes per unit) — **H/M**
Built by `FUN_142e38518` from the game unit record (`FUN_142e6836c` plus sub-fillers `FUN_142e455f0` missile
weapon, `FUN_142e45dc0` artillery, `FUN_142e45944` entity, `FUN_142e459e4` melee stats, `FUN_143019990` ammo).
Confirmed contents: entity count, max and current hit points per entity, ammo (carriers × primary_ammo), missile
damage and armour-piercing damage (base attribute plus percentage modifier), explosion damage and radius,
penetration, projectile velocity, **fire rate = shots_per_volley / max(4 s, (100 − reload_skill%) × base_reload)
× rate factors**, range, "ignores shields" flag, leadership, missile block chance, melee attack and defence
(each times a per-unit multiplier table T(i) whose origin is unknown, default 1.0), charge bonus, bonus-vs trio,
max targets and splash per attack from the melee weapon record, crew divisor = men / (engines or mounts), mass
(plus rider mass when mounted), speed and run speed, entity radius and size class, formation spacing, number of
ranks, hit-point regeneration per second from passive abilities, single-entity flag (hit points scaled instead of
entity count), unbreakable flag (from several boolean attributes), "fires while charging" flag. Artillery sums
its engine weapons (fire rate = sqrt of the sum, range averaged). Melee attack, defence and armour are reached
through adapter objects whose vtables were outside every dump, so armour's exact slot is still inferred (**M**).
Full offset and attribute-index tables are in `re/analysis/unit_stats_and_modifiers.md`.

### 3.2 Per-unit modifier vector — **H**
Each simulated unit carries six kill-rate modifiers (melee multiplier and addition, missile multiplier and
addition, plus two per-shot missile terms), a per-target-class map, a retreat threshold, an ammo multiplier and a
morale-loss scale. They come from:

1. **Battle type selection** (`FUN_142ee172c`): rows of `autoresolver_battle_types` are scored against the setup
   with weights stance 32, encampment 16, battle type 8, night 4, difficulty 2 (tri-state columns; 0x17 = any battle
   type). The best row wins.
2. **Lookup rows** (`FUN_142ee406c`): `autoresolver_modifier_group_lookups` rows for that battle type are filtered
   by `player_type` (human/AI, attacker/defender, difficulty = clamp(2 − raw, 0, 5), 0 = any) and applied to side
   A or side B.
3. **Modifier values** (`FUN_142ebfc7c`): `value × mechanic` where mechanic 1 = general level, 2 = sum of siege
   equipment strength, otherwise 1. Kinds decoded: win-chance share, retreat modifier, melee multiplier/addition,
   missile multiplier/addition, per-shot missile multiplier/addition, ammo multiplier, morale-loss scale. Targets
   are a unit class (20 entries) or a class-vs-class map.
4. **Ability buffs/debuffs** (`FUN_142ec0ba4`): `m' = (m+1) × (buff_avg+1) / (debuff_avg+1) − 1` on the melee and
   missile multipliers, where the averages are the side's ability lists divided by its own unit count.
5. **Lua / faction-potential parameters** (`FUN_142ebb9e4`): attacker block gets `p4 + p5`, defender `p3 + p6` as
   kill-rate multiplier bonuses.

`FUN_142ecad64` combines them: `kills/s = max(kps_base × max(1 + Σmultipliers, 0.01) + Σadditions, 0)`.

### 3.3 Retreat threshold and ammo — **H**
`retreat_threshold = clamp(unit_base_retreat_threshold (0.25) + class_offset, 0, 1)`; ammo is multiplied by the
side's ammo multiplier. Special abilities become ability records: strength = clamp(cost × ability_value / 500, 0, 1),
damage = 1 + 29 × strength, buff/debuff kill-rate modifier = 0.1 × strength (the `special_ability_*` variables).

### 3.4 Combat potential — **H**
`CP = (melee_cp, missile_cp) + ability CP (top 10 abilities, weights 1 − j×0.9/(n−1)) × hp_ratio`, then
`multiplier × CP + additive_mod` from `autoresolver_ai_usage_group_combat_potential_modifiers` keyed by the unit's
`ai_usage_group`. CP is used for ordering (which unit the excess attackers target, which groups ranged fire
prefers, kill-credit weighting) and for the strength ratios in the post-battle classification, **not** for the duel
math itself.

## 4. The duel matrix (`FUN_142f130b0`) — **H**

For every attacker unit A and defender unit B the game runs six duels and stores the outcome as 16 floats keyed by
enemy unit: melee kills/s each way, ranged kills/s each way, the two ranged durations, two "variant" values used as
sort keys for excess melee, and morale-loss rates (scaled by the victim's morale-loss scale).

Each duel (`FUN_142f1bebc` → `FUN_142ee381c` → `FUN_142e47084`) copies both stat blocks, normalises multi-entity
units by a unit-scale divisor and single-entity units by their hit-point divisor, runs one of ten duel types, and
divides the before/after deltas by the duel duration (10 s if the duel reports zero). Only two types are used by
the precompute: **type 0** (melee at distance 0) and **type 3** (A fires at B from `range × 0.65`, no reply). The
unit's `ar_unit_category` does not select the duel type; category behaviour emerges from "has a missile weapon",
range and the modifier layer.

### 4.1 Melee duel (type 0, `FUN_142e473d0` → `FUN_142e2c460`) — **H** arithmetic
Closed form, one attack per engaged entity per 4 s timestep:

```
frontage_X    = entities of X on the contact line, from entity radius × count / ranks (FUN_142e4b1d8)
engaged_X     = frontage_X × (3 if "engages 3× frontage" flag else 1)
dmg_X         = hit%(MA_X, MD_Y, charge bonus, bonus-vs, flank/rear) × armour_reduced(base, ap, armour_Y) / 100
                capped at min(0.75 × max_targets, count_Y) × hp_per_entity_Y, plus secondary weapon per step
need_X        = sqrt(morale_fraction_Y) × total_hp_Y / dmg_X          # attacks X needs to break Y
rounds_X      = need_X / engaged_X
winner        = fewer rounds; duration = 4 s × rounds × outnumbering correction ((1 − r³) × 0.15 + 0.7)
```
Casualties from damage `d` on a unit with total hit points `T`: survivors = `count × (1 − x^1.5)`, `x = d/T`,
so half the pool of hit points kills about 35% of the entities (wounds spread over survivors).

Charge phase (`FUN_142e2c0a8`): contact hits scaled by max targets; impact = mass ratio × speed when the unit has a
charge bonus; a 10 m point-blank volley if it fires while charging. A unit whose charge discriminators exceed the
enemy's by 3.5× cycle-charges: six timesteps of melee, disengage, re-charge.

### 4.2 Ranged volley (type 3, `FUN_142e2cc68` / damage `FUN_142e324bc`) — **H** structure
```
p_hit     = clamp(k × accuracy / distance², 0.01, 1) × (1 − block% / 100 unless shooter ignores shields)
dmg_shot  = armour_reduced(base, ap) × p_hit × entities hit (1 + penetration + explosion radius / spacing)
need      = ceil(morale_fraction_T × total_hp_T / dmg_shot);   shots = min(need, ammo)
time      = shots / (firing_weapons × fire_rate)
```
Distance for the precompute is `range × battle_missile_range_modifier_used_in_ranged_combat (0.65)`; artillery
(unit class 3) uses its full range.

### 4.3 Morale in the duel — **H**
Seven bands (0 best, 6 broken). A band drops by `damage_fraction² × (leadership × k + c)`; the fraction of hit
points that must be destroyed to break a unit is `sqrt(band_value / scale)`, fixed at 0.95 for unbreakable units.

## 5. The battle loop (`FUN_142f0b1c8`, `FUN_142f1cd50`) — **H**

The battlefield is a line. Each army is split into groups: one melee line (type 0) plus ranged/skirmish groups
held 0.75 × range behind their own line. The attacker moves toward −x, the defender toward +x; melee contact at
distance ≤ 1.0. Reinforcement armies arrive when the elapsed time passes their arrival time
(`battle_reinforcement_time` = 0) and are placed behind the current rear group.

```
for step in 0..199:                                  # exit early when one side is eliminated
    dt = battle_timestep (4 s);  if step > 149: dt = 16 s
    1. movement and reach: the leading unengaged group advances toward the enemy front unless the enemy main
       line has more than 2× its units; move time is subtracted from this step's fighting time
    2. MELEE (FUN_142ef48e8):
         pair the engaged units one-to-one by best (kills dealt / kills received) from the duel matrix
         skirmisher vs non-skirmisher: split the time by the campaign_autoresolver_skirmish_effectiveness table
           interpolated at speed_skirmisher / speed_enemy (flying skirmishers get the whole time); ranged time is
           capped at range / enemy_speed; the rest is melee
         flying vs ground melee: flyer deals ×1.0, ground deals ×0.7 to the flyer (flying_unit_melee_*_modifier)
         leftover units are EXCESS ATTACKERS: they deal 0.65× (battle_excess_melee_damage_multiplier) and
           receive 0.3× (0.2× from single-entity targets); at most 2 attackers per target (by elimination, M);
           their fighting time is scaled by the attacker's win-chance share p
    3. RANGED (FUN_142f07190): every group not in melee shoots twice (weights p and 1−p) at the enemy main line or
       the most valuable enemy group, choosing the target with the max / min return fire
    4. ABILITIES (FUN_142f13fb4): only while the front lines are within special_ability_damage_range (100);
       targets scored by strength × health × cost × (100 − resistance); spells cost mana
    5. TOWERS (FUN_142ec2948): defender only, 3 towers in a fortified / 1 in an unfortified settlement, kill rate
       battle_tower_base_kps (0.4) × tower-level multiplier (0.2/0.4/0.6/0.8) spread over the front enemy group
    6-7. regrouping: ranged units out of ammo or whose line is gone join the melee line, and vice versa
    8. reinforcement arrival
    9. RETREAT (FUN_142ec6450), only once elapsed ≥ min_battle_time_before_retreat (20 s): a side may retreat
       only while own_units > 0.75 × enemy_units; at most 2 units per step, never below 40% of its starting unit
       count; a unit retreats when count ≤ retreat_threshold × starting entities
    each phase ends with an elimination check: a unit is out at count 0, morale band 6 or 7, or a general below
    25% health; a side with all armies eliminated and no reinforcements ends the battle
```

Casualty application per engagement (`FUN_142f0beec`): the unit state is interpolated toward the duel-predicted
end state over the engaged time, with total hit points dropping linearly (a quadratic solve splits it between
entity count and hit points per entity), ammo linearly, and the morale band rising at the unit's morale-loss scale
(floor `minimum_morale_loss` = 0). Counts below 1% of maximum are zeroed. The "ensured loss" path forces at least
`min_entity_reduction_unary_of_max` (0.002) of max entities.

## 6. After the loop (`FUN_142f0b00c` tail, `FUN_142f103b8`) — **H** unless noted

1. **Winner and kills-per-death class** (`FUN_142f0f378`): the side still standing wins, unless a forced winner was
   set by Lua. Class 0 decisive if winner_kills / loser_kills > 3.0 (`winner_kpd_major_win_threshold`) or the loser
   killed nothing, 1 close between 0.3 and 3.0, 2 pyrrhic below 0.3. A forced winner keeps class 1 and still goes
   through every casualty step.
2. **Damage transfer** (M): among the loser's units, the healthier half donate hit points down to
   `damage_transfer_min_health_remaining` (0.2) so that the hardest-hit units are pulled toward the average loss.
3. **Faction-potential / Lua heal**: `health += clamp(lost × params[7], 0, 1)` on the favoured side.
4. **Chase-down** (`FUN_142ec56a8`, skipped for battle types 3 and 6): routing units lose
   `clamp((clamp((enemy_avg_speed + 10 − speed) / 160, 0, 0.2) + survivor_ratio × 0.05) × (0.1 if on the winning
   side else 1.0), 0, 0.2)` of their maximum entities.
5. **Ensured unit loss** (M): a number of the loser's lowest-ranked units proportional to the enemy's remaining
   combat potential are destroyed; ×1.75 on a siege assault (`siege_attack_kill_multiplier`).
6. **Wipe-outs**: a unit below `max(round(max_entities × 0.2), 1 if general)` entities is destroyed; an army that
   lost more than 92% is destroyed; the losing alliance is wiped if the winner has 7× its strength and it is below
   30% of maximum, or if any winner unit carries the "annihilate" flag; Lua `modify_next_autoresolve_battle`'s
   boolean kills every surviving loser unit.
7. **Survivor return and general survival**: dead small units (< 11 entities) may be revived with a random
   remnant; a dead general is revived unless his force lost ≥ 65% (loser) or ≥ 80% (winner), at 50% health.
8. **Victory type** (`FUN_142d5dca8`): from the winner's loss fraction and the initial strength ratio with
   thresholds 0.5 / 0.588 / 0.26 / 0.4 / 0.83 / 1.2 and an 11-unit "big battle" split: close, decisive, heroic or
   pyrrhic victory, mirrored as close, decisive, valiant defeat or defeat against a pyrrhic winner.
9. **Building, wall and tower damage** (`FUN_142ebee8c`): attacker-only counts of assault equipment, units and
   artillery times the `building_damage_*` / `wall_damage_*` percentages; the winner adds `5 + round(min(artillery
   × 0.1, 1) × 5)` breaches × `winner_additional_wall_damage_per_wall_breach`.

### 6.1 Balance of power and prediction noise (`FUN_142ee3b64`) — **H**
```
KPDm = loser_losses / winner_losses (100 if the winner lost nothing);  SR = winner_initial / loser_initial
true% = clamp(clamp(KPDm + SR, 0.83, 5) × 12 + 40 − clamp(40 × winner_loss_fraction, 0, 100), 50, 100)
```
The loser shows `100 − true%`. The displayed value adds uniform noise of ±`variation × scale` percentage points,
where variation is chosen by the difference in best general level between the sides (≥ 7 above: 0.0; 3..6: 0.01;
−2..2: 0.05; −6..−3: 0.10; ≤ −7: 0.15, the `battle_result_accuracy_*_prediction_variation` variables) and
`scale = clamp(min(unit counts) / 10, 0, 1)`. The noise generator is seeded from the sum of unit ids times the
side's initial strength: **re-running the same pending battle gives identical numbers**. The displayed own-casualty
percentage gets independent noise of the same size.

### 6.2 What the player's settings do not do
`nominal_autoresolver_handicap` and `override_autoresolve_handicap` are console settings that are referenced
nowhere in this chain. The `autoresolver_player_types` difficulty columns select modifier groups whose values are
all zero at 9.0, so campaign difficulty does not change the fight; it only changes the default faction-potential
parameters. Stance (balanced/aggressive/defensive) acts only through the battle-type scoring in §3.2; the ±5% term
in post-battle code keys off the victory type, not the stance.

## 7. What this means for unit evaluation

- **Kill rate is king.** A unit's value is its kills per second against the specific enemy units, from real
  stats, with armour, hit chance, hit points, formation width and ranks all mattering. `melee_cp`/`missile_cp` do
  not feed the fight.
- **Ranged units fight at 65% of their range** in the precompute and in the ranged phase, and get a second shot
  weighted by `1 − p` at a different target. Ammo is a hard cap on each volley.
- **Skirmishers** avoid melee in proportion to the speed-ratio table: equal speed gives 3% effectiveness, 1.2×
  gives 55%, 3× gives 90%.
- **Frontage matters**: a wide, shallow formation engages more entities per step; single entities are normalised by
  hit points and take a 20% stat cut when swarmed by small entities.
- **Excess attackers are heavily discounted**: 65% damage dealt, 30% received, two per target. Outnumbering helps
  far less than in a real battle.
- **Morale ends fights early**: a unit breaks when `sqrt(band_value / scale)` of its hit points are gone;
  leadership scales that; unbreakable units fight to 95% losses.
- **Retreat is capped**: at most two units per step, never below 40% of the starting unit count, and never while
  outnumbered by more than 4:3.
- **The displayed balance bar is the simulator's own answer plus deterministic noise** that shrinks with a better
  general and with smaller battles; a general 7 or more levels above the enemy sees the exact value.

## 8. Reproducing and extending this

- Tools: Ghidra 12.1.4 under `C:\Users\jaymi\tools\ghidra_12.1.4_PUBLIC` (JDK 21), quick project
  `C:\Users\jaymi\tools\ghidra_quick` (no auto-analysis), dump script `ghidra_scripts\DumpAutoresolver.java`
  (`-Dar.depth`, `-Dar.cap`, seeds as hex addresses), pseudo-C in `ghidra_quick\decomp8..16\`.
- Repo: `scripts/re/*.py` (string/xref/displacement scanners, table getter scanner, mod builder),
  `re/NOTES.md` (call chain and offsets), `re/analysis/*.md` (four detailed reports), `re/*.json` (indices,
  getters, hits), `mods/ar_zero_prediction_noise.pack` (sets the five prediction-variation variables to 0 so the
  pre-battle bar shows the exact simulator value).
- Open questions are listed at the end of each analysis report. The most useful next steps are: resolve the
  adapter vtables that map melee attack/defence/damage onto the stat block (needs the whole-program Ghidra
  analysis, still running in `ghidra_proj`), confirm the two rounded excess-melee caps, and validate the model
  against in-game predictions with the zero-noise mod.
