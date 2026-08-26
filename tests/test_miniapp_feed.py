import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_miniapp_feed.py"
SPEC = importlib.util.spec_from_file_location("build_miniapp_feed", MODULE_PATH)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(module)

def write_json(root: Path, relative: str, value: dict) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value), encoding="utf-8")

class MiniAppFeedTest(unittest.TestCase):
    def test_plain_language_and_silent_terminal_filter(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_json(root, "output/penny_microcap/daily.json", {"as_of_date": "2026-08-25", "candidates": [
                {"symbol": "VISIBLE", "state": "READY", "score": 80, "close": 10},
                {"symbol": "JBCHEPHARM", "state": "CONFIRMING", "score": 90, "close": 2400}]})
            write_json(root, "output/pine_hull_daily_run.json", {"trade_date": "2026-08-25", "created": [], "watch": []})
            registry = root / "corporate_data/normalized/security_lifecycle_events.csv"
            registry.parent.mkdir(parents=True)
            with registry.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["symbol", "terminal"])
                writer.writeheader(); writer.writerow({"symbol": "JBCHEPHARM", "terminal": "1"})
            with patch.object(module, "ROOT", root):
                self.assertEqual(module.main(), 0)
            feed = json.loads((root / "docs/data/feed.json").read_text(encoding="utf-8"))
            self.assertEqual([row["symbol"] for row in feed["items"]], ["VISIBLE"])
            self.assertEqual(feed["items"][0]["stage"], "Ready to watch")
            self.assertNotIn("JBCHEPHARM", json.dumps(feed))

if __name__ == "__main__":
    unittest.main()
