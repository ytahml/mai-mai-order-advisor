import json
from pathlib import Path
import subprocess
import sys
import unittest


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
