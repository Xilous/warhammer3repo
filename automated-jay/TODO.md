# Open items (written 2026-10-19, end of the session that released v0.3.10)

At the start of a session, remind the player of these, and say which need a multiplayer session.

## Needs a multiplayer session
- [ ] **Steal-Takes in multiplayer**: start, complete and abandon a Steal-Take with the command-paced clicks.
      2026-10-22, single player: started and completed live with the command pacing on turns 50-58 (Castle
      Templehof, King's Glade, Waldenhof, Waterfall Palace, Vaul's Anvil), each confirmed in memory. Abandon (only
      with at_max_alarm "abandon") takes the same board and confirm path; not run live. What is left: the multiplayer
      sync of those clicks.
- [x] **Camera edge-scroll panning** (2026-10-22, single player with edge forced): bring_into_view brought 10
      settlement labels on screen by edge scrolling, near and far, as fast as WASD (0.7-4.8 s each). Steal-Take
      targets and hero walks use the same call.
- [x] **Desync / reload recovery** (2026-10-22, single player): a real reload was exercised twice (the turn-58
      autosave loaded on turn 59, then on turn 58). A load shows no campaign for a moment, so it was taken for a new
      campaign ("acts from next turn"); fixed: a save of the same campaign at the same or an earlier turn runs that
      turn's start again ("the campaign was reloaded: running this turn's start again", checked live). A desync
      reloads the same way; an actual desync is still unseen.
- [ ] **auto_end_turn on a second PC** (strategy/automation.json): tested in single player only.
- [ ] **A pass interrupted by another player's hold mid-pass**: should stay pending and resume (runner._try_pass).
      2026-10-22 review: the hold raises InputAborted after 3 minutes (tools/ui.wait_for_other_players), a
      BaseException no step can swallow; the turn-start pass stays pending. A Build & End Turn cut short that way
      was dropped; now it stays queued and runs again once the game is free. Not seen live.

- [ ] **Secrets shop from memory in multiplayer (2026-10-22)**: the shop's offer is read per player (each player's
      own DLCs, bot/sensor/masterplans.shop: the entitlement entry is found by [faction+0xD88] -> player slot +0x398).
      Check that the local player's entry is the one read and that runs/masterplans.jsonl has no "shop_check" rows.
      2026-10-22, single player: 3 entries (one more per load, it seems), all with the local player's slot (420) and
      the same bits.

## Any session (single player is fine)
- [ ] **Secrets shop from memory (2026-10-22)**: after a few Build & End Turn passes that open the shop, runs/
      masterplans.jsonl should have no "shop_check" rows (panel and memory listing the same lines per tab).
      Turn 56: one row, a false one (a tab checked again after its last line was bought, against the reading from
      before the purchase); fixed: each tab is checked once, before anything is bought in it. Watch a few more.
- [x] **Building spending order and saving (2026-10-20)**: checked from the logs of 2026-10-21/22 (turns 13-46):
      "saving for ... (in 1 turn(s))" was followed by that building the next turn 26 times out of 30; the 4 others
      had a reason the next turn (blocked by war, greyed out, or a cheaper main-building upgrade in the same province
      took its development points first: cheapest main upgrade first is the order). Cheap items went with the spare
      gold on the same turns.
- [x] **Skill step after the memory_state fix (2026-10-20)**: taken in order since (Ulcess Triangulation turn 53,
      Thanquol Lightning Strike / Ancient Cunning, Gottri Warp-Smart, Bonded Service, Draftmaster live 2026-10-22);
      the only skills_check rows left were the unlock-rank off-by-one, fixed 2026-10-22.
- [ ] **Spilled-over recruits**: what the game does when a unit queued past the recruitment capacity cannot be paid
      when it starts (dropped, or waits); decode which queue items are paid (queue item X) to replace runs/army_owed.json.
- [x] **Magma Cannon build swap (2026-10-20) live checks**: Zhufbar (Black Water) recruits both; turn 54 queued 6
      Warp-Doom Magma-Cannons there for Tichit from the local pool; turn 59 Thanquol's refill disbanded his off-template
      troops first (Warpfire Throwers; 2026-10-22: now only as many as the gold replaces); the dashboard line is
      eligible() = Black Water, green.
- [ ] **Workshop level 2 from the planned Cavern line** (Ikit, workshop level 1, no Cavern yet): no temporary Cavern
      is built while a capital plans the Warp-Turbine Plant; the planned one counts once it stands.
- [ ] **Skill prerequisites from memory** (skills.memory_state): runs next to the card states; every disagreement is
      logged to runs/skills_check.jsonl. 2026-10-22: the unique_0 disagreement was an off-by-one: unlocked_at_rank
      counts from 0 (Mentor 29 showed "Available at rank 30" live); fixed, and the skill-locks table
      (character_skill_nodes_skill_locks) is read too. One lock is still unexplained: Thanquol's Chittering Masses
      (unique_4, REQUIRED parent unique_0 taken) reads locked on the card with no reason in its tooltip and nothing
      in the DB. Until it is found the card check stays. Checked 2026-10-22: no row in the skill locks, level details
      or node links beyond unique_0, set item not mod_disabled, and no campaign script names it (scripts read with
      scripts/game/packread.py, zstd now supported). Lead: a content-ownership (DLC) gate, like the Secrets lines.
- [x] **The Lord's recruitment cost** (2026-10-22): agent_subtypes.cost; the Recruit Lord panel showed exactly it for
      every Lord type (Warpseer 1000, Grey Seer 850, Warlord 550, Warlock Master 1200), and the Warlock Engineer's 400
      likewise. new_army.create and the engineer recruitment check the gold before any click. Cost modifiers from
      effects are not decoded (none seen yet).
- [x] **Hero caps with bonuses** (2026-10-22, turn 55): memory engineer cap 2 = the Recruit Hero panel's "1 / 2" (base
      1 plus a bonus). The turn-55 "refused at cap 1/2" was gold (399 against 400): fixed, reported as no gold.
- [ ] **Workshop (Ikit)** with the command pacing: not run since the change.
- [ ] **Standing answers for routine decisions** (idea): strategy/decisions.json, the player's rules for AI diplomacy
      offers, captives, recurring dilemmas. Needs the player's rules.
