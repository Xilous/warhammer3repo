# Frontline for the Stormfiend (Ratling Cannons) army: which melee unit to spam

Companion to `GUIDE_Stormfiend_Ratling_Cannons.md`. Same setup: Clan Skryre, Update 9.0, Stormfiend armies led by a
Verminlord Warpseer. Every number comes from the twwstats 9.0 dataset and the installed game's database; the ranking
is produced by `scripts/game/frontline_eval.py` (section 6 has the model and how to rebuild). Every Skaven unit
without a missile weapon is in the pool: infantry, monstrous infantry, monsters, war beasts, the Cauldron, Doom-Flayers
and the Doomwheel (vehicles are scored on their vehicle entity: 1500 and 2000 mass, 2 m and 3 m tall).

## 1. Answer

**The line: Stormvermin (Swords & Shields)**, from the Clan Armoury (Clan Pit chain, third level, settlement tier 3).
**The monster, if you want one: Stormfiends (Grinderfists)**, from the Brain-Breeding Facilities (Stormfiend chain,
first level, settlement tier 4), used on the flanks of the line, never in front of the cannons.

"Soak up damage" splits into two different jobs, and the two units win one each:

- **Stopping the enemy army reaching the guns** needs frontage and total damage absorbed. Stormvermin absorb the most
  damage of any Skaven unit before they break, 32 m wide, and do it for the least upkeep per point absorbed outside
  Skavenslave chaff. They are 1.6 m tall, so the 2.8 m Stormfiends fire over them.
- **Pinning one thing for a long time** (a cavalry wedge, a monster, a lord diving the guns) needs a unit that few
  enemy models can reach at once and that does not rout. Here single entities and monstrous infantry win on time in
  contact, and Grinderfist Stormfiends win on time per gold: Workshop Regeneration, 95 armour, Frenzy, same building
  and the same Workshop as the cannons. They are 2.8 m tall, the same as the cannons, so they block the line of fire
  if they stand in front; on the flanks they are a wall the enemy cavalry has to chew through.

Before the Armoury exists, use **Clanrat Spears (Shields)**: Clan Skryre's capital landmark (Warpstone Telescope,
tier 1 of the Warpstone Tractor Beam chain) recruits them from turn 1, otherwise the Clan Barracks at tier 2.

## 2. Ranking (full stack: all techs, Workshop, Warpseer red line, no rank 7)

Three measures, 100 = Clanrats (Shields) at full stack for the first two:

- **Soak**: enemy melee attacks the unit absorbs before it breaks, averaged over four enemy archetypes (line infantry,
  Chosen with great weapons, Minotaurs, Demigryph Knights). This is total damage taken off the cannons.
- **Time**: seconds the unit stays in contact before it breaks, allowing for how many enemy models can reach it at
  once (contact front divided by enemy model spacing). This is how long a diving unit is pinned.
- **Width**: formation frontage in metres. MD and LD include Strength in Numbers (+8 / +6) where the unit has it.

| Unit | Building (tier) | Men | HP | Arm | MD | LD | Mass | Width m | Upkeep | Soak | Soak /100 upk | Time | Time /100 upk | Size |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Stormvermin (Swords & Shields)** | Clan Armoury (3) | 160 | 9920 | 95 | 49 | 76 | 150 | 32 | 176 | **345** | **196** | 304 | 173 | small |
| Stormvermin (Halberds) | Clan Armoury (3) | 160 | 9920 | 95 | 47 | 76 | 150 | 32 | 197 | 315 | 160 | 278 | 141 | small |
| Doomwheel | Warp-Turbine Plant (5) | 1 | 6220 | 137 | 47 | 65 | 2000 | 6 | 280 | 252 | 90 | 857 | 306 | very large |
| Hell Pit Abomination | Laboratory (5) | 1 | 12100 | 50 | 30 | 90 | 5000 | 9 | 373 | 202 | 54 | 488 | 131 | very large |
| **Stormfiends (Grinderfists)** | Brain-Breeding Facilities (4) | 12 | 8772 | 95 | 31 | 70 | 1500 | 9 | 248 | 183 | 74 | **610** | **245** | large |
| Stormfiends (Doom-flayer Gauntlets) | Brain-Breeding Facilities (4) | 12 | 8772 | 95 | 31 | 70 | 1500 | 9 | 269 | 183 | 68 | 610 | 227 | large |
| Stormfiends (Shock Gauntlets) | Equipment Warpforge (5) | 12 | 8772 | 95 | 31 | 70 | 1500 | 9 | 290 | 183 | 63 | 610 | 210 | large |
| Doom-Flayers (all 5 Workshop upgrades) | Warp-Forge (4) | 8 | 6064 | 136 | 36 | 60 | 1500 | 26 | 248 | 174 | 70 | 191 | 77 | large |
| Plague Monk Censer Bearers | Pestilent Nave (4) | 120 | 9600 | 10 | 38 | 88 | 120 | 33 | 207 | 160 | 77 | 147 | 71 | small |
| Plague Monks | Pox Cauldron (3) | 120 | 9120 | 10 | 33 | 84 | 100 | 32 | 135 | 132 | 98 | 125 | 93 | small |
| Clanrat Spears (Shields) | Clan Barracks (2); Skryre landmark (1) | 160 | 9600 | 35 | 36 | 61 | 100 | 30 | 78 | 117 | 150 | 116 | 150 | small |
| Cauldron of a Thousand Poxes | Pox Cauldron chain (3) | 1 | 5408 | 72 | 35 | 72 | 2000 | 5 | 269 | 111 | 41 | 526 | 195 | very large |
| Mutant Rat Ogre | Force-Feeding Chambers (4) | 1 | 6508 | 30 | 38 | 60 | 3000 | 4 | 269 | 106 | 40 | 596 | 222 | very large |
| Clanrats (Shields) | Clan Barracks (2); Skryre landmark (1) | 160 | 9600 | 35 | 30 | 61 | 100 | 30 | 73 | 100 | 137 | 100 | 137 | small |
| Rat Ogres | Pits of the Packmasters (3) | 16 | 7728 | 30 | 26 | 61 | 1500 | 12 | 166 | 75 | 45 | 196 | 118 | large |
| Brood Horror | Force-Feeding Chambers (4) | 1 | 6009 | 40 | 30 | 55 | 2500 | 8 | 236 | 71 | 30 | 210 | 89 | very large |
| Warp-Grinders | Weapons Dump (2) | 24 | 4416 | 92 | 26 | 51 | 600 | 34 | 118 | 61 | 52 | 53 | 45 | small |
| Skavenslave Spears | any settlement (0) | 180 | 9000 | 0 | 29 | 41 | 90 | 29 | 21 | 59 | 277 | 61 | 288 | small |
| Skavenslaves | any settlement (0) | 180 | 9000 | 0 | 23 | 41 | 90 | 29 | 18 | 52 | 290 | 54 | 302 | small |

Below Clanrats on every column and omitted: Pusbags, Wolf Rats (both), Eshin Triads, Death Runners. Rank 7 perks lift
everyone 4 to 30 percent and change no order; the Grinderfists gain most (+10 armour, 10% physical resistance from
Mutagenic Elixirs) and reach Time 773 / 311 per 100 upkeep.

Seconds in contact by enemy type (full stack), which is where the monsters earn their place:

| Unit | vs line infantry | vs Chosen | vs Minotaurs | vs Demigryphs |
|---|---|---|---|---|
| Stormvermin (Swords & Shields) | 522 | 83 | 65 | 225 |
| Stormfiends (Grinderfists) | 904 | 188 | 240 | 461 |
| Hell Pit Abomination | 612 | 180 | 223 | 421 |
| Mutant Rat Ogre | 726 | 219 | 287 | 522 |
| Rat Ogres | 230 | 78 | 93 | 176 |
| Doomwheel | 1557 | 181 | 283 | 500 |
| Doom-Flayers | 333 | 46 | 63 | 120 |
| Clanrat Spears (Shields) | 153 | 46 | 34 | 109 |

Reading the tables:

- **Stormvermin are the wall.** 3.5x the soak of shielded Clanrats for 2.4x the upkeep, 1.9x the soak of melee
  Stormfiends for 0.7x the upkeep, and 32 m of front per unit against 9 m for a monster. Five units cover 160 m,
  which is a whole deployment-width line. They also carry the best autoresolve weight per upkeep of any real unit
  (melee combat potential 950 for 176 gold).
- **Their weakness is monstrous infantry and elite anti-infantry.** Minotaurs go through a Stormvermin unit in about a
  minute. That is exactly what the cannons kill fastest (a 10000 HP monster in under three volleys), so the fix is
  target priority, not a different line.
- **Grinderfists are the monster pick.** Best time per gold in the roster, from a building you build anyway one tier
  before the cannons, and the only monster candidate the Workshop improves (Melee Stormfiends I to III: +10 melee
  attack, +15% weapon strength, Blade Swirl, Regeneration). Regeneration heals 0.1 percent of HP per second, which on
  8772 HP is 9 HP a second for the whole unit, worth about a sixth more holding over a long fight; it also adds 20
  percent fire weakness.
- **The Hell Pit Abomination is the strongest single tarpit, not a spam unit.** Highest mass (5000) and leadership
  (90), 12100 HP, Regeneration, and Too Horrible to Die (on death, two seconds of 10 percent per second healing or a
  pack of rats). It is also 6 m tall, 373 upkeep, and needs the separate Moulder chain to tier 5. One per army at
  most, and only if the enemy is cavalry-heavy.
- **Rat Ogres, Brood Horror, Mutant Rat Ogre, Cauldron** sit on the Moulder chains, have no Workshop line (Clan Skryre
  cannot have the Flesh Lab), and lose to the Grinderfists on time per gold, soak per gold or both.
- **Skavenslaves** are cheapest per gold but break after a third of their models die and cover the same width as
  Clanrats. A charge sponge, not a line.
- **Doom-Flayers, even with every Workshop upgrade, are a hammer, not a wall.** The Workshop line is real (Doom
  Diagnostics +15 charge and +8 damage vs infantry, Propeller Knife-Blades = Blade Swirl, Obsidian Alloy +10 melee
  attack and +12% weapon strength, Spiked Armour Plates +10 melee defence and 12% ward save, Aero-Die-Namics vanguard
  and +15% speed), the tech They Can't Blame Their Tools adds +10 armour and +10% weapon strength, the Warpseer's
  Engineering Skill +12 armour and +12 charge, and the unit's own passive The Best Defence is an unconditional +24
  armour. That stacks to 136 armour and a 67 charge bonus with 43 bonus vs infantry: excellent at hitting infantry.
  But holding is about hit points, melee defence and leadership, and there the unit has 6064 HP in eight 758 HP
  vehicles, melee defence 36, leadership 60 and no Strength in Numbers. Armour 136 blanks base damage, but every
  elite unit's armour-piercing half goes straight through (Chosen: 38 of 50 damage is AP). Result at full stack:
  about half the soak of Stormvermin for 1.4x the upkeep, 46 seconds against Chosen and 63 against Minotaurs
  before breaking. Chariots also cannot brace, stop dealing damage once stationary, and lose a whole vehicle per 758
  damage, none of which the model charges them for. They do stay 2 m tall, so the cannons can fire over them.
  Use them as a cycle-charging flank hammer in an army that needs one; the Stormfiend army does not, because the
  cannons are the damage.
- **The Doomwheel is the surprise of the vehicle pass, as a tarpit.** Skavenslave Grease (+10 melee defence,
  Strider), Meat Shields (+15 armour, 12% missile resistance), the same tech and Engineering Skill, and 100 base
  armour make a 137-armour, 47-defence, 2000-mass single entity that stays in contact longer per gold than anything
  else in the roster. It is 3 m tall (blocks fire if in front), its lightning hits whatever is in range including
  friends, and it needs the tier 5 Warp-Turbine Plant. A flank anchor if you already own one, not a spam unit.

## 3. Everything permanent that touches the two picks

Stormvermin (Swords & Shields):

| Source | Effect | How to get it |
|---|---|---|
| Strength in Numbers (unit passive) | +8 melee defence, +6 leadership, 10% slower, while enough Skaven units are nearby | Always on in a 20-unit Skaven army |
| Tech: Ensure Absolute Loyalty (tier 7, 1600 RP) | +5 melee attack, +5 melee defence | Skaven military tree |
| Tech: Requisition Protective Gear (tier 9, 1200 RP) | +5 armour | Already on the Stormfiend tech path |
| Tech: Hit & Run (tier 1, 800 RP) | +10% speed (all infantry) | Already on the Stormfiend tech path |
| Lord red line: Respected & Feared | +6 melee attack, +9% weapon strength | Any Skaven lord, including the Verminlord Warpseer |
| Lord red line: Quartermaster, Renowned & Feared, Draftmaster | -18% upkeep, +2 recruit rank | Same skills the Stormfiend build already takes |
| Lord red line: Whip-Smart (rank 7 units only) | +5 melee attack, +5 leadership, 15% missile resistance | Takes battle experience |

Result: melee attack 38 to 49, melee defence 36 to 41 (49 with Strength in Numbers), armour 90 to 95, leadership 70 to
76 in the stack, upkeep 213 to 176. Not applicable: the Forbidden Workshop, Ikit Claw's trait, any Skryre faction tech.

Stormfiends (Grinderfists):

| Source | Effect | How to get it |
|---|---|---|
| Forbidden Workshop: Melee Stormfiends I | +10 melee attack, +15% weapon strength | Workshop, Clan Skryre only |
| Forbidden Workshop: Melee Stormfiends II | Blade Swirl (10% missile resistance, sunders armour on contact) | Workshop |
| Forbidden Workshop: Melee Stormfiends III | Regeneration (0.1% HP/s, -20% fire resistance) | Workshop |
| Tech: Monstrous Abominations (tier 5, 800 RP) | +15 charge bonus, +5% weapon strength | Same tech the cannons want |
| Tech: Refined Punching Power (tier 8, 400 RP) | +10% weapon strength, 10% missile resistance | On the cannons' Portable Destruction line |
| Tech: Practiced Goaders (tier 5, 400 RP) | +5 leadership | Same line |
| Tech: Requisition Protective Gear (tier 9, 1200 RP) | +5 armour | Same tech as above |
| Tech: Hit & Run | +10% speed | Same tech as above |
| Lord red line: Moulder Knowledge | +12 charge bonus, +10% speed | Any Skaven lord |
| Lord red line: Mutagenic Elixirs (rank 7 only) | +10 armour, +5 leadership, 10% physical resistance | Takes battle experience |
| Lord red line: upkeep skills | -18% upkeep | As above |
| Frenzy (unit passive) | +10 melee attack, +10% weapon strength, immune to psychology while above half health | Always |

Result: melee attack 38 to 58 with Frenzy, armour 90 to 95 (105 at rank 7), leadership 65 to 70, upkeep 300 to 246,
plus Regeneration and Blade Swirl. No hero skill tree (Packmaster included) carries an army-wide passive for any of
these units; the lord red line is the whole list.

## 4. Progression

| Phase | Unit | Building and settlement tier |
|---|---|---|
| Turn 1 (Skryre only) | Clanrat Spears (Shields) | Warpstone Telescope, tier 1, the capital landmark chain |
| Tier 2 elsewhere | Clanrat Spears (Shields) | Clan Barracks, Clan Pit chain level 2 |
| Tier 3 | Stormvermin (Swords & Shields) | Clan Armoury, Clan Pit chain level 3 |
| Tier 4 (optional anchors) | Stormfiends (Grinderfists) | Brain-Breeding Facilities, Stormfiend chain level 1, the same building step the cannons need anyway |

Two chains in the recruitment province cover the whole army: Clan Pit (to the Armoury) and Stormfiends (Brain-Breeding
Facilities, then Equipment Warpforge).

Suggested 20-slot army at the end state: Verminlord Warpseer, 5 Stormvermin (Swords & Shields), 2 Stormfiends
(Grinderfists) on the flanks, 12 Stormfiends (Ratling Cannons). Drop the Grinderfists for two more cannons against
infantry-only enemies; swap one for a Hell Pit Abomination against heavy cavalry if a Laboratory exists.

## 5. Deployment notes from the stat model

- Line of fire: the cannons are 2.8 m tall. Stormvermin (1.6 m) and Clanrats (1.5 m) are fired over; any monster or
  monstrous infantry (2.8 m and up) in front of a cannon unit blocks it and eats its own side's 78 percent
  armour-piercing bullets. Anchors go on the ends of the line.
- Mass: a Demigryph charge (mass 1500 per model) throws Stormvermin (150) around and barely moves Stormfiends (1500) or
  a Hell Pit (5000). Spears or halberds braced negate the charge bonus of large attackers; swords do not. If the
  enemy is mostly shock cavalry, make the two anchors the units that take the charge.
- Leadership: Stormvermin sit at 76 inside the stack, the melee Stormfiends at 70 with Frenzy making them immune to
  fear and terror while above half health. Nothing in the line is expendable except Clanrats (with the Strength in
  Numbers tech) and Skavenslaves, so a routing Stormvermin unit does cost its neighbours leadership.

## 6. Model, scripts and caveats

**Soak.** For each enemy archetype (Empire Swordsmen; Chosen with great weapons; Minotaurs; Demigryph Knights) hit
chance = 35 + enemy melee attack (+ bonus vs infantry or vs large) - our melee defence, clamped to 8..90 percent;
damage per hit = base x (1 - armour x U(0.5, 1) / 100) + armour-piercing, times physical and ward resistance; soak =
hit points / (hit chance x damage). Leadership enters as the fraction of hit points a unit spends before routing,
0.2 + leadership/100 capped at 1 (unbreakable = 1); Regeneration adds 15 percent.

**Time.** Contact front for a formation = files (men / rank depth) x model pitch (2 x radius + 0.2 m) x 1.15 for the
wrapped corners; for a single entity = half its circumference. Enemy models in contact = contact front / enemy pitch
(1.1 m for small, 2.2 m for large). Time = soak x enemy attack interval / models in contact. Charges, splash, fatigue,
spells and army abilities are not modelled; the intent is a ranking, not a battle simulator.

**Rebuild.**

```
python scripts/game/melee_model.py                                            # Skaven non-missile units -> tww/model_melee.json
python scripts/game/buffs.py  tww/model_melee.json tww/buffs_melee.json        # tech / Workshop / lord-skill layer for them
python scripts/game/settle.py tww/model_melee.json tww/settlement_melee.json   # recruitment building + settlement tier
python scripts/game/frontline_eval.py [raw|full|full+r7]                       # the ranking above (default full)
```

`buffs.py` and `settle.py` take optional input/output paths; with no arguments they behave as before (ranged page).
The DB tables listed in `run_all.py` (`TABLES`) plus `special_ability_to_special_ability_phase_junctions_tables`,
`special_ability_phase_stat_effects_tables` and `special_ability_phase_attribute_effects_tables` must be dumped first
(`python scripts/game/dumpdb.py <tables>`); the last three are where the Strength in Numbers, Frenzy, Regeneration,
Blade Swirl and Too Horrible to Die numbers come from.

**Caveats.** Friendly fire is argued from entity heights, not measured. The twwstats dump lists every Skaven unit
under one faction key, so Skryre availability was read from the game's building tables; no unit here is locked away
from Skryre. Pusbags, the Brood Horror and the melee Stormfiend variants are 9.0-era units whose abilities were read
from the game DB, not the wiki. The contact-front arithmetic is a geometric estimate; it is good enough to separate
"one monster pinned by twelve models" from "a line engaged by forty", not to predict a duel.

## 8. Army-level comparison: Stormvermin line vs Stormfiend melee line (18 slots)

Produced by `scripts/game/frontline_compose.py` from the same model as section 2. Army = Verminlord Warpseer + Warlock Engineer + 18 slots; cannon DPS 679 per unit (full stack plus the Engineer's three cannon skills); cannon row 16 m per unit in two ranks; 45 s of fire before infantry contact. Grinderfists "1 rank" = the unit stretched to a single rank of 12 (26 m) to cover frontage; "3 ranks" = default 4-wide block (9 m).

Per unit, full stack, no rank 7 (the three melee variants share every defensive stat, so only Grinderfists are modelled; the gauntlets change upkeep and damage output, not holding power):

| Unit | Width m | Upkeep | Soak | Soak /100 upk | Time | secs vs line inf | vs Chosen | vs Minotaurs | vs Demigryphs |
|---|---|---|---|---|---|---|---|---|---|
| Stormvermin (S&S) | 32 | 176 | 345 | 196 | 304 | 522 | 83 | 65 | 225 |
| Grinderfists, 3 ranks | 9 | 248 | 183 | 74 | 610 | 904 | 188 | 240 | 461 |
| Grinderfists, 1 rank | 26 | 248 | 183 | 74 | 203 | 301 | 63 | 80 | 154 |
| Doom-flayer Gauntlets, 3 ranks | 9 | 269 | 183 | 68 | 610 | 904 | 188 | 240 | 461 |
| Shock Gauntlets, 3 ranks | 9 | 290 | 183 | 63 | 610 | 904 | 188 | 240 | 461 |

Compositions (SV = Stormvermin S&S, GF = Grinderfists, RC = Ratling Cannon Stormfiends):

| Composition | Line width m | Cannon row m | Line covers row | Line soak (sum) | Weakest unit secs vs Chosen | vs Demigryphs | Cannon DPS | Damage before contact | Upkeep / turn | Recruit gold | Line of fire |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 6 SV + 12 RC (baseline) | 192 | 192 | yes | 2071 | 83 | 225 | 8148 | 366k | 5018 | 24400 | clear (1.6 m line) |
| 6 GF (3 ranks) + 12 RC | 53 | 192 | no (139 m short) | 1099 | 188 | 461 | 8148 | 366k | 5450 | 26500 | blocked: 2.8 m line in front of 2.8 m guns |
| 6 GF (1 rank) + 12 RC | 158 | 192 | no (34 m short) | 1099 | 63 | 154 | 8148 | 366k | 5450 | 26500 | blocked: 2.8 m line in front of 2.8 m guns |
| 7 GF (1 rank) + 11 RC | 185 | 176 | yes | 1283 | 63 | 154 | 7469 | 336k | 5422 | 26350 | blocked: 2.8 m line in front of 2.8 m guns |
| 8 GF (1 rank) + 10 RC | 211 | 160 | yes | 1466 | 63 | 154 | 6790 | 305k | 5393 | 26200 | blocked: 2.8 m line in front of 2.8 m guns |
| 4 SV + 2 GF (3 ranks, flanks) + 12 RC | 146 | 192 | no (46 m short) | 1747 | 83 | 225 | 8148 | 366k | 5162 | 25100 | clear if GF stay on the flanks |
| 5 SV + 1 GF (3 ranks) + 12 RC | 169 | 192 | no (23 m short) | 1909 | 83 | 225 | 8148 | 366k | 5090 | 24750 | clear if GF stay on the flanks |
