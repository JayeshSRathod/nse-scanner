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
            write_json(root, "output/v2_daily_run.json", {"trade_date": "2026-08-25", "dashboard_candidates": [
                {"symbol": "V3TEST", "timing_state": "READY", "score": 88, "entry": 100, "stop": 95}]})
            write_json(root, "output/old_nse_hull_daily.json", {"as_of_date": "2026-08-25", "shortlist": [
                {"symbol": "LADDERTEST", "hull_state": "WATCH", "discovery_score": 75, "close": 50}]})
            registry = root / "corporate_data/normalized/security_lifecycle_events.csv"
            registry.parent.mkdir(parents=True)
            with registry.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["symbol", "terminal"])
                writer.writeheader(); writer.writerow({"symbol": "JBCHEPHARM", "terminal": "1"})
            with patch.object(module, "ROOT", root):
                self.assertEqual(module.main(), 0)
            feed = json.loads((root / "docs/data/feed.json").read_text(encoding="utf-8"))
            self.assertEqual({row["symbol"] for row in feed["items"]}, {"VISIBLE", "V3TEST", "LADDERTEST"})
            by_symbol = {row["symbol"]: row for row in feed["items"]}
            self.assertEqual(by_symbol["VISIBLE"]["stage"], "Watch for entry")
            self.assertEqual(by_symbol["V3TEST"]["stage"], "Watch for entry")
            self.assertEqual(by_symbol["LADDERTEST"]["stage"], "Watchlist—wait for confirmation")
            self.assertTrue(all(scanner["available"] for scanner in feed["scanners"]))
            self.assertNotIn("JBCHEPHARM", json.dumps(feed))

    def test_each_scanner_is_limited_to_25_and_ladder_requires_75(self):
        rows = [{"scanner": "penny", "symbol": f"P{i}", "stage": "Early watchlist", "score": i,
                 "price": 10, "entry_low": 10, "entry_high": 10, "stop": 9, "target1": 11, "target2": 12}
                for i in range(30)]
        limited = module.limit_per_scanner(rows)
        self.assertEqual(len(limited), 25)
        self.assertEqual(limited[0]["symbol"], "P29")
        ladder = module.ladder_items({"shortlist": [
            {"symbol": "LOW", "hull_state": "WATCH", "discovery_score": 74.99},
            {"symbol": "SHOW", "hull_state": "WATCH", "discovery_score": 75.0}]})
        self.assertEqual([row["symbol"] for row in ladder], ["SHOW"])

if __name__ == "__main__":
    unittest.main()
