"""Internal data contract, not an official MCP response schema."""

import hashlib
import json
import random


class Invalid(ValueError):
    """Unusable or incomplete evidence. Messages never include input values."""


def digest(value):
    data = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":"))
    return hashlib.sha256(data.encode()).hexdigest()


def integer(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise Invalid("expected nonnegative integer")
    return value


def required_text(value):
    if not isinstance(value, str) or not value.strip():
        raise Invalid("missing text evidence")
    return value


def cart_key(cart):
    if not isinstance(cart, list) or not cart:
        raise Invalid("missing cart")
    rows = {}
    for line in cart:
        key = (required_text(line.get("sku")), required_text(line.get("variant")))
        required_text(line.get("name"))
        if key in rows:
            raise Invalid("duplicate cart line; normalize quantities first")
        rows[key] = integer(line.get("quantity"), 1)
    return rows


def context(quote):
    return tuple(required_text(quote.get(k)) for k in
                 ("store", "mode", "fulfillment_ref", "time_slot", "currency"))


def validate_quote(quote, now):
    if not isinstance(quote, dict):
        raise Invalid("missing quote")
    integer(now)
    if quote.get("source") not in ("tool", "fixture"):
        raise Invalid("unrecognized source")
    if quote.get("tool") != "calculate-price":
        raise Invalid("quote must come from calculate-price")
    required_text(quote.get("response_ref"))
    required_text(quote.get("store_name"))
    context(quote)
    if quote["currency"] != "CNY":
        raise Invalid("unsupported currency")
    cart_key(quote.get("cart"))
    start = integer(quote.get("observed_at"))
    end = integer(quote.get("expires_at"))
    if not start <= now < end or end - start > 300:
        raise Invalid("quote expired or invalid freshness window")
    amounts = [integer(quote.get(k)) for k in
               ("subtotal", "delivery_fee", "other_fees", "discount", "total")]
    subtotal, delivery, other, discount, total = amounts
    if subtotal + delivery + other - discount != total:
        raise Invalid("inconsistent total")
    coupons = quote.get("coupons")
    if (not isinstance(coupons, list) or
            any(not isinstance(c, str) or not c.strip() for c in coupons) or
            len(set(coupons)) != len(coupons)):
        raise Invalid("missing or invalid applied coupons")
    return quote


def _pair(before, after, now):
    validate_quote(before, now)
    validate_quote(after, now)
    if context(before) != context(after):
        raise Invalid("store or fulfillment context differs")
    if before["source"] != after["source"]:
        raise Invalid("mixed fixture and live sources")
    if abs(before["observed_at"] - after["observed_at"]) > 120:
        raise Invalid("quotes observed too far apart")


def compare(before, after, now, kind="same_cart", evidence=None):
    """Return spend delta only when all needed evidence is valid."""
    try:
        _pair(before, after, now)
        old, new = cart_key(before["cart"]), cart_key(after["cart"])
        if kind == "same_cart":
            if old != new:
                raise Invalid("same-cart comparison requires identical products")
        elif kind == "top_up":
            if old == new or any(new.get(k, 0) < v for k, v in old.items()):
                raise Invalid("top-up must strictly preserve and extend original cart")
            if not isinstance(evidence, dict):
                raise Invalid("missing official coupon conditions")
            if evidence.get("source") != before["source"]:
                raise Invalid("coupon evidence source differs")
            if evidence.get("tool") not in ("query-store-coupons", "query-my-coupons",
                                            "available-coupons"):
                raise Invalid("missing official coupon tool evidence")
            required_text(evidence.get("response_ref"))
            required_text(evidence.get("conditions"))
            integer(evidence.get("threshold"), 1)
            if evidence.get("conditions_known") is not True:
                raise Invalid("coupon applicability is unknown")
            if type(evidence.get("before_eligible")) is not bool:
                raise Invalid("original cart eligibility is unknown")
            if evidence.get("after_eligible") is not True:
                raise Invalid("top-up eligibility is not confirmed")
            if (evidence.get("before_quote") != digest(before) or
                    evidence.get("after_quote") != digest(after)):
                raise Invalid("coupon evidence is not bound to these quotes")
            if required_text(evidence.get("coupon")) not in after["coupons"]:
                raise Invalid("target coupon was not applied")
        else:
            raise Invalid("unsupported comparison kind")
    except (Invalid, KeyError, TypeError, AttributeError) as exc:
        reason = str(exc) if isinstance(exc, Invalid) else "malformed evidence"
        return {"status": "unknown", "reason": reason, "delta": None}
    delta = after["total"] - before["total"]
    verdict = "not_worth_topping_up" if kind == "top_up" and delta > 0 else (
        "higher_spend" if delta > 0 else "lower_spend" if delta < 0 else "same_spend")
    return {"status": "known", "verdict": verdict, "delta": delta,
            "before_total": before["total"], "after_total": after["total"],
            "source": before["source"], "includes_all_fees": True}


def nutrition_value(candidate, field):
    nutrition = candidate.get("nutrition")
    if not isinstance(nutrition, dict):
        return None
    quote = candidate["quote"]
    if (nutrition.get("source") != quote["source"] or
            nutrition.get("tool") != "list-nutrition-foods" or
            not isinstance(nutrition.get("response_ref"), str) or
            not nutrition["response_ref"].strip() or
            nutrition.get("cart_digest") != digest(quote["cart"])):
        return None
    value = nutrition.get(field)
    return value if type(value) is int and value >= 0 else None


def recommend(candidates, now, preference=None, target_kcal=None, budget=None, seed=None):
    """Rank prefiltered feasible carts. No menu generation or medical inference."""
    preference = preference or {"likes": [], "dislikes": []}
    if target_kcal is not None:
        integer(target_kcal, 1)
    if budget is not None:
        integer(budget)
    valid, excluded = [], 0
    base = None
    for item in candidates:
        try:
            q = validate_quote(item.get("quote"), now)
            required_text(item.get("id"))
            if item.get("constraints_checked") is not True:
                raise Invalid("hard constraints not checked")
            if budget is not None and q["total"] > budget:
                raise Invalid("over budget")
            key = (context(q), q["source"])
            if base is not None and base != key:
                raise Invalid("candidate context differs")
            tags = item.get("tags", [])
            if not isinstance(tags, list) or any(not isinstance(t, str) for t in tags):
                raise Invalid("invalid taste tags")
            score = len(set(tags) & set(preference.get("likes", [])))
            score -= len(set(tags) & set(preference.get("dislikes", [])))
            valid.append({"id": item["id"], "total": q["total"],
                          "kcal": nutrition_value(item, "kcal"),
                          "protein_g": nutrition_value(item, "protein_g"),
                          "taste_score": score, "source": q["source"]})
            base = key
        except (Invalid, KeyError, TypeError, AttributeError):
            excluded += 1
    wallet = sorted(valid, key=lambda v: (v["total"], v["id"]))
    taste = sorted(valid, key=lambda v: (-v["taste_score"], v["total"], v["id"]))
    nutrition = None if target_kcal is None else sorted(
        [v for v in valid if v["kcal"] is not None],
        key=lambda v: (abs(v["kcal"] - target_kcal), v["total"], v["id"]))
    return {"wallet": wallet, "nutrition": nutrition, "taste": taste,
            "random": random.Random(seed).choice(wallet) if wallet else None,
            "excluded": excluded, "nutrition_unknown": [v["id"] for v in valid
                                                         if v["kcal"] is None],
            "nutrition_rule": "distance_to_user_kcal_target" if target_kcal else "unknown"}
