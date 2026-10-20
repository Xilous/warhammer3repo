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
- [ ] **Magma Cannon build swap (2026-10-20) live checks**: a capital with Equipment Warpforge + Warp-Turbine Plant
      shows the Magma Cannon card in the local pool and the army builder refills it there; the first refill disbands
      the Stormvermin; the dashboard's "Province recruiting Ratling Cannons + Magma Cannons" line turns green there.
- [ ] **Workshop level 2 from the planned Cavern line** (Ikit, workshop level 1, no Cavern yet): no temporary Cavern
      is built while a capital plans the Warp-Turbine Plant; the planned one counts once it stands.
- [ ] **Skill prerequisites from memory** (skills.memory_state): runs next to the card states; every disagreement is
      logged to runs/skills_check.jsonl. Needs a character with unspent points. If the log shows no disagreement,
      drop the card-state check (SKIP_STATES) so memory alone decides.
- [ ] **The Lord's recruitment cost** for a new playbook army (new_army.create): not read from memory yet; the money
      check uses the budget. Decode the Recruit Lord pool candidate's cost.
- [ ] **Hero caps with bonuses** (world.agent_cap): only the base value was checked (1 each, turn 12). Check against
      the Recruit Hero panel on a save with hero buildings.
- [ ] **Workshop (Ikit)** with the command pacing: not run since the change.
- [ ] **Tech queued count** is still read from the panel (tech.queued_in_ui), for reporting only.
- [ ] **Standing answers for routine decisions** (idea): strategy/decisions.json, the player's rules for AI diplomacy
      offers, captives, recurring dilemmas. Needs the player's rules.
