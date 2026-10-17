# legacy/ — old code, do not run

Everything in this folder is the project's first proof of concept and early drafts that the assistant no longer
uses. It was moved here on 2026-10-16 so it cannot be started by accident. Nothing in `assist/`, `bot/`, `tools/`
or `tests/` imports it. It is kept for reference only; the folder layout mirrors where each file used to live.

**Do not run anything here.** `run.py` was a bot that **ends turns** in the loaded campaign (Shift+Enter, once per
turn) as soon as it was started or even imported. It now refuses to start, and its imports no longer resolve.

| File | What it was | Replaced by |
|---|---|---|
| `run.py` | entry point of the turn-ending bot (`python run.py --turns N`) | `run_assistant.bat` / `python -X utf8 -m assist.runner` |
| `bot/loop.py` | read memory -> ask the rulebook -> end the turn -> wait for the next turn | `assist/runner.py` |
| `bot/brain/rulebook.py` | the PoC "rulebook": one rule, end the turn | the turn-start steps in `assist/` and `strategy/*.json` |
| `bot/hands/osinput.py` | keyboard/mouse wrapper with a foreground check | `tools/ui.py` + `bot/focus.py` (`game_focus`, `InputAborted`) |
| `bot/sensor/screen.py` | screenshot fingerprint used by the loop as a stuck detector | memory + UI-tree reads (`bot/sensor/ui.py`), window capture in `tools/ui.py` |
| `bot/sensor/base.py` | unused `Sensor` protocol | - |
| `assist/army_step.py` | first army step (walked free heroes into ticked armies, only reported the rest) | `assist/army_builder.py` |
| `assist/widget.py` | stand-alone always-on-top status widget | `assist/app.py` (window + overlay); only `COLORS` stayed in `assist/widget.py` |
| `assist/slots.py` | read building slots by matching screenshots against the game's building icons | the settlement panel's UI tree (`assist/build.py`, 2026-10-16) |

If you ever need one of these again, copy it back to its old path and check its imports first. Never restore
`run.py` on a campaign you care about: End Turn also triggers the game's autosave.
