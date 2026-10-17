# WH3 autoresolver — duel math (unit-vs-unit kill-rate precompute)

Source: Ghidra pseudo-C without whole-program analysis (`C:\Users\jaymi\tools\ghidra_quick\decomp14` = duel core, `decomp13` = wider simulator). Parameter lists are frequently wrong; control flow, constants and struct offsets are reliable. Everything below is derived from *usage* only. Confidence: **H** (direct arithmetic/constant), **M** (consistent across 2+ sites but name inferred), **L** (single site or lost arguments).

Notation: `A` = the unit whose stat block is the first stat argument (`param_5` in the handlers), `B` = the second (`param_6`). `S.x` = field at offset `+x` of a unit's 0x17c-byte stat block. `state[i]` = the 7-int live-state block overlaid at stat `+0xc..+0x24` (`state[0]=S.0xc`, `state[1]=S.0x10`, ... `state[6]=S.0x24`). `dt` = the float returned by vfunc `+0x28` of the duel-parameter object (`param_2`), almost certainly `autoresolver_battle_timestep` = 4 s (M). `round()` = `FUN_1404eda50`/`FUN_1405af474` (round half away from zero). `vfN(obj)` = virtual call at vtable slot `+N`.

## Summary

1. The duel type is **not classified from the stat blocks**: it is the first int of a caller-built descriptor `{int type; float dist_or_range; int; int}`. `FUN_142f130b0` only ever uses type **0** (melee engagement, approach distance 0) and type **3** (A fires at B from distance `FUN_142ef58ec(A)`, no reply). Types 1,2,4,5,6,7,9 exist in the dispatcher but are unused by the kps precompute.
2. Type 0 = optional approach (`dist/speed`), optional charge impact + point-blank volley, then either a **cycle-charge loop** (one side has both `S.0xec` and `S.0x118` > 3.5x the other's) or the generic melee simulation `FUN_142e2c460`.
3. The generic simulation is a **closed-form single-step** model, not a tick loop: per-attack expected damage = battle hit-chance formula (`base + k*(MA-MD)` clamped) x armour-reduced weapon damage; attacks-needed = `sqrt(morale fraction) x total HP / dmg`; rounds = attacks-needed / engaged frontage; fewer rounds wins; duration = `dt x rounds` (with an outnumbering correction when someone wins).
4. Ranged volleys (`FUN_142e2cc68`, `FUN_142e2ce80`): expected damage per shot = projectile hit probability (inverse-square of distance, clamped `[0.01,1]`, x `(1 - missile_block%)`) x armour-reduced damage x entities hit (penetration/explosion); shots needed = `morale_frac x total HP / dmg`, capped by ammo; time = shots / (firing entities x fire rate).
5. Casualty curve: survivors = `count x (1 - x^1.5)`, `x` = damage / total HP (`FUN_142e2d48c`).
6. Morale is a 7-band state (0 best, 6 broken); band drops by `dmg_frac^2 x (leadership x k + c)`; a side is "done" when count is 0 or band is 6/7.
7. Output of `FUN_142f1bebc`: `[0]` A->B fractional kills/s, `[1]` B->A kills/s, `[2]` A ammo delta/s (<=0), `[3]` -(B band delta)/s, `[4]` -(A band delta)/s, `[5]` duration (default 10 s if 0).
8. Unit-size normalisation: before the duel multi-entity counts are divided by `sim+0x8c` (ctor param; behaves as a unit-scale factor), single-entity units (`S.0x17b`) have HP divided by `S.0x15c`; results are rescaled afterwards.
9. None of the `autoresolver_bound_*` caps (20 kills/s, ammo x3, 50 proportion) appear in this slice; they must live in the modifier/aggregation side (`FUN_142ebcfa4`/`FUN_142ecad64`).

## Duel type classification

`FUN_142e47084(ctx, duelparams, int* desc, A_stat, B_stat, A_state_out, B_state_out, float* elapsed)`:
- Requires both `S.0x10` (entity count) != 0; copies both stat blocks (`FUN_142e05b08`, 0x17c bytes) to the stack, dispatches on `*desc`, then copies `stat+0xc..+0x24` (7 ints, `uStack_2fc/2f4/2ec/2e4`) into the two output state blocks. (H)
- Dispatch: 0->`FUN_142e473d0`, 1->`FUN_142e47550`, 2->`FUN_142e477d0`, 3->`FUN_142e4774c`, 4->`FUN_142e478c0`, 5->`FUN_142e2c460(..., cap=FLT_MAX 0x7f7fffff)`, 6->`FUN_142e47b90`, 7->`FUN_142e47b24`, 8->nothing, 9->`FUN_142e47a54`. (H)

Where the type comes from (H): `FUN_142f130b0` (decomp13) calls, for every attacker unit `a` x defender unit `b` (unit object: stat block at `unit+0x28`, live state at `unit+0x1a8`):

```
FUN_142f1bebc(out, sim+0x8c, *sim, p2, a.stat, a.state, b.stat, b.state, 0, 0,                0)  // melee a vs b
FUN_142f1bebc(out, ...,                 a.stat, a.state, b.stat, b.state, 3, FUN_142ef58ec(a), 0)  // a shoots b
FUN_142f1bebc(out, ...,                 b.stat, b.state, a.stat, a.state, 3, FUN_142ef58ec(b), 0)  // b shoots a
...then (A,B,0,0,2), (A,B,3,ef(a),2), (B,A,0,0,2), (B,A,3,ef(b),2)
```
The two trailing ints form the descriptor `{type, param}`; `param` is 0 for type 0 and `FUN_142ef58ec(unit)` for type 3. The final 0/2 argument is lost inside `FUN_142f1bebc` (open question).

Handler semantics (M, from what each handler does):

| type | handler | meaning |
|---|---|---|
| 0 | `FUN_142e473d0` | A closes `desc.dist` at speed `A.0x114`; optional charge impact / pre-charge volley (`FUN_142e2c0a8`); then melee: cycle-charge loop if one side dominates 3.5x on `0xec` & `0x118`, else generic sim. **Used by precompute with dist=0.** |
| 1 | `FUN_142e47550` | A (melee) advances on B (ranged): B shoots A during the approach at distance `min(dist, B.range)/2`, then A charges, then melee. |
| 2 | `FUN_142e477d0` | Both have missile weapons -> mutual fire (`FUN_142e2ce80`) at `desc.param`; else only A shoots B. |
| 3 | `FUN_142e4774c` | If A has a missile weapon: A shoots B at distance `desc.param` (`FUN_142e2cc68`), nothing else. **Used by precompute with param = `FUN_142ef58ec(A)`.** |
| 4 | `FUN_142e478c0` | Like 1 (B shoots the approaching A) but skips the charge step and goes straight to the generic sim. |
| 5 | `FUN_142e2c460` | Generic melee simulation only, no time cap. |
| 6 | `FUN_142e47b90` | Mutual fire at `desc.param` (no weapon check). |
| 7 | `FUN_142e47b24` | A volley at `desc.param` (no weapon check). |
| 9 | `FUN_142e47a54` -> `FUN_142e2d384` | Geometric "pass-through" damage from a 9x9 table indexed `(A.0x128*9 + B.0x128)` plus speeds `0x114/0x11c`; no weapons. (L) |

`FUN_142ef58ec(unit)` (type-3 distance, M/L): if `unit+0x20 == 3` (unit class on the unit object; class 3 is counted as the "artillery" class in `FUN_142ebee8c`: `if (*(int*)(*plVar5+0x20)==3) uVar9++` feeding a wall-damage percentage) return DB record `+0x54` as float (or 10.0 if `FUN_142eeb658` finds the unit in one of three engine lists); otherwise `FUN_142ef5834()` (same record `+0x54`) x `*(float*)(engine+0x19568)`. Hypothesis: record `+0x54` = missile range and `engine+0x19568` = cached `autoresolver_battle_missile_range_modifier_used_in_ranged_combat` (0.65), i.e. firing distance = `0.65 x range` for non-artillery, full range for artillery. Not verifiable from this dump.

**ar_unit_category (melee/skirmish/archer/artillery) therefore does not select the duel type**; the caller always evaluates one melee duel and two one-sided ranged duels per pair, and the per-category behaviour emerges from `has_missile`, range and the modifier layer.

## Per-type formulas

### Common helpers
- `has_missile(S)` = `FUN_142e52a14(S+0x28)`: `S.0x3c >= 0.01 && (S.0x28 + S.0x2c) >= 0.01` (fire rate > 0, damage + AP damage > 0). (H)
- `firing(S)` = `FUN_142e33674(S.0x10, S.0xfc)` = `S.0xfc == 0 ? count : max(1, round(count / S.0xfc))` — number of shooting "weapons" (crew-size divisor). (M)
- `eff_count(S)` = `FUN_142e336b0(S)` = same, bypassed (raw count) when `S.0x173` set. (M)
- `done(A,B)` = `FUN_142e73a9c`: true if `A.count == 0 || B.count == 0 || state[0] in {6,7}` for either side. (H)
- `situation(dist, flag)` = `FUN_142e05940`: `{vtable UNK_1439061c0, dist (x0.5 if flag), desc[2], desc[3]}`; `flag` is `S.0x69` of (usually) the shooter. The projectile hit chance divides by `dist^2`. (M)
- Fatigue-like accumulator `FUN_142e2db20(state, t, rate)`: `state[5] += (1000 / _DAT_143d0e294) * t * rate` (`_DAT_143d0e294` = ms-per-tick global, also used in `FUN_14305e9c0`). Rates are vfuncs `+8/+0x10/+0x18` of the rate object `{UNK_143914208, FUN_141508930(ctx)}` (running / fighting / shooting). Never read back in this slice. (M)

### Type 0 (`FUN_142e473d0`) — melee engagement
```
if A.speed(0x114) >= 0.01: t_approach = desc.dist / A.speed
elif desc.dist > 0.01:    return                  # cannot reach
else:                      t_approach = 0
elapsed += t_approach; fatigue(A, t_approach, run_rate)
FUN_142e2c0a8(A,B)                                 # charge phase
if not done:
    r = FUN_142e783ac(A,B):
        0 if A.0xec > 3.5*B.0xec and A.0x118 > 3.5*B.0x118
        1 if B.0xec > 3.5*A.0xec and B.0x118 > 3.5*A.0x118
        2 otherwise
    r==0: FUN_142e2c354(A,B)      # A cycle-charges B
    r==1: FUN_142e2c354(B,A)
    r==2: FUN_142e2c460(A,B, cap=FLT_MAX)
```
Cycle-charge loop `FUN_142e2c354(X,Y)`: `while !done: FUN_142e2c460(X,Y, cap = 6*dt); X.0x16a = 1; FUN_142e2c0a8(X,Y)` — six timesteps of melee, disengage, re-charge. (H)

Charge phase `FUN_142e2c0a8(A,B)` (H structure, L on lost args), only if `A.0x16a != 0 && desc.dist > 0`:
1. `FUN_142e2c20c`: `n_hits = FUN_142e32910(A,B) * A.0xe4`; `dmg = melee_dmg_per_attack(A,B) / n_hits`, capped at `B.0x14`; applied via `FUN_142e1cfbc(ctx, n_hits, dmg, B.state)` (not in dump).
2. if `A.0xe8 != 0`: `FUN_142e2c2d0` -> impact `FUN_142e32858`: `v = A.0x110 * (B.0x110 > 1 ? 1/B.0x110 : 1) * A.0x114` (mass ratio x speed), transformed by `FUN_141158b90(v, vf0xd8)` x `vf0xe0`, clamped `[0, vf0xe8]`; applied through `FUN_142e2db64/FUN_142e1cfbc`.
3. if `A.0x168 != 0 && A.ammo(0x24) != 0`: point-blank volley, `situation(10.0, A.0x69)`, `max_shots = min(A.ammo, A.count)` -> `FUN_142e2cc68(A->B)`.
4. clear `A.0x16a`, `B.0x16a`.

`FUN_142e32910(A,B)` (charge contact count): `wA = A.0x130 * effA / A.0x140`, `wB = B.0x130 * effB / B.0x140`; `n = min(effA, min(wA,wB) / A.0x130)`; multiplier if `B.0x172`: `A.0x16f -> 2.0`, `A.0x171 -> 3.0`, `A.0x174 -> 2.5`; `round(mult*n)` capped at `effB`. (H arithmetic, flag meanings L)

### Type 1 (`FUN_142e47550`) — melee A approaches ranged B
```
if has_missile(B):
    d   = min(desc.dist, B.0x40) * 0.5                # half of min(distance, range)
    sit = situation(d, B.0x69)
    if A.speed < 0.01: FUN_142e2cc68(B shoots A; args lost); return
    t = desc.dist / A.speed; elapsed += t
    shots = (int)(firing(B) * B.0x3c * t)             # weapons x fire rate x approach time
    FUN_142e2cc68(ctx, p2, rates, sit, shots, shooter=B, target=A, &elapsed)
    fatigue(A, t, run_rate); fatigue(B, t, shoot_rate)
    if done: return
FUN_142e2c0a8(A,B)
if not done: FUN_142e2c460(A,B, FLT_MAX)
```
Type 4 (`FUN_142e478c0`) is identical except the flag passed to `situation` is `A.0x69` (the target's) and the charge step is skipped. (H)

### Type 3 (`FUN_142e4774c`) — one-sided volley (used by precompute)
```
if has_missile(A): sit = situation(desc.param, A.0x69); FUN_142e2cc68(A shoots B; max_shots arg lost)
```
Types 2/6/7 reuse the same blocks (2 and 6 use `FUN_142e2ce80` with two situations at `desc.param`).

### Volley `FUN_142e2cc68(ctx, p2, rates, sit, max_shots, S, T, &elapsed)` (H)
```
n_avail  = min(max_shots, S.ammo(0x24))
nf       = firing(S);  if nf == 0: return
dmg_shot = FUN_142e324bc(p2, sit, S+0x28, S, T)        # expected damage per shot; if <= 0 return
hpT      = T.0x18 * T.count                             # current total HP
fracT    = FUN_142e32330(T.state[0], T.0xbc, T)         # morale fraction that must be destroyed
need     = ceil(fracT * hpT / dmg_shot)
shots    = min(need, n_avail)
S.ammo  -= shots
FUN_142e2d48c(T.state, shots*dmg_shot)                  # casualties (arg lost but implied)
T.state[0] = need > n_avail ? FUN_142e3cd0c(T.state[0], T.0xbc, shots*dmg_shot/hpT, no_break) : 6
rate     = nf * S.0x3c                                  # unit shots per second
elapsed += rate > 0 ? shots / rate : FLT_MAX
fatigue(S, ..., shoot_rate)
```
Mutual fire `FUN_142e2ce80(S,T)` (H): `dmgS, dmgT`; `needS = fracT*hpT/dmgS`, `needT = fracS*hpS/dmgT`; `rateS, rateT`; four ammo cases: both run dry (`t = max(ammoS/rateS, ammoT/rateT)`, both ammo = 0, both bands from damage fractions); one runs dry (the other finishes it, victim band 6); both sufficient: `tS = needS/rateS`, `tT = needT/rateT`, the faster kills (victim band 6) while the slower fires `floor(rate * t_win)` shots and the band comes from its damage fraction. `FUN_142e1e050`: `elapsed += max(shotsS/rateS, shotsT/rateT)`, half-rate fatigue to both, `state[5]` on the second object.

### Expected damage per shot `FUN_142e324bc(p2, sit, W=S+0x28, S, T)` (H structure, M names)
```
p_hit = FUN_142e59328(ctx, {S}, {sit,S})       # projectile hit chance, [0.01, 1]:
        clamp( (a * b * c * d^2 * e^2 * acc * 0.01) / dist^2 , 0.01, 1 ),  dist = vf0(sit) (>=0.01 else result 1.0)
        acc = max(0, vf0x48(S) + vf8(sit)); e = max(g.0x39bc + g.0x39b8, g.0x39c0) (global tuning)
        minus vf0x80(p2) if vf0x20(sit)        # vtable-based; stat identities not recoverable here
if W.0x40 (S.0x68) == 0 and vf0x10(sit) in {0,1}:      # shooter does not ignore shields, frontal arc
    p_hit *= (1 - T.0xd8 * 0.01)                     # missile block chance %
dmg   = FUN_142e338c0(.., base, ap) = (1 - armour_frac) * base + ap
        armour_frac = clamp(armour * (0.5 + 0.5*f), 0, 100) / 100       (FUN_142e2e9e0)
dmg_c = min(dmg, T.0x18)                             # one entity's HP
sp    = 2 / (T.0x13c + T.0x138)                      # 1 / mean entity spacing
explosion (if W.0x30 (S.0x58) > 0):
    n_ex   = min(round(sp * W.0x30 + 1), T.count)
    dmg_e  = min(FUN_142e338c0(explosion base/ap), T.0x18)
    direct = min(T.0x14 - dmg_c * p_hit, dmg_e)
    expl   = (dmg_e * (n_ex-1) * p_hit + direct) * 0.5
penetration:
    n_pen = W.0x34 (S.0x5c) > 0 ? (int)(sp * W.0x34 + 1) : 1
    if (W.0x41 (S.0x69) || W.0x28 (S.0x50) > 80.0) and T.0x134 < W.0x38 (S.0x60):
        k = min(W.0x10 (S.0x38), T.0x140); if n_pen > 1: n2 = min(round(?), T.count)   # args lost
n1 = min(round(?), T.count)
return (n2 * min(dmg/2, dmg_c) + n1 * dmg_c) * p_hit + expl
```
Primary entity takes full damage, penetrated entities half, explosion adds blast damage over `n_ex` entities.

### Casualties `FUN_142e2d48c(state, dmg)` (H)
```
total = state[1] * state[3]                   # count x hp/entity; if 0: count = hp = 0
x = clamp((dmg - state[4]) / total, 0, 1)
survivors_f = (1 - sqrt(x)*x) * state[1]      # count * (1 - x^1.5)
n = min(round(?), ceil(survivors_f))          # round() arg lost
state[4] = round(n)                           # bookkeeping (lost)
FUN_142e76248(state, remaining_hp, n): state[1] = n; state[3] = min(remaining_hp / n, state[2])
```
At `x = 0.5` only ~35% of entities die (damage spreads into wounded survivors); at `x = 1` all die.

### Morale (H arithmetic, M naming; globals table `G = FUN_141508fcc(ctx)`)
- `FUN_142e3330c(band, L)` morale value of a band: `0: L*G.0xe0; 1: 0.5*(G.0x1b0+G.0x148)*L; 2: 0.5*(G.0x280+G.0x218)*L; 3: 0.5*(L*G.0x2e8+G.0x350); 4: 0.5*(G.0x420+G.0x3b8); 5: 0.5*(G.0x4f0+G.0x488); else G.0x558`, rounded.
- `FUN_142e332b0(L)` = `max(1, L*G.0x148) + |G.0x4f0|` (morale scale).
- `frac = FUN_142e32330(band, L, S)` = `S.0x178 ? 0.95 : clamp(sqrt(morale(band,L) / scale(L)), 0, 1)` — fraction of total HP to destroy before the unit gives up (unbreakable -> 95%).
- `FUN_142e3cd0c(band, L, dmg_frac, allow_break)`: `m = morale(band,L) - round(dmg_frac^2 * scale(L))`; new band from `FUN_142e3cd98`: `m/L > G.0xe0 -> 0; > G.0x1b0 -> 1; > G.0x280 -> 2; m > G.0x350 -> 3; m > G.0x420 -> 4; m > G.0x4f0 -> 5; else 6`; `!allow_break && band == 6 -> 5`.
- Band 6 (and 7) terminates the duel (`FUN_142e73a9c`); `FUN_142e2d384` sets band 6 + count 0 + hp 0 on a wipe.

### Type 9 (`FUN_142e47a54` -> `FUN_142e2d384`) (L)
`k = FUN_142e5d290(p2, geom)` (dot products of two direction vectors, a `[0.5,5]` ratio, `vf0x30 * vf0 * ratio`); `hits = k * A.count`; if `hits < B.0x18*B.count`: `FUN_142e2d48c(B.state, hits)` else wipe B. `elapsed += vf0x20(p3) * desc.param + 5.0`. `geom` carries `G2[0x78 + (A.0x128*9 + B.0x128)*4]` (9x9 class-pair table from `FUN_141514e78`), `A.0x114, B.0x114, A.0x11c`.

## Generic simulation (type 5, `FUN_142e2c460(ctx, p2, rates, p4, A, B, &elapsed, cap)`)

Closed-form estimate of one melee engagement (H arithmetic; vtable sub-call identities M/L):

```
effA, effB = eff_count(A), eff_count(B)
hpA = A.0x18 * A.count ; hpB = B.0x18 * B.count                    # current total HP
mode = (A.0x16c && !B.0x16c) ? 3 : 0                               # 3/4 = one side envelops (flag 0x16c, L)
cA = FUN_142e4b1d8(.., A, B, mode)         # A entities on the contact line (frontage model below)
cB = FUN_142e4b1d8(.., B, A, swap(mode))   # swap: 1<->2, 3<->4 (FUN_142e529e0)
engA = (A.0x177 ? 3 : 1) * cA ; engB = (B.0x177 ? 3 : 1) * cB
fracA = FUN_142e32330(A.state[0], A.0xbc, A) ; fracB likewise
A' = copy(A); if effA == 1 && cB > 6 && A.0x134 == 1 && B.0x134 == 1: A'.0xc8 = round(A.0xc8 * 0.8)   # swarmed single entity: -20% on 0xc8 (L)
B' likewise
dA = FUN_142e323c8(p2, p4, A', B')          # A's expected damage per attack vs B (melee formula below)
dB = FUN_142e323c8(p2, p4, B', A')
dA = min(dA, min(max(1,(int)(A.0xe4*0.75)), B.count) * B.0x14)    # cap: 0.75 x max-targets x B hp/entity
dB = min(dB, min(max(1,(int)(B.0xe4*0.75)), A.count) * A.0x14)
secondary weapon (FUN_142e52a14(A+0x6c)): xA = dt * FUN_142e324bc(p2, situation(0), A+0x6c, A, B) * A.0x80   # per-step extra
                                           xB likewise
if B.0x120 > 0: dA = dt * max(0.1, dA/dt - (B.0x120/dt) * (cB / cA))   # flat per-step reduction x frontage ratio (L)
if A.0x120 > 0: dB = dt * max(0.1, dB/dt - (A.0x120/dt) * (cA / cB))
dA += xA ; dB += xB
needA = dA ? fracB * hpB / dA : 0           # attacks A needs to finish B
needB = dB ? fracA * hpA / dB : 0
rA = engA ? needA / engA : 0                # rounds (timesteps) A needs
rB = engB ? needB / engB : 0
t = min(rA, rB, cap)
A_wins = rA < rB && rA <= t ;  B_wins = rB < rA && rB <= t
FUN_142e2d48c(A.state, ...) ; FUN_142e2d48c(B.state, ...)         # damage args lost (implied dX*engX*t)
B.state[0] = A_wins ? 6 : FUN_142e3cd0c(B.state[0], B.0xbc, dA*engA*t / hpB, false)
A.state[0] = B_wins ? 6 : FUN_142e3cd0c(A.state[0], A.0xbc, dB*engB*t / hpA, B_wins)
if A_wins or B_wins:
    w = max(1, (winner.count_before + winner.count_after)/2) ; l = same for loser
    r = 2*w/(w+l) - 1                                             # outnumbering in [-1,1]
    need = min(needA, needB)
    rounds = max(1, need + ((1 - r^3)*0.15 + 0.7) * (need/w - need))   # ~ need/w when even
    duration = dt * rounds
else:
    duration = dt * t
elapsed += duration ; fatigue(A, duration, fight_rate) ; B.state[5] += (1000/_DAT) * duration * fight_rate * 0.5
```
Implication: one attack per engaged entity per timestep `dt`; the real battle melee interval is not a stat here (the 4 s timestep plays that role).

Frontage `FUN_142e4b1d8(nA, nB, A, B, mode)` (H): `perRankA = A.0x140 >= 1 ? nA / A.0x140 : A.count` (same for B); `rA = A.0x130`, `rB = B.0x130`:
- mode 0: `fA = rA*(2*nA/perRankA + perRankA)`, `fB = rB*(2*nB/perRankB + perRankB)`; `f = min(fA,fB)`, `extra = fA > fB ? 4 : 0`
- mode 1: `f = 2*rA*nA/perRankA + 2*rA*perRankA`; mode 2: same with B, `extra = 8`
- mode 3: `f = rA*nA`; mode 4: `f = rB*nB`
- `contact = min(nA, (extra*rA + f)/rA) * A.0x100`

Melee damage per attack `FUN_142e323c8(p2, sit, X, Y)` (H structure): `hit% = FUN_142e58560(...)`; `(base, ap, ?) = FUN_142e589a4(...)`; `return FUN_142e338c0(armour, base, ap) * hit% * 0.01`.
- `FUN_142e58560` (hit chance = the battle formula): `MA = vf0xb0(X)`; `+ vf0x110(X) * G3[0x40a8 | 0x4110]` (charge bonus, when `FUN_142e52c20` says charging); `+ vf0xe0/0xe8/0xf0(X)` (bonus vs class) when `vf0x78/0x68/0x70(Y)`; `MD = vf0xb8(Y)` (`+ vf0x40(p2)` if `vf0x58(Y)`); `MD = round(MD * FUN_142e32a04(...))` (flank/rear multipliers `vf0x30/0x38(p2)`, else 1.0); `MD = round(MD * vf0x70(p2))` if `vf8(sit)`; `hit = clamp(round(vf8(p2) + vf0x20(p2) * (MA - (MD + extra))), vf0x10(p2), vf0x18(p2))`. I.e. `base + k*(MA-MD)` clamped `[min,max]` (battle: 35 + (MA-MD), 8..90).
- `FUN_142e589a4` (melee damage triple): `vf0xc8(X)`, `vf0xd8(X)` rounded, clamped >= 0 (base, AP); third = `vf0xa0(X)` through `FUN_142df6e04`.
- `FUN_142e5955c` (missile damage triple): `vf0x10/0x18(W)` rounded; bonus-vs via the `0x28/0x30/0x38` <-> `0x30/0x38/0x40` pairs; third = `vf0x80(W)` through `FUN_142df6e48`.

The stat wrappers (`UNK_143906018` melee unit, `UNK_143905f80` target, `UNK_143906228` missile weapon, `UNK_143905f50` shooter-in-situation) adapt the 0x17c stat block to the battle engine's combat interfaces; their vtables are not in the dump, so the stat offsets behind `vf0xb0/vf0xb8/vf0xc8/...` cannot be recovered from usage.

## Stat-block field table (from usage)

| offset | type | meaning (usage-derived) | conf | evidence |
|---|---|---|---|---|
| +0x0c | int | morale band / combat state (0 best .. 6 broken; 7 also terminal) | H | written by `FUN_142e3cd0c`; `FUN_142e73a9c`: `state-6 < 2` ends duel; wipe sets 6 |
| +0x10 | uint | entity count | H | `hp(0x18) * count(0x10)`; `FUN_142f1bebc` kills from its delta |
| +0x14 | uint | max HP per entity | M | `FUN_142e76248` caps `state[3]` at `state[2]`; per-hit cap `engaged * 0x14` |
| +0x18 | uint | current HP per entity | H | `total = state[1]*state[3]`; `FUN_142f1bebc` weights survivors by `after/before` |
| +0x1c | uint | damage carry/offset subtracted from incoming damage | L | `FUN_142e2d48c`: `(dmg - state[4]) / total` |
| +0x20 | int | accumulated fatigue-like counter | M | `FUN_142e2db20`, `FUN_142e1e050`, tail of `FUN_142e2c460` |
| +0x24 | uint | ammunition | H | `S.0x24 -= shots`; volley capped by it; `0x168 && 0x24 != 0` gate |
| +0x28 | int | primary missile weapon damage | M | `FUN_142e52a14`: `p[0]+p[1] >= 0.01` |
| +0x2c | int | primary missile AP damage | M | same |
| +0x38 | int | missile projectiles-per-shot / penetration count cap | L | `min(W.0x10, T.0x140)` |
| +0x3c | float | missile fire rate (shots/s per firing weapon) | H | `rate = firing * 0x3c`; `shots = firing * 0x3c * t` |
| +0x40 | float | missile range (m) | H | `min(desc.dist, B.0x40) * 0.5` |
| +0x48 | - | missile sub-field copied into the situation wrapper | L | `uStack_80 = *(W+0x20)` |
| +0x50 | float | missile velocity-like (> 80 enables penetration) | L | `80.0 < W.0x28` |
| +0x58 | float | explosion radius | M | `round(2/spacing * W.0x30 + 1)` entities |
| +0x5c | float | penetration distance | M | `(int)(2/spacing * W.0x34 + 1)` |
| +0x60 | int | penetration max entity-size class | M | `T.0x134 < W.0x38` |
| +0x68 | char | missile ignores shields | M | `if W.0x40 == 0: p_hit *= 1 - block%` |
| +0x69 | char | halves engagement distance / penetration gate (artillery-like) | L | `FUN_142e05940(.., dist, 0x69)`: `dist*0.5`; `W.0x41 \|\|` |
| +0x6c..+0x80 | block | secondary weapon (layout as +0x28: `+0x6c` dmg, `+0x70` AP, `+0x80` rate) | M | `FUN_142e52a14(A+0x6c)`, `* A.0x80` |
| +0xbc | int | leadership / morale | H | `L` in `FUN_142e3330c/332b0/3cd0c` |
| +0xc8 | int | melee stat cut 20% when a single entity is swarmed (MA or damage) | L | `FUN_142e33420` |
| +0xd8 | int | missile block chance (%) | H | `(1 - T.0xd8*0.01) * p_hit` |
| +0xe4 | int | max targets per attack (splash) | M | `*0.75` cap; `contact * 0xe4` charge hits |
| +0xe8 | int | charge bonus (nonzero -> impact step) | M | `if A.0xe8 != 0: FUN_142e2c2d0` |
| +0xec | int | cycle-charge discriminator #1 (3.5x rule) | L | `FUN_142e783ac` |
| +0xfc | uint | entities per weapon/crew (count divisor) | M | `max(1, round(count / 0xfc))` |
| +0x100 | float | contact-count multiplier | M | `return S.0x100 * contact` |
| +0x110 | float | mass | H | `A.0x110 / B.0x110 * A.0x114` |
| +0x114 | float | speed (m/s): approach time and impact | H | `t = dist / S.0x114` (3 handlers) |
| +0x118 | float | cycle-charge discriminator #2 (speed-like) | L | `FUN_142e783ac` |
| +0x11c | float | second speed-like value (type-9 geometry) | L | `FUN_142e47a54` |
| +0x120 | float | per-step incoming damage reduction (regen/ward-like) | L | `dA/dt - 0x120/dt * cB/cA`, floor 0.1 |
| +0x128 | uint | unit class index 0..8 | M | `(A.0x128*9 + B.0x128)*4` |
| +0x130 | float | entity width/radius (m) | H | `0x130 * count / ranks` |
| +0x134 | int | entity size class (1 = smallest) | M | `== 1` swarm penalty; `< W.0x38` penetration |
| +0x138, +0x13c | float | formation spacing (two axes) | M | `2/(0x13c + 0x138)` |
| +0x140 | int | number of ranks | H | `count / 0x140` = entities per rank |
| +0x15c | float | HP divisor for single-entity normalisation | H | `1/S.0x15c` -> `FUN_142e7403c` when `0x17b` |
| +0x168 | char | fires while charging (pre-charge volley) | M | gate with ammo for the 10 m volley |
| +0x16a | char | "charging" flag | H | set by `FUN_142e2c354`, cleared by `FUN_142e2c0a8` |
| +0x16c | char | selects frontage mode 3/4 (envelopment) | L | `A.0x16c && !B.0x16c -> mode 3` |
| +0x16f / +0x171 / +0x174 | char | charge multiplier class flags (2.0 / 3.0 / 2.5) vs `0x172` targets | L | `FUN_142e32910` |
| +0x172 | char | target class flag enabling charge multipliers | L | same |
| +0x173 | char | count entities individually (bypass `0xfc`) | M | `FUN_142e336b0` |
| +0x177 | char | engages 3x frontage | L | `(0x177 ? 3 : 1) * contact` |
| +0x178 | char | unbreakable (fixed 0.95 fraction) | M | `FUN_142e32330` |
| +0x17b | char | single-entity unit (HP-scaled instead of count-scaled) | H | `FUN_142ee381c` |
| unit+0x20 | int | unit class on the unit object (3 = artillery-like) | M | `FUN_142ef58ec`, `FUN_142ebee8c` |
| unit+0x298 | float | weight applied to the morale-delta outputs | L | `FUN_142f130b0`: `0x298 * result[3]/[4]` |

Stat-block size 0x17c confirmed by `FUN_142e05b08` (copies through `+0x17b`); live state is 7 ints at `+0xc..+0x27`.

### Normalisation in `FUN_142ee381c` (H)
```
sA = A.0x17b ? 1/A.0x15c : 1/scale     (scale = sim+0x8c; 0 if <= 0)
multi-entity (0x17b == 0): count = round(count / scale)
single-entity:             FUN_142e7403c(state, 1/0x15c): state[3] = max(1, round(state[3]*s)); state[2] = max(1, round(state[2]*s));
                           hp-per-entity re-derived from total, capped at state[2]
... FUN_142e47084 ...
multi-entity: count_out = round(count_orig * count_after / count_scaled)
single-entity: FUN_142e7403c(state_out, scale)        # HP x scale
```

### Result vector `FUN_142f1bebc` (H)
```
T = elapsed > 0 ? elapsed : 10
res[0] = (B.count0 - B.count1 * (B.hp1 / B.hp0)) / T     # A -> B fractional kills/s
res[1] = (A.count0 - A.count1 * (A.hp1 / A.hp0)) / T     # B -> A
res[2] = (A.ammo1 - A.ammo0) / T                          # <= 0
res[3] = (B.band0 - B.band1) / T                          # <= 0 as B degrades
res[4] = (A.band0 - A.band1) / T
res[5] = elapsed
```
Caller: `kps = mult * res[0] + add` (clamped >= 0) with `FUN_142ecad64` factors; `res[3]/res[4]` and the type-3 `res[3]` are multiplied by the victim's `unit+0x298`; `res[2]` (ammo/s) copied through; the 8-float block goes to `FUN_142ebcfa4` (per-pair store at `unit+0x218`).

## Campaign-variable constants seen (constant -> where)

| constant | value seen | where | note |
|---|---|---|---|
| `autoresolver_battle_timestep` (4) | `dt` = vf0x28 of the duel-params object | `FUN_142e2c460`, `FUN_142e2c354` (`dt*6` cap), `FUN_142e1e050` | M — not a literal; inferred from role |
| `autoresolver_battle_missile_range_modifier_used_in_ranged_combat` (0.65) | `*(float*)(engine+0x19568)` scaling a range-like DB value | `FUN_142ef58ec` (type-3 distance) | L hypothesis; the literal `0.65` in `FUN_142ec60d8` is a strength-ratio test, unrelated |
| default duration 10 s | literal `10.0` | `FUN_142f1bebc`; also the 10 m pre-charge volley distance in `FUN_142e2c0a8` | H literal, not a campaign variable |
| `bound_max_ranged_kills_per_second` 20, `bound_max_ammo_per_second_mod_unit_size` 3, `bound_max_melee_strength_proportion` 50, `flying_unit_melee_damage_received_modifier` -30, `max/min_hp_for_enemy_hp_dps_modifier` 2000/600, `special_ability_*` | **absent** from every function in this slice | — | applied in `FUN_142ecad64`/`FUN_142ebcfa4`/aggregation |
| hard-coded literals | `3.5` (cycle-charge ratio), `0.75` (splash cap), `0.8` (swarm penalty), `0.5/0.15/0.7` (duration correction), `0.95` (unbreakable), `80.0` (penetration gate), `0.01..1.0` hit clamp, `0.1` damage floor, `6` (timesteps per cycle-charge), `3`, `2.0/3.0/2.5` charge multipliers | duel core | not campaign variables |

## Open questions

1. `FUN_142e2d48c`: the inner `round()` argument (remaining HP vs survivors) and the write to `state[4]` (+0x1c) are lost; the survivor curve `1 - x^1.5` is certain, the `+0x1c` bookkeeping is not.
2. Identities behind the vtable calls in `FUN_142e58560/589a4/5955c/59328` (MA/MD/damage/AP/accuracy/bonus-vs); the adapters' vtables (`UNK_143906018`, `UNK_143905f80`, `UNK_143906228`, `UNK_143905f50`) are outside the dump. The constructor-side table should map them.
3. `FUN_142ef58ec`: is DB record `+0x54` the missile range and `engine+0x19568` the 0.65 modifier? `unit+0x20 == 3` = artillery is inferred only from `FUN_142ebee8c`.
4. The trailing 0/2 argument of `FUN_142f1bebc` (second batch of four calls) is invisible inside it; it probably reaches the duel-params object or `FUN_142ee381c`.
5. `+0xec` / `+0x118` (3.5x cycle-charge rule): `0x118` is a speed-like float distinct from `0x114`; `0xec` is an int. Not resolvable from usage.
6. `sim+0x8c` (ctor `param_7` of `FUN_142ea091c`; NOTES calls that slot "override") behaves here as a unit-scale divisor. Reconcile with the ctor-side analysis.
7. Sign convention of `unit+0x298` on the (<= 0) morale-delta outputs.
8. `_DAT_143d0e294` (ms per tick) and the fatigue accumulator `state[5]` are never read in this slice.
9. `FUN_142e1cfbc` (applies charge hits) and `FUN_141158b90` (impact transform) are not in the dump.
10. Why type 4 passes the *target's* `0x69` to `situation` while every other site passes the shooter's.

## Functions read

decomp14: FUN_142e47084, FUN_142e473d0, FUN_142e47550, FUN_142e477d0, FUN_142e4774c, FUN_142e478c0, FUN_142e47b90, FUN_142e47b24, FUN_142e47a54, FUN_142ee381c, FUN_142e2c460, FUN_142e05b08, FUN_142e05940, FUN_142e2db20, FUN_142e2db64, FUN_142e2c0a8, FUN_142e2c20c, FUN_142e2c2d0, FUN_142e2c354, FUN_142e73a9c, FUN_142e783ac, FUN_142e52a14, FUN_142e529e0, FUN_142e2cc68, FUN_142e2ce80, FUN_142e1e050, FUN_142e2d384, FUN_142e2d48c, FUN_142e76248, FUN_142e33674, FUN_142e336b0, FUN_142e33420, FUN_142e4b1d8, FUN_142e32910, FUN_142e32858, FUN_142e324bc, FUN_142e32330, FUN_142e332b0, FUN_142e3330c, FUN_142e338c0, FUN_142e2e9e0, FUN_142e323c8, FUN_142e590f8, FUN_142e58560, FUN_142e589a4, FUN_142e5955c, FUN_142e59328, FUN_142e59a3c, FUN_142e52c20, FUN_142e32a04, FUN_142e3cd0c, FUN_142e3cd98, FUN_142e5d290, FUN_141514e78, FUN_141508930, FUN_141508fcc, FUN_141509464, FUN_1404eda50, FUN_1405af474, FUN_14305e9c0.

decomp13: FUN_142f130b0, FUN_142f1bebc, FUN_142e7403c, FUN_142f1be40, FUN_142ef58ec, FUN_142ef5834, FUN_142eeb658, FUN_142f0ba78, FUN_142ea091c (excerpt), FUN_142ebcfa4 (head), FUN_142ebee8c (excerpt), FUN_142ec60d8 (excerpt).
