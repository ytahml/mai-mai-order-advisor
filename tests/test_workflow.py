import copy
import unittest

from copilot.__main__ import fixture
from copilot.core import Invalid, digest
from copilot.workflow import GateError, initial, transition


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.data = fixture()
        self.now = self.data["now"]
        self.quote = self.data["original"]
        self.payload = digest({"simulation": True, "cart": self.quote["cart"]})
        self.state = initial()

    def step(self, action, **kwargs):
        result = transition(self.state, dict(action=action, **kwargs), self.now)
        self.state = result["state"]
        return result

    def ready(self):
        offer = self.step("offer_order", quote=self.quote, payload_digest=self.payload)
        self.step("confirm_order", confirmation=offer["prompt"])

    def sent(self):
        self.ready()
        return self.step("dispatch_order", quote=self.quote, payload_digest=self.payload)

    def verify(self, **overrides):
        event = {"source": "fixture", "tool": "query-order", "response_ref": "fixture-read",
                 "order_ref": "fixture-order", "matches_summary": True,
                 "total": self.quote["total"], "status": "pending_payment"}
        event.update(overrides)
        return self.step("verified", **event)

    def test_browsing_cannot_write(self):
        for action in ("confirm_coupons", "confirm_order", "dispatch_order", "create_result"):
            with self.subTest(action=action), self.assertRaises(GateError):
                self.step(action)
        self.assertEqual(self.state, initial())

    def test_pickup_missing_fees_cannot_offer_order(self):
        quote = dict(self.quote, mode="pickup", delivery_fee=0, other_fees=0,
                     total=self.quote["subtotal"] - self.quote["discount"])
        for field in ("delivery_fee", "other_fees"):
            with self.subTest(field=field):
                incomplete = dict(quote)
                del incomplete[field]
                with self.assertRaises(Invalid):
                    self.step("offer_order", quote=incomplete, payload_digest=self.payload)
                self.assertEqual(self.state, initial())

    def test_all_coupon_confirmation_and_forced_refresh(self):
        offer = self.step("offer_coupons", source="fixture")
        with self.assertRaises(GateError):
            self.step("confirm_coupons", confirmation="领一张")
        result = self.step("confirm_coupons", confirmation=offer["prompt"])
        self.assertEqual(result["intent"]["scope"], "绑定全部当前可领券")
        self.assertFalse(result["intent"]["retry"])
        with self.assertRaises(GateError):
            self.step("confirm_coupons", confirmation=offer["prompt"])
        self.step("coupon_result")
        with self.assertRaises(GateError):
            self.step("offer_order", quote=self.quote, payload_digest=self.payload)
        self.now += 1
        fresh = dict(self.quote, observed_at=self.now, expires_at=self.now + 300,
                     response_ref="fixture-fresh-price")
        self.step("refreshed", wallet_response_ref="fixture-wallet", wallet_observed_at=self.now,
                  quote=fresh)
        self.assertEqual(self.state["phase"], "browsing")

    def test_pre_claim_wallet_or_quote_cannot_refresh(self):
        offer = self.step("offer_coupons", source="fixture")
        self.step("confirm_coupons", confirmation=offer["prompt"])
        self.now += 10
        self.step("coupon_result")
        with self.assertRaises(GateError):
            self.step("refreshed", wallet_response_ref="fixture-old", wallet_observed_at=self.now - 10,
                      quote=self.quote)

    def test_coupon_confirmation_expires(self):
        offer = self.step("offer_coupons", source="fixture")
        self.now += 300
        with self.assertRaises(GateError):
            self.step("confirm_coupons", confirmation=offer["prompt"])

    def test_same_second_pre_claim_quote_cannot_refresh(self):
        offer = self.step("offer_coupons", source="fixture")
        self.step("confirm_coupons", confirmation=offer["prompt"])
        self.step("coupon_result")
        checkpoint = copy.deepcopy(self.state)
        with self.assertRaises(GateError):
            self.step("refreshed", wallet_response_ref="fixture-wallet-after",
                      wallet_observed_at=self.now, quote=self.quote)
        self.assertEqual(self.state, checkpoint)
        with self.assertRaises(GateError):
            self.step("offer_order", quote=self.quote, payload_digest=self.payload)

    def test_same_second_refresh_requires_later_read_even_with_new_references(self):
        offer = self.step("offer_coupons", source="fixture")
        self.step("confirm_coupons", confirmation=offer["prompt"])
        self.step("coupon_result")
        completed_at = self.now
        self.now += 1
        checkpoint = copy.deepcopy(self.state)
        for wallet_time, quote_time in ((completed_at, completed_at),
                                        (completed_at, self.now), (self.now, completed_at)):
            with self.subTest(wallet_time=wallet_time, quote_time=quote_time):
                self.state = copy.deepcopy(checkpoint)
                fresh = dict(self.quote, observed_at=quote_time, expires_at=quote_time + 300,
                             response_ref="fixture-fresh-price")
                with self.assertRaises(GateError):
                    self.step("refreshed", wallet_response_ref="fixture-new-wallet",
                              wallet_observed_at=wallet_time, quote=fresh)
                self.assertEqual(self.state, checkpoint)

    def test_old_quote_cannot_return_after_refresh_or_reset(self):
        offer = self.step("offer_coupons", source="fixture")
        self.step("confirm_coupons", confirmation=offer["prompt"])
        self.now += 10
        self.step("coupon_result")
        self.now += 1
        fresh = dict(self.quote, observed_at=self.now, expires_at=self.now + 300,
                     response_ref="fixture-fresh-price")
        self.step("refreshed", wallet_response_ref="fixture-wallet", wallet_observed_at=self.now,
                  quote=fresh)
        self.step("reset")
        with self.assertRaises(GateError):
            self.step("offer_order", quote=self.quote, payload_digest=self.payload)
        self.step("offer_order", quote=fresh, payload_digest=self.payload)

    def test_order_needs_specific_confirmation(self):
        self.step("offer_order", quote=self.quote, payload_digest=self.payload)
        with self.assertRaises(GateError):
            self.step("confirm_order", confirmation="就它吧")

    def test_every_quote_field_and_actual_parameters_bound(self):
        self.ready()
        for field, value in (("store", "fixture-other"), ("mode", "pickup"),
                             ("fulfillment_ref", "fixture-other"), ("coupons", ["fixture-other"]),
                             ("store_name", "changed")):
            with self.subTest(field=field), self.assertRaises(GateError):
                changed = dict(self.quote, **{field: value})
                self.step("dispatch_order", quote=changed, payload_digest=self.payload)
        with self.assertRaises(GateError):
            self.step("dispatch_order", quote=self.quote, payload_digest=digest({"changed": True}))

    def test_confirmation_invalidated_on_new_offer(self):
        old = self.step("offer_order", quote=self.quote, payload_digest=self.payload)
        self.step("offer_order", quote=self.quote, payload_digest=self.payload)
        with self.assertRaises(GateError):
            self.step("confirm_order", confirmation=old["prompt"])

    def test_expired_quote_never_dispatched(self):
        self.ready()
        self.now += 300
        with self.assertRaises(Invalid):
            self.step("dispatch_order", quote=self.quote, payload_digest=self.payload)

    def test_single_dispatch_and_matching_readback(self):
        result = self.sent()
        self.assertEqual(result["intent"]["tool"], "create-order")
        with self.assertRaises(GateError):
            self.step("dispatch_order", quote=self.quote, payload_digest=self.payload)
        readback = self.step("create_result", order_ref="fixture-order")
        self.assertEqual(readback["intent"]["tool"], "query-order")
        result = self.verify()
        self.assertTrue(result["may_show_payment_link"])
        self.assertEqual(self.state["phase"], "pending_payment")

    def test_timeout_cannot_resend_or_reset(self):
        self.sent()
        result = self.step("create_result")
        self.assertIsNone(result["intent"])
        for action in ("reset", "offer_order", "dispatch_order"):
            with self.assertRaises(GateError):
                self.step(action, quote=self.quote, payload_digest=self.payload)
        self.assertFalse(self.verify()["may_show_payment_link"])

    def test_mismatched_readback_does_not_show_link(self):
        self.sent()
        self.step("create_result", order_ref="fixture-order")
        checkpoint = copy.deepcopy(self.state)
        for field, value in (("order_ref", "fixture-other"), ("total", 1),
                             ("matches_summary", False), ("source", "tool"),
                             ("tool", "create-order"), ("status", "cancelled")):
            self.state = copy.deepcopy(checkpoint)
            result = self.verify(**{field: value})
            self.assertFalse(result["may_show_payment_link"])
            self.assertEqual(self.state["phase"], "status_unknown")

    def test_paid_is_not_pending_payment(self):
        self.sent()
        self.step("create_result", order_ref="fixture-order")
        self.assertFalse(self.verify(status="paid")["may_show_payment_link"])
        self.assertEqual(self.state["phase"], "paid")

    def test_malformed_readback_reference_does_not_show_link(self):
        self.sent()
        self.step("create_result", order_ref="fixture-order")
        checkpoint = copy.deepcopy(self.state)
        for value in (123, True, ["fixture-ref"], {}, "", "   ", None):
            with self.subTest(value=value):
                self.state = copy.deepcopy(checkpoint)
                self.assertFalse(self.verify(response_ref=value)["may_show_payment_link"])
                self.assertEqual(self.state["phase"], "status_unknown")

    def test_reset_revokes_unspent_confirmation(self):
        self.ready()
        self.step("reset")
        with self.assertRaises(GateError):
            self.step("dispatch_order", quote=self.quote, payload_digest=self.payload)

    def test_input_state_is_not_mutated(self):
        before = copy.deepcopy(self.state)
        transition(self.state, {"action": "offer_coupons", "source": "fixture"}, self.now)
        self.assertEqual(self.state, before)


if __name__ == "__main__":
    unittest.main()
