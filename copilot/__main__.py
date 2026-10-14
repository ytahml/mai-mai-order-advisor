"""Usage: python3 -m copilot <command>

Commands:
  demo        Run synthetic recommendations, price comparisons and order flow.
  compare     Compare two normalized quotes from stdin JSON.
  recommend   Rank normalized candidates from stdin JSON.
  transition  Advance a confirmation state using stdin JSON.

Use help, -h or --help to show this message.
JSON commands write stdout; they never save inputs or call MCP.
Input contracts: references/contracts.md
"""

import json
import sys
import time

from .core import compare, recommend
from .demo import demo
from .workflow import initial, transition


def main():
    args = sys.argv[1:]
    if not args or args in (["help"], ["-h"], ["--help"]):
        print(__doc__)
        return 0
    if len(args) != 1 or args[0] not in ("demo", "compare", "recommend", "transition"):
        print(__doc__, file=sys.stderr)
        return 2
    command = args[0]
    try:
        if command == "demo":
            result = demo()
        elif command in ("compare", "recommend", "transition"):
            data = json.load(sys.stdin)
            now = int(time.time())
            if command == "compare":
                result = compare(data.get("before"), data.get("after"), now,
                                 data.get("kind", "same_cart"), data.get("evidence"))
            elif command == "recommend":
                result = recommend(data["candidates"], now, data.get("preference"),
                                   data.get("target_kcal"), data.get("budget"),
                                   exclude_ids=data.get("exclude_ids"))
            else:
                result = transition(data.get("state", initial()), data["event"], now)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ValueError, TypeError, KeyError, AttributeError):
        # Never echo malformed data, tool payloads, credentials or tracebacks.
        print(json.dumps({"error": "invalid input or transition; no action authorized"}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
