# Open items (written 2026-10-19, end of the session that released v0.3.10)

At the start of a session, remind the player of these, and say which need a multiplayer session.

## Needs a multiplayer session
- [ ] **Steal-Takes in multiplayer**: start, complete and abandon a Steal-Take with the command-paced clicks
      (they were not unlocked yet in the 2026-10-19 campaign).
- [ ] **Camera edge-scroll panning** (heroes.pan_by_edge, camera_pan auto/edge): never run live. Steal-Take targets
      and hero walks use it in multiplayer.
- [ ] **Desync / reload recovery**: the turn record is keyed on the human factions so a reload of the same campaign
      keeps queued requests and resumes an unfinished pass. Only an assistant restart was exercised; a real reload or
      desync was not.
- [ ] **auto_end_turn on a second PC** (strategy/automation.json): tested in single player only.
- [ ] **A pass interrupted by another player's hold mid-pass**: should stay pending and resume (runner._try_pass).

## Any session (single player is fine)
- [ ] **Diplomacy for gold: live checks (assist/diplomacy.py)**. Join-war deals only (peace for gold and tribute
      removed 2026-10-21). Checked live on turn 1 (Scruten): three deals (Wissenland 587, Karaz-a-Karak 1103, Sylvania
      802), each the most the AI accepted, each confirmed in memory; faction_strength matches the panel's bars. Still
      to see: (a) what the answer looks like when the AI turns a sent offer down; (b) a turn-start pass from the app
      with the widget's diplomacy list and toggles; (c) a weak major as a target; (d) multiplayer (needs multiplayer).
- [ ] **Diplomacy evaluation from memory**: the AI's value of a proposal is read from the panel (UI stop-gap). It is
      computed on demand and only found on the stack (assist/diplomacy.py docstring): decode the evaluation function
      and its inputs (attitude, treasury, war state) to replace the panel read.
- [ ] **A "recruiter" lord: answered 2026-10-21, the player decides**. Supply Lines (game script
      wh_campaign_setup.lua): every army from the 2nd on adds +1% (normal) / 2% (hard) / 4% (very hard, legendary)
      upkeep to every unit; a lord-only army counts. A permanent recruiter costs about 320 (1 army, normal) to 1,150
      gold (3 armies, legendary) a turn and pays only with heavy losses far from a recruiting province. The cheap form:
      a 250-upkeep lord hired with the units queued, walked over, merged, disbanded at once (Supply Lines drops on the
      disband). With Thanquol's "Replaceable Fodder" (global recruitment -2 turns, -50% cost) global recruitment does
      the job. Not built into the army builder unless the player wants the temporary form.
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
      logged to runs/skills_check.jsonl. 2026-10-21: the log's "rank / no card" and "taken / maxed_hover" rows were
      artefacts (fixed: no row without a card, the _hover suffix stripped, also where a full skill was clicked again).
      One real disagreement is left: Thanquol's and the Warpseer's unique_0 (unlock rank 11 / 10, no parents) read
      open in memory, locked on the card, at a rank at or above the unlock (the rank read was checked: memory 2 = panel
      2). Some lock is not in the DB tables; needs a Thanquol at rank 11+. Until then the card check stays.
- [ ] **The Lord's recruitment cost** for a new playbook army (new_army.create): not read from memory yet; the money
      check uses the budget. 2026-10-21: the UI context function RecruitmentCost has two natives, 0x141EEF528 and
      0x1408D3F90 (returns u32 [context+0x10]); the context is not the pool entry (its +0x10 is a pointer). Find
      which context class registers 0x1403f6dd0 (Ghidra) and how it is made from a pool entry.
- [ ] **Hero caps with bonuses** (world.agent_cap): only the base value was checked (1 each, turn 12). Check against
      the Recruit Hero panel on a save with hero buildings.
- [ ] **Workshop (Ikit)** with the command pacing: not run since the change.
- [ ] **Standing answers for routine decisions** (idea): strategy/decisions.json, the player's rules for AI diplomacy
      offers, captives, recurring dilemmas. Needs the player's rules.
