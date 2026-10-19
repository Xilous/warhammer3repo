# automated-jay: rules for working on the assistant

## State and detection come from memory (player rule, 2026-10-18)

Every piece of game state the assistant decides on is read from the game's memory: the campaign model and the
objects it points at. Never from screenshots, pixels, OCR or template matching, and not from what a UI panel
happens to display.

- **Game state = the campaign model in memory.** Factions, regions, owners, wars, buildings, armies, characters,
  treasury, turn, pooled resources (Warpstone, food), research, skills, Masterplans (plans, Risk, Alarm, loot,
  cards, Underlings, cooldowns, Secrets owned) and so on. Readers live in `bot/sensor/` (`memory.py`, `world.py`,
  `turn.py`, `camera.py` ...); add new ones there. Offsets are decoded from the exe (Lua binding tables and Cco
  context functions -> native function -> Ghidra decompile, see `tools/re_bindings.py`, `../re/NOTES.md`) and
  written down in the reader's docstring with the game build they were checked on.
- **The UI tree (read from memory, `bot/sensor/ui.py`) is only for acting on the UI**: finding the component to
  click, confirming a click took effect (a panel opened or closed, a button's state changed), and seeing which
  panels and popups are open (those exist only in the UI). It is never the source of a game value the logic
  decides on (a number, a count, a lock, a cooldown, who is free) when that value lives in the model.
- **No screenshots.** No pixel colours, image templates, OCR or screen grabs in the assistant (`assist/`, `bot/`).
  `assist/tech.py run_screen` is an old manual-only leftover: not used by any step, not to be copied.
- **A value not decoded yet** is reverse-engineered first and then read from memory. Reading it from a panel is
  at most a stop-gap: say so in the code ("UI stop-gap: <what>, memory reader pending") and to the player, and
  replace it.
- **Verify against the live game** before relying on a new offset (compare with what the game shows), and keep
  that check repeatable (a test or a `--selftest` line where possible).

## Single player is played as multiplayer (player rule, 2026-10-18)

The player uses single-player campaigns to practise multiplayer with the assistant on. So the assistant plays a
single-player campaign as a multiplayer one as far as it can:

- Nothing it plans or buys may rely on something only single player has: story missions and their rewards,
  story-locked buildings (the Morskittar Engine at Zhufbar is skipped in `strategy/settlements.json`), story-only
  unlocks or items. If a feature exists in both but unlocks differently (Masterplans, Underlings), the assistant
  reads what is unlocked from memory and never assumes the single-player route.
- When you add a plan, a shop order or a priority, check that it works the same in multiplayer; if it does not,
  leave it out or make it optional, and say so.

## Other standing rules
- Player decisions are recorded where they apply (strategy/*.json `_doc` notes, code comments) with the date.
- Kill-Stab Masterplans are the player's: never started, completed or abandoned by the assistant.
