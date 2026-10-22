# Open items (written 2026-10-19, end of the session that released v0.3.10)

At the start of a session, remind the player of these, and say which need a multiplayer session.

## Needs a multiplayer session
- [ ] **Steal-Takes in multiplayer**: start, complete and abandon a Steal-Take with the command-paced clicks
      (they were not unlocked yet in the 2026-10-19 campaign).
- [ ] **Camera edge-scroll panning** (heroes.pan_by_edge, camera_pan auto/edge): never run live. Steal-Take targets
      and hero walks use it in multiplayer.
- [x] **Desync / reload recovery** (2026-10-22, single player): a real reload was exercised twice (the turn-58
      autosave loaded on turn 59, then on turn 58). A load shows no campaign for a moment, so it was taken for a new
      campaign ("acts from next turn"); fixed: a save of the same campaign at the same or an earlier turn runs that
      turn's start again ("the campaign was reloaded: running this turn's start again", checked live). A desync
      reloads the same way; an actual desync is still unseen.
- [ ] **auto_end_turn on a second PC** (strategy/automation.json): tested in single player only.
- [ ] **A pass interrupted by another player's hold mid-pass**: should stay pending and resume (runner._try_pass).

- [ ] **Secrets shop from memory in multiplayer (2026-10-22)**: the shop's offer is read per player (each player's
      own DLCs, bot/sensor/masterplans.shop: the entitlement entry is found by [faction+0xD88] -> player slot +0x398).
      Check that the local player's entry is the one read and that runs/masterplans.jsonl has no "shop_check" rows.

## Any session (single player is fine)
- [ ] **Secrets shop from memory (2026-10-22)**: after a few Build & End Turn passes that open the shop, runs/
      masterplans.jsonl should have no "shop_check" rows (panel and memory listing the same lines per tab).
- [ ] **Building spending order and saving (2026-10-20)**: watch a few turns: "saving for ... in N turn(s)" appears for a top item,
      cheap items are still bought with the spare gold, the saved item is bought on the turn it said, and the army
      still recruits with what is beyond the reserve.
- [ ] **Skill step after the memory_state fix (2026-10-20)**: Triangulation, Warp-Smart, Draftmaster, Quartermaster etc.
      are taken again in order; runs/skills_check.jsonl shows no memory/card disagreement.
- [ ] **Spilled-over recruits**: what the game does when a unit queued past the recruitment capacity cannot be paid
      when it starts (dropped, or waits); decode which queue items are paid (queue item X) to replace runs/army_owed.json.
- [ ] **Magma Cannon build swap (2026-10-20) live checks**: a capital with Equipment Warpforge + Warp-Turbine Plant
      shows the Magma Cannon card in the local pool and the army builder refills it there; the first refill disbands
      the Stormvermin; the dashboard's "Province recruiting Ratling Cannons + Magma Cannons" line turns green there.
- [ ] **Workshop level 2 from the planned Cavern line** (Ikit, workshop level 1, no Cavern yet): no temporary Cavern
      is built while a capital plans the Warp-Turbine Plant; the planned one counts once it stands.
- [ ] **Skill prerequisites from memory** (skills.memory_state): runs next to the card states; every disagreement is
      logged to runs/skills_check.jsonl. 2026-10-22: the unique_0 disagreement was an off-by-one: unlocked_at_rank
      counts from 0 (Mentor 29 showed "Available at rank 30" live); fixed, and the skill-locks table
      (character_skill_nodes_skill_locks) is read too. One lock is still unexplained: Thanquol's Chittering Masses
      (unique_4, REQUIRED parent unique_0 taken) reads locked on the card with no reason in its tooltip and nothing
      in the DB. Until it is found the card check stays.
- [x] **The Lord's recruitment cost** (2026-10-22): agent_subtypes.cost; the Recruit Lord panel showed exactly it for
      every Lord type (Warpseer 1000, Grey Seer 850, Warlord 550, Warlock Master 1200), and the Warlock Engineer's 400
      likewise. new_army.create and the engineer recruitment check the gold before any click. Cost modifiers from
      effects are not decoded (none seen yet).
- [x] **Hero caps with bonuses** (2026-10-22, turn 55): memory engineer cap 2 = the Recruit Hero panel's "1 / 2" (base
      1 plus a bonus). The turn-55 "refused at cap 1/2" was gold (399 against 400): fixed, reported as no gold.
- [ ] **Workshop (Ikit)** with the command pacing: not run since the change.
- [ ] **Standing answers for routine decisions** (idea): strategy/decisions.json, the player's rules for AI diplomacy
      offers, captives, recurring dilemmas. Needs the player's rules.
