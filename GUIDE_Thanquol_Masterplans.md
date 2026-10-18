# Thanquol's Masterplans in the Stormfiend (Ratling Cannons) playbook

Companion to `GUIDE_Stormfiend_Ratling_Cannons.md`, `GUIDE_Stormfiend_Frontline.md` and
`GUIDE_Skryre_Tech_Beeline.md`, for the backup campaign: **Clan Scruten (Thanquol)**, Immortal Empires, game 9.0.4.
The army is the playbook's: Verminlord Warpseer, Warlock Engineer, 6 Stormvermin (Swords & Shields), 12 Stormfiends
(Ratling Cannons). Every number is read from the game's scripts (`wh3_dlc29_thanquol_chaotic_plans*.lua`,
`wh3_dlc29_thanquol_schemers.lua`, `wh3_dlc29_episode_narrative_thanquol.lua`, `wh_campaign_setup.lua`) and DB
tables (`chaotic_plan_*`, `resource_cost_*`, `building_*`), not from the wiki.

Masterplans stay the player's: the assistant never acts in the panel (section 8).

## 1. Answer

Masterplans do not make the army hit harder. They feed the three things the playbook is short of: **Warpseer lords**,
**the first complete province**, and **resources** (Warpstone, gold). In single player they are also the road to
the Morskittar Engine.

| Playbook bottleneck | Without Masterplans | What Masterplans add |
|---|---|---|
| A Warpseer for every Stormfiend army | Dominating Scheme rite: one Verminlord per 15 turns, into the lord pool, 2100 gold to recruit | The Grey Seer Underling summons Warpseers through a Great-Smart plan, at rank 10 once Verminlord Study V is bought, with an army |
| The first complete province (commandments, the Dominating Scheme, the assistant's building step) | Black Water is Karag Dromar, Oakenhammer and Zhufbar; Zhufbar is a Dwarf hold Thanquol's army must take alone | A Kill-Stab plan on Zhufbar spawns a free army that joins Thanquol's assault; it is also story mission 1 |
| Gold for the Stormfiend chain (Brain-Breeding Facilities 4000, Equipment Warpforge 8000 per recruiting province) | Buildings, sacking | Steal-Take plans steal gold, Warpstone and food in lump sums; story missions 1 and 3 pay 1000 gold each |
| Siege work that costs the doomstack ammunition and time | The doomstack does every siege | The Warlock Master's Kill-Stab armies can field Ratling Cannon Stormfiends, with no recruitment or upkeep cost |
| Morskittar Engine (+10% missile strength, single player only) | Locked | Story missions 1 to 5 are mostly Masterplan missions; mission 4 is a Steal-Take on Skavenblight |

The short version: open with a Kill-Stab on Zhufbar timed with Thanquol's army, pick the **Warlock Master** as the
second Underling, buy his Warpstone drill upgrade first, then turn the **Grey Seer** into a full-time Warpseer
summoner.

## 2. How a Masterplan works

1. Pick an Underling, a plan type and a foreign settlement that is not a ruin. Starting costs 50 Warpstone.
2. Every turn the plan draws Schemes (cards) from that Underling's bag: 2 per turn for Kill-Stab and Steal-Take,
   1 per turn for Great-Smart. Green = Rewards (units, loot, ritual pieces). Red = Complications, which raise Alarm
   by 1 to 3 and sometimes worse. Yellow = Manipulations, which fight Complications. Purple = Coincidences,
   mostly good wildcards. Every Scheme added raises the risk of a Complication next turn.
3. **Complete** is available from the plan's 2nd turn. The game's advisor says waiting to turn 3 is better and turn 4
   is the time to complete. At Alarm 4 you must complete at once or abandon.
4. **Abandon** at any time: nothing is refunded and the Underling sits out 1 turn. A region that just had a
   Masterplan cannot be targeted again for a few turns.
5. **Tricks** are paid actions during a plan (for example, remove a Complication).
6. The Underling earns 250 XP per Scheme drawn when the plan succeeds (half for a failed Steal-Take), levels up, and
   gets skill points like a character.
7. The **Clan Scruten Secrets** shop (Warpstone) is where the bag is improved: upgrades add better Schemes and remove
   junk. Each Underling has a shop of their own; Thanquol's Planning Rooms apply to every Underling. An upgrade marked
   "needs N" needs N earlier purchases in the same shop.

The three plan types:

| Plan | Result | Unlock (single player / multiplayer) |
|---|---|---|
| **Kill-Stab** (military) | A free army gathers under the target. On Complete it spawns, declares war on the owner (unless rebels) and besieges. It can only fight that settlement. If your own army attacks once Complete is available, the plan army spawns and joins the battle. Attacking earlier forces you to abandon. | From the first capture / same |
| **Steal-Take** (economic) | Gold, Warpstone and food from the target. At max Alarm, completing pays much less; abandoning instead gives a 10-turn mission to capture the region for the full amount. Conquering the target abandons the plan. | Story mission 1 / after your first successful plan |
| **Great-Smart** (magic) | Summon a Verminlord with an army (Grey Seer only); create an Under-City with up to 4 buildings already built (any Underling); Entreat the Horned Rat, which devastates a province (100 Warpstone). Completes only once the panel's Ritual Requirements (5 Plan Components) are drawn and you can pay the Schemes' costs. | Summon Verminlord: buy Verminlord Study I (both). Under-City: story mission 5 / turn 31. Entreat: after the final battle / turn 81 |

Every Underling's Kill-Stab bag starts as Clanrats, Night Runners, Rat Ogres and Skavenslaves. Without shop upgrades a
Kill-Stab army is chaff.

## 3. The Underlings and their jobs in this build

| Underling (shop) | Available | Job in this build | Upgrades that matter, Warpstone |
|---|---|---|---|
| **Grey Seer** (Scryanak's Temple) | From the start | Zhufbar Kill-Stab, then the permanent Warpseer summoner: the only Underling who can run Summon Verminlord | Superior Rats! 200 and Warlord Clan's Tunnel I 300 (the cheapest two, to open Study I); **Verminlord Study I 800** (unlocks Summon Verminlord); **Study II to V, 600 each** (summoned Verminlords start at rank 3, 5, 7, 10) |
| **Warlock Master** (Tailclaw's Labs) | Second Underling: pick him | Steal-Take Warpstone engine; Kill-Stab support armies with Ratling Cannons | Warpfire Equipment Racks 300; **Clan Skryre Drillers 300** (needs 1: each Drillers card +150 Warpstone; Veteran +250 and Elite +450 at 300 each); **Heavy Weapons Facility I 600** (needs 2: replaces Rat Ogres with Stormfiends (Ratling Cannons) in his Kill-Stab bag) |
| **Warlord** (Reekjaw's Warrens) | All Underlings: story mission 5 / turn 36 | Under-City plans; Kill-Stab line infantry | Clan Rictus Quarters I 600 (needs 2): Stormvermin (Swords & Shields) |
| **Master Assassin** (Chitterstab's Hideouts) | Same | Gold Steal-Take; Tricks that remove Complications | Clan Eshin Thieves 1000 (needs 4): cards that pay 100% / 200% / 300% of the target's income in gold, plus some Warpstone |

**Why the Warlock Master at the second-Underling choice** (story dilemma "First, a Rat's Paw" after mission 2; turn 6
in multiplayer): his shop is the only one with both a cheap Warpstone engine (Racks plus Drillers, 600) and the
playbook's own unit in Kill-Stab (Heavy Weapons Facility I, 600 more, and Racks and Drillers already count as its two
earlier purchases). The Warlord's Stormvermin cost 600 after two other purchases; the Assassin's gold upgrade needs
four. Both arrive later anyway.

Thanquol's Planning Rooms add, for every Underling: Training: Monsters I to III (400 / 500 / 600), which give the
monsters and monstrous infantry of a completed Kill-Stab army +3 / +6 / +9 ranks. Stormfiends count. Optional.

## 4. Warpstone: where it comes from and what to buy first

Income:

| Source | Amount | Notes |
|---|---|---|
| Grey Seer Lair, Karag Dromar | 25 / 50 / 100 per turn at levels 1 / 2 / 3 (2000 / 5000 / 10000 gold, settlement tiers 1 / 2 / 3) | Also 300 / 400 / 500 income. The assistant keeps and upgrades it |
| Under-Empire buildings | Warpstone Refinery 40, Strip Mine 60, Crafting 20 / 40 per turn | An Under-City plan can come with a Refinery or Crafting already built |
| Steal-Take | Warpstone cards of 30 to 600 each, plus cards that pay a share of the target's income | Clan Skryre Drillers add 150 / 250 / 450 per Drillers card, with a small chance of a Warlock mishap |
| Story missions (single player) | Mission 1: 50; mission 3: 50 + 50; mission 4: 500; mission 6: 200. Total 850 | None in multiplayer |

Spending order:

| # | Buy | Warpstone | Running total | Why here |
|---|---|---|---|---|
| 1 | Plans as you go | 50 each | | |
| 2 | Warpfire Equipment Racks + Clan Skryre Drillers (Warlock) | 600 | 600 | Pays for everything after it |
| 3 | Superior Rats! + Warlord Clan's Tunnel I + Verminlord Study I (Grey Seer) | 1300 | 1900 | A second Warpseer supply next to the rite: the playbook's bottleneck |
| 4 | Heavy Weapons Facility I (Warlock) | 600 | 2500 | Ratling Cannons in Kill-Stab armies, for the mid-game sieges |
| 5 | Verminlord Study II to V (Grey Seer), one level between summons | 2400 | 4900 | Summoned Warpseers at rank 10, with the red line and Purest Warpstone already affordable |
| 6 | Veteran and Elite Drillers (Warlock) | 600 | 5500 | Whenever Warpstone piles up between the big buys |
| 7 | Optional: Training: Monsters I to III (Thanquol) | 1500 | 7000 | Only if Kill-Stab armies do real fighting |
| 8 | Single player, late: Final Battle Support tokens | 1000 each | | For Thanquol's final battle |

## 5. The campaign, phase by phase

The phases follow the playbook's progression (`GUIDE_Stormfiend_Ratling_Cannons.md` section 3,
`GUIDE_Stormfiend_Frontline.md` section 4) and tech order (`GUIDE_Skryre_Tech_Beeline.md`).

### Phase 1: opening (settlement tiers 1 to 2; tech: Horned One's Approval, then Rat-Daemons)

- Take Oakenhammer first. Any capture unlocks Masterplans, and Oakenhammer is the second of Black Water's three
  regions.
- Grey Seer: **Kill-Stab on Zhufbar** as soon as Masterplans unlock (story mission 1). Move Thanquol's army next to
  Zhufbar. Do not attack until Complete is available, then attack: the plan army spawns and joins the battle. In the
  2026-10-17 test campaign the plan army attacked alone and lost when Zhufbar's garrison sallied out.
- What Zhufbar gives you:
  - **Black Water complete.** That allows the Expansionist Planning commandment, which the Dominating Scheme rite
    needs, so the playbook's Warpseer ladder can start. It also takes Black Water off the frontline, so the assistant
    starts building there.
  - **The Morskittar Engine's site.**
  - **Mission 1's reward:** 1000 gold, 50 Warpstone, and Steal-Take unlocked.

### Phase 2: economy (settlement tiers 2 to 3; Clanrat Spears then Stormvermin; Warpfire Throwers or Ratling Guns)

- Choose the **Warlock Master** at the dilemma. Buy Racks and Drillers. From now on the Warlock runs Steal-Take
  almost continuously.
- Steal-Take targets: the richest settlements you will not attack while the plan runs (conquering the target cancels
  it). Steal-Take does not declare war in the script; Kill-Stab does, on completion.
- Story mission 3 (2 Kill-Stab and 2 Steal-Take plans): 1000 gold and 50 Warpstone each, and a 6-turn bonus each.
- Story mission 4 (Steal-Take on Skavenblight): 500 Warpstone and the Morskittar notes.
- Buy the Verminlord Study I path (1300). The Grey Seer switches to Summon Verminlord for good; pick the Warpseer in
  the ritual selection.

### Phase 3: Stormfiend armies (settlement tiers 4 to 5; Brain-Breeding Facilities, Equipment Warpforge)

- Each new Stormfiend army's lord is a summoned Warpseer (rank 10 once Study V is in) or the rite's Warpseer, which
  the assistant picks in "A Dark Song Complete". The rite gives one per 15 turns; a summon plan draws one Scheme per
  turn until its five Plan Components are in, so the Grey Seer adds one every several turns on top.
- A summoned Warpseer comes with an army of its own. Tick it in the assistant only when you want the template: a
  ticked army has every off-template unit disbanded at once.
- Buy Heavy Weapons Facility I. The Warlock's Kill-Stab armies now carry Ratling Cannon Stormfiends: use them on
  secondary settlements the doomstack should not spend ammunition on, or to join the doomstack's siege.
- Single player: **story mission 5** (Thanquol at rank 13 and the "Death From Within" battle) unlocks all Underlings,
  Under-City plans and the Morskittar Engine. Build the Engine to level 5 at Zhufbar: 28,500 gold over 15 turns, and
  Zhufbar must reach tier 5. Level 5 gives the cannons +10% missile strength on base and armour-piercing damage,
  +50 research per turn (half again on the tech bee-line's base 100) and +500 income.

### Phase 4: late (all four Underlings)

- Warlord and Assassin: Under-City plans in neighbours you will not conquer, for Warpstone Refineries and Crafting.
- Warlord: Clan Rictus Quarters puts Stormvermin into his Kill-Stab armies, if you want a second support-army maker.
- Single player: Final Battle Support tokens (1000 Warpstone each) before Thanquol's final battle; Entreat the Horned
  Rat after it.

## 6. Multiplayer

- No story: no mission rewards (850 Warpstone, 3000 gold), no Morskittar Engine (`GUIDE_Stormfiend_Ratling_Cannons.md`
  section 4e).
- Unlocks by turn: second Underling choice on turn 6 (the same dilemma), Steal-Take after your first successful plan,
  Under-City on turn 31, all Underlings on turn 36, Entreat the Horned Rat on turn 81. Summon Verminlord unlocks the
  same way as in single player, through the shop.
- So the first plan has to be a Kill-Stab, and Zhufbar is still the target. Warpstone comes only from the Lair and
  Steal-Take, which makes the Drillers the most important early purchase.
- Kill-Stab declares war on the target's owner when completed. Never aim one at a friend's settlement unless that is
  the plan.

## 7. Rules that keep a plan alive

- Kill-Stab: no attack on the target before Complete is available. After that, attack with your own army and the plan
  army joins.
- Steal-Take at maximum Alarm: if you will take the region within 10 turns, abandon instead of completing; the mission
  pays the full amount on capture.
- Summon Verminlord: four Complications ("Corruptor / Deceiver / Warbringer / Warpseer Unbound") spawn an enemy
  Verminlord army. If one turns up, expect a fight near the target. (Not checked: whether it spawns when drawn or on
  completion.)
- "Teleport Daemon Lord" (a Complication in any plan) can bring a Chaos daemon legendary lord to the target.
- Conquering the target of any plan abandons it.

## 8. What the assistant does around Masterplans

- Never acts in the Masterplans panel. Run now and Build & End Turn close the panel (and its guided tour) first.
- Underlings are never treated as armies.
- Keeps and upgrades the Grey Seer Lair (Warpstone 25 to 100 per turn).
- Casts the commandment and the Dominating Scheme as soon as a complete province allows, and picks the Warpseer in
  the rite's dilemma.
- Does not tick summoned Verminlord armies; that stays your choice.
- Not checked yet: whether the building step tries to build the Morskittar Engine at Zhufbar while it is still locked.

## 9. Sources

- Plan rules, costs and multiplayer unlock turns: `wh3_dlc29_thanquol_chaotic_plans.lua`, `chaotic_plans_tables`,
  `chaotic_plan_types_resource_costs_junctions_tables`, `resource_cost_pooled_resource_junctions_tables`.
- Underlings, Kill-Stab army spawning: `wh3_dlc29_thanquol_schemers.lua`.
- Verminlord summons, Under-Cities, Entreat the Horned Rat, enemy Verminlords: `wh3_dlc29_thanquol_chaotic_plans_token_payloads.lua`.
- Shop: `chaotic_plan_shop_category_objects_tables` and its chain and category junctions, `chaotic_plan_upgrade_tokens_tables`,
  `chaotic_plan_token_to_generated_tokens_junctions_tables`, `chaotic_plan_token_removed_token_junctions_tables`.
- Story missions and rewards: `wh3_dlc29_episode_narrative_thanquol.lua`. Morskittar Engine lock:
  `wh_campaign_setup.lua`.
- Warpstone buildings: `building_effects_junction_tables` (`wh3_dlc29_pooled_resource_warpstone_buildings`),
  `building_levels_tables`.
- Tables dumped with `python scripts/game/dumpdb.py <table>`; scripts read from `data_script.pack`.
