"""Usage: python3 -m copilot demo | compare | recommend | transition.

JSON commands read stdin and write stdout. They never save inputs or call MCP.
"""

import json
from pathlib import Path
import sys
import time

from .core import compare, digest, recommend
from .workflow import initial, transition


def fixture():
    path = Path(__file__).resolve().parent.parent / "fixtures" / "demo.json"
    return json.loads(path.read_text(encoding="utf-8"))


def top_up_evidence(data, after):
    evidence = dict(data["coupon_evidence"])
    evidence.update(before_quote=digest(data["original"]), after_quote=digest(after))
    return evidence


def demo():
    data = fixture()
    now = data["now"]
    before = data["original"]
    output = {"notice": "全部为模拟数据；未连接 MCP、未领券、未创建真实订单。",
              "unit": "CNY 整数分", "recommendations": recommend(
                  data["candidates"], now, {"likes": ["鸡肉"], "dislikes": []},
                  target_kcal=600, seed=1024),
              "top_up_loss": compare(before, data["top_up_loss"], now, "top_up",
                                     top_up_evidence(data, data["top_up_loss"])),
              "top_up_saving": compare(before, data["top_up_saving"], now, "top_up",
                                       top_up_evidence(data, data["top_up_saving"])),
              "missing_conditions": compare(before, data["top_up_loss"], now, "top_up")}
    state = initial()
    trace = []

    def step(event):
        nonlocal state
        result = transition(state, event, now)
        state = result["state"]
        trace.append({"event": event["action"], "phase": state["phase"],
                      "intent": result.get("intent")})
        return result

    offer = step({"action": "offer_coupons", "source": "fixture"})
    step({"action": "confirm_coupons", "confirmation": offer["prompt"]})
    step({"action": "coupon_result"})
    step({"action": "refreshed", "wallet_response_ref": "fixture-wallet-refresh",
          "wallet_observed_at": now, "quote": before})
    payload = digest({"simulation": True, "cart": before["cart"]})
    offer = step({"action": "offer_order", "quote": before, "payload_digest": payload})
    step({"action": "confirm_order", "confirmation": offer["prompt"]})
    step({"action": "dispatch_order", "quote": before, "payload_digest": payload})
    step({"action": "create_result", "order_ref": "fixture-order"})
    verified = step({"action": "verified", "source": "fixture", "tool": "query-order",
                     "response_ref": "fixture-order-readback", "order_ref": "fixture-order",
                     "matches_summary": True, "total": before["total"],
                     "status": "pending_payment"})
    output["simulated_flow"] = trace
    output["may_show_simulated_link"] = verified["may_show_payment_link"]
    output["payment_link"] = "https://example.invalid/fixture-payment-not-real"
    return output


def main():
    command = sys.argv[1] if len(sys.argv) == 2 else "help"
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
                                   data.get("target_kcal"), data.get("budget"))
            else:
                result = transition(data.get("state", initial()), data["event"], now)
        else:
            print(__doc__)
            return 0 if command == "help" else 2
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ValueError, TypeError, KeyError, AttributeError):
        # Never echo malformed data, tool payloads, credentials or tracebacks.
        print(json.dumps({"error": "invalid input or transition; no action authorized"}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
