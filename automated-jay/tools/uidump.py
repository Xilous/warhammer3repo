"""Print part of the live UI tree with screen rectangles.

  python -X utf8 -m tools.uidump                       # top two levels
  python -X utf8 -m tools.uidump settlement_panel 4    # subtree under the first component with that id, 4 levels
  python -X utf8 -m tools.uidump --grep slot           # every visible component whose id contains 'slot'
"""
from __future__ import annotations
import sys

from bot.sensor.ui import UI


def main() -> int:
    ui = UI()
    root = ui.find_root()
    args = sys.argv[1:]
    if args[:1] == ["--grep"]:
        pat = args[1].lower()
        for c, ids in ui.walk():
            if pat in ids[-1].lower():
                k = ui.comp(c)
                print(f"{'/'.join(ids[-4:]):90s} {k.x:7.0f} {k.y:6.0f} {k.w:6.0f} {k.h:5.0f}")
        return 0
    start, depth = root, 2
    if args:
        for c, ids in ui.walk():
            if ids[-1] == args[0]:
                start = c
                break
        depth = int(args[1]) if len(args) > 1 else 3
    base = None
    for c, ids in ui.walk(start):
        if base is None:
            base = len(ids)
        d = len(ids) - base
        if d > depth:
            continue
        k = ui.comp(c)
        print(f"{'  ' * d}{ids[-1]:60s} {k.x:7.0f} {k.y:6.0f} {k.w:6.0f} {k.h:5.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
