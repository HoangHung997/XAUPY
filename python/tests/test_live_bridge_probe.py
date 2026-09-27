from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest


path = Path(__file__).resolve().parents[2] / "scripts" / "probe_live_bridge.py"
spec = importlib.util.spec_from_file_location("live_bridge_probe", path)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def samples():
    result = []
    for index in range(3):
        result.append({
            "elapsed_ms": index * 1000.0,
            "bridge": {"connected": True, "terminal_connected": True,
                       "account_trade_mode": "DEMO", "execution_locked": True,
                       "execution_ready": False, "age_ms": 500, "snapshots_total": 20 + index},
            "overview_available": True, "bid": 4286.08, "ask": 4286.43,
            "tick_time_msc": 1_790_371_799_876,
            "trading_enabled": False, "execution_enabled": False,
            "strategy_trading_enabled": False, "strategy_execution_enabled": False,
            "history_counts": {tf: 256 for tf in probe.REQUIRED_TIMEFRAMES},
            "bars_seen": {tf: 256 for tf in probe.REQUIRED_TIMEFRAMES},
            "strategy_ready": True,
        })
    return result


class LiveProbeAcceptanceTests(unittest.TestCase):
    def test_closed_market_unchanged_quote_and_tick_can_pass(self):
        self.assertTrue(all(probe.assess_samples(samples()).values()))

    def test_restart_counter_dip_cannot_hide_behind_later_growth(self):
        evidence = samples()
        evidence[1]["bridge"]["snapshots_total"] = 1
        checks = probe.assess_samples(evidence)
        self.assertTrue(checks["new_snapshots_received"])
        self.assertFalse(checks["snapshot_counter_monotonic"])

    def test_each_execution_lock_must_remain_false_or_locked(self):
        for key in ("trading_enabled", "execution_enabled", "strategy_trading_enabled", "strategy_execution_enabled"):
            evidence = samples()
            evidence[1][key] = True
            self.assertFalse(probe.assess_samples(evidence)["execution_locked"], key)
        evidence = samples()
        evidence[1]["bridge"]["execution_ready"] = True
        self.assertFalse(probe.assess_samples(evidence)["execution_locked"])

    def test_tick_or_sample_clock_regression_fails(self):
        evidence = samples()
        evidence[1]["tick_time_msc"] -= 1
        self.assertFalse(probe.assess_samples(evidence)["tick_time_nondecreasing"])
        evidence = samples()
        evidence[1]["elapsed_ms"] = -1
        self.assertFalse(probe.assess_samples(evidence)["sample_clock_monotonic"])

    def test_missing_strategy_history_and_nonfinite_quote_fail(self):
        evidence = samples()
        evidence[-1]["bars_seen"]["M30"] = 1
        evidence[-1]["bid"] = float("nan")
        checks = probe.assess_samples(evidence)
        self.assertFalse(checks["strategy_history_loaded"])
        self.assertFalse(checks["quote_valid"])


if __name__ == "__main__":
    unittest.main()
