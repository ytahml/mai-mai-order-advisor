"""Synthetic examples only; never connects to MCP or creates real orders."""

import json
from pathlib import Path

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
    output["recommendations_after_feedback"] = recommend(
        data["candidates"], now, {"likes": ["鸡肉"], "dislikes": ["牛肉"]},
        target_kcal=600, budget=4000, seed=1024, exclude_ids=["C"])
    output["missing_fees"] = compare(before, dict(data["top_up_loss"], delivery_fee=None,
                                                other_fees=None), now, "top_up")
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
    now += 1
    refreshed_quote = dict(before, observed_at=now, expires_at=now + 300,
                           response_ref="fixture-price-refresh")
    step({"action": "refreshed", "wallet_response_ref": "fixture-wallet-refresh",
          "wallet_observed_at": now, "quote": refreshed_quote})
    payload = digest({"simulation": True, "cart": refreshed_quote["cart"]})
    offer = step({"action": "offer_order", "quote": refreshed_quote, "payload_digest": payload})
    step({"action": "confirm_order", "confirmation": offer["prompt"]})
    step({"action": "dispatch_order", "quote": refreshed_quote, "payload_digest": payload})
    step({"action": "create_result", "order_ref": "fixture-order"})
    verified = step({"action": "verified", "source": "fixture", "tool": "query-order",
                     "response_ref": "fixture-order-readback", "order_ref": "fixture-order",
                     "matches_summary": True, "total": refreshed_quote["total"],
                     "status": "pending_payment"})
    output["simulated_flow"] = trace
    output["may_show_simulated_link"] = verified["may_show_payment_link"]
    output["payment_link"] = "https://example.invalid/fixture-payment-not-real"
    return output
