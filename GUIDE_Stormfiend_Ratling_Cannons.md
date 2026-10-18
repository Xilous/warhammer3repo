# Stormfiends (Ratling Cannons) mono-unit campaign guide

Total War: Warhammer III, Update 9.0 line. Every number below is read from the game's own database and English text
packs, not from the wiki. Rebuild notes and scripts: `C:\Users\jaymi\Documents\warhammer3repo`.

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

How to get a Verminlord Warpseer:

- **Every Skaven faction:** the Dominating Scheme rite, once the tech Horned One's Approval is researched (one
  Verminlord per 15-turn rite cooldown; see `GUIDE_Skryre_Tech_Beeline.md`). Clan Skryre is permitted all four
  Verminlord types.
- **Clan Scruten (Thanquol) only, in addition:** the Great-Smart Masterplan "Summon Verminlord", run by the Grey Seer
  Underling. It is unlocked by buying Verminlord Study I (800 Warpstone) in the Clan Scruten Secrets shop, single
  player and multiplayer alike. Verminlord Study II to V (600 each) raise the summoned Verminlord's starting rank from
  1 to 3, 5, 7 and 10, and it arrives with an army. See `GUIDE_Thanquol_Masterplans.md`.

Thanquol's unique Replaceable Fodder (−50% recruitment cost and −10% upkeep for his own army, −2 turns global
recruitment duration) only matters when Thanquol himself leads.

### 4d. Unit veterancy (makes Warp-Smart live)

Warp-Smart's bonuses need the unit at rank 7. Draftmaster and Renowned & Feared start them two ranks up; the rest
is battle experience. Treat the Warp-Smart numbers as a late-campaign bonus, not a baseline.

### 4e. Landmark (Clan Scruten only, single player only)

The Morskittar Engine, a five-step landmark chain in Zhufbar (1500 / 3000 / 6000 / 8000 / 10000 gold, 1 to 5 turns,
settlement tiers 1 to 5). Its final level gives +10% missile strength faction-wide for artillery and monstrous
missile infantry, which includes Stormfiends. Not available to Clan Skryre.

- **It hits both halves of the bullet.** The effect carries both `missile_damage_mod_mult` and
  `missile_damage_ap_mod_mult`, like the techs and Purest Warpstone. The Workshop's +15% carries only the base half.
  On a 2 base + 7 armour-piercing bullet, the Engine's +10% is worth about 7% more damage per bullet; the Workshop's
  +15% about 2.4%.
- **Unlock: Thanquol's story missions 4 and 5.** `wh_campaign_setup.lua` locks all five levels for Clan Scruten at
  the start of every new Immortal Empires campaign (tooltip: "Complete Missions: Steal the Plan-Prints and Remind
  Them of Their Place"). Only mission 5's scripted reward removes the lock. Mission 4 is a Steal-Take Masterplan on
  Skavenblight; mission 5 needs Thanquol at rank 13 and the "Death From Within" quest battle.
- **Multiplayer: never.** The story registers itself only when the game is not multiplayer
  (`episode_narrative_thanquol.is_available_this_game` returns false for `cm:is_multiplayer()`), and no other game
  script removes the lock. Doing the same deeds in a multiplayer campaign unlocks nothing.
- The levels also add research points (+10 to +50 per turn), income (+100 to +500), Skaven diplomacy, and recruit
  rank and range for Warp Lightning Cannons, Warp-Doom Magma-Cannons and Doomwheels.

### 4f. Things that look relevant but do not apply

- Refined Punching Power, Moulder Knowledge, Mutagenic Elixirs: melee Stormfiends only (Grinderfists, Doomflayer
  Gauntlets, Shock Gauntlets).
- Throt's Flesh Lab augments: Clan Moulder only, and you cannot have the Lab and the Workshop in the same faction.
  (Clan Moulder can buy 33 of them for Ratling Cannon Stormfiends, upkeep reductions and a ward save among them; not
  evaluated here.)
- Ikit Claw's lord trait: Warplock Jezzails, Warpfire Throwers and Ratling Guns only.
- Warp-Smart's bonus-vs-infantry line: Doomwheel, Doom-Flayers and Warp-Grinders only.
- Buildings, items, banners and hero skills: not counted here. The only building-level effect in the tables that
  targets Stormfiends is the Morskittar Engine above.

## 5. Full-stack arithmetic

Missile strength multiplies base and AP separately: techs 20% + Workshop 15% + Warpseer 15% = +50% base and +35% AP
(the Workshop line is base-only in the tables), +12% more at rank 7. Range 145 × 1.20 = 174. Reload skill 8
(Blastmaster) + 10 (Workshop) = 18, so the 5 s reload becomes 4.1 s. Ammunition 588 × (1 + 0.20 + 0.25 + 0.10) = 911
shots, 21 volleys, about 89 s of continuous fire. Armour 70 + 5 + 25 = 100. Upkeep 338 × 0.82 = 277.

Clan Scruten, single player (Morskittar Engine instead of the Workshop): techs 20% + Engine 10% + Warpseer 15% = +45%
on both base and AP. Reload skill 8, so 4.6 s. Ammunition 588 × 1.30 = 764 shots, 18 volleys. Armour 75. In
multiplayer, or in any other Skaven faction, drop the Engine: +35% on both.

## 6. Playing it as Clan Scruten (Thanquol)

Clan Scruten is the backup campaign, and the way to play this build without The Prophet & The Warlock. Same techs,
same red line, same Warpseer. What changes for one unit of 12 at full stack, against armoured elite infantry
(the same target and model as the table in section 1):

| | Clan Skryre (Ikit) | Clan Scruten, single player | Clan Scruten in multiplayer, or any other Skaven faction |
|---|---|---|---|
| Missile strength, base / AP | +50% / +35% | +45% / +45% | +35% / +35% |
| Damage per bullet against 100 armour | 10.2 | **10.9** | 10.1 |
| Reload | 4.1 s | 4.6 s | 4.6 s |
| Ammunition per model | 911 (21 volleys) | 764 (18 volleys) | 764 (18 volleys) |
| Armour / missile resistance | 100 / 10% | 75 / 0% | 75 / 0% |
| DPS | 564 | 536 (−5%) | 499 (−11%) |
| Battle damage, one unit | 50.2k | 44.9k (−11%) | 41.8k (−17%) |

Against unarmoured targets the gaps are a little wider: −7% and −13% DPS, −12% and −18% battle damage.

- Per bullet, single-player Thanquol hits hardest, because the Morskittar Engine's +10% reaches the armour-piercing
  part and the Workshop's +15% does not. The Workshop wins everything else: reload, ammunition, armour and missile
  resistance.
- In multiplayer the Engine stays locked (section 4e), so the army is no stronger than any Skaven faction's.
- Without The Prophet & The Warlock, the mid game becomes Warpfire Throwers (tier 2), then Poisoned Wind Globadiers
  or other weapon teams until tier 5. With it, Clan Scruten recruits Ratling Guns from the same buildings as
  Clan Skryre (the recruitment rows carry no faction), without Ikit's halved upkeep or the Endless Drum.
- What Clan Scruten adds is campaign-side, through Masterplans: rank-10 Warpseers on top of the rite's one per 15
  turns, free one-siege armies that can carry Ratling Cannon Stormfiends, and Warpstone income. That strategy is in
  `GUIDE_Thanquol_Masterplans.md`.

## 7. Battlefield notes from the stat model

- Armour hardly matters to the cannon: 78% of each bullet is armour-piercing. Shields do: 55% shields from the
  front cut damage to 36%, so flank or let them come to you.
- Large single entities die fast (a 10000 HP, 100-armour monster in about 2.6 volleys from one unit), but small
  single entities on foot are mostly missed at range (about 7% hit chance at 145 m). Close to 60 m or charge them.
- Ethereal units (75% physical resistance) take a quarter damage. The Scratterfire Team regiment fires magical
  bullets and is the answer if Vampire Counts or Vampire Coast are neighbours.
- Ammunition is the real limit. Do not spend it on chaff before the monsters and lords arrive.
