import copy
import pathlib
import random
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xaupy_engine.config_schema import (
    FIELDS,
    TIMEFRAME_OPTIONS,
    default_profile,
    field_for_set_key,
    get_path,
    normalized_profile,
    schema_payload,
    validate_profile,
)


class ConfigSchemaTests(unittest.TestCase):
    def test_timeframe_options_are_exact_product_requirement(self):
        self.assertEqual(
            ("M1", "M3", "M5", "M15", "M30", "H1", "H2", "H4"),
            TIMEFRAME_OPTIONS,
        )

    def test_default_profile_is_valid_and_comprehensive(self):
        profile = default_profile()
        self.assertEqual([], validate_profile(profile))
        self.assertGreaterEqual(len(FIELDS), 100)
        self.assertEqual(len(FIELDS), schema_payload()["field_count"])

    def test_all_three_timeframes_are_independent_and_unusual_order_is_allowed(self):
        profile = default_profile()
        profile["timeframes"]["direction"] = "M1"
        profile["timeframes"]["pullback"] = "H4"
        profile["timeframes"]["trigger"] = "M3"
        self.assertEqual([], validate_profile(profile))

    def test_invalid_timeframe_is_rejected(self):
        profile = default_profile()
        profile["timeframes"]["trigger"] = "M2"
        errors = validate_profile(profile)
        self.assertTrue(any("timeframes.trigger" in error for error in errors))

    def test_task004_safety_values_cannot_be_unlocked(self):
        cases = (
            ("execution", "allow_real_account", True),
            ("execution", "demo_only", False),
            ("execution", "max_retry_count", 1),
            ("safety", "never_widen_sl", False),
            ("safety", "require_server_sl", False),
            ("safety", "block_on_stale_market_data", False),
        )
        for section, key, value in cases:
            with self.subTest(section=section, key=key):
                profile = default_profile()
                profile[section][key] = value
                self.assertNotEqual([], validate_profile(profile))

    def test_cross_field_ranges_are_checked(self):
        profile = default_profile()
        profile["pullback"]["rsi_buy_level"] = 80
        profile["pullback"]["rsi_sell_level"] = 20
        profile["filters"]["adx"]["min"] = 60
        profile["filters"]["adx"]["max"] = 20
        profile["risk"]["fixed_lot"] = 1.0
        profile["risk"]["max_lot"] = 0.1
        errors = validate_profile(profile)
        self.assertGreaterEqual(len(errors), 3)

    def test_every_set_key_and_alias_resolves_to_exact_field(self):
        for field in FIELDS:
            self.assertIs(field, field_for_set_key(field.set_key))
            for alias in field.aliases:
                self.assertIs(field, field_for_set_key(alias))
                self.assertIs(field, field_for_set_key(alias.lower()))

    def test_normalized_profile_is_deep_copy_and_stable(self):
        profile = default_profile()
        normalized = normalized_profile(profile)
        self.assertEqual(profile, normalized)
        normalized["timeframes"]["direction"] = "H1"
        self.assertEqual("M30", profile["timeframes"]["direction"])

    def test_random_numeric_mutations_respect_declared_bounds(self):
        rng = random.Random(4004)
        numeric = [field for field in FIELDS if field.kind in {"int", "float"}]
        self.assertGreater(len(numeric), 20)

        for _ in range(500):
            field = rng.choice(numeric)
            if field.locked_value is not None:
                continue
            profile = default_profile()

            low = field.minimum if field.minimum is not None else -100
            high = field.maximum if field.maximum is not None else 100
            if low == high:
                continue
            value = rng.uniform(float(low), float(high))
            if field.kind == "int":
                value = int(round(value))

            parts = field.path.split(".")
            node = profile
            for part in parts[:-1]:
                node = node[part]
            node[parts[-1]] = value

            # Some independently valid numeric values can violate a cross-field
            # relation. We only assert that any errors name a documented cross-rule
            # or another field relation, never a type/coercion failure for this path.
            errors = validate_profile(profile)
            self.assertFalse(
                any(error.startswith(field.path + ":") for error in errors),
                msg=(field.path, value, errors),
            )


if __name__ == "__main__":
    unittest.main()
