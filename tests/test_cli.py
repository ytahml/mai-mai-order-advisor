import json
from pathlib import Path
import subprocess
import sys
import time
import unittest

from copilot.__main__ import fixture


ROOT = Path(__file__).resolve().parent.parent


class CliTests(unittest.TestCase):
    def run_cli(self, command, data=""):
        return subprocess.run([sys.executable, "-m", "copilot", command], input=data,
                              text=True, capture_output=True, cwd=ROOT, check=False)

    def test_offline_demo_end_to_end(self):
        result = self.run_cli("demo")
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["top_up_loss"]["delta"], 200)
        self.assertEqual(output["top_up_saving"]["delta"], -400)
        self.assertEqual(output["missing_conditions"]["status"], "unknown")
        self.assertEqual(output["simulated_flow"][-1]["phase"], "pending_payment")
        self.assertIn("example.invalid", output["payment_link"])
        self.assertEqual(output["top_up_loss"]["breakdown"]["subtotal"]["spend_change"], 1200)
        self.assertEqual(output["recommendations_after_feedback"]["random"]["id"], "B")
        self.assertEqual(output["missing_fees"]["status"], "unknown")
        self.assertIsNone(output["missing_fees"]["delta"])

    def test_recommend_json_supports_feedback_and_reroll(self):
        candidates = fixture()["candidates"]
        now = int(time.time())
        for item in candidates:
            item["quote"].update(observed_at=now, expires_at=now + 300)
        data = {"candidates": candidates, "preference": {"dislikes": ["牛肉"]},
                "exclude_ids": ["C"], "budget": 4000, "target_kcal": 650}
        result = self.run_cli("recommend", json.dumps(data))
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["random"]["id"], "B")
        self.assertEqual(output["random"]["kcal_distance"], 50)
        self.assertEqual(output["excluded"], 2)
        self.assertEqual(len(output["excluded_details"]), 2)

    def test_malformed_preference_does_not_echo_private_input(self):
        data = {"candidates": [], "preference": {"dislikes": "SYNTHETIC-PRIVATE-INPUT"}}
        result = self.run_cli("recommend", json.dumps(data))
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, "")
        self.assertNotIn("SYNTHETIC-PRIVATE-INPUT", result.stdout)

    def test_invalid_input_has_safe_error_and_nonzero_exit(self):
        result = self.run_cli("transition", '{"event": {"action": "dispatch_order"}}')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, "")
        self.assertNotIn("Traceback", result.stdout)

    def test_malformed_data_not_echoed(self):
        result = self.run_cli("transition", "SYNTHETIC-PRIVATE-INPUT")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("SYNTHETIC-PRIVATE-INPUT", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
