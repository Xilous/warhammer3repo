"""LEGACY - DO NOT RUN. The original proof-of-concept bot: it ENDS TURNS in the loaded campaign.

Was: python run.py --turns 10 [--dry-run]   (read state -> rulebook -> Shift+Enter, once per turn)

Moved here from the project root on 2026-10-16. The modules it used (bot/loop.py, bot/brain/, bot/hands/,
bot/sensor/screen.py) now live in legacy/bot/, so the import below fails even if this file is started; on top of
that, starting it only prints a refusal. Importing it does nothing. The assistant is started with
run_assistant.bat (python -X utf8 -m assist.runner). See legacy/README.md.
"""
import sys


def main() -> None:
    """The original entry point, kept for reference only. Never called."""
    import argparse
    from bot.loop import run          # bot/loop.py now lives in legacy/bot/loop.py

    p = argparse.ArgumentParser()
    p.add_argument("--turns", type=int, default=1)
    p.add_argument("--dry-run", action="store_true", help="read state and decide, but send no input")
    a = p.parse_args()
    run(a.turns, a.dry_run)


if __name__ == "__main__":
    sys.exit("legacy/run.py is the old turn-ending bot and is disabled.\n"
             "Start the assistant with run_assistant.bat (python -X utf8 -m assist.runner).")
