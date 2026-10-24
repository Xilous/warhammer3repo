# Open items (written 2026-10-19, end of the session that released v0.3.10; worked through 2026-10-22)

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
      reloads the same way; an actual desync is still unseen. 2026-10-23: the player agrees with rerunning the turn
      start when a session starts on a campaign and turn already recorded.
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
- [ ] **Game crash after two Steal-Take completions in one pass (2026-10-23, turn 46)**: the game stopped rendering
      right after the second completion (1.5 s after the first) and crashed (crash_report D2026-10-23_T23-14-58, the same
      stack as D2026-10-18_T21-48-27, which also came between two completions). 2 crashes in 10 passes with two
      completions, none in ~75 with one. Changed: after a completion nothing is clicked until its loot shows in the
      treasury or the Warpstone (memory), and frames must come steadily 2 s (was 1 s). runs/masterplans.jsonl
      "loot_paid" rows show how long the payment takes (23-29 ms: not the gap). Crashed again on turn 49
      (D2026-10-23_T23-58-17, same stack; The High Place then Mount Squighorn), so: the panel is now closed after
      every completion and reopened for the next, and before every input of every step the game's UI must be still
      for 3 frames (tools/ui.wait_quiet; player: "it was clearly still doing things while certain ui animations were
      still going"). Crashed again on turn 61 (D2026-10-24_T01-15-10, same stack) after a SINGLE completion, so not the
      second-completion theory. Cause (player, 2026-10-24): the click skipped the completion animation. Measured live:
      the plan-complete screen animates for ~1.4 s after it shows (38 changes), the click came at 0.2-0.5 s. Fixed:
      nothing touches the screen until every byte of its components is still for 10 frames (tools/wait.animation_done),
      and after Complete nothing until its completion animation is over and the screen closed by itself
      (runs/masterplans.jsonl "trigger_screen_still", "completion_animation_s" rows). Watch the next completions.
- [ ] **Steal-Takes with negative gold (2026-10-23, turn 36)**: Karaz-a-Karak drew a -4,000 gold Complication on
      its first turn (before it could be completed) and reached Alarm 4/4 at -3,280 gold with a treasury of 2,781:
      Complete did nothing. Fixed: a plan the treasury cannot pay waits, or is abandoned at maximum Alarm (also when
      25% of the loot, the gold taken counted in full, is worth less than 0). (1) Abandon confirmed live
      2026-10-23 (Fort Soll, turn 36, second campaign): the prompt is popup_message_box, not dialogue_box (the pass had
      clicked the X behind it until the player pressed Shift+Esc); its text says no Complication consequences, so a
      negative plan costs nothing to abandon. To do: (2)
      whether the 25% at maximum Alarm scales the gold taken too, (3) player decision: keep gold aside from the build
      step for a running plan with negative gold, (4) count "the treasury could not pay" in the stay/exit weighing.
- [x] **Secrets shop from memory (2026-10-22)**: after a few Build & End Turn passes that open the shop, runs/
      masterplans.jsonl should have no "shop_check" rows (panel and memory listing the same lines per tab).
      Turn 56: one row, a false one (a tab checked again after its last line was bought, against the reading from
      before the purchase); fixed: each tab is checked once, before anything is bought in it. Turns 59-64 bought 8 Secrets (several per tab)
      with no new row.
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
      2026-10-22: needs a queue holding a paid and a spilled unit at once (the buildings took the gold every turn
      tried). Fields that differ between two queued Stormfiends (turn 61): +0x34, +0x44, +0xCC, +0xD0, +0xDC, +0xE0,
      +0xF4 (u32). Also: runs/unit_prices.json learns an army's real unit price only from a paid click.
      2026-10-22, turn 78, measured: a Warp-Doom Magma-Cannon queued for Thanquol into an EMPTY queue (0 -> 1) was not
      charged (memory treasury and the HUD stayed 10,072 for 2 s+), so "spilled over" is not only past the capacity:
      Thanquol's army had no capacity that turn (why: unknown; Tichit's clicks on turns 49-53 were charged at once).
      The item read +0x34 4, +0x44 4, +0xCC 4, +0xF4 4, +0xD0/+0xD4/+0xDC/+0xE0 0. The owed booking keeps the
      gold aside, so the accounting is safe; the per-army price only learns where clicks are charged at once.
- [x] **Magma Cannon build swap (2026-10-20) live checks**: Zhufbar (Black Water) recruits both; turn 54 queued 6
      Warp-Doom Magma-Cannons there for Tichit from the local pool; turn 59 Thanquol's refill disbanded his off-template
      troops first (Warpfire Throwers; 2026-10-22: now only as many as the gold replaces); the dashboard line is
      eligible() = Black Water, green.
- [ ] **Buildings the game greys out with no reason read (2026-10-23)**: a non-main building card greyed out though
      memory said it could go (gold, main level, development points, locks all fine), most often right after another
      construction in the same settlement (Zhufbar turn 16: Breeding Pit and Scrap Heap after Warplightning
      Capacitors; turn 19: Castle Drakenhof's Temple, Oakenhammer's Overseer's Lookout); each went up a turn later.
      _why_greyed found no text on the card (its tooltip shows only on hover). Find the rule in memory, then plan
      by it; until then these show as failures in the widget.
      Player question (2026-10-23): is the assistant going too fast for the game's UI? Plausible: on turn 16 the
      card's state was read ~30 ms after it was laid out, right after the previous build in that settlement was
      clicked, with no wait for the slot panel to refresh from that build. Checks, in order:
        1. Speed: on a greyed card, wait for its state to hold for a few frames (or for the panel to refresh after
           the last build) and read it again; if it turns active, it was the UI lagging, not the game refusing.
        2. A game rule: compare a greyed card's level record and the settlement's state (slots under construction,
           gold the previous build took, any per-settlement limit) in memory against one that went through.
        3. Get the game's own reason: hover the greyed card and read its tooltip (UI stop-gap for the report only).
- [ ] **Hiring the Warlock Engineer after a new army (2026-10-23, fixed, to confirm live)**: turn 43, Chiriflesh was
      raised at Zhufbar but no engineer was hired. A wheel aimed at the recruitment pool while it was still sliding
      up landed on the map and zoomed the camera out into the tactical view, whose Overlays panel then covered the
      Provinces list and hid the settlement labels. Also a case of going faster than the UI. Fixed in 8884785: a wheel
      waits for its list to stop moving, and the tactical view is left before a Provinces row or a map label. To
      confirm: the next raised army gets its engineer in the same pass. Also look for other clicks or wheels aimed at
      a panel that may still be sliding in.
- [ ] **Workshop level 2 from the planned Cavern line** (Ikit, workshop level 1, no Cavern yet): no temporary Cavern
      is built while a capital plans the Warp-Turbine Plant; the planned one counts once it stands.
      2026-10-22 (the Ikit save of 2026-10-18, turns 82-84): the first half holds: Magritta built the planned chain's
      Construction Cavern (turn 83) as a normal building, no temporary one anywhere. Still level 1 on turn 84 with
      the Cavern going up; the level-2 count is left to see.
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
- [ ] **Workshop (Ikit)** with the command pacing: not run since the change. 2026-10-22: the step ran on turns 82-84 of
      the Ikit save (level gate from memory: "the rest waits for workshop level 2"); no purchase was possible yet.
      The new workshop.missed memory check ran with it and reported nothing.
- [ ] **Standing answers for routine decisions** (idea): the player's rules for AI diplomacy offers, captives,
      recurring dilemmas. 2026-10-22: AI offers have a widget setting, "AI diplomacy offers" (automation.json
      ai_offers): ask (default) or accept_gifts (they ask at most a Non-Aggression Pact or Trade Agreement and give
      only gold, a Non-Aggression Pact or a Trade Agreement). Checked live (turn 68, Ikit Claw's pact accepted with
      accept_gifts on for the test; set back to ask). Diplomacy notices with OK alone (a pact ended) are closed like
      event notices. UI stop-gap: the offer's terms come from the panel; a memory reader for pending proposals is
      still to find. Captives and dilemmas still need the player's rules.
- [x] **Steal-Take risk model (2026-10-22, turn 66)**: Vaul's Anvil was kept one more turn at Alarm 2 (Risk 100% x q
      0.15 = 0.15 vs 0.23); the Complication that came took Alarm past its maximum and 2,277 gold off the loot (1,337
      -> -940). The rule counted only the 25% paid at maximum Alarm, not Complications that take loot.
      2026-10-23 (player: weigh stay against exit each turn like poker, from the information given): every card of
      the settlement level's Complication pool is weighed, its Alarm and the loot it takes (assist/masterplans.py
      complications(), settlement level read from memory P+0x188). Replayed on the logged boards from turn 40: 6 of
      ~70 decisions change, each completing a turn earlier at Alarm 2 or 3; live on Marienburg turn 84: stay 2,902
      vs exit 2,712, wait. Open: which pool a Steal-Take really draws from is taken from the game tables (region
      sets by level, the same ones the Alarm odds came from); the plan holds no pool of its own in memory (scanned
      P+0 to P+0x600). Risk read 100% while a turn passed with no Complication (Marienburg turn 83): to watch.
