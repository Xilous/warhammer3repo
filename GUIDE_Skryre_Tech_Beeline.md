# Clan Skryre tech bee-line for Stormfiend (Ratling Cannons) + Warp-Doom Magma-Cannon

Source: installed game DB (technology_nodes / technology_node_links / technology_effects_junction / unit sets). Node set `skv_mil`, 56 nodes available to `wh2_main_skv_clan_skryre` (Eshin/Moulder-only nodes dropped). 
Every node has required_parents=0 (= ALL linked parents needed) and there are no technology-to-technology extra requirements, so the prerequisite closure of a tech is exactly its ancestor set in the link graph. The `building_level` column on these techs is the placeholder `wh_main_chs_port_ruin`: no building gates. In-game, clicking a locked tech queues every missing prerequisite ahead of it.

**Rule.** Every effect of every tech is classified: OUR UNITS (unit set contains Stormfiend Ratling Cannons or Warp-Doom Magma-Cannon, any scope: stats, recruit rank, upkeep...), other units only, hero/lord in play (Warlock Engineer, Verminlord, Lord recruit rank, Hero action, Hero recruitment cost), hero not in play (Chieftain, Assassin, Plague Priest, Packmaster, Grey Seer, Eshin Sorcerer), or faction / army / province (no unit targeting at all). A tech is wanted unless every effect is "other units only" or "hero not in play", or the player left it out (Best of the Best, Ensure Absolute Loyalty, 2026-10-20). Hidden script effects are ignored.

## Techs that directly touch either unit

| Tier | Tech (db key) | RP | Effect | Units | Unit set |
|---|---|---|---|---|---|
| 1 | Hit & Run (`wh2_main_tech_skv_3_2`) | 800 | Speed: +10% for Infantry units | Stormfiend (Ratling) | `infantry_units` |
| 5 | Monstrous Abominations (`wh2_main_tech_skv_4_1`) | 800 | Charge bonus: +15 for Rat Ogres, Mutant Rat Ogre and Stormfiend units | Stormfiend (Ratling) | `wh2_dlc16_skv_rat_ogres_mutant_rat_ogres`, `wh3_dlc29_stormfiends` |
| 5 | Monstrous Abominations (`wh2_main_tech_skv_4_1`) | 800 | Weapon strength: +5% for Rat Ogres, Mutant Rat Ogre and Stormfiend units | Stormfiend (Ratling) | `wh2_dlc16_skv_rat_ogres_mutant_rat_ogres`, `wh3_dlc29_stormfiends` |
| 5 | Practiced Goaders (`wh2_main_tech_skv_4_4`) | 400 | Leadership: +5 for Rat Ogre and Stormfiend units | Stormfiend (Ratling) | `skv_ratogres`, `wh3_dlc29_stormfiends` |
| 7 | Ensure Product Quality (`wh2_main_tech_skv_6_2`) | 1200 | Missile strength: +10% for Warpfire Thrower, Warplock Jezzails, Ratling Gun, Poisoned Wind Globadiers, Poisoned Wind Mortars, Death Globe Bombardiers and Ranged Stormfiend units | Stormfiend (Ratling) | `skv_weaponteams_no_warpgrinder`, `wh2_dlc12_skv_jezzail` |
| 7 | Ensure Product Quality (`wh2_main_tech_skv_6_2`) | 1200 | Range: +10% for Warpfire Thrower, Warplock Jezzails, Ratling Gun, Poisoned Wind Globadiers, Poisoned Wind Mortars, Death Globe Bombardiers and Ranged Stormfiend units | Stormfiend (Ratling) | `skv_weaponteams_no_warpgrinder`, `wh2_dlc12_skv_jezzail` |
| 7 | Unfathomable Horrors (`wh2_main_tech_skv_4_3`) | 800 | Recruit rank: +2 for Rat Ogres, Mutant Rat Ogre, Hell Pit Abomination and Stormfiend units | Stormfiend (Ratling) | `skv_hellpit_abomination`, `wh2_dlc16_skv_rat_ogres_mutant_rat_ogres`, `wh3_dlc29_stormfiends` |
| 9 | Requisition Protective Gear (`wh2_main_tech_skv_7_2`) | 1200 | Armour: +5 for Stormvermin and Stormfiend units | Stormfiend (Ratling) | `skv_stormvermin`, `wh3_dlc29_stormfiends` |
| 9 | They Can't Blame Their Tools (`wh2_main_tech_skv_7_3`) | 1200 | Armour: +10 for Plagueclaw Catapult, Doom-Flayers, Warp Lightning Cannon, Warp-Doom Magma-Cannon and Doomwheel units | Warp-Doom Magma-Cannon | `skv_artillery`, `skv_doomwheel`, `wh2_dlc12_skv_doomflayers` |
| 8 | Portable Destruction (`wh3_dlc29_tech_skv_9_1_2`) | 400 | Missile strength: +10% for Stormfiend (Ratling Cannons, Warpfire Projectors, Windlaunchers) units | Stormfiend (Ratling) | `wh3_dlc29_missile_stormfiends` |
| 8 | Portable Destruction (`wh3_dlc29_tech_skv_9_1_2`) | 400 | Range: +10% for Stormfiend (Ratling Cannons, Warpfire Projectors, Windlaunchers) units | Stormfiend (Ratling) | `wh3_dlc29_missile_stormfiends` |

## Every tech, classified

| Tier | Tech | RP | Wanted | Effects |
|---|---|---|---|---|
| 0 | Ferocious Plans | 100 | **yes** | Local recruitment capacity: +1 [faction / army / province] |
| 0 | Ruthless Plans | 100 | **yes** | Food generated: 1 [faction / army / province] |
| 0 | Devious Plans | 100 | **yes** | Upkeep: -13% for Skavenslaves units [other units only]<br>Recruitment cost: -5% [faction / army / province] |
| 1 | Driven by Hunger | 400 | **yes** | Recruit rank: +2 for Clanrats units [other units only]<br>Income from post-battle loot: +5% [faction / army / province] |
| 1 | Harsh Production Quotas | 400 | **yes** | Recruitment cost: -5% for Skavenslaves, Pusbags and Clanrats units [other units only]<br>Growth: +10 [faction / army / province] |
| 1 | Fight Dirty! | 800 | no | Missile strength: +10% for Night Runners and Gutter Runners units [other units only]<br>Weapon strength: +10% for Night Runners and Gutter Runners units [other units only] |
| 1 | Always More Besides | 400 | **yes** | Casualty replenishment rate: +5% [faction / army / province] |
| 1 | Hit & Run | 800 | **yes** | Speed: +10% for Infantry units [OUR UNITS] |
| 1 | Intensive Training | 800 | no | Recruit rank: +2 for Night Runners and Gutter Runners units [other units only] |
| 2 | Strength in Numbers | 400 | no | Attribute: Expendable for Clanrats units [other units only]<br>Charge bonus: +5 for Clanrats units [other units only]<br>Melee attack: +5 for Clanrats units [other units only] |
| 2 | Set Examples | 400 | **yes** | Leadership: +3 [faction / army / province] |
| 2 | Abduct Promising Candidates | 800 | no | Recruitment cost: -5% for Night Runners and Gutter Runners units [other units only]<br>Upkeep: -5% for Night Runners and Gutter Runners units [other units only] |
| 2 | Scavenging Runs | 400 | no | Armour: +10 for Clanrats units [other units only] |
| 2 | Numbers Beyond Counting | 400 | no | Charge bonus: +5 for Skavenslaves and Pusbags units [other units only]<br>Melee defence: +5 for Skavenslaves and Pusbags units [other units only]<br>Upkeep: -20% for Skavenslaves and Pusbags units [other units only] |
| 2 | Murder Dissenters | 400 | **yes** | Public order: +1 [faction / army / province] |
| 2 | Know Your Place! | 400 | **yes** | Loyalty: +2 for new recruits [faction / army / province] |
| 2 | Eyes Everywhere | 800 | **yes** | Ambush success chance: +5% [faction / army / province] |
| 2 | Exotic Martial Arts | 800 | no | Hero recruit rank: +2 for Assassins [hero not in play] |
| 3 | Take Everything! | 400 | **yes** | Magic item drop chance from battle: +3% [faction / army / province]<br>Income from sacking settlements: +5% [faction / army / province] |
| 3 | Virulent Plans | 100 | **yes** | Adds an extra Clanrat unit to the army spawned from "The Vermintide" Under-City building [faction / army / province]<br>Food capacity: +30 [faction / army / province]<br>Food generated: 1 [faction / army / province] |
| 3 | Cadre of Hench-Rats | 400 | no | Hero recruit rank: +2 for Chieftains [hero not in play]<br>Leadership: +5 for Clanrats units [other units only] |
| 3 | Carve Undertunnels | 400 | **yes** | Campaign movement range: +10% [faction / army / province] |
| 3 | Exploit Criminals | 800 | **yes** | Hero action cost: -20% [hero/lord in play]<br>Hero recruitment cost: -33% [hero/lord in play] |
| 4 | The Menace Below | 400 | **yes** | Missile resistance: 10% during siege battles [faction / army / province]<br>Leadership: +10 when laying siege or encircling [faction / army / province] |
| 4 | Distil Poisons | 1200 | no | Weapon strength: +10% for Plague Monks units [other units only] |
| 3 | Horned One's Approval | 400 | **yes** | Disable Domination Scheme with Verminlord [STATUS: HIDDEN] [hero/lord in play]<br>After using the Dominating Scheme rite, a Verminlord will become available for recruitment [hero/lord in play] |
| 4 | Monstrous Plans | 100 | **yes** | Adds an extra Clanrat unit to the army spawned from "The Vermintide" Under-City building [faction / army / province]<br>Food capacity: +30 [faction / army / province]<br>Food generated: 1 [faction / army / province] |
| 5 | Hallucinogenics | 1200 | no | Leadership: +10 for Plague Monk units [other units only]<br>Melee attack: +5 for Plague Monks units [other units only] |
| 5 | Spread Rot & Decay | 1200 | **yes** | Adds an extra Plague Monk unit to the army spawned from "The Vermintide" Under-City building [faction / army / province]<br>Skaven corruption in adjacent provinces: +1 [faction / army / province] |
| 6 | Volatile Plans | 100 | **yes** | Adds an extra Clanrat unit to the army spawned from "The Vermintide" Under-City building [faction / army / province]<br>Food capacity: +30 [faction / army / province]<br>Food generated: 1 [faction / army / province] |
| 4 | Rat-Daemons | 400 | **yes** | Campaign movement range: +10% for Verminlords [hero/lord in play]<br>Experience gain: +25% for Verminlords [hero/lord in play] |
| 5 | Monstrous Abominations | 800 | **yes** | Charge bonus: +15 for Rat Ogres, Mutant Rat Ogre and Stormfiend units [OUR UNITS]<br>Weapon strength: +5% for Rat Ogres, Mutant Rat Ogre and Stormfiend units [OUR UNITS] |
| 5 | Practiced Goaders | 400 | **yes** | Hero recruit rank: +2 for Packmasters [hero not in play]<br>Leadership: +5 for Rat Ogre and Stormfiend units [OUR UNITS] |
| 5 | Record Effective Recipes | 1200 | no | Hero recruit rank: +2 for Plague Priests [hero not in play] |
| 6 | Enormous Caches | 1200 | **yes** | Adds an extra Plagueclaw Catapult unit to the army spawned from "The Vermintide" Under-City building [faction / army / province]<br>Upkeep: -5% for Warpfire Thrower, Ratling Gun, Warplock Jezzails, Poisoned Wind Globadiers, Poisoned Wind Mortars and Death Globe Bombardiers units [other units only]<br>Ammunition: +25% for Missile Infantry units [other units only] |
| 7 | Ensure Product Quality | 1200 | **yes** | Missile strength: +10% for Warpfire Thrower, Warplock Jezzails, Ratling Gun, Poisoned Wind Globadiers, Poisoned Wind Mortars, Death Globe Bombardiers and Ranged Stormfiend units [OUR UNITS]<br>Range: +10% for Warpfire Thrower, Warplock Jezzails, Ratling Gun, Poisoned Wind Globadiers, Poisoned Wind Mortars, Death Globe Bombardiers and Ranged Stormfiend units [OUR UNITS] |
| 6 | Twisted Beyond Recognition | 800 | no | Melee attack: +5 for Hell Pit Abomination units [other units only]<br>Weapon strength: +10% for Hell Pit Abomination units [other units only] |
| 6 | Freaks off the Leash | 400 | no | Bonus vs Infantry: +5 for Wolf Rat and Brood Horror units [other units only]<br>Weapon strength: +10% for Wolf Rat and Brood Horror units [other units only] |
| 6 | Oppressive Plans | 100 | **yes** | Adds an extra Clanrat unit to the army spawned from "The Vermintide" Under-City building [faction / army / province]<br>Food capacity: +30 [faction / army / province]<br>Food generated: 1 [faction / army / province] |
| 7 | Reject Poor Recruits | 1200 | no | Recruit rank: +2 for Warpfire Thrower, Ratling Gun, Warplock Jezzails, Poisoned Wind Globadiers, Poisoned Wind Mortars and Death Globe Bombardiers units [other units only] |
| 8 | Ingenious Plans | 100 | **yes** | Adds an extra Clanrat unit to the army spawned from "The Vermintide" Under-City building [faction / army / province]<br>Food capacity: +30 [faction / army / province]<br>Food generated: 1 [faction / army / province] |
| 6 | Eliminate the Competition | 1600 | **yes** | Agent action name assassinate action: Additional 5% success chance [faction / army / province] |
| 7 | Unfathomable Horrors | 800 | **yes** | Adds a Hell Pit Abomination unit to the army spawned from "The Vermintide" Under-City building [faction / army / province]<br>Recruit rank: +2 for Rat Ogres, Mutant Rat Ogre, Hell Pit Abomination and Stormfiend units [OUR UNITS] |
| 7 | Brood Breeders | 400 | no | Recruit rank: +2 for Wolf Rat and Brood Horror units [other units only]<br>Upkeep: -5% for Wolf Rats and Brood Horror units [other units only] |
| 7 | Masters of Infiltration | 1600 | **yes** | Diplomatic relations: +10 with all factions [faction / army / province] |
| 7 | Best of the Best | 1600 | no | Adds a Doomwheel unit to the army spawned from "The Vermintide" Under-City building [faction / army / province]<br>Recruit rank: +2 for Stormvermin and Death Runners units [other units only] |
| 7 | Rule Through Fear | 1600 | no | Charge bonus: +10 for Death Runners units [other units only]<br>Leadership: +10 for Death Runners units [other units only]<br>Weapon strength: +10% for Death Runners units [other units only] |
| 7 | Ensure Absolute Loyalty | 1600 | no | Melee attack: +5 for Stormvermin units [other units only]<br>Melee defence: +5 for Stormvermin units [other units only]<br>Public order: +1 [faction / army / province] |
| 8 | Promoted on Merit | 1200 | **yes** | Hero recruit rank: +2 for Warlock Engineers [hero/lord in play]<br>Ammunition: +20% for Doomwheel, Plagueclaw Catapult, Warp Lightning Cannon and Warp-Doom Magma-Cannon units [other units only]<br>Reload time reduction: +10% for Doomwheel, Plagueclaw Catapult, Warp Lightning Cannon and Warp-Doom Magma-Cannon units [other units only]<br>Lord recruit rank: +2 [hero/lord in play] |
| 8 | Plans Within Plans | 100 | **yes** | Adds an extra Clanrat unit to the army spawned from "The Vermintide" Under-City building [faction / army / province]<br>Food capacity: +30 [faction / army / province]<br>Food generated: 1 [faction / army / province] |
| 9 | Requisition Protective Gear | 1200 | **yes** | Armour: +10 for Warpfire Thrower, Ratling Gun, Poisoned Wind Globadiers, Poisoned Wind Mortars and Death Globe Bombardiers units [other units only]<br>Armour: +5 for Stormvermin and Stormfiend units [OUR UNITS] |
| 8 | New Warpstone Uses | 1600 | **yes** | Casualty replenishment rate: +10% [faction / army / province]<br>Local recruitment capacity: +1 [faction / army / province] |
| 9 | They Can't Blame Their Tools | 1200 | **yes** | Armour: +10 for Plagueclaw Catapult, Doom-Flayers, Warp Lightning Cannon, Warp-Doom Magma-Cannon and Doomwheel units [OUR UNITS]<br>Missile strength: +10% for Plague Claw Catapults, Warp Lightning Cannons, Warp-Doom Magma-Cannon and Doomwheel units [other units only]<br>Weapon strength: +10% for Doomwheel and Doom-Flayers units [other units only] |
| 9 | Ultimate Experiments | 1600 | **yes** | Replaces all Clanrat units spawned from "The Vermintide" Under-City building with Stormvermin [faction / army / province]<br>Income from all buildings: +5% [faction / army / province]<br>Growth: +25 [faction / army / province] |
| 8 | Refined Punching Power | 400 | no | Missile resistance: +10% for Stormfiend (Grinderfist, Doomflayer Gauntlets, Shock Gauntlets) units [other units only]<br>Weapon strength: +10% for Stormfiend (Grinderfist, Doomflayer Gauntlets, Shock Gauntlets) units [other units only] |
| 8 | Portable Destruction | 400 | **yes** | Missile strength: +10% for Stormfiend (Ratling Cannons, Warpfire Projectors, Windlaunchers) units [OUR UNITS]<br>Range: +10% for Stormfiend (Ratling Cannons, Warpfire Projectors, Windlaunchers) units [OUR UNITS] |

## Bee-line targets

37 wanted techs out of 56. 16 targets; their chains cover 47 techs for 32100 RP (10 of those are unwanted but sit on the way). 9 techs are never researched: Scavenging Runs, Numbers Beyond Counting, Cadre of Hench-Rats, Freaks off the Leash, Reject Poor Recruits, Brood Breeders, Best of the Best, Rule Through Fear, Ensure Absolute Loyalty.

Unwanted techs researched only because they are prerequisites: Fight Dirty!, Intensive Training, Strength in Numbers, Abduct Promising Candidates, Exotic Martial Arts, Distil Poisons, Hallucinogenics, Record Effective Recipes, Twisted Beyond Recognition, Refined Punching Power.

## Click order

Phase 0 = the Verminlord unlock, forced first (see the section after the table). Every row is a leaf: no click in this table is a prerequisite of a later click, so each click is a separate queue entry and nothing is clicked twice. Phase 1 = every target whose chain adds a tech that buffs our units, cheapest remaining chain first. Phase 2 = the remaining faction-buff leaves, cheapest first. Click the target; the game queues every missing prerequisite ahead of it. Cumulative RP assumes nothing else is researched; turns = cumulative RP at the base 100 RP per turn (Warp-Forge +4, Warp-Turbine Plant +8 each shorten this).

| # | Phase | Click this target | New techs queued | Added RP | Cumulative RP | Turns at 100 RP | Unit buffs gained on the way |
|---|---|---|---|---|---|---|---|
| 1 | 0 | Rat-Daemons (T4) | 10 | 3400 | 3400 | 34 |  |
| 2 | 1 | Practiced Goaders (T5) | 3 | 900 | 4300 | 43 | Practiced Goaders |
| 3 | 1 | Hit & Run (T1) | 3 | 1700 | 6000 | 60 | Hit & Run |
| 4 | 1 | Unfathomable Horrors (T7) | 3 | 2400 | 8400 | 84 | Monstrous Abominations, Unfathomable Horrors |
| 5 | 1 | Promoted on Merit (T8) | 4 | 2600 | 11000 | 110 | Ensure Product Quality |
| 6 | 1 | They Can't Blame Their Tools (T9) | 2 | 2400 | 13400 | 134 | Requisition Protective Gear, They Can't Blame Their Tools |
| 7 | 1 | Portable Destruction (T8) | 9 | 7000 | 20400 | 204 | Portable Destruction |
| 8 | 2 | Always More Besides (T1) | 1 | 400 | 20800 | 208 |  |
| 9 | 2 | Murder Dissenters (T2) | 1 | 400 | 21200 | 212 |  |
| 10 | 2 | Know Your Place! (T2) | 1 | 400 | 21600 | 216 |  |
| 11 | 2 | Eyes Everywhere (T2) | 1 | 800 | 22400 | 224 |  |
| 12 | 2 | Spread Rot & Decay (T5) | 1 | 1200 | 23600 | 236 |  |
| 13 | 2 | Enormous Caches (T6) | 1 | 1200 | 24800 | 248 |  |
| 14 | 2 | Ultimate Experiments (T9) | 1 | 1600 | 26400 | 264 |  |
| 15 | 2 | Eliminate the Competition (T6) | 5 | 4100 | 30500 | 305 |  |
| 16 | 2 | Masters of Infiltration (T7) | 1 | 1600 | 32100 | 321 |  |

## Why the Verminlord techs go first (from the game script and DB)

- Clan Skryre has one way to get a Verminlord: the **Dominating Scheme** rite. Horned One's Approval (T3, 400 RP) carries two hidden effects: it disables the plain rite (`wh2_main_ritual_skv_ascendancy`, 13-turn cooldown) and enables `wh3_main_ritual_skv_ascendancy_verminlord` (same name and icon, **15-turn cooldown**, 5-turn global rite cooldown, same growth / food / recruitment-cost / public-order payload for 5 turns).
- When the Verminlord version completes, `ritual_payload_trigger_dilemmas` fires the dilemma `wh3_dlc29_ascendancy_summon_verminlord` ("A Dark Song Complete") with five choices: Corruptor, Deceiver, **Warpseer**, Warbringer, Do Nothing. `wh3_dlc29_verminlords.lua` spawns the chosen subtype into the lord pool (`spawn_character_to_pool`; the Warpseer arrives with the Scry Orb). **There is no success roll for the player**: the random pick only applies to AI Skaven. Recruiting from the pool costs the normal 2100.
- So the Verminlord supply is one per 15 turns from the turn the tech completes. Research the chain first and the first Warpseer lands around turn 30 at the base 100 RP per turn, the second 15 turns later, and so on; every turn the tech slips, the whole ladder slips.
- Rat-Daemons (T4, 400 RP, only parent is Horned One's Approval): +25% experience and +10% campaign movement for Verminlords. Cheap, and it compounds over the whole campaign, so it follows immediately.


Flat research order (what the queue will actually research, in a valid order; bold = buffs our units, (skip) = unwanted prerequisite):

1. Ferocious Plans (T0, 100 RP)
2. Ruthless Plans (T0, 100 RP)
3. Driven by Hunger (T1, 400 RP)
4. Harsh Production Quotas (T1, 400 RP)
5. Strength in Numbers (T2, 400 RP) (skip)
6. Set Examples (T2, 400 RP)
7. Take Everything! (T3, 400 RP)
8. Carve Undertunnels (T3, 400 RP)
9. Horned One's Approval (T3, 400 RP)
10. Rat-Daemons (T4, 400 RP) <- click target
11. The Menace Below (T4, 400 RP)
12. Monstrous Plans (T4, 100 RP)
13. **Practiced Goaders** (T5, 400 RP) <- click target
14. Devious Plans (T0, 100 RP)
15. Fight Dirty! (T1, 800 RP) (skip)
16. **Hit & Run** (T1, 800 RP) <- click target
17. **Monstrous Abominations** (T5, 800 RP)
18. Twisted Beyond Recognition (T6, 800 RP) (skip)
19. **Unfathomable Horrors** (T7, 800 RP) <- click target
20. Volatile Plans (T6, 100 RP)
21. **Ensure Product Quality** (T7, 1200 RP)
22. Ingenious Plans (T8, 100 RP)
23. Promoted on Merit (T8, 1200 RP) <- click target
24. **Requisition Protective Gear** (T9, 1200 RP)
25. **They Can't Blame Their Tools** (T9, 1200 RP) <- click target
26. Abduct Promising Candidates (T2, 800 RP) (skip)
27. Virulent Plans (T3, 100 RP)
28. Distil Poisons (T4, 1200 RP) (skip)
29. Hallucinogenics (T5, 1200 RP) (skip)
30. Record Effective Recipes (T5, 1200 RP) (skip)
31. Plans Within Plans (T8, 100 RP)
32. New Warpstone Uses (T8, 1600 RP)
33. Refined Punching Power (T8, 400 RP) (skip)
34. **Portable Destruction** (T8, 400 RP) <- click target
35. Always More Besides (T1, 400 RP) <- click target
36. Murder Dissenters (T2, 400 RP) <- click target
37. Know Your Place! (T2, 400 RP) <- click target
38. Eyes Everywhere (T2, 800 RP) <- click target
39. Spread Rot & Decay (T5, 1200 RP) <- click target
40. Enormous Caches (T6, 1200 RP) <- click target
41. Ultimate Experiments (T9, 1600 RP) <- click target
42. Intensive Training (T1, 800 RP) (skip)
43. Exotic Martial Arts (T2, 800 RP) (skip)
44. Exploit Criminals (T3, 800 RP)
45. Oppressive Plans (T6, 100 RP)
46. Eliminate the Competition (T6, 1600 RP) <- click target
47. Masters of Infiltration (T7, 1600 RP) <- click target

# Hero skills that buff the army (hero embedded in the army)

Scopes counted as army-wide: agent_to_parent_army_own, character_to_force_own, character_to_force_own_alt_text, character_to_force_own_unseen, character_to_force_regionwide_own. Self-only (character_to_character_own) and general-only (agent_to_parent_army_general_own) skills are ignored. Values are listed per skill level.

## Warlock Engineer

### Hits Stormfiend / Magma Cannon directly

| Skill (row, unlock rank) | Effect | Value per level | Units | Unit set | Prerequisite nodes |
|---|---|---|---|---|---|
| Standardised Firing Drill (row 0, rank 0) | Reload time reduction: %+n% for all Missile units | +8 | Stormfiend (Ratling) | `missile_units` | - |
| Triangulation (row 4, rank 0) | Missile strength: %+n% | +3 / +7 / +12 | Stormfiend (Ratling) | `all_units` | Standardised Firing Drill (REQUIRED) |
| Sapper (row 9, rank 0) | Speed: %+n% for all Missile units | +3 / +8 / +15 | Stormfiend (Ratling), Warp-Doom Magma-Cannon | `missile_units` | Ballistics Calibration (REQUIRED) |

### Army-wide, not unit-targeted (still applies to the army)

| Skill (row, unlock rank) | Effect | Value per level | Scope |
|---|---|---|---|
| Arms Dealer (row 1, rank 0) | Ammunition: %+n% | +8 / +12 / +20 | agent_to_parent_army_own |
| Cunning (row 5, rank 0) | Ambush success chance: %+n% | +25 | character_to_force_regionwide_own |
| Confident (row 7, rank 0) | Leadership: %+n | +2 | character_to_force_own |
| Disciplined (row 8, rank 0) | Leadership: %+n | +2 | character_to_force_own |
| Disciplined (row 8, rank 0) | Melee attack: %+n | +2 | character_to_force_own |
| Perceptive (row 9, rank 0) | Magic item drop chance from battle: %+n% | +15 | character_to_force_own_unseen |
| Perceptive (row 9, rank 0) | Ambush defence chance: %+n% | +15 | character_to_force_own_alt_text |
| Tactician (row 15, rank 0) | Reinforcements supporting this army can have their arrival point adjusted by %+n metres without incurring any time penalty | +500 | character_to_force_own_unseen |
| Knowledgeable (row 16, rank 0) | Magic item drop chance from battle: %+n% | +15 | character_to_force_own_unseen |


# Appendix: the whole Skryre tech graph (parents = must be researched first)

| Tier | Tech | RP | Parents | Wanted |
|---|---|---|---|---|
| 0 | Ferocious Plans | 100 | (root) | yes |
| 0 | Ruthless Plans | 100 | (root) | yes |
| 0 | Devious Plans | 100 | (root) | yes |
| 1 | Driven by Hunger | 400 | Ferocious Plans | yes |
| 1 | Harsh Production Quotas | 400 | Ruthless Plans | yes |
| 1 | Fight Dirty! | 800 | Devious Plans |  |
| 1 | Always More Besides | 400 | Driven by Hunger | yes |
| 1 | Hit & Run | 800 | Fight Dirty! | yes |
| 1 | Intensive Training | 800 | Fight Dirty! |  |
| 2 | Strength in Numbers | 400 | Driven by Hunger |  |
| 2 | Set Examples | 400 | Harsh Production Quotas | yes |
| 2 | Abduct Promising Candidates | 800 | Fight Dirty! |  |
| 2 | Scavenging Runs | 400 | Strength in Numbers |  |
| 2 | Numbers Beyond Counting | 400 | Always More Besides |  |
| 2 | Murder Dissenters | 400 | Set Examples | yes |
| 2 | Know Your Place! | 400 | Set Examples | yes |
| 2 | Eyes Everywhere | 800 | Abduct Promising Candidates | yes |
| 2 | Exotic Martial Arts | 800 | Intensive Training |  |
| 3 | Take Everything! | 400 | Strength in Numbers | yes |
| 3 | Virulent Plans | 100 | Abduct Promising Candidates | yes |
| 3 | Cadre of Hench-Rats | 400 | Scavenging Runs |  |
| 3 | Carve Undertunnels | 400 | Take Everything!, Set Examples | yes |
| 3 | Exploit Criminals | 800 | Exotic Martial Arts | yes |
| 4 | The Menace Below | 400 | Take Everything! | yes |
| 4 | Distil Poisons | 1200 | Virulent Plans |  |
| 3 | Horned One's Approval | 400 | Carve Undertunnels | yes |
| 4 | Monstrous Plans | 100 | The Menace Below | yes |
| 5 | Hallucinogenics | 1200 | Distil Poisons |  |
| 5 | Spread Rot & Decay | 1200 | Distil Poisons | yes |
| 6 | Volatile Plans | 100 | The Menace Below | yes |
| 4 | Rat-Daemons | 400 | Horned One's Approval | yes |
| 5 | Monstrous Abominations | 800 | Monstrous Plans | yes |
| 5 | Practiced Goaders | 400 | Monstrous Plans | yes |
| 5 | Record Effective Recipes | 1200 | Carve Undertunnels, Hallucinogenics |  |
| 6 | Enormous Caches | 1200 | Volatile Plans | yes |
| 7 | Ensure Product Quality | 1200 | Volatile Plans | yes |
| 6 | Twisted Beyond Recognition | 800 | Monstrous Abominations |  |
| 6 | Freaks off the Leash | 400 | Practiced Goaders |  |
| 6 | Oppressive Plans | 100 | Exploit Criminals, Record Effective Recipes | yes |
| 7 | Reject Poor Recruits | 1200 | Ensure Product Quality |  |
| 8 | Ingenious Plans | 100 | Ensure Product Quality | yes |
| 6 | Eliminate the Competition | 1600 | Oppressive Plans | yes |
| 7 | Unfathomable Horrors | 800 | Twisted Beyond Recognition | yes |
| 7 | Brood Breeders | 400 | Freaks off the Leash |  |
| 7 | Masters of Infiltration | 1600 | Oppressive Plans | yes |
| 7 | Best of the Best | 1600 | Oppressive Plans |  |
| 7 | Rule Through Fear | 1600 | Oppressive Plans |  |
| 7 | Ensure Absolute Loyalty | 1600 | Oppressive Plans |  |
| 8 | Promoted on Merit | 1200 | Ingenious Plans | yes |
| 8 | Plans Within Plans | 100 | Record Effective Recipes, Ingenious Plans | yes |
| 9 | Requisition Protective Gear | 1200 | Ingenious Plans | yes |
| 8 | New Warpstone Uses | 1600 | Plans Within Plans | yes |
| 9 | They Can't Blame Their Tools | 1200 | Requisition Protective Gear | yes |
| 9 | Ultimate Experiments | 1600 | Plans Within Plans | yes |
| 8 | Refined Punching Power | 400 | New Warpstone Uses |  |
| 8 | Portable Destruction | 400 | Refined Punching Power | yes |

Rebuild: `python scripts/game/skv_beeline.py` (needs `tww/db` from `python run_all.py game` plus `python scripts/game/dumpdb.py character_skill_node_links_tables technology_required_technology_junctions_tables`).