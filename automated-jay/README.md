# automated-jay

A turn-start assistant for Total War: Warhammer III (Clan Skryre). It runs next to the game as a separate program,
reads game memory, and acts only through ordinary mouse and keyboard input. Nothing is installed into the game.

## Quickstart

### What you need

- **Windows** 10 or 11 and **Total War: WARHAMMER III** (tested on patch 9.0.4 with Clan Skryre).
- The game in **borderless windowed** mode (not exclusive fullscreen) at **1920x1080**, UI scale **100%**
  (`bot/config.py`). Clicks and screen templates assume exactly this.
- **Python 3.14** from python.org. Once, in this folder, install the packages:

  ```
  py -3.14 -m pip install -r requirements.txt
  ```

- The parent repo's data folders `../tww/` and `../re/` (see "External dependencies" below). They are already
  there in this checkout.

### Start and stop

Double-click **`run_assistant.bat`**. Start it before or after the game: it finds the game by itself and
re-attaches when the game is restarted. Three things appear:

- no console window: the log goes to `runs\console.log` (`run_assistant_console.bat` starts it with a console
  that shows the log live, and stays open on an error);
- the **assistant window**, titled "automated-jay";
- a small **overlay** in the top-left corner of the game with the current status.

To stop, close the assistant window.

`run_assistant_once.bat` does a single pass right now, without the window, after asking you to confirm. It makes
the same checks as **Run now** (your turn, 3 s idle, no open decision). While the assistant is running, use **Run now** instead.

### Using the exe (any Windows PC, no Python needed)

1. Download `automated-jay.exe` from the repo's [Releases](https://github.com/Xilous/warhammer3repo/releases) and put it
   in a folder of its own (e.g. `C:\Games\automated-jay\`).
2. Double-click it. On first start it creates `strategy\` (your settings, ticks and skill/settlement orders),
   `anchors.json` and `runs\` (logs) next to itself. A new exe starts with no army ticked.
3. `automated-jay.exe --selftest` checks the bundled game data and the connection to the game (memory reads only,
   no input) and writes `runs\selftest.txt`.

To update, replace the exe in the same folder. On its first start a newer exe brings these files up to its own
defaults once: every setting you never changed takes the new default, what you changed (and your ticks) stays,
and new settings are added. The files it changed are copied to `runs\upgrade_backup\` first;
`runs\defaults_version.txt` names the release the files were last brought up to.

The exe has no console window: what the console would show goes to `runs\console.log`. Requirements are the same
as from source: the game at 1920x1080 borderless, the same game build (9.0.4: memory offsets change with patches).
To build the exe yourself: `python -X utf8 -m tools.build_exe --release automated-jay-vX.Y.Z` from automated-jay/
(needs the repo's game-data dump in `../tww` and `../re`, which is not published; see tools/build_exe.py). Tag the
release `automated-jay-vX.Y.Z`: the next build ships each tagged release's defaults for the update above.

### Emergency stop: Shift+Esc

Press **Shift+Esc** at any time, in any window, to end the assistant immediately (and any test driver or test
script of this project that is running). Every process that can send input to the game watches the keyboard for
it (bot/killswitch.py, armed by bot/focus.py): it lets go of the mouse buttons and any held keys and exits on the
spot, mid-click. Only a key press you make counts (the automation cannot trigger it), and the game does not see
that Escape. Start the assistant again with run_assistant.bat.

### Your mouse and keyboard during a pass

A pass starts as soon as it is really your turn: it does not wait for you to stop clicking. While it runs it
**takes mouse and keyboard away from you**: your moves, clicks and key presses are held back until it is done
(its own input goes through), so nothing can interrupt it. When it ends, the cursor is put back where you left
it and both come back to you; also after an error, after 5 minutes at most whatever happens, and when the
process ends. **Shift+Esc** always gets through and stops everything at once. Try the hold by hand with
`python -X utf8 -m bot.killswitch 5`.

Popups still open at the start or end of a pass are recorded in `runs/popups_seen.jsonl` (id, buttons, texts),
so a notice the assistant leaves open can be taught to it.

**Verification.** After each step, the assistant runs the step once more. Every step plans from what memory
shows, so a second run that changes nothing (gold, research, skill points, army units and queues) proves that
everything the first run tried really happened: the step line ends in `verified`. If the second run had to do
something (a click that went astray, a construction that got cancelled), the line says `verification redid:
...` and it is checked once more. The army step's verification only redoes disbands and recruitment; march and
walk orders are not issued twice.

### What it does

Every rule, step by step, is in [Logic](#logic) below.

### The assistant window

| Part | What it does |
|---|---|
| Status line | the same headline as the overlay |
| **Build & End Turn** | for when you are done with your turn: runs the end-of-turn steps (tech if research is idle, skill points, repairs, buildings, upgrades, then the army builder) and then ends the turn like Shift+Enter does in the game: the game's End Turn warnings (unspent skill points, a building that could be constructed, an army that can still move) are skipped, because they are about things the assistant leaves alone on purpose. It does not wait for idle (you asked), but it checks it is your turn and leaves any decision popup to you; if a step is interrupted or the game asks you something, the turn is **not** ended. |
| **Run now** | one full pass for the current turn, right away. It still checks that it is your turn; your mouse and keyboard are yielded to click by click. Use it after INTERRUPTED, SKIPPED or ERROR, after loading a save, or for a turn you paused through. |
| **Restart** | starts a fresh copy of the assistant (latest code and settings) and closes this one; refused while a pass runs. The window title shows the commit the running copy is on. |
| **Pause / Resume** | while paused, turn starts are skipped (the overlay says so). Resuming does not redo a skipped turn; Run now does. |
| Turn and treasury | read from memory every 4 s |
| **Ignore &lt;id&gt;** | shown when a pass is held by a panel the assistant does not recognise. If that panel is harmless, click it: the id goes into `strategy/popup_ignore.json` and never holds a pass again. Delete the id from that file to undo. Diplomacy offers, battles, dilemmas, message boxes and the game menu never get this button. |
| This turn | what each step did in the last pass |
| **Armies** (tick boxes) | every field army and how it differs from the template. Tick an army to let the army step manage it; unticked armies are never touched. The ticks are saved in `strategy/automation.json`. Also lists heroes on their own and which provinces can recruit the template units now. |
| **Army finances** | you decide when a new army is raised (the builder no longer raises one by itself). A green ✓ or orange ✗ line says whether you can afford a new army, after what the ticked refills will add. Below it: income per turn (last turn's, as the HUD shows it), the Supply Lines % per extra army for your difficulty, what each army costs now and what it would cost once refilled to the template (units not in the template are disbanded, so they drop out of upkeep and Supply Lines), and what the next army would add in all. Unit upkeep is the game's base upkeep with Supply Lines, calibrated against last turn's real army upkeep. All from memory (`assist/army_finance.py`, `bot/sensor/economy.py`). |
| **Create new playbook army** | always pressable, whatever income would be after it. Below it, ✓/✗: a Verminlord Warpseer in the Recruit Lord pool, a Warlock Engineer (free or room under the cap), a province recruiting Stormfiend Ratling Cannons and Warp-Doom Magma-Cannons. Pressed, it raises the Warpseer, ticks the new army and recruits the template; without a Warpseer or a recruiting province it says why; without an engineer it raises the army anyway and the engineer follows. |
| Provinces where nothing is built | the provinces the building step skips, and why |

The window only reads memory. It never sends input to the game.

### Your strategy files

Plain JSON, read fresh at every pass: edits apply from the next pass without a restart. Every single setting in
them is also in the widget's SETTINGS; the long ordered lists (build priority, skill orders, the Secrets shop
order, the army template) are edited here.

| File | What it holds |
|---|---|
| `strategy/settlements.json` | building priority list (main building, port, then the rest in order) |
| `strategy/skills.json` | skill order per character type |
| `strategy/automation.json` | how the assistant acts (`schedule`: which steps run when; `buildings.repair_damaged`: repairs on or off; pacing, camera), the doomstack template (units and heroes), the ticked armies |
| `strategy/masterplans.json` | Thanquol's Masterplans: Steal-Take rules and the Clan Scruten Secrets shop order |
| `strategy/popup_ignore.json` | panels you marked harmless with Ignore |
| `../tww/skv_beeline.json` | tech bee-line targets in click order (made by `../scripts/game/skv_beeline.py`, explained in `../GUIDE_Skryre_Tech_Beeline.md`) |

### Logs

| Where | What |
|---|---|
| the console | one line per status change, and the full error when something fails |
| `runs/assistant-YYYYMMDD.jsonl` | one line per pass: `{"t", "turn", "steps"}`, the steps being what each one did |
| `%LOCALAPPDATA%\automated-jay\state.json` (outside OneDrive, which locks synced files) | the current status: `{"state", "headline", "detail", "turn", "time"}` |

### Troubleshooting

| You see | What to do |
|---|---|
| WAITING "the game is not running" or "no campaign loaded" | Nothing. It attaches by itself when the game starts or restarts (also after a crash) and acts from the first new turn once a campaign is loaded. |
| YOUR TURN "campaign changed; acts from next turn" after loading a save, or "assistant started mid-turn" | Normal: a load is never treated as a turn start. Press **Run now** if you want this turn done too. |
| DECISION NEEDED that does not go away | Answer or close that popup in the game. If it is a harmless panel, press **Ignore &lt;id&gt;** in the window. |
| INTERRUPTED, SKIPPED or ERROR | Go back to the game, close anything half-open, press **Run now**. It redoes the whole pass for this turn. |
| WAITING "waiting for you to stop clicking" | Leave mouse and keyboard alone for 3 s. |
| Nothing happens at a new turn | Check that it does not say PAUSED and that the game is borderless windowed at 1920x1080. The status line says what it is waiting for. |
| The console says a module is missing, or that Python 3.14 was not found | Install Python 3.14, then run `py -3.14 -m pip install -r requirements.txt` in this folder. |

More situations, and how each was tested, are under "Day-to-day robustness" below.

Do **not** run anything in `legacy/`. `legacy/run.py` is the old bot that ends turns (see `legacy/README.md`).

---

## Logic

Every rule the assistant follows, top-down in the order it happens. All game state comes from memory; the UI tree
is used only to find what to click, to confirm a click took, and for what exists only in the UI.

### 1. Start-up
- `--once` -> one Run now, no widget, exit. `--selftest` -> checks written to `runs/selftest.txt`, exit.
- Single instance: mutex `Local\automated-jay-assistant`, 8 s wait; not obtained -> exit 3.
- Restarted copy (`AJ_RESTARTED`) -> reads the old copy's `state.json` first; `AJ_FOCUS_GAME` -> game raised after 900 ms.
- Loads `runs/turn_state.json` (the turn record). No game running -> waits for one. Kill switch installed.
- Exe only: default strategy files seeded or merged into the player's (see 12).

### 2. Main loop (`runner.loop`)
- Each poll: `_tick`, `_watch`, sleep 0.1 s (pass pending or not your turn) or 0.5 s.
- `InputAborted` -> INTERRUPTED (Run now redoes it). Other exception -> ERROR, loop goes on.

### 3. Attaching and turn detection (`_tick`)
- No campaign for 2 polls (or on the first poll) -> forget the turn, WAITING "no campaign loaded" / "game not running".
- First campaign seen:
  - pass owed now if it is not your turn yet, or if your turn is unfinished (record for this turn with turn start
    not done, record from the previous turn, previous copy's state not YOUR TURN, or previous copy ended the last turn);
  - otherwise "assistant started mid-turn / campaign changed: acts from next turn" (no pass this turn).
- Model changed or turn jumped (save loaded):
  - same campaign id (local faction + all human factions) and same turn -> carry on with what the turn owes;
  - else "campaign changed; acts from next turn".
- Turn +1 -> new turn: rail reset; paused -> "skipped"; else pass pending.
- Record for another campaign or turn -> fresh record (owed requests dropped).
- Turn already ended by the assistant but phase is free again (MP) -> TURN N REOPENED; End Turn never re-pressed by itself.
- Owed request and phase free and not busy -> Build & End Turn first, else Run now.
- Else: pending pass -> pass gate (4); auto_end due -> End Turn; your turn -> close notices; not your turn -> report
  open decisions (5).

### 4. Phase and the pass gate
- **Phase** (`phase`), first match:
  - memory "whose turn" list lacks the local faction (`[[G+0x2F60]+0x1C8]`) -> not mine (AI turns, sequential MP);
  - no UI / cinematic / no campaign HUD -> held;
  - `ai_turns` panel -> not mine;
  - simultaneous MP ended (`mp_waiting`) -> ended;
  - another player's battle or decision pending -> held;
  - no End Turn button -> held; button selected -> ended;
  - button inactive/disabled -> free if a Masterplan is at max Alarm, else held;
  - otherwise free.
- **MP ended check** (`mp_waiting`): ended list in memory (simultaneous mode only) vs your ready tick vs the End
  Turn button. Button selected or tick on -> ended. List says ended but tick off or button active -> not ended
  (after 2 s; at once when about to press End Turn); logged UNEXPECTED once.
- **Pass gate** (`_try_pass`):
  - busy -> wait; paused -> drop the pass;
  - not free: "End Turn button is..." -> close notices first, re-check; still not free -> WAITING;
  - first time free -> settle: camera still 250 ms (centre point moved < 0.1 px; your own panning ignored after
    1 s idle) and root panels unchanged 500 ms; timeout 20 s -> go on; re-check free;
  - no idle wait: your input is yielded to click by click (11);
  - popups (5): decisions open -> DECISION NEEDED, stays pending; popup check failed -> SKIPPED;
  - pass (6). Cinematic or another player's action -> stays pending.

### 5. Popups and notices
- Popup = visible root panel not in the normal HUD set, not in `popup_ignore.json`, not a tooltip or event-feed preview.
- Notices closed (up to 24): event panels with a close button, no choice, not significant (episode, endgame,
  end times, chaos invasion). Each close confirmed (gone or changed); one not confirmed stops the closing.
  Re-click of the same notice within 8 s skipped.
- Verminlord dilemma -> Verminlord Warpseer. Every other decision is never answered: diplomacy offers, battles,
  dilemmas, message boxes, game menu, endgame, story events, unknown panels (unknown panels can be Ignored).
  Headline: GLOBAL EVENT / GUIDED TOUR / DECISION NEEDED.
- Your turn, no pass, game in front, `close_notices_during_turn` on -> notices closed as they come.
- Not your turn -> open decisions posted every 3 s ("the other factions' turns are held until you answer").
- Game notifications showing (not "end turn") -> notification settings: Disable all; still showing -> marked
  unsuppressible.

### 6. The pass (`automate`)
- One `game_focus` for the whole pass (game raised once, focus returned after). Not raisable -> "could not bring
  the game to the front".
- Steps from the schedule (`automation.json` `schedule`, read every call):
  - turn start: rites, workshop, tech, skills;
  - Build & End Turn: rites, workshop, tech, skills, masterplans, buildings, army;
  - turn start adds the end-turn steps when the previous turn was not ended by Build & End Turn, and masterplans
    when an economic plan is at max Alarm.
- Per step: leave the tactical view -> run -> verify -> memory check -> rail bar done / failed.
  - Step exception -> "ERROR ..."; `InputAborted` stops the pass.
  - **Verify** (up to 2 rounds): fingerprint from memory, rerun with `verify=True`, fingerprint again. Same ->
    "verified"; changed -> "verification redid: ..."; still changing -> said so.
    Fingerprints: buildings treasury; tech research; rites gold + cooldowns + commandments; workshop upgrades;
    skills points per character; army treasury + unit and queue counts per force.
  - **Memory check** (`missed()`, buildings tech skills masterplans army): plan made again from memory;
    anything left with "not possible" / "refused by the game" / "greyed out" -> "not done, with a reason"; anything
    else -> "MISSED (memory check)" and the bar turns red.
- After the steps: late notices closed; "paused Nx while you used the mouse/keyboard" if it yielded; Kill-Stab at
  max Alarm -> "complete it yourself"; YOUR TURN N; `auto_end_turn` on -> End Turn pressed.
- Logged to `runs/assistant-YYYYMMDD.jsonl`.

### 7. Steps

#### Rites (`assist/rites.py`)
- Commandments: every complete province (all its regions owned) -> Exploitative Planning. Until the Dominating
  Scheme has been cast once: the first complete province with Expansionist keeps it; none with any commandment ->
  the first complete province gets Expansionist. Already picked -> skipped.
- Pick: Regions tab -> province row -> hover the commandment slot -> the item -> click; confirmed in memory.
- Dominating Scheme (Verminlord version first): not in your rites / on cooldown -> nothing. Waits when: no complete
  province; Expansionist only picked (next turn); no Expansionist in effect. Cost from memory > treasury -> "needs X".
  Perform greyed -> its requirement text. Click confirmed by the cooldown in memory. Verminlord dilemma -> Warpseer.

#### Workshop (`assist/workshop.py`, Clan Skryre only)
- Workshop level = highest `workshop_level_N` bundle. Upgrades not owned: type 0 and 1 (level 1), type 2 (level 2).
- Reachable ones bought in the Weapon Teams tab; each confirmed by its bundle in memory. Locked -> waits for the level.

#### Tech (`assist/tech.py`)
- Researching -> nothing (a click would cancel it).
- Click order: `tech.first`, then bee-line targets in order, then every other tech by (research points, tier, indent).
  Candidates: not researched; locked ones stay (a click queues their prerequisites).
- Panel open -> up to 4 candidates: dragged on screen, clicked; confirmed by research starting or the target
  changing in memory. Missed click -> once more (never in multiplayer). Started -> stop.
- Report: queued X (path to target, N locked techs queued: target's ancestors locked in memory).
- Missed: nothing researching while candidates remain.

#### Skills (`assist/skills.py`)
- Characters with unspent points whose subtype is in `skills.json` (Ikit, Thanquol, Verminlord Warpseer, Warlock
  Engineer). Others never touched.
- Plan: mounts to take (1 rank) -> `order` (`asap` first) -> rest of the tree (not skipped mounts, not hidden):
  passives before abilities, by indent, tier, name, each to its max.
- Open: switch inside the open panel, else Lords & Heroes row -> skills.
- Walk the plan from the top; after each skill taken, walk again from the top. Per skill:
  - memory: taken (at planned rank) / rank (unlock rank above the character's) / locked (a required parent untaken,
    or subset parents below `required_num_parents` points) / open;
  - card: maxed, locked, locked_rank (hover suffix ignored) -> skipped; memory and card disagree -> logged;
  - open on both -> click up to its ranks, each confirmed by the points dropping; not confirmed -> not again this turn.
- Missed: points left while a planned skill is open and was not refused.

#### Masterplans (`assist/masterplans.py`, Clan Scruten only)
- Off, not found or not unlocked -> nothing. Panel opened only when something will be done.
- Each economic plan (Steal-Take), never military or Great-Smart:
  - not completable yet -> wait; Alarm at max -> complete (or abandon if `at_max_alarm` says so);
  - V = Warpstone + gold / `gold_per_warpstone` (10); G = next turn's draws x expected card worth; q by Alarm
    0, 0, 0.15, 0.99; V <= 0 -> wait; risk x q < G / (G + (1 - 0.25) V) -> wait; else complete.
  - confirmed by the plan leaving memory.
- Free Underlings (unlocked, idle, cooldown 0, unwounded) and 50+ Warpstone -> Steal-Take on the best target:
  - targets: not in a plan, not on cooldown, not in or next to your provinces (`skip_near_provinces`), owned by
    someone else, explored, has a main building;
  - score: main level x 10, +5 major settlement, +100 not at war with you (`prefer_not_at_war`);
  - on screen, or within `max_pan` (120) map units (2 pans); confirmed by the plan appearing in memory.
- Secrets: walk `shop.order`; skip unknown chains, locked tabs (Underling not unlocked) and levels below their
  unlock count; stop when buying would leave less than `keep_warpstone` (50). Each buy confirmed by Warpstone in memory.
- Kill-Stabs never touched; one at max Alarm -> "complete it yourself".

#### Buildings (`assist/build.py`, `assist/buildplan.py`)
- Settlement skipped: next to a region held by an enemy you are at war with (any distance into your provinces).
- Plan per province (settlement list):
  - main building to max; port upgraded within the main tier;
  - layout: the priority list top-down into the slots at max tier, each chain to its highest reachable level;
    capital-only / minor-only entries; Equipment Warpforge once per province; standing landmarks keep their slots;
    Morskittar Engine skipped;
  - actions: main upgrade, port upgrade, then per layout item: upgrade / construct (free slot) / replace (off-list
    slot) / wait (tier or slot).
- Replace only when `off_list_buildings` = replace, in a secondary slot, never a special building (landmark,
  legendary, unique, wonder).
- Repairs first (`repair_damaged`): damaged buildings on the plan; estimate = cost x missing hp share > gold -> needs gold.
- Construction Cavern (Ikit, workshop level 1, no Cavern standing, none planned): one temporary Cavern in a free
  slot, else an off-list slot, else the lowest-priority building; kept until it has counted, then released.
- Off-list buildings: demolished right after the main/port upgrades, even when the planned building cannot be paid
  yet (it goes up once the gold is there); kept while the planned building is locked or short of main level or
  development points.
- Spending, all provinces at once (income first): main/port upgrades (they unlock the slots) -> every other building
  and upgrade by payback = build turns + cost / gold per turn it adds (game data: its income, the province's %
  bonuses such as the Reactor's, an upgrade's difference, a replaced building's loss; `assist/payback.py`); ties by
  list order; no gold added -> last, still built. Every building still reaches its highest tier.
- Saving: a main/port upgrade, or a building paying back within 20 turns, not affordable but reachable within 2
  turns of net income is saved for; anything cheaper is bought only if it does not push a saved item a turn later
  (else held); the army keeps off what the saved items still need.
- Per action, first match: no longer yours; slot changed since the plan; Cavern slot; under construction; locked
  by the game; main level too low; development points short; not affordable (held / saving / needs gold); no slot;
  damaged building (waits for repair); panel or slot not found; else act.
- Act: slot hovered, building card found (greyed -> its tooltip reason), click confirmed by construction in memory.
  Replace: demolish confirmed first, then build.
- Missed: a planned action not under way without a memory reason.

#### Army (`assist/army_builder.py`)
- Ticked armies only. A tick counts only for the same general (id or name), set with a turn, at or before the
  army's turn and rank (another campaign's tick ignored).
- Template: lord Ikit Claw, Thanquol or Verminlord Warpseer (new armies are raised as Warpseers), 1 Warlock Engineer,
  12 Stormfiend Ratling Cannons, 6 Warp-Doom Magma-Cannons. Queued units count as present.
- Eligible province: recruits every template unit type (finished, active buildings in owned regions).
- Engineers: free ones (not in an army) kept on or assigned to the nearest army that needs one
  (`runs/engineer_claims.json`).
- Spendable = treasury - buildings' saving reserve - gold owed for units queued this turn.
- Per army:
  - extra heroes -> "remove it yourself" (heroes and lords never disbanded);
  - off-template units: kept when no gold for a replacement or not at an eligible province; else disbanded
    (cards checked against memory, selection checked, confirmed by the unit count);
  - at an eligible province: missing units queued from the local pool only (never global), room = 20 - units -
    queued - missing engineer; gold checked before each click; each click confirmed by the queue in memory;
  - else marched to the closest eligible province (fewest region hops, then distance, then most missing units
    covered; not within 1.5 of another army); re-chosen every turn;
  - engineer missing and none free: recruited at the nearest settlement that can, if the cap (memory) allows;
  - assigned engineers walked into the army every turn until they join (not with no movement left or the army full).
- Refilled (nothing missing, nothing to disband) -> tick cleared.
- **New playbook army**: the button is never locked (the ✓/✗ checks are information). Pressed: needs an eligible
  province, a Verminlord Warpseer in the Recruit Lord pool and a free settlement there; income after it and a
  missing engineer never block (the engineer is recruited once the cap allows). `auto_create` (by itself): also
  needs an engineer (free or cap room) and income after it >= `income_reserve`. Raised at a free settlement of an
  eligible province, capitals first; confirmed by the new army in memory; ticked and built the same pass.
- **Finances**: upkeep = base x (1 + Supply Lines % x (armies - 1)); Supply Lines 1% easy/normal, 2% hard, 4% very
  hard/legendary; verdict = income after ticked refills and the next army.

### 8. Run now
- Busy -> ignored. No campaign -> said so.
- Not free: panels put away (campaign map hidden) / notices cleared (End Turn greyed), then re-check; held ->
  RUN NOW QUEUED; not your turn -> refused.
- Decisions open -> queued until answered. Else the pass (turn-start steps, plus end-turn steps when the last turn
  was not ended by the app).

### 9. Build & End Turn
- Busy or campaign map down (battle, load) -> END TURN QUEUED, runs once possible; a new turn drops it.
- Tactical view left; panels put away / notices cleared; not free but your turn -> queued, else refused.
- Panels closed; decisions open -> queued.
- Steps: turn-start steps still owed + the end-turn steps.
- Panels closed again; popups again (decision -> queued).
- **End Turn press** (`press_end_turn`):
  - ended = turn moved, or not your turn in memory, or MP ended, or your ready tick on;
  - waits until End Turn is allowed (up to 3 min, other players' actions);
  - Shift+Enter (game warnings skipped), wait 8 s for ended; another player's action -> wait up to 3 min;
  - up to 2 tries, panels it opened closed in between; then the End Turn button itself;
  - TURN N ENDED, or NOT ENDED with the reason.
- **Close panels**: tactical view left; tour, Masterplans, Hero Actions closed with their X (decline); then Escape
  (up to 6) on character, settlement, technology, recruitment, units, diplomacy panels; a game menu opened by
  Escape is resumed.

### 10. Confirming a click (`commands.act`)
- The game's outgoing command stream is watched during the click.
- Effect in memory -> done. No command within 0.6 s -> missed (safe to click again, after 2.5 s more without the
  effect). Command sent, no effect within 15 s -> refused (never clicked again). Stream unreadable -> refused after 15 s.

### 11. Input safety
- Every input inside `game_focus`: system mutex (one input sender), your mouse and keys held off (releases pass,
  300 s cap), game raised (8 tries, then forced); exit: previous window and cursor restored.
- Before every click / key: game in front, window under the cursor is the game, no cinematic -> else INTERRUPTED.
- Target hovered until it shows its hover state (40 frames, 1 px nudges, re-aim up to 3x).
- You moved the mouse or pressed a key -> it waits until 1 s idle (2 min cap), then re-aims. Another player's
  pending action -> waits (3 min cap).
- Pause after every click / key: `pace_ms` (120).
- Waits poll game state every 2 ms (never fixed sleeps); frame waits follow the UI's frame counter.
- Shift+Esc (physical) -> buttons and keys released, the assistant exits at once.

### 12. Widget, window, settings, files
- **Rail**: compact over the game, full while automating; bars per step (done / active / failed / later / pending);
  button RUN NOW (after an error), QUEUED (End Turn owed), else BUILD & END TURN; click elsewhere = pause; clicks
  pass through while the assistant is acting; position saved.
- **Panel** (expand): Run now, Pause, Restart (fresh copy, refused while busy), Exit, treasury / income /
  Warpstone, this turn, armies with ticks (a tick that cannot refill is disabled; a tick can always be removed),
  next army, SETTINGS, frontline. Refreshed every 4 s from
  memory only.
- **SETTINGS**: every option in `assist/settings.py` (switch: click; choice: click cycles; number: - / + within its
  limits) and each step on/off per phase; written at once (atomic), read fresh by the next pass.
- **Exe defaults** (once per release): missing strategy files copied; changed defaults merged into the player's
  (the player's own changes kept), backup in `runs/upgrade_backup/`.
- **Logs**: `state.json` (status), `runs/assistant-*.jsonl` (passes), `runs/timeline.jsonl` (phases),
  `runs/heartbeat.json`, UNEXPECTED / RESOLVED self-checks (widget stalled, out of sync, press unhandled).

## Overview

The player makes the decisions. The assistant applies rules the player already follows every campaign:
settlement build-out order, tech order, skill orders and the doomstack template. Anything else is left to the
player.

## Status

| Feature | State |
|---|---|
| Settlement build planner (`assist/buildplan.py`, `strategy/settlements.json`) | Done and tested; fed live by `bot/sensor/world.py`. |
| Tech auto-progress (`assist/tech.py`) | Working: research state from memory; when idle, clicks the next beeline target (then cheapest remaining) in the technology panel by UI-tree id and confirms in memory that research started. Tested live 2026-10-16. |
| Turn-start runner (`assist/runner.py`) | Working: detects the new turn from memory, waits until it is really the player's turn and the player is idle, runs every step, the overlay shows AUTOMATING / YOUR TURN. Click the overlay to pause. Survives game restarts, the main menu and save loads; stops at once if the player alt-tabs away (see "Day-to-day robustness"). |
| Skill auto-spend (`assist/skills.py`, `strategy/skills.json`) | Working: opens each character with points from the Lords & Heroes list (then switches inside the open panel), spends points in the player's order by UI-tree node id, every point confirmed in memory. |
| Rites and commandments (`assist/rites.py`) | Working: commandments and the Dominating Scheme from memory, before any gold is spent. |
| Forbidden Workshop (`assist/workshop.py`, Ikit) | Working: Ratling Cannon upgrades as soon as they can be bought. |
| Masterplans (`assist/masterplans.py`, `bot/sensor/masterplans.py`, Thanquol) | Working: Steal-Takes and Secrets from memory; Kill-Stabs stay the player's. Multiplayer not yet exercised. |
| Widget settings (`assist/settings.py`, `assist/railpanel.py`) | Working (2026-10-21): every option and each step's schedule changed with a click in the expanded widget. |
| Building automation (`assist/build.py`) | Working: state from memory, provinces next to an enemy at war are skipped; damaged buildings repaired first, then upgrades and constructions through the province panel, each verified in memory. Repairs verified live 2026-10-16. |
| Army builder (`assist/army_builder.py`, `assist/army.py`, `assist/recruit.py`, `assist/heroes.py`) | Built: per-army tick in the window. For a ticked army: disband off-template units, recruit missing units from the local pool, recruit a Warlock Engineer, move toward the closest province that can recruit what is missing, walk free heroes in (see "Army builder"). Walking heroes in was verified live. |
| Assistant window and overlay (`assist/app.py`) | Working: status, Run now, Pause, last turn's log, armies with template gap, free heroes, blocked provinces, Ignore buttons. |
| Launchers (`run_assistant.bat`, `run_assistant_once.bat`) | Start the assistant, or one pass, from a double-click. |

`bot/` is the sensor and focus layer and `tools/ui.py` sends all input. The original turn-ending bot (`run.py`,
`bot/loop.py`, `bot/brain/`, `bot/hands/`) is in `legacy/` and must not be run.

## Principles

- **Player-visible information only.** `bot/schema.py` is the allowlist for the memory sensor. A field is added
  only if you can say where on screen a human would read it.
- **Deterministic rules.** The player's strategy lives in `strategy/*.json` and `../tww/skv_beeline.json`; the
  steps in `assist/` apply it. When something needs a decision, the pass stops and leaves it to the player.
- **Ordinary input.** `tools/ui.py` sends real keyboard and mouse events and refuses (`InputAborted`) unless the
  game window is in the foreground (`bot/focus.py`).
- **Battles and turn ends are the human's.** The assistant works the campaign map at the start of a turn only.

## Layout

```
run_assistant.bat      start the assistant (double-click)
run_assistant_once.bat one pass right now, no window (asks first)
assist/runner.py       turn-start loop: new turn -> your turn? idle? popups? -> tech, skills, buildings, army
assist/app.py          the assistant window and the overlay (colours in assist/widget.py)
assist/popups.py       turn-start popups: closes event notices, holds the pass for decisions
assist/tech.py         tech step
assist/skills.py       skill step
assist/build.py        building step: repairs, upgrades, constructions (plan: assist/buildplan.py)
assist/army_builder.py army step (template compare: army.py, recruitable units: recruit.py, heroes: heroes.py)
assist/gamedata.py     static game data from ../tww/db and ../tww/loc_en.json
assist/templates/      screen templates and building icons
bot/config.py          fixed game config (window title, resolution, RE offsets, paths)
bot/focus.py           focus discipline, the input mutex, InputAborted, idle time
bot/schema.py          State: what the memory sensor returns
bot/sensor/memscan.py  region walk, byte scan, static-pointer scan (pymem + VirtualQueryEx)
bot/sensor/cvtable.py  expected campaign_variables float[1068] used as the memory anchor
bot/sensor/memory.py   MemorySensor: static pointer -> campaign model -> fields; re-attaches to a restarted game
bot/sensor/world.py    factions, regions, provinces, buildings, armies, characters from memory
bot/sensor/ui.py       the game's UI tree from memory
bot/sensor/camera.py   camera and map-to-screen projection
tools/ui.py            every click, key, move and wheel (checks the game is in front first)
tools/wait.py          waits on game state (UI tree / memory), never on the clock; next_frame()
tools/timing.py        per-step / per-action timing to runs/timing-YYYYMMDD.jsonl (python -m tools.timing)
tools/bench.py         benchmark: load a save through the menus, time one full pass (python -m tools.bench)
tools/inputcal.py      measures how little delay the game needs to register clicks, keys, wheel, drags
tools/turn_driver.py   test harness that plays whole turns on a test save (not part of the assistant)
tools/probe.py         find the campaign model and a static pointer to it; writes anchors.json
tools/watch.py         snapshot/diff/find around the model to locate field offsets
tools/extract_icons.py building icons from the game packs into assist/templates/buildings
tools/...              other research helpers (re_*.py, trace.py, track.py, uidump.py, hover.py, clicktest.py, bg.py)
strategy/              the player's rules (JSON)
anchors.json           build-specific anchors (static pointer offset, field offsets)
runs/                  logs, status file, memory snapshots (gitignored)
tests/                 rule checks for the build planner
legacy/                the old turn-ending bot and unused drafts: do not run
```

## External dependencies

Run everything from this folder with `python -X utf8` (the launchers do). Besides the packages in
`requirements.txt` (`pefile` and `zstandard` are only for the research tools), the assistant reads files from the
parent repo. The paths are fixed relative to this folder:

| File | Used by | Made by (from the repo root, see `../README.md`) |
|---|---|---|
| `../tww/db/*.json` | `assist/gamedata.py`, `recruit.py`, `skills.py`, `tech.py`, `bot/sensor/world.py` | `python run_all.py game` dumps the default tables from the installed game's packs. Four the assistant needs are not in the default set; dump them once with `python -X utf8 scripts/game/dumpdb.py building_chain_set_items_tables building_effects_junction_tables region_to_province_junctions_tables campaign_variables_tables` |
| `../tww/loc_en.json` | in-game names (`assist/gamedata.py`, the window) | `python run_all.py game` (`scripts/game/extract_loc.py`) |
| `../tww/skv_beeline.json` | tech step | `python scripts/game/skv_beeline.py` (needs `character_skill_node_links_tables` and `technology_required_technology_junctions_tables` dumped) |
| `../re/cv_globals.json` (with `../tww/db/campaign_variables_tables.json`) | memory anchor (`bot/sensor/cvtable.py`) | a reverse-engineering output (`scripts/re/cv_consumers.py`) |

The pack reader has the Steam install path hard-coded (`scripts/game/packread.py`, `GAME=`). After a game patch,
re-dump the tables and check `anchors.json` and the offsets in this README: they are build-specific.

End Turn hotkeys, for the test harness: Shift+Enter ends the turn and skips warnings; plain Enter stops at warnings
such as "Lord not moved" and only pans the camera to them. The assistant itself never ends a turn.

## Known fields (9.0 build)

| Field | Path from campaign model | Verified |
|---|---|---|
| turn | not found | `+0x715c` read 1, 2, 3 then stuck on turn 4; `+0x719c` read turn+1 for four turns, unconfirmed |
| treasury | `+0x7f0 -> +0x20 -> +0x270` | 9000, 10901, 12802 matched the top bar |
| income | `+0x7f0 -> +0x20 -> +0x27c` | 1901 matched the top bar |

`tools/trace.py <value>` finds pointer paths like these by walking out from the model.

## How the memory anchor works

The campaign model holds a `float[1068]` copy of the `campaign_variables` table at `+0x5be8`
(from `re/NOTES.md`). `tools/probe.py` scans the heap for the first 48 default values, then
scans the exe's data section for an 8-byte pointer to the object that holds them. On the 9.0
build that pointer is `Warhammer3.exe+0x4480d88`, the same global the autoresolver notes
call `_DAT_144480d88`. `MemorySensor` re-reads it on every read (it is 0 at the main menu, and a
loaded save gets a new model object). Only when the pointer is non-zero but does not lead to a model (a
patch moved it) does it fall back to the heap scan: at most every 30 s per process (backing off to 5 min),
one scan at a time, and a candidate is only taken when the exe holds a static pointer to it and its turn
fields read sanely, so the DB and engine copies of the same array are never picked. The pointer it finds
is saved to `anchors.json`. A scan takes about 40 s on a late-game save.

## Finding a field offset (turn, treasury)

With a campaign loaded:

```
python -X utf8 -m tools.watch find 12345        # the treasury shown on screen
python -X utf8 -m tools.watch snap A
# end a turn in-game
python -X utf8 -m tools.watch snap B
python -X utf8 -m tools.watch diff A B --eq 8   # the new turn number shown on screen
```

Put confirmed offsets in `anchors.json` under `"fields"`. The window scanned is
`model-0x1000 .. model+0x20000`; a field that lives behind a pointer (likely the treasury,
which belongs to the faction object) needs a pointer hop added to `MemorySensor`.

## Legacy

`legacy/` holds the original proof of concept (`run.py`, `bot/loop.py`, `bot/brain/`, `bot/hands/`), which ended
turns by itself, and drafts the assistant replaced. Nothing imports it and it must not be run; see
`legacy/README.md`.

## Settlement build planner

`strategy/settlements.json` is the priority list; `assist/buildplan.py` applies it per province (rules: [Logic](#logic), Buildings).

| Rule | Source |
|---|---|
| Slots per main-building level: major 1, 2, 3, 5, 7; minor 1, 2, 3; Skavenblight 2, 4, 6, 9, 12 | building effects |
| Warpstone Reactor chain is not allowed in minor settlements | secondary-slot chain sets |
| Chained Sentry Beasts has a minor-settlement counterpart, Fortified Entries | garrison chain sets |
| Spy Nests is tier 4, so minor settlements stop at Deep Burrows | building levels |
| Equipment Warpforge and Warp-Turbine Plant need tier 5, so they can only go in a capital | building levels |
| Breeding Pit and Scrap Heap stop at tier 3; Reactor, Temple and Sentry Beasts reach tier 5 | building levels |

Unverified: whether the port takes one of the main building's slots (assumed yes, `PORT_TAKES_A_SLOT`).

```
python -X utf8 -m assist.buildplan        # demo on example provinces
python -X utf8 tests/test_buildplan.py    # rule checks
```

## Faction facts in memory (9.0.4, decoded 2026-10-21)

From the faction script interface's Lua bindings (natives disassembled), checked live. Not used by any step now
(the diplomacy automation they were decoded for was removed); kept for later use.

| Fact | Where |
|---|---|
| can a player pick it (`can_be_human`, "major") | byte F+0xEB5 != 0: all 109 lord-select factions, none of the 451 others |
| dead (`is_dead`) | byte F+0x10C0 != 0 |
| treasury | i32 F+0xD58 |
| relationship | entry e in [F+0xDB8] (count +4, base +8, stride 0x78, other faction e+0x28); state i32 [[e+0x30]+0x20]: 0 war, 1 peace, 2 defensive, 3 military alliance, 2..7 ally/vassal/client, 7 vassal; byte e+0x74: bit 0 trade, bit 2 met, bit 3 NAP |
| strength (`faction_strength`) | B = [[[[[F+0x3A8]+0x90]+0x6CD0]+0x990]+0x10]; table [[B+0xE0]+0x280] keyed u32 F+8 -> E; map [B+0x1D8]+0x1E8 keyed u32 E+0x40 -> u32 node+0x14 (matches the diplomacy panel's strength bars) |

## Running the assistant

```
run_assistant.bat                        # the same as the next line, from a double-click
python -X utf8 -m assist.runner          # window + overlay + loop; acts at every new turn
python -X utf8 -m assist.runner --once   # run the automations once now (no turn or idle check)
python -X utf8 -m assist.tech status     # memory: research idle or running, the next click
```

The current status is also in `%LOCALAPPDATA%\automated-jay\state.json` (outside OneDrive, which locks synced files) (`state`, `headline`, `detail`, `turn`, `time`), replaced
atomically on every change. The overlay lets clicks through while the assistant is automating (it sits over
the game) and never takes focus; click it at other times to pause or resume. Only one of the project's
processes sends input at a time: `bot/focus.py: game_focus` holds a system-wide mutex.

## Day-to-day robustness (tested live 2026-10-16, 9.0.4)

The assistant can be started before the game, kept running across game restarts, and left alone while the
player loads saves or plays with friends.

| Situation | What the assistant does |
|---|---|
| Game closed, or started before the game | Window says WAITING "the game is not running"; it looks for the game every 2 s and attaches by itself. |
| Main menu, or a different save loaded | WAITING "no campaign loaded". Once a campaign appears: "campaign changed; acts from next turn". A loaded save is never treated as a turn start. |
| Game crashed or restarted while the assistant runs | It notices the process exit within a second, re-attaches to the new process, and works from the next turn. |
| Turn counter moved but it is not the player's turn yet (AI turns, or another player's turn in sequential multiplayer) | The pass starts only when the End Turn button is shown and enabled (`[component + 0x2F0] + 0x18` is its state name, "inactive" while waiting) and no `ai_turns` panel is up. |
| Player is using mouse or keyboard at turn start | WAITING "waiting for you to stop clicking" until 3 s without input (`GetLastInputInfo`). |
| Player alt-tabs away during a pass | Every click, key, move and wheel first checks that the game is the foreground window and that the window under the cursor is the game; otherwise `InputAborted` stops the pass at once. The overlay says INTERRUPTED, focus stays where the player put it, held keys and mouse buttons are released. |
| A popup needs the player | DECISION NEEDED with the panel's id. The check repeats every 2 s without blocking anything: Pause skips the turn, Run now tries again. An unknown panel gets an "Ignore <id>" button in the window: one click adds it to `strategy/popup_ignore.json` and it never blocks again. |
| The UI tree or the popup check cannot be read | The step reports the failure ("game UI not found in memory; nothing clicked", "SKIPPED turn N: the popup check failed"). There are no fixed-coordinate fallbacks in the turn-start steps. |

How to recover:

- **INTERRUPTED** or **SKIPPED**: go back to the game, close anything half-open if you like, and press
  **Run now** in the assistant window. It redoes the whole pass for the current turn.
- **DECISION NEEDED** for a panel that is harmless: press **Ignore <id>**. To undo, remove the id from
  `strategy/popup_ignore.json`. Diplomacy offers, battles, dilemmas, message boxes and the game menu are
  always left to you and cannot be ignored.
- **Paused** by accident: click the overlay or Resume; the skipped turn can be done with Run now.
- **Nothing happens at a new turn**: check that the window does not say PAUSED, and that the game is in
  borderless windowed mode at 1920x1080. The window's status line says why it is waiting.
- **Stopping**: close the window or press Ctrl+C in the terminal. If a test harness was started from a
  shell wrapper, look for leftover `assist.runner` / `tools.turn_driver` Python processes
  (`Get-CimInstance Win32_Process`) and end them; killing only the wrapper can leave the Python child running.

## Input and focus (verified on 9.0.4)

- The game ignores window messages (PostMessage) for both keys and mouse, even with faked activation.
  It only accepts real input while it is the foreground window.
- It also ignores pydirectinput/SendInput mouse BUTTON events, but accepts `SetCursorPos` + legacy
  `mouse_event` (`tools/ui.py: click_at`). Keyboard via pydirectinput works.
- Typed text drops characters and capitals at automation speed (`type_text` slows it down; still flaky).
- Window capture (PrintWindow with PW_RENDERFULLCONTENT) works with the game in the background, so all
  screen reading happens without focus. `bot/focus.py` raises the game only around input and always
  returns focus to the user's terminal, verified with retries.
- All input goes through `tools/ui.py` (`click_at`, `move_to`, `double_click`, `drag`, `wheel`, `press`,
  `held`, `hold_key`, `type_text`). Each one raises `bot.focus.InputAborted` (a BaseException, so a step's
  `except Exception` cannot swallow it) when the game is not in front. A topmost window over the game can take
  a click even while the game has the focus, so button and wheel events also check `WindowFromPoint`. The
  assistant's own overlay is click-through while automating, so it never trips this check.

## Game UI facts used

| Thing | Where / how |
|---|---|
| End turn | Shift+Enter skips warnings ("Lord not moved"); plain Enter stops at them |
| Technology panel | `button_technology` on the end-turn ring (hotkey 8); its `alert_icon` child is visible while research is idle |
| Tech research queue | one chain at a time; clicking a tech (also a queued one) re-targets the chain to it; clicking the tech being researched cancels research and the chain; Shift-click does not append. Some locked techs ignore the click (Plans Within Plans and everything behind it, while Record Effective Recipes is unresearched) |
| Diplomacy | hotkey 7 |
| Lords & Heroes list | top bar `tab_units` (state "selected" while shown); clicking a row's rank badge `skill_button` opens that character's skills |
| Skill panel | `character_details_panel`; the characters of the Lords & Heroes list along its top (`CcoCampaignCharacter<id>`), clicking one switches the panel to it; closed with `button_ok` |
| Provinces list | top bar `tab_regions`; rows `row_entry_<province key>` open that province's `settlement_panel` |
| Building slot | hovering a slot opens its popup; clicking a slot under construction CANCELS that construction (refunded) |
| Turn counter | memory: model+0x6cb0 -> +0x10 (cross-check model+0x719c = turn + 1) |

## Reading the campaign from memory (`bot/sensor/world.py`)

The game ships its Lua scripting interface in the exe as binding tables of {method name, C function}.
Decompiling the C functions (Ghidra, `tools/re_bindings.py`, `tools/re_tables.py`) gives the exact field
offsets, so the assistant reads the same data the game's own scripts use, from outside the process:

| Object | Field | Offset |
|---|---|---|
| faction | regions | count u32 +0xF3C, array +0xF40 (entry -> region) |
| faction | relationships | [+0xDB8]: count +4, base +8, stride 0x78; other faction +0x28; at war when int [[e+0x30]+0x20] == 0 |
| faction | name | [[+0xD88]+8] string |
| region | key | [+0x80] DB record, +0x10 char* |
| region | owner | [[+0x120]+0x10] |
| region | neighbours | count u32 +0x8C, array +0x90 |
| region | province | [[+0x3A8]+0x10]; province regions list at +0x78 (entries -> region), capital +0x90, adjacent provinces +0x104/+0x108 |
| region | slots | [+0x148]+0x10: count +4, array +8 |
| slot | building / construction | [+0x190]: building +0x20, construction +0x10; active byte +0x1D8 |
| building | level | [+0x30] level record: key string +8, level index +0x1F0 |
| building | health | f32 +0x38, max f32 +0x3C (`percent_health` = 100 * hp / max); damaged when hp < max |
| construction | kind / cost | u32 +0x10: 1 repair, 3 construction or upgrade; cost u32 +0x20 |

The player's faction is found by following candidate paths from the campaign model (`anchors.json:
faction_paths`) and accepting the one whose name is `player_faction_key`.

The no-build rule (per settlement, player decision 2026-10-20): an owned settlement, capital or minor, is blocked when
a region next to it (the region's neighbour list in memory: land borders) is held by a faction the player is at war
with. The rest of its province is built as usual. (Until 2026-10-20 the whole province was blocked when such a
faction held a region in it or in a bordering province.)

## Building UI mechanics (`assist/build.py`)

All from the UI tree and memory (verified 2026-10-16, 9.0.4); no screenshots:

- Province panel: Provinces tab (`tab_regions`) -> `row_entry_<province>` -> `settlement_panel`, one column
  `CcoCampaignSettlement<region>` per settlement, slots `CcoCampaignBuildingSlotregion_slot_<n>` (n = u32 at memory
  slot +0x8). The panel slides in from below the screen when it opens (~0.4 s); the step waits until it is still.
- Slots are only hovered, never clicked: hovering opens the slot's popup (a child of the slot component) in about
  20 ms, and a click on a slot under construction cancels that construction.
- Upgrade: the popup's `construction_building_tree` has one card per level (id = level key); its
  `square_building_button` reads "built", "normal" (can be built) or "greyed" (not now: not clicked). Card states
  settle a frame or two after the popup appears, so the step waits for 3 still frames.
- Construct: an empty slot's popup lists categories (`CcoBuildingSetRecord<set>`); hovering one builds its tree
  (`CcoBuildingChainRecord<chain>`, one chain per frame). The category each chain was found in is remembered in
  `runs/build_categories.json`.
- Repair: a damaged building's popup has `button_repair` (cost in its tooltip: level cost x damaged fraction, less any
  local construction discount) next to `button_abandon`. The gold goes at once and the repair takes a turn. An
  upgrade the game starts on a damaged building halts ("construction on it has halted") until it is repaired, and
  continues after the repair, so damaged buildings are repaired first and never upgraded.
- A popup item is clicked only once the game shows the cursor over that very item (its hover state): one click aimed
  while a popup was still being laid out hit Abandon.
- Every action is confirmed in memory (construction in the slot, or the treasury going down) before the next one.

```
python -X utf8 -m assist.build plan      # memory only: blocked provinces, repairs and the next builds
python -X utf8 -m assist.build run       # do it
```

## Camera and map positions (`bot/sensor/camera.py`)

| Thing | Where |
|---|---|
| character map position | float x, y at character +0x60; grid u16 x, y at +0x68 |
| camera block | `[Warhammer3.exe + 0x48610A0] + 0x3710` |
| camera eye | block +0x00: float3 (x, height, y) |
| camera forward | block -0x60: float3 (plane normal) |
| projection scales | m00 at block +0x0C, m11 at block +0xA0 (m11 / m00 = 16:9) |

`Camera.project(x, y, h)` turns a map position into a screen pixel. It was checked against characters on
screen and against hover tooltips. A garrisoned lord's army is targeted by its banner above the settlement
(height about 2.6 over the lord's position). The camera is moved with WASD, closed-loop on these values.

## Moving a hero into an army (`assist/heroes.py`)

Select the hero (click its projected position), right-click the lord's army banner, then click the action in
the "Hero Actions" panel. For your own army that panel offers the hero's embed action, labelled with the
buff the army gets (Warlock Engineer: "Increase Mobility"). A hero out of reach gets a move order and
joins later. Verified once on 9.0.4 with a lord garrisoned in a settlement.

## Lords & Heroes list as navigation (verified 9.0.4)

- Double-clicking a row selects that character and centres the camera on it at a fixed zoom and angle
  (eye height 11.5, pitch -0.76), whatever the zoom was before. A single click selects without moving the
  camera. Right-clicking a row does nothing.
- Embedded heroes are listed indented under their lord. Rows are about 79 px apart starting at y 354.
- The vertical bar on the right of each row is the movement left this turn: a bronze frame that is
  always drawn, with an orange fill rising from the bottom. Rows are found by the frame (so characters
  who have moved are not missed) and `list_rows()` returns the fill as a 0..1 movement fraction.
- Rows are identified by double-clicking each top-level row and matching the camera centre to character
  positions in memory. Long lists are scrolled with the mouse wheel over the list (not tested yet: the
  test campaign has two rows).
- Hero step: double-click the lord's row, single-click the hero's row, right-click the lord's banner,
  click the Hero Actions card. WASD panning is the fallback when a name is not in the list.

## Recruitment awareness (`assist/recruit.py`)

Which provinces can recruit each template unit right now, from game data plus live memory:

- Units are gated by buildings only; no game table locks these units behind a technology.
  Stormfiends (Ratling Cannons) need an Equipment Warpforge, Warp-Doom Magma-Cannons a Warp-Turbine Plant
  (Thanquol's Morskittar Engine also has them, but it is single player only and never planned).
- Warlock Engineers are recruitable in a province with a Construction Cavern chain building (or Galbaraz's
  oathgold landmark). Since 2026-10-20 that chain is on the settlement list (Warp-Turbine Plant, capitals). For
  Ikit's Forbidden Workshop level 2 the planned one counts; a temporary Cavern is only built when no managed
  settlement plans the chain.
- Only finished buildings count; one under construction or being upgraded does not.
- Recruitment draws on buildings anywhere in the province the army stands in.

The army step and the window use this, so the builder never plans around a building that does not exist.

## Other memory facts found on the endgame save (9.0.4)

| Thing | Where |
|---|---|
| treasury | int at player faction +0xD58 (the old model-relative path did not survive a different save) |
| unspent skill points | u32 at [character +0x3F0] +0x240 |
| renamed characters | name entry holds inline UTF-16 text (vtable in the exe, length +0x10, text +0x18) |

The skill step reads points from memory and confirms each click by the points going down in memory (70-120 ms
after the click). It never looks at the screen (see "The game's UI tree" below for the panel).

## The game's UI tree (`bot/sensor/ui.py`)

Every on-screen element is a UI component in memory (layout from the UIComponent Lua bindings):

| Field | Offset |
|---|---|
| child count / child array | +0x1CC / +0x1D0 |
| id string | +0x2A0 (string object; short ids are stored inline) |
| parent | +0x2E8 (0 at the root) |
| x, y in screen pixels | +0x2C0, +0x2C4 |
| width, height | [+0x2F0] +0x11C, +0x120 |
| visible | +0x353 |
| state count / state array | +0x1D8 / +0x1E0 (state object, name at +0x18) |
| current state object | +0x2F0: name at +0x18, width / height +0x11C / +0x120, text shown [+0x138] (wide string) |
| frame stamp | +0x334 (u32 ms, written twice per rendered frame: `tools/wait.py next_frame`) |

The root (id "root") is found once and a static pointer to it is cached in `anchors.json` (`ui_root_ptr`).
One read of +0x1C8..+0x358 covers every field a lookup needs: a full walk of ~1,000 visible components takes about
12 ms, a root panel or a cached pointer about 0.1 ms (`UI.first`, `UI.cached`, `UI.root_children`). Useful ids:

- `character_row_<character id>` rows in Lords & Heroes, with `skill_button` (the rank badge).
  Character id = u32 at character +0x110.
- `character_details_panel_skills` (skills panel); each skill node's id is its character_skill_key, with
  child `card` and `icon_check`. The tick shows once any rank is taken, so it only means "maxed" for
  one-rank skills. The card's state tells more: "available" (a click takes a point), "maxed", "locked",
  "locked_rank" (a click changes nothing). Two `list_clip` components exist (skills tree, Lords & Heroes list):
  scope lookups. The tree's scrollbar thumb is `hslider/handle`.
- The skills panel lists the Lords & Heroes characters along its top (`char_select_list/.../CcoCampaignCharacter<id>`,
  `button_character_holder` "selected" for the one shown); clicking one switches the panel to that character. The game
  then builds a NEW tree (new components, one row per indent level of the character's node set: Ikit 6, Warlock
  Engineer 4, Verminlord 6), row by row or all at once, 15-300 ms after the switch; until then the previous
  character's tree is shown. The step waits until every row is a new component.
- `3d_ui_parent` holds map labels: `label_<character id>` (character flags) and
  `label_settlement:<region key>` (settlement nameplates), positioned in screen pixels.
- `technology_panel`: see the technology section below.
- `button_menu`, `button_load`, `button_end_turn`, `button_technology`, `popup_message_box` with
  `button_tick` / `button_cancel`.

The skill step opens the first character's skills from its list row, switches to the others inside the open panel,
skips maxed and locked cards without clicking, and clicks nodes by id: 4 characters and 5 points in about 2.3 s (was
about 7 s per point, and 90 s per character before that), following the order exactly.

## Army builder (`assist/army_builder.py`)

Rules: [Logic](#logic), Army.

## Turn-start popups (`assist/popups.py`)

Any visible child of the UI root that is not part of the normal HUD is a popup. Event notices are closed;
anything needing a decision (AI diplomacy, battles, dilemmas, confirmation boxes, unknown popups) holds the
pass and the overlay says what is waiting, by panel id. Unknown panels can be ignored from the window (see
"Day-to-day robustness"). Escape is never pressed blindly: with nothing selected it opens the game menu.

`tools/turn_driver.py` is a test harness that plays whole turns on a test save (cancels AI offers,
autoresolves battles). It is not part of the assistant. With `--external` it tests the real app: start
`python -X utf8 -m assist.runner` first; the driver only ends turns and answers the runner's DECISION NEEDED
popups (read from `%LOCALAPPDATA%\automated-jay\state.json` (outside OneDrive, which locks synced files)), then checks each turn's log line and that focus came back.

## Memory scans and the game's RAM use

The game commits about 18 GB on a loaded late-game save but keeps only about 6.6 GB of it in RAM. Reading
a committed page that is not in RAM makes Windows give it real memory, so a scan that reads every page
pulls the whole commit into RAM. That is what pushed the game to 20 GB on 2026-10-17. It was not a game leak:
opening panels and sitting idle caused no growth. `memscan.read_region` now asks Windows which pages are
resident (QueryWorkingSetEx) and reads only those. A full scan then leaves the game's RAM flat and runs about
3 times faster. Live game data is always resident, so nothing is missed.

## Technology (memory + UI tree, 9.0.4)

`T` = [player faction +0xFD8] is the faction's technology manager:

| Thing | Where |
|---|---|
| tech being researched | entry at [T+0x28]; research is running iff non-null and u32 [E+8] == 2 (0 when idle) |
| last clicked research target | entry at [T+0x30]; set by every click, even one the game ignores (so it can be non-null while idle); 0 after research is cancelled; equals the end of the chain after a successful click |
| researched techs | cap u32 T+0x38, count u32 T+0x3C, array [T+0x40] of entries |
| every tech | sets: count u32 T+0xC, array [T+0x10] -> A; rows: count u32 A+4, array [A+8], stride 0x10; row R: count u32 R+4, entries [R+8], stride 0x80 |
| entry E | key = string object at [[E]+0x50]+8; state u32 E+8: 0 researched, 2 researching, 3 available, 4 locked; byte E+0x78 is 0; E+0x10 / E+0x20 look like link lists (count = number of parent / child links), not decoded |

The queued chain itself is not stored: re-targeting it changes only T+0x28/T+0x30, nothing else in T (first
0x1000 bytes), the faction (0x3000 bytes) or the entries. It is worked out instead (2026-10-21, `queued_chain`): a
click queues the target with all its missing prerequisites, and every Skaven node needs all its parents
(`required_parents` 0), so the chain is the target and its ancestors (`technology_node_links`, plus
`technology_required_technology_junctions`) whose entries are locked. Checked against the panel: 7 of 7.

Panel components:

- `technology_panel`, closed with `button_ok` (bottom centre). The panel fades in: clicks right after it
  appears are not trusted, so the step waits 1 s.
- Tree: `technology_list` / `list_clip` / `list_box` / `tech_template` / `tree_parent` / `slot_parent` /
  `<technology key>` (the node id is the technology key, e.g. `wh3_dlc29_tech_skv_9_1_2`), child
  `technology_entry` with `icon_check` (researched), `dy_time` (hourglass + turns: available or queued, so a
  locked node with `dy_time` visible is in the queued chain) and `researching_icon`.
- The tree (2703 px) is wider than `list_clip` (x 36..1882). All 56 nodes are in the tree and read as visible,
  including those past the clip at off-screen x (same trap as the recruitment list). The scrollbar is
  `technology_list` / `hslider` / `handle`; dragging it moves the nodes' rectangles, so positions are re-read
  after a drag. The panel remembers its scroll position between openings.

The step reads the state from memory and sends no input while research is running (a click on the tech being
researched would cancel it). When idle it opens the panel, clicks the first target in click order, waits up
to 2.5 s for [T+0x28] to show research, and moves on to the next target when the game ignored the click.

```
python -X utf8 -m assist.tech status   # memory only: what is researched, the target, the next click
python -X utf8 -m assist.tech run      # queue research if idle
```

## Recruitment queue (memory, 9.0.4)

From the force's `recruitment_item_count` / `recruitment_items` bindings: count u32 at force +0x6EC, item array
at +0x6F0; entry -> item X; unit key = string object at [X+0x90]+0x3E0. Queued units count as present when
comparing an army with the template (both template units take 2 turns to recruit).

## Speed: waits on game state, measured input (2026-10-16, 9.0.4)

Every wait is a condition on the UI tree or memory, polled every 2 ms (`tools/wait.py`: `appears`, `gone`, `stable`,
`stable_rect`, `value_changes`, `camera_settled`, `root_children_stable`, `ui_live`), with a timeout that raises
`WaitTimeout` naming what it waited for. The only fixed delays left are in `tools/ui.py`, in rendered frames, each the
measured minimum plus one frame (`python -m tools.inputcal`):

| Input | Rule | Measured |
|---|---|---|
| click | move, wait until the target shows its hover state, down, 1 frame, up | a click before hover registers is lost (10/30); after it 220/220 |
| key | down, 2 frames, up | 0 frames 0/20, half a frame 13/20, 1 frame 60/60 |
| wheel | notches 2 frames apart | notches in the same frame count once |
| drag | down, 2 frames, one jump, 2 frames, up | 0 frames 12/24, 1 frame 24/24 |
| double-click | 1 frame hold, 1 frame gap | 0 / 0 worked 10/10 |
| after raising the game | 2 frames | keys 0 frames after the switch were lost (0/15), 1 frame 10/10 |

The game renders about 155 frames/s; the UI stamp (+0x334) changes twice per frame. A just-opened panel can ignore
the first cursor move: the click then nudges the cursor 1 px. Camera pans (Lords & Heroes double-click, minimap
click) are eased and take about 1.9 s; `camera_settled` returns when the screen-centre point moves < 0.1 px/frame.
After a save load the HUD exists about 12 s before the game renders again, and the loading screen comes back for
about 4 s: `tools/bench.py` waits for all of it. The turn-start settle (`assist/runner.py settle`) is a condition:
camera still for 250 ms and no root panel coming or going for 500 ms. The 3 s player-idle check is unchanged.

Benchmark (`python -m tools.bench`, save "ENDGAME SKAVEN", turn 90, same results every step): 94.0 / 93.6 s before,
55.5 / 55.1 s after the input, lookup, popup, runner and tech changes, 10.2 / 9.7 s after the skills (19.8 -> 2.5 s)
and buildings (30.9 -> 1.7 s) steps waited on conditions too, with identical results. With repairs on (2026-10-16)
the building step also repairs 6 buildings on that save and does 9 upgrades instead of 6: buildings 3.7 s, pass
10.5-11.4 s. The skills and buildings steps have no fixed sleeps left; what is left is in the army step:
`python -m tools.timing` lists them by file:line.
