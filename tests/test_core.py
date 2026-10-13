import copy
import unittest

from copilot.__main__ import fixture, top_up_evidence
from copilot.core import Invalid, compare, digest, recommend


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

    def test_breakdown_explains_net_spend_including_discount_sign(self):
        result = self.top_up(self.data["top_up_saving"])
        changes = {field: row["spend_change"] for field, row in result["breakdown"].items()}
        self.assertEqual(changes, {"subtotal": 1200, "delivery_fee": -600,
                                   "other_fees": 0, "discount": -1000})
        self.assertEqual(sum(changes.values()), result["delta"])
        self.assertEqual(result["breakdown"]["delivery_fee"],
                         {"before": 600, "after": 0, "spend_change": -600})

    def test_breakdown_covers_added_fees_and_reduced_discount(self):
        self.before.update(discount=500, total=3100)
        after = dict(self.before, discount=200, other_fees=100, total=3500)
        result = compare(self.before, after, self.now)
        self.assertEqual(result["breakdown"]["discount"]["spend_change"], 300)
        self.assertEqual(result["breakdown"]["other_fees"]["spend_change"], 100)
        self.assertEqual(sum(row["spend_change"] for row in result["breakdown"].values()), 400)

    def test_missing_fees_report_all_gaps_without_partial_savings(self):
        del self.after["delivery_fee"]
        self.after["other_fees"] = None
        result = self.top_up()
        self.assertEqual(result["reason"], "missing quote amounts: delivery_fee, other_fees")
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["delta"])
        self.assertNotIn("breakdown", result)

    def test_invalid_amount_names_field_without_echoing_value(self):
        self.after["delivery_fee"] = "SYNTHETIC-PRIVATE-INPUT"
        result = self.top_up()
        self.assertEqual(result["reason"], "invalid quote amount: delivery_fee")
        self.assertNotIn("SYNTHETIC-PRIVATE-INPUT", str(result))

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

    def test_pickup_missing_fees_are_not_inferred_from_total(self):
        quote = dict(self.before, mode="pickup", delivery_fee=0, other_fees=0,
                     total=self.before["subtotal"] - self.before["discount"])
        for field in ("delivery_fee", "other_fees"):
            with self.subTest(field=field):
                incomplete = dict(quote)
                del incomplete[field]
                result = compare(quote, incomplete, self.now)
                self.assertEqual((result["status"], result["delta"]), ("unknown", None))
                candidate = {"id": "fixture-pickup", "quote": incomplete,
                             "constraints_checked": True}
                ranking = recommend([candidate], self.now)
                self.assertEqual(ranking["excluded"], 1)
                self.assertEqual(ranking["wallet"], [])
                self.assertIsNone(ranking["random"])

    def test_pickup_explicit_zero_fees_are_valid(self):
        quote = dict(self.before, mode="pickup", delivery_fee=0, other_fees=0,
                     total=self.before["subtotal"] - self.before["discount"])
        result = compare(quote, quote, self.now)
        self.assertEqual((result["status"], result["delta"]), ("known", 0))
        candidate = {"id": "fixture-pickup", "quote": quote, "constraints_checked": True}
        ranking = recommend([candidate], self.now)
        self.assertEqual(ranking["excluded"], 0)
        self.assertEqual(ranking["wallet"][0]["total"], quote["total"])

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

    def test_dislikes_are_excluded_from_every_choice(self):
        result = self.rank(preference={"likes": ["鸡肉"], "dislikes": ["鸡肉"]},
                           target_kcal=600, seed=1024)
        for ranking in ("wallet", "nutrition", "taste"):
            self.assertNotIn("B", [item["id"] for item in result[ranking]])
        self.assertNotEqual(result["random"]["id"], "B")
        self.assertEqual(result["excluded"], 1)
        self.assertEqual(result["excluded_details"], [{"index": 1, "reason": "matches disliked tags"}])

    def test_reroll_excludes_shown_candidates_without_relaxing_constraints(self):
        shown = []
        for _ in range(2):
            result = self.rank(budget=3600, exclude_ids=shown, seed=1024)
            choice = result["random"]
            self.assertNotIn(choice["id"], shown)
            self.assertLessEqual(choice["total"], 3600)
            shown.append(choice["id"])
        result = self.rank(budget=3600, exclude_ids=shown)
        self.assertEqual(result["wallet"], [])
        self.assertIsNone(result["random"])
        self.assertEqual(result["excluded"], 3)
        self.assertEqual({row["reason"] for row in result["excluded_details"]},
                         {"over budget", "candidate excluded by user or already shown"})

    def test_cards_explain_price_taste_nutrition_and_source(self):
        original = copy.deepcopy(self.data)
        result = self.rank(preference={"likes": ["鸡肉", "鸡肉"]}, target_kcal=650, budget=4000)
        card = result["taste"][0]
        self.assertEqual(card["id"], "B")
        self.assertEqual(card["matched_likes"], ["鸡肉"])
        self.assertEqual(card["taste_score"], 1)
        self.assertEqual(card["kcal_distance"], 50)
        self.assertEqual(card["budget_remaining"], 0)
        self.assertTrue(card["includes_all_fees"])
        self.assertEqual(card["cart"][0]["name"], "模拟鸡肉餐")
        self.assertEqual(card["source"], "fixture")
        self.assertEqual(card["response_ref"], "fixture-price-second")
        self.assertEqual(card["observed_at"], self.data["now"])
        self.assertIsNone(result["wallet"][0]["kcal_distance"])
        card["cart"][0]["quantity"] = 99
        self.assertEqual(self.data, original)

    def test_unset_targets_do_not_invent_reasons(self):
        card = self.rank()["wallet"][0]
        self.assertEqual(card["matched_likes"], [])
        self.assertIsNone(card["budget_remaining"])
        self.assertIsNone(card["kcal_distance"])

    def test_exclusion_diagnostics_preserve_input_indexes_and_hide_malformed_data(self):
        candidates = self.data["candidates"]
        candidates[0]["quote"]["delivery_fee"] = None
        candidates[1]["constraints_checked"] = False
        candidates.append("SYNTHETIC-PRIVATE-INPUT")
        result = self.rank()
        self.assertEqual(result["excluded_details"], [
            {"index": 0, "reason": "missing quote amounts: delivery_fee"},
            {"index": 1, "reason": "hard constraints not checked"},
            {"index": 3, "reason": "malformed candidate"}])
        self.assertNotIn("SYNTHETIC-PRIVATE-INPUT", str(result))
        self.assertEqual(result["random"]["id"], "C")

    def test_malformed_preferences_and_exclusions_fail_instead_of_being_ignored(self):
        cases = [{"preference": []}, {"preference": False},
                 {"preference": {"likes": "鸡肉"}}, {"preference": {"dislikes": None}},
                 {"preference": {"dislikes": [""]}}, {"preference": {"likes": [{}]}},
                 {"exclude_ids": "A"}, {"exclude_ids": [None]}]
        for kwargs in cases:
            with self.subTest(kwargs=kwargs), self.assertRaises(Invalid):
                self.rank(**kwargs)

    def test_recommend_requires_list_and_valid_clock_even_with_no_candidates(self):
        with self.assertRaises(Invalid):
            recommend({}, self.data["now"])
        with self.assertRaises(Invalid):
            recommend([], True)

    def test_disliked_candidate_does_not_choose_store_context(self):
        self.data["candidates"][0]["quote"]["store"] = "fixture-other-store"
        result = self.rank(preference={"dislikes": ["牛肉"]})
        self.assertEqual(result["excluded"], 1)
        self.assertEqual(len(result["wallet"]), 2)

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
