# Stormfiends (Ratling Cannons) mono-unit campaign guide

Total War: Warhammer III, Update 9.0 line. Every number below is read from the game's own database and English text
packs, not from the wiki. Rebuild notes and scripts: `C:\Users\jaymi\tww3-ranged-doomstack`.

## 1. What you are building

A single-unit-type army progression that ends in Stormfiends (Ratling Cannons), played in **Clan Skryre** (Ikit Claw's
faction) so the Forbidden Workshop is available, with the Stormfiend armies led by a **Verminlord Warpseer** generic lord.

Why this combination:

- The Workshop's three Ranged Stormfiend upgrades are the largest single buff source outside the tech tree, and only
  Clan Skryre has it.
- Every Skaven lord shares the same red line for ranged Stormfiends. The Warpseer is the only lord with an extra
  missile buff for them (Purest Warpstone, +15% missile strength, +10% ammunition for Skryre units).
- Ikit Claw's own trait only touches weapon teams, so he leads the Ratling Gun army in the mid game and hands the
  Stormfiend armies to Warpseers later.

Full stack result for one unit of 12, against armoured elite infantry:

| Stat | Raw | Full stack (no rank 7) | With Rank 7 perks |
|---|---|---|---|
| Range | 145 | 174 | 174 |
| Damage per bullet (base / AP) | 2 / 7 | 3.0 / 9.5 | 3.2 / 10.3 |
| Reload skill | 0 | 18 | 18 |
| Ammunition per model | 588 (14 volleys) | 911 (21 volleys) | 911 |
| Armour | 70 | 100 | 100 |
| Upkeep | 338 | 277 | 277 |
| DPS | 340 | 564 | 614 |
| Battle damage, one unit | 23.8k | 50.2k | 54.6k |

## 2. What to own

| Item | Exact name | Steam app ID |
|---|---|---|
| Base game | Total War: WARHAMMER III | 1142710 |
| Stormfiends, Verminlords, Warp-Doom Magma-Cannon, Thanquol | Total War: WARHAMMER III – Thanquol – Lords of the End Times (in-game product "Lords of the End Times - Skaven") | 3589660 |
| Clan Skryre, Ikit Claw, Forbidden Workshop, Ratling Guns, Warplock Jezzails | Total War: WARHAMMER II – The Prophet & The Warlock | 1834045 |

Not needed: Warhammer I, Warhammer II, The Shadow & The Blade, The Twisted & The Twilight, Tretch Craventail's free
pack, the other three Lords of the End Times packs. The Thanquol pack alone satisfies the Skaven core-roster check.

Caveat: the game only checks the pack, but Steam has historically required the Warhammer II app to buy its DLC.
If The Prophet & The Warlock cannot be bought on a Warhammer III-only account, use the fallback in section 6.

## 3. Progression (one unit type at a time)

| Phase | Unit | Building and settlement tier | Notes |
|---|---|---|---|
| Opening | Skavenslave Slingers or Night Runners (slings) | tier 1, base roster | Placeholder until a tier 2 settlement exists. |
| Tier 2 | Warpfire Throwers | Weapons Dump (Weapon Burrow chain, first level), 1000 gold, main building tier 2 | Already a weapon team, so Blastmaster and the weapon-team techs carry forward. |
| Tier 3 | Ratling Guns | Weapon Burrow, 2000 gold, main building tier 3 | Same gun family as the Stormfiend cannon, same buff sets. Ikit's trait halves their upkeep, so Ikit leads this army. Workshop "Endless Drum" makes their ammunition effectively infinite. |
| Tier 4 | (build step) | Brain-Breeding Facilities, 4000 gold, 4 turns, main building tier 4 | First level of the Stormfiend chain. |
| Tier 5 | Stormfiends (Ratling Cannons) | Equipment Warpforge, 8000 gold, 5 turns, main building tier 5 | Final spam unit, led by a Verminlord Warpseer. |

The Weapon Burrow chain is a support building; put it in a province that will reach tier 5 anyway. Skaven
technologies no longer require buildings (since 9.0), so research runs on its own clock.

## 4. Every permanent, non-active buff on Stormfiends (Ratling Cannons), and how to get each one online

"Permanent, non-active" means: once obtained it applies to the unit in every battle with no button to press. Rites,
Masterplans, army abilities, spells and items are excluded.

### 4a. Technology tree (Skaven military tree, all factions)

| Tech | Tier | Research points | Effect on the unit | Prerequisite chain |
|---|---|---|---|---|
| Hit & Run | 1 | 800 | +10% speed (all infantry) | Devious Plans → Fight Dirty! |
| Monstrous Abominations | 5 | 800 | +15 charge bonus, +5% weapon strength (melee only) | Ferocious Plans → Driven by Hunger → Strength in Numbers → Take Everything! → The Menace Below → Monstrous Plans |
| Practiced Goaders | 5 | 400 | +5 leadership (also +2 recruit rank for Packmasters) | same line as Monstrous Abominations |
| Ensure Product Quality | 7 | 1200 | +10% missile strength, +10% range | The Menace Below → Volatile Plans |
| Portable Destruction | 8 | 400 | +10% missile strength, +10% range | Record Effective Recipes → Carve… → Plans Within Plans → New Warpstone Uses → Refined Punching Power |
| Requisition Protective Gear | 9 | 1200 | +5 armour | Ensure Product Quality → Ingenious Plans |

Tech total: +20% missile strength, +20% range, +5 armour, +5 leadership, +10% speed, +15 charge bonus.
Priority order for this build: Ensure Product Quality, Portable Destruction, then the rest as the tree allows.

### 4b. Forbidden Workshop (Clan Skryre only)

Found in Ikit Claw's faction panel. Upgrades are bought with Warpstone and Warp-fuel as the Workshop levels up
(Technician's Grotto through Great Warpforge). Buy the three Ranged Stormfiend upgrades in order:

| Upgrade | Effect on ranged Stormfiends |
|---|---|
| Ranged Stormfiends I | Reload time reduction +10% |
| Ranged Stormfiends II | +25 armour, 10% missile resistance |
| Ranged Stormfiends III | +25% ammunition, +15% missile strength |

Also relevant for the mid game: the Ratling Gun upgrades, including the Endless Drum passive (ammunition
regenerates once it drops below 80%).

### 4c. Army lord skills (the lord leading the Stormfiend army)

Available to every Skaven lord in the army ("red line") section:

| Skill | Points | Effect on ranged Stormfiends |
|---|---|---|
| Blastmaster | 3 | Ammunition +8% / +12% / +20%; reload time reduction +4% at rank 2, +8% at rank 3 |
| Warp-Smart | 1 | Only for units at veteran rank 7: +12% missile strength, +5 leadership, 15% spell resistance |
| Draftmaster | 1 | +1 recruit rank for all units |
| Renowned & Feared | 1 | +1 recruit rank, −8% upkeep |
| Quartermaster | 1 | −10% upkeep |

Verminlord Warpseer only (unique line):

| Skill | Effect |
|---|---|
| Purest Warpstone | +15% missile strength, +10% ammunition for Skryre units (Stormfiends count) |

How to get a Verminlord Warpseer: Verminlords become recruitable after the Dominating Scheme rite is used, or via the
Great-Smart Masterplan that unlocks "Summon Verminlord". Clan Skryre is permitted all four Verminlord types.
Thanquol's unique Replaceable Fodder (−10% upkeep) only applies when Thanquol himself leads.

### 4d. Unit veterancy (makes Warp-Smart live)

Warp-Smart's bonuses need the unit at rank 7. Draftmaster and Renowned & Feared start them two ranks up; the rest
is battle experience. Treat the Warp-Smart numbers as a late-campaign bonus, not a baseline.

### 4e. Landmark (Clan Scruten only, listed for the fallback path)

The Morskittar Engine, a five-step landmark chain in Zhufbar (1500 / 3000 / 6000 / 8000 / 10000 gold, settlement
tiers 1 to 5), unlocked by Thanquol's fourth narrative mission. Its final level gives +10% missile strength
faction-wide for artillery and monstrous missile infantry, which includes Stormfiends. Not available to Clan Skryre.

### 4f. Things that look relevant but do not apply

- Refined Punching Power, Moulder Knowledge, Mutagenic Elixirs: melee Stormfiends only (Grinderfists, Doomflayer
  Gauntlets, Shock Gauntlets).
- Throt's Flesh Lab augments: Clan Moulder only, and you cannot have the Lab and the Workshop in the same faction.
- Ikit Claw's lord trait: Warplock Jezzails, Warpfire Throwers and Ratling Guns only.
- Warp-Smart's bonus-vs-infantry line: Doomwheel, Doom-Flayers and Warp-Grinders only.
- Buildings, items, banners and hero skills: not counted here. The only building-level effect in the tables that
  targets Stormfiends is the Morskittar Engine above.

## 5. Full-stack arithmetic

Missile strength multiplies base and AP separately: techs 20% + Workshop 15% + Warpseer 15% = +50% base and +35% AP
(the Workshop line is base-only in the tables), +12% more at rank 7. Range 145 × 1.20 = 174. Reload skill 8
(Blastmaster) + 10 (Workshop) = 18, so the 5 s reload becomes 4.1 s. Ammunition 588 × (1 + 0.20 + 0.25 + 0.10) = 911
shots, 21 volleys, about 89 s of continuous fire. Armour 70 + 5 + 25 = 100. Upkeep 338 × 0.82 = 277.

## 6. Fallback without The Prophet & The Warlock

Play **Clan Scruten (Thanquol)** with the Thanquol pack only. Mid game becomes Warpfire Throwers (tier 2) then
Poisoned Wind Globadiers or Warplock-less weapon teams until tier 5. You lose the Workshop (reload 10, armour 25,
missile resistance 10%, ammunition 25%, missile strength 15%) and Ratling Guns. You keep every tech, the full red
line, a Verminlord Warpseer if you recruit one, and gain the Morskittar Engine's +10% missile strength.

## 7. Battlefield notes from the stat model

- Armour hardly matters to the cannon: 78% of each bullet is armour-piercing. Shields do: 55% shields from the
  front cut damage to 36%, so flank or let them come to you.
- Large single entities die fast (a 10000 HP, 100-armour monster in about 2.6 volleys from one unit), but small
  single entities on foot are mostly missed at range (about 7% hit chance at 145 m). Close to 60 m or charge them.
- Ethereal units (75% physical resistance) take a quarter damage. The Scratterfire Team regiment fires magical
  bullets and is the answer if Vampire Counts or Vampire Coast are neighbours.
- Ammunition is the real limit. Do not spend it on chaff before the monsters and lords arrive.
