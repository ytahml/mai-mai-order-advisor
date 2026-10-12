"""Cooperative host-side confirmation protocol; no tool transport or disk state."""

from copy import deepcopy
import re

from .core import digest, integer, required_text, validate_quote


class GateError(ValueError):
    """A transition is not authorized; safe to display without input data."""


COUPON_SCOPE = "绑定全部当前可领券"
STATES = {"browsing", "coupon_confirmation", "coupon_in_flight", "refresh_required",
          "order_confirmation", "order_ready", "order_in_flight", "verify_required",
          "pending_payment", "paid", "status_unknown"}


def initial():
    return {"phase": "browsing", "revision": 0}


def _snapshot(quote, payload_digest, now):
    validate_quote(quote, now)
    if not isinstance(payload_digest, str) or not re.fullmatch(r"[a-f0-9]{64}", payload_digest):
        raise GateError("missing actual order parameters digest")
    return {"quote": deepcopy(quote), "payload_digest": payload_digest}


def transition(state, event, now):
    """Return new state and at most one intent. Host must retain newest state.

    Confirmation input is supplied ONLY from a new human turn by the host.
    States and intents are private, ephemeral data, not authenticated capabilities.
    """
    state = deepcopy(state)
    integer(now)
    phase = state.get("phase")
    action = event.get("action")
    fence = deepcopy(state.get("quote_fence"))
    if phase not in STATES or type(state.get("revision")) is not int:
        raise GateError("invalid state")
    result = {"intent": None}
    if action == "reset" and phase in ("browsing", "coupon_confirmation",
                                       "order_confirmation", "order_ready"):
        state = {"phase": "browsing", "revision": state["revision"]}
    elif action == "offer_coupons" and phase == "browsing":
        source = event.get("source")
        if source not in ("fixture", "tool"):
            raise GateError("missing source")
        # Revision ties consent to this offer, never to an earlier conversation.
        state.update(phase="coupon_confirmation", source=source, offered_at=now,
                     challenge=digest({"scope": COUPON_SCOPE, "source": source,
                                       "revision": state["revision"], "now": now}))
        result["prompt"] = "确认" + COUPON_SCOPE + ":" + state["challenge"]
    elif action == "confirm_coupons" and phase == "coupon_confirmation":
        expected = "确认" + COUPON_SCOPE + ":" + state["challenge"]
        if event.get("confirmation") != expected:
            raise GateError("explicit all-coupons confirmation required")
        if not 0 <= now - state["offered_at"] < 300:
            raise GateError("coupon confirmation expired")
        state["phase"] = "coupon_in_flight"
        result["intent"] = {"tool": "auto-bind-coupons", "source": state["source"],
                            "scope": COUPON_SCOPE, "retry": False}
    elif action == "coupon_result" and phase == "coupon_in_flight":
        # Success, error and uncertain timeout all invalidate earlier quotes.
        state["phase"] = "refresh_required"
        state["completed_at"] = now
    elif action == "refreshed" and phase == "refresh_required":
        required_text(event.get("wallet_response_ref"))
        wallet_time = integer(event.get("wallet_observed_at"))
        quote = validate_quote(event.get("quote"), now)
        if (quote["source"] != state["source"] or
                not state["completed_at"] <= wallet_time <= quote["observed_at"]):
            raise GateError("fresh wallet and quote required")
        state = {"phase": "browsing", "revision": state["revision"]}
        fence = {"observed_at": quote["observed_at"], "digest": digest(quote),
                 "source": quote["source"]}
    elif action == "offer_order" and phase in ("browsing", "order_confirmation", "order_ready"):
        snapshot = _snapshot(event.get("quote"), event.get("payload_digest"), now)
        quote = snapshot["quote"]
        if fence and (quote["source"] != fence["source"] or
                      quote["observed_at"] < fence["observed_at"] or
                      (quote["observed_at"] == fence["observed_at"] and
                       digest(quote) != fence["digest"])):
            raise GateError("order must use refreshed or newer quote")
        challenge = digest({"snapshot": snapshot, "revision": state["revision"]})
        state = {"phase": "order_confirmation", "revision": state["revision"],
                 "snapshot": snapshot, "challenge": challenge}
        result["summary"] = deepcopy(snapshot["quote"])
        result["prompt"] = "确认创建订单:" + challenge
    elif action == "confirm_order" and phase == "order_confirmation":
        validate_quote(state["snapshot"]["quote"], now)
        if event.get("confirmation") != "确认创建订单:" + state["challenge"]:
            raise GateError("specific order confirmation required")
        state["phase"] = "order_ready"
    elif action == "dispatch_order" and phase == "order_ready":
        current = _snapshot(event.get("quote"), event.get("payload_digest"), now)
        if current != state["snapshot"]:
            raise GateError("order changed; present and confirm a new summary")
        state["phase"] = "order_in_flight"
        result["intent"] = {"tool": "create-order", "source": current["quote"]["source"],
                            "payload_digest": current["payload_digest"], "retry": False}
    elif action == "create_result" and phase == "order_in_flight":
        state["phase"] = "verify_required"
        state["order_ref"] = event.get("order_ref")
        # No order identifier after a timeout means manual reconciliation, no resend.
        if state["order_ref"]:
            required_text(state["order_ref"])
            result["intent"] = {"tool": "query-order", "order_ref": state["order_ref"],
                                "source": state["snapshot"]["quote"]["source"]}
    elif action == "verified" and phase == "verify_required":
        quote = state["snapshot"]["quote"]
        matched = (bool(state.get("order_ref")) and
                   event.get("order_ref") == state["order_ref"] and
                   event.get("source") == quote["source"] and
                   event.get("tool") == "query-order" and
                   isinstance(event.get("response_ref"), str) and
                   bool(event["response_ref"].strip()) and
                   event.get("matches_summary") is True and
                   type(event.get("total")) is int and event["total"] == quote["total"])
        status = event.get("status")
        state["phase"] = status if matched and status in ("pending_payment", "paid") else "status_unknown"
        # The host displays the original tool-returned link privately after this flag.
        result["may_show_payment_link"] = state["phase"] == "pending_payment"
    else:
        raise GateError("transition not allowed; no write authorized")
    if fence:
        state["quote_fence"] = fence
    state["revision"] += 1
    result["state"] = state
    return result
