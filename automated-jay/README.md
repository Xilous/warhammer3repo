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

### What happens each turn

1. The assistant sees the turn counter go up. It waits until it really is your turn (End Turn button shown and
   enabled, no AI-turn panel; in sequential multiplayer, once the others are done), lets the turn start settle
   (camera still, no panel coming or going), then takes over at once.
2. **Popups.** Event notices are closed. Anything that needs a decision is **always left to you**: diplomacy
   offers, battles, dilemmas, confirmation boxes, the game menu, and any panel it does not recognise. The overlay
   says **DECISION NEEDED** and nothing is clicked. Once you close the popup, the pass starts (it checks every 2 s).
   Popups about significant global events (the endgame) and story panels that only have "Continue" (Thanquol's
   story chapters) are left for you to read: **GLOBAL EVENT**. A guided tour of a panel: **GUIDED TOUR**.
   **While a cinematic plays** (a movie or an in-game cut-scene) nothing is clicked or pressed at all; a pass that
   a cinematic interrupts waits and runs again when it is over.
3. **The pass**, in this order. Each step is independent: one that fails is reported and the next still runs.
   Which steps run at turn start and which at **Build & End Turn** is set in `strategy/automation.json`
   (`schedule`). By default Rites, Tech and Skills run at turn start; Rites, Tech, Skills, Buildings and Army run when you press
   **Build & End Turn**, so settlements you take during the turn are built on the same turn, and research and skill
   points are handled on a campaign's very first turn too (there is no turn start to act on there; unspent skill
   points would make the game stop at its End Turn warning). Before pressing End Turn every open panel is closed,
   so it is only ever clicked on the bare campaign map. If you end a
   turn in the game instead, the next turn start runs Buildings and Army too, so nothing waits a turn.
   0. **Rites and commandments** (runs first, before any gold is spent): every complete province is kept on
      **Exploitative Planning**. On a fresh campaign the first complete province gets **Expansionist Planning**
      first, the requirement of the rite **The Dominating Scheme**, and keeps it until the rite has been cast once.
      The Dominating Scheme is cast whenever it is off cooldown and affordable; after Horned One's Approval its
      Verminlord choice is answered with **A Verminlord Warpseer** (that dilemma only). Cooldowns and commandments
      are read from memory (assist/rites.py).
   1. **Tech**: if research is idle, start the next tech on the bee-line, after that the cheapest remaining one.
   2. **Skills**: spend skill points on Ikit Claw, Thanquol, Verminlord Warpseers and Warlock Engineers in your order.
      Other characters are left alone.
   3. **Buildings**: first every damaged building is repaired, then upgrades and constructions from your
      settlement priority list. Provinces where an enemy you are at war with holds a region, or that border one,
      are skipped, repairs included. A damaged building is never upgraded (the game would halt the upgrade).
   4. **Army**: only armies you ticked in the window. Each is made to match the doomstack template (since
      2026-10-20: lord, 1 Warlock Engineer, 12 Stormfiends with Ratling Cannons, 6 Warp-Doom Magma-Cannons; pure
      ranged, the cannons fire over the Stormfiends): extra units
      are disbanded once the army stands where its missing units can be recruited locally, missing units are
      recruited from the local pool (never the global one), the army is moved toward the nearest such province,
      and free Warlock Engineers are walked in. It spends the gold the buildings left.
4. The overlay turns green: **YOUR TURN N**, with one line per step. The window's "This turn" box shows the same.

The game is brought to the front only while the pass clicks. Afterwards, focus goes back to the window you were
using. **If you switch away from the game during a pass, the pass stops at once (INTERRUPTED)**; press Run now to
redo it. The assistant never fights a battle, and ends a turn only when you press **Build & End Turn**.

Overlay colours: grey WAITING, amber AUTOMATING, green YOUR TURN, pink PAUSED and DECISION NEEDED, red ERROR and
INTERRUPTED. Clicking the overlay toggles pause, except while automating (then clicks go through to the game).

### Playing Thanquol (Clan Scruten), the backup faction

The assistant finds out from memory which faction you play (the human faction that is Ikit's Clan Skryre or
Thanquol's Clan Scruten); there is nothing to set. What is different with Thanquol:
- **Masterplans** (`assist/masterplans.py`, `strategy/masterplans.json`), at Build & End Turn only: every free
  Underling is sent on a Steal-Take (the best foreign settlement on screen: highest settlement level, factions you
  are not at war with first, none on a Masterplans cooldown, none in one of your provinces or a province bordering
  one); each running Steal-Take is completed once waiting
  another turn is worth less than completing (Risk x the chance one Complication maxes the Alarm, against the loot
  the next turn adds over the loot gathered; at maximum Alarm a plan pays 25%), and Clan Scruten Secrets are bought
  in the file's `shop.order`, keeping 50 Warpstone for a Kill-Stab. **Kill-Stab plans stay yours**: the assistant
  never starts, completes or abandons one. Everything it decides on is read from memory (`bot/sensor/masterplans.py`:
  plans, Risk, Alarm, loot, cards, Underlings, cooldowns, Warpstone, Secrets owned); the panel is opened only to click,
  and every action is confirmed in memory. Single player and multiplayer work the same: what is unlocked (the
  Masterplans, each Underling, each Secrets line) is read from the game every time, never from the mode, the turn or
  the story, so whatever unlocks later is used from that turn on. Every board it reads is logged to
  `runs/masterplans.jsonl`. Run now and
  Build & End Turn close the panel (and its guided tour) before they start. Underlings are not armies to it: they
  are never listed for ticking and the army builder ignores them.
- **Skills** (`strategy/skills.json`, "thanquol"): Route Marcher, Inspiring Presence, then his unique Blessings of
  the Horned Rat (required by the next three), Hasty Redirection, Insatiable Greed and Replaceable Fodder (his
  unique row unlocks at rank 11), then Ikit's army and campaign skills, Mentor last; Boneripper with **Warpfire
  Projectors** as soon as rank 15 allows, Warpfire Braziers never.
- **Buildings**: the same settlement list. His Grey Seer Lair in Karag Dromar is kept and upgraded as a landmark;
  the Morskittar Engine is left out (single player only, story-locked until mission 5): Zhufbar's slot takes the
  next building on the list. Frontline provinces stay yours, as with
  Ikit (Black Water is one while Zhufbar is an enemy's).
- **No Forbidden Workshop**: the Shop step does nothing.
- Rites, tech tree and the army template are the same (Thanquol is an allowed lord); Ferocious Plans comes
  researched.
- **Warlock Engineers**: his capitals build the Warp-Turbine Plant line like Ikit's (it recruits the Magma Cannons),
  and its Construction Cavern level is what recruits Warlock Engineers. Until one stands the army builder says so.

### The widget (everything without alt-tab)

The bar over the game (the Turn rail, compact while you play, full while a pass runs) has three small buttons
at its right end: **expand** (fold-out panel), **restart** (a fresh copy with the latest code) and **exit**.
The panel holds what the full window has: Run now, Pause/Resume, Restart, Exit, turn and treasury, this turn's
results, the armies with their army-builder tick boxes, Ignore buttons for blocking popups, the frontline
provinces, and a "full window" link. Neither takes focus, so the game stays in front; the panel hides itself
while a pass runs. Drag the bar to move both. Restart and Exit are refused while a pass runs.

### The assistant window

| Part | What it does |
|---|---|
| Status line | the same headline as the overlay |
| **Build & End Turn** | for when you are done with your turn: runs the end-of-turn steps (tech if research is idle, skill points, repairs, buildings, upgrades, then the army builder) and then ends the turn like Shift+Enter does in the game: the game's End Turn warnings (unspent skill points, a building that could be constructed, an army that can still move) are skipped, because they are about things the assistant leaves alone on purpose. It does not wait for idle (you asked), but it checks it is your turn and leaves any decision popup to you; if a step is interrupted or the game asks you something, the turn is **not** ended. |
| **Run now** | one full pass for the current turn, right away. It still checks that it is your turn and waits for 3 s without input. Use it after INTERRUPTED, SKIPPED or ERROR, after loading a save, or for a turn you paused through. |
| **Restart** | starts a fresh copy of the assistant (latest code and settings) and closes this one; refused while a pass runs. The window title shows the commit the running copy is on. |
| **Pause / Resume** | while paused, turn starts are skipped (the overlay says so). Resuming does not redo a skipped turn; Run now does. |
| Turn and treasury | read from memory every 4 s |
| **Ignore &lt;id&gt;** | shown when a pass is held by a panel the assistant does not recognise. If that panel is harmless, click it: the id goes into `strategy/popup_ignore.json` and never holds a pass again. Delete the id from that file to undo. Diplomacy offers, battles, dilemmas, message boxes and the game menu never get this button. |
| This turn | what each step did in the last pass |
| **Armies** (tick boxes) | every field army and how it differs from the template. Tick an army to let the army step manage it; unticked armies are never touched. The ticks are saved in `strategy/automation.json`. Also lists heroes on their own and which provinces can recruit the template units now. |
| **Army finances** | you decide when a new army is raised (the builder no longer raises one by itself). A green ✓ or orange ✗ line says whether you can afford a new army, after what the ticked refills will add. Below it: income per turn (last turn's, as the HUD shows it), the Supply Lines % per extra army for your difficulty, what each army costs now and what it would cost once refilled to the template (units not in the template are disbanded, so they drop out of upkeep and Supply Lines), and what the next army would add in all. Unit upkeep is the game's base upkeep with Supply Lines, calibrated against last turn's real army upkeep. All from memory (`assist/army_finance.py`, `bot/sensor/economy.py`). |
| **Create new playbook army** | greyed out, with the reason, until a Verminlord Warpseer is in the Recruit Lord pool, a Warlock Engineer is free or the engineer cap has room, and a province recruits Stormfiend Ratling Cannons and Warp-Doom Magma-Cannons. Pressed, it raises the Warpseer at once, ticks the new army and recruits the template. It does not stop you when the ✗ says it is not affordable: that is your call. |
| Provinces where nothing is built | the provinces the building step skips, and why |

The window only reads memory. It never sends input to the game.

### Your strategy files

Plain JSON, read fresh at every pass: edits apply from the next pass without a restart.

| File | What it holds |
|---|---|
| `strategy/settlements.json` | building priority list (main building, port, then the rest in order) |
| `strategy/skills.json` | skill order per character type |
| `strategy/automation.json` | how the assistant acts (`buildings.repair_damaged`: repairs on or off), the doomstack template (units and heroes), the ticked armies |
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

`strategy/settlements.json` is the player's priority list. `assist/buildplan.py` applies it per province:

- Slot 1 is the main building, upgraded to the maximum: tier 5 in a capital, tier 3 in a minor settlement.
  Skavenblight uses its own main-building chain with 12 slots at tier 5.
- Port settlements keep the port in slot 2 and upgrade it as far as the main building allows.
- The rest of the slots are filled top to bottom from the list, each chain to the highest level the
  settlement allows. Lower entries are dropped when slots run out.
- The order (player decision 2026-10-20): landmarks, then the two buildings that recruit the army template
  (Equipment Warpforge, Warp-Turbine Plant, both tier 5, so capital only), then chains that reach tier 5
  (Warpstone Reactor, Temple of the Horned Rat) before the tier-3 ones (Breeding Pit, Scrap Heap), fillers last
  (Chained Sentry Beasts, Spy Nests). Minor settlements keep Breeding Pit, Scrap Heap, Overseer's Lookout.
- What a capital lets go: no port: Spy Nests; one landmark or a port: also Sentry Beasts; port + landmark: also
  the Scrap Heap; port + two landmarks: also the Breeding Pit. Every capital can recruit the template.
- Equipment Warpforge is one per province. The Warp-Turbine Plant is capital only (never a lone Cavern in a minor);
  a Construction Cavern left in a minor is off the list there and replaced.
- Clan Armoury (Stormvermin) is off the list since 2026-10-20; a standing one is replaced when its slot is needed.
- Spending (2026-10-20, `assist/build.py` `spend_rank`): the gold goes across all provinces at once, in value order:
  main building and port upgrades; the Warpstone Reactor line (+30/40/50% income from every building in the
  province, paid back in about 6 turns); landmarks; the template's recruit buildings, the capital closest to tier 5
  first; then the rest in list order. A top item affordable within 2 turns of net income is saved for: nothing
  below it is bought that turn, and the army step leaves that gold alone too ("saving for ..." in the result).
- The army step checks the gold before every recruit click (base price until a click shows the real one), so it
  never clicks on with an empty treasury.
- Nothing is planned above the current main-building tier. Buildings that are not on the list are only
  offered for replacement, never demolished silently.

Facts taken from the game data rather than assumed:

| Rule | Source |
|---|---|
| Slots per main-building level: major 1, 2, 3, 5, 7; minor 1, 2, 3; Skavenblight 2, 4, 6, 9, 12 | building effects |
| Warpstone Reactor chain is not allowed in minor settlements | secondary-slot chain sets |
| Chained Sentry Beasts has a minor-settlement counterpart, Fortified Entries | garrison chain sets |
| Spy Nests is tier 4, so minor settlements stop at Deep Burrows | building levels |
| Equipment Warpforge and Warp-Turbine Plant need tier 5, so they can only go in a capital | building levels |
| Breeding Pit and Scrap Heap stop at tier 3; Reactor, Temple and Sentry Beasts reach tier 5 | building levels |

Unverified: whether the port occupies one of the slots the main building unlocks. The planner assumes
it does (`PORT_TAKES_A_SLOT`).

```
python -X utf8 -m assist.buildplan        # demo on example provinces
python -X utf8 tests/test_buildplan.py    # rule checks
```

## Running the assistant

```
run_assistant.bat                        # the same as the next line, from a double-click
python -X utf8 -m assist.runner          # window + overlay + loop; acts at every new turn
python -X utf8 -m assist.runner --once   # run the automations once now (no turn or idle check)
python -X utf8 -m assist.tech status     # research idle or running (screen only)
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

The no-build rule: a province is blocked when a faction the player is at war with holds a region in it,
or when it shares a border with a province where such a faction holds a region.

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

Runs at turn start for armies ticked in the window, after the building step: building upgrades (in provinces
not next to an enemy at war) take precedence over refilling armies, so the builder recruits with what is left. Per army:

1. Disband units not in the template, but only once the army stands in a province that can recruit its
   missing units locally (player rule: a stripped lord on the march gets attacked). Contiguous cards: click
   the first, Shift-click the last. Scattered cards: Ctrl-click. Heroes one at a time, because the game leaves
   embedded heroes out of a group disband. The clicked cards are checked in memory (unit card +0x1B8 is 2
   when selected; Shift-range members are not flagged), and what was disbanded is verified in memory.
2. If the army stands in an eligible province, queue the missing units from the **local** recruitment pool
   only (`local1/<unit>_recruitable`), never the global pool, which costs far more. Each click is confirmed by
   the treasury going down; when it stops going down, local capacity or gold has run out and the rest waits
   for later turns. The local pool is a horizontal list that scrolls: a card past the `list_clip` window
   still reads as visible but its centre can be off screen (the click lands on the map), so each card is
   first wheeled into view inside its `list_clip` (one notch = about 82 px). A Warlock Engineer never decides where the army goes (player rule): when the army has none and
   none is free or already walking to it, one is recruited as soon as the faction-wide cap allows, at the
   settlement nearest the army that can recruit one (settlement > `button_agents` > engineer tab > first
   candidate > confirm), and it walks to wherever the army is, re-ordered every turn until it joins. The cap
   rises +2 per Verminlord Warpseer with Inscrutable Genius; while it is full the widget says so. Heroes are
   never disbanded automatically.
3. Otherwise order the army to the closest eligible province: fewest region hops over the land adjacency
   graph, ties broken by straight-line distance, preferring provinces that cover more of the missing units.
   Re-evaluated every turn, so a province that becomes eligible mid-march takes over if it is closer.
   The order is a right-click on the settlement's nameplate component after panning the camera to it.
4. Walk free Warlock Engineers into the army: double-click the hero's row, pan until the lord's flag
   component (`label_<lord id>`) is on screen, right-click it, take the Hero Actions card.

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

The queued chain itself was not found: re-targeting it changes only T+0x28/T+0x30, nothing else in T (first
0x1000 bytes), the faction (0x3000 bytes) or the entries. The open panel shows it instead (below).

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
