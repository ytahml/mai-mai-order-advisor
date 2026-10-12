import copy
import unittest

from copilot.__main__ import fixture, top_up_evidence
from copilot.core import compare, digest, recommend


class PricingTests(unittest.TestCase):
    def setUp(self):
        self.data = fixture()
        self.now = self.data["now"]
        self.before = self.data["original"]
        self.after = self.data["top_up_loss"]

    def top_up(self, after=None, evidence=None):
        after = after or self.after
        evidence = evidence if evidence is not None else top_up_evidence(self.data, after)
        return compare(self.before, after, self.now, "top_up", evidence)

    def test_top_up_loses_money_despite_discount(self):
        result = self.top_up()
        self.assertEqual((result["verdict"], result["delta"]), ("not_worth_topping_up", 200))

    def test_delivery_fee_changes_verdict(self):
        result = self.top_up(self.data["top_up_saving"])
        self.assertEqual((result["verdict"], result["delta"]), ("lower_spend", -400))

    def test_equal_spend(self):
        self.after.update(discount=1200, total=3600)
        self.assertEqual(self.top_up()["verdict"], "same_spend")

    def test_missing_conditions_are_unknown(self):
        result = compare(self.before, self.after, self.now, "top_up")
        self.assertEqual((result["status"], result["delta"]), ("unknown", None))

    def test_incomplete_or_inapplicable_evidence(self):
        evidence = top_up_evidence(self.data, self.after)
        cases = {"source": "tool", "tool": "campaign-calendar", "threshold": None,
                 "conditions": "", "conditions_known": False, "before_eligible": None,
                 "after_eligible": False, "coupon": "not-applied", "before_quote": "old",
                 "after_quote": "old", "response_ref": ""}
        for field, value in cases.items():
            with self.subTest(field=field):
                invalid = dict(evidence, **{field: value})
                self.assertEqual(self.top_up(evidence=invalid)["status"], "unknown")

    def test_missing_or_invalid_amounts(self):
        original = copy.deepcopy(self.after)
        for field in ("subtotal", "delivery_fee", "other_fees", "discount", "total"):
            for value in (None, -1, True, 1.5):
                with self.subTest(field=field, value=value):
                    self.after = dict(original, **{field: value})
                    self.assertEqual(self.top_up()["status"], "unknown")

    def test_total_must_reconcile(self):
        self.after["total"] += 1
        self.assertEqual(self.top_up()["status"], "unknown")

    def test_incomparable_contexts_and_sources(self):
        original = copy.deepcopy(self.after)
        for field in ("store", "mode", "fulfillment_ref", "time_slot", "currency", "source"):
            with self.subTest(field=field):
                self.after = dict(original, **{field: "different"})
                self.assertEqual(self.top_up()["status"], "unknown")

    def test_stale_future_or_distant_quotes(self):
        original = copy.deepcopy(self.after)
        cases = [{"expires_at": self.now}, {"observed_at": self.now + 1},
                 {"expires_at": self.now + 301}, {"observed_at": self.now - 121,
                                                        "expires_at": self.now + 100}]
        for case in cases:
            self.after = dict(original, **case)
            self.assertEqual(self.top_up()["status"], "unknown")

    def test_original_cart_cannot_be_replaced(self):
        self.after["cart"][0]["variant"] = "changed"
        self.assertEqual(self.top_up()["status"], "unknown")

    def test_duplicate_lines_and_boolean_quantity_are_invalid(self):
        self.after["cart"].append(copy.deepcopy(self.after["cart"][0]))
        self.assertEqual(self.top_up()["status"], "unknown")
        self.after["cart"].pop()
        self.after["cart"][0]["quantity"] = True
        self.assertEqual(self.top_up()["status"], "unknown")

    def test_same_cart_coupon_comparison(self):
        after = copy.deepcopy(self.before)
        after.update(discount=500, total=3100, coupons=["fixture-owned"])
        self.assertEqual(compare(self.before, after, self.now)["delta"], -500)
        self.assertEqual(compare(self.before, self.after, self.now)["status"], "unknown")

    def test_increased_quantity_is_top_up(self):
        self.after["cart"] = copy.deepcopy(self.before["cart"])
        self.after["cart"][0]["quantity"] = 2
        self.assertEqual(self.top_up()["status"], "known")

    def test_malformed_quotes_are_unknown(self):
        for quote in (None, [], {"cart": None}):
            self.assertEqual(compare(quote, quote, self.now)["status"], "unknown")


class RecommendationTests(unittest.TestCase):
    def setUp(self):
        self.data = fixture()

    def rank(self, **kwargs):
        return recommend(self.data["candidates"], self.data["now"], **kwargs)

    def test_three_priorities_and_unknown_nutrition(self):
        result = self.rank(preference={"likes": ["鸡肉"]}, target_kcal=600)
        self.assertEqual(result["wallet"][0]["id"], "C")
        self.assertEqual(result["nutrition"][0]["id"], "B")
        self.assertEqual(result["taste"][0]["id"], "B")
        self.assertEqual(result["nutrition_unknown"], ["C"])
        self.assertIsNone(result["wallet"][0]["kcal"])

    def test_no_target_means_no_nutrition_ranking(self):
        self.assertIsNone(self.rank()["nutrition"])

    def test_random_respects_budget_and_constraints(self):
        self.data["candidates"][2]["constraints_checked"] = False
        result = self.rank(budget=3600, seed=1024)
        self.assertEqual(result["random"]["id"], "A")
        self.assertEqual(result["excluded"], 2)

    def test_empty_eligible_set(self):
        self.assertIsNone(self.rank(budget=1)["random"])

    def test_unmatched_nutrition_stays_unknown(self):
        self.data["candidates"][0]["nutrition"]["cart_digest"] = digest([])
        self.assertIn("A", self.rank(target_kcal=600)["nutrition_unknown"])

    def test_no_mixed_store_recommendation(self):
        self.data["candidates"][1]["quote"]["store"] = "fixture-other-store"
        self.assertEqual(self.rank()["excluded"], 1)

    def test_malformed_nutrition_reference_stays_unknown(self):
        for value in (123, True, ["fixture-ref"], {}, "", "   ", None):
            with self.subTest(value=value):
                self.data["candidates"][0]["nutrition"]["response_ref"] = value
                self.assertIn("A", self.rank(target_kcal=600)["nutrition_unknown"])

    def test_rejected_candidate_does_not_choose_store_context(self):
        first = self.data["candidates"][0]
        first["quote"]["store"] = "fixture-rejected-store"
        first["tags"] = None
        result = self.rank()
        self.assertEqual(result["excluded"], 1)
        self.assertEqual(len(result["wallet"]), 2)


if __name__ == "__main__":
    unittest.main()
