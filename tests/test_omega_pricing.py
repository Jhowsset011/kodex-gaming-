import importlib.util
import json
from decimal import Decimal, Inexact, ROUND_DOWN, localcontext
from pathlib import Path
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location(
    "omega_pricing", Path(__file__).parents[1] / "scripts/omega_pricing.py")
pricing = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pricing)


def fictional_rules():
    return {
        "discountPercent": "20",
        "bands": [
            {"maxCost": "100", "markupPercent": "10"},
            {"maxCost": "500", "markupPercent": "30"},
        ],
        "aboveMax": "public",
    }


class PricingTests(unittest.TestCase):
    def setUp(self):
        self.policy = pricing.PricingPolicy.from_dict(fictional_rules())

    def test_discount_then_addition_to_cost(self):
        self.assertEqual(self.policy.sale_price(Decimal("50")), Decimal("44.00"))
        self.assertEqual(self.policy.sale_price(Decimal("250")), Decimal("260.00"))

    def test_inclusive_band_limits_and_immediately_adjacent_costs(self):
        cases = {
            "124.9875": "109.99",  # Cost 99.99.
            "125": "110.00",       # Cost exactly 100.00.
            "125.0125": "130.01",  # Cost 100.01 enters the next band.
            "624.9875": "649.99",  # Cost 499.99.
            "625": "650.00",       # Cost exactly 500.00.
            "625.0125": "625.01",  # Cost 500.01 uses the public price.
        }
        for public, expected in cases.items():
            with self.subTest(public=public):
                self.assertEqual(self.policy.sale_price(Decimal(public)), Decimal(expected))

    def test_cost_rounds_before_band_selection(self):
        self.assertEqual(self.policy.sale_price(Decimal("125.00624")), Decimal("110.00"))
        self.assertEqual(self.policy.sale_price(Decimal("125.00625")), Decimal("130.01"))

    def test_cost_and_sale_round_half_up_separately(self):
        self.assertEqual(self.policy.sale_price(Decimal("12.50625")), Decimal("11.01"))
        self.assertEqual(self.policy.sale_price(Decimal("0.00625")), Decimal("0.01"))

    def test_above_max_uses_public_price_rounded_half_up(self):
        self.assertEqual(self.policy.sale_price(Decimal("900.005")), Decimal("900.01"))

    def test_zero_and_no_discount_are_supported(self):
        rules = fictional_rules()
        rules["discountPercent"] = 0
        policy = pricing.PricingPolicy.from_dict(rules)
        self.assertEqual(policy.sale_price(Decimal("0")), Decimal("0.00"))
        self.assertEqual(policy.sale_price(Decimal("50")), Decimal("55.00"))

    def test_decimal_calculation_ignores_callers_low_precision_and_rounding(self):
        with localcontext() as context:
            context.prec = 3
            context.rounding = ROUND_DOWN
            context.traps[Inexact] = True
            self.assertEqual(self.policy.sale_price(Decimal("125.00625")), Decimal("130.01"))
            self.assertEqual(self.policy.sale_price(Decimal("900.005")), Decimal("900.01"))

    def test_large_amounts_remain_exact(self):
        self.assertEqual(self.policy.sale_price(Decimal("98765432109876543210.005")),
                         Decimal("98765432109876543210.01"))

    def test_inputs_are_parsed_without_binary_float_artifacts(self):
        self.assertEqual(self.policy.sale_price(12.50625), Decimal("11.01"))
        self.assertEqual(self.policy.sale_price("12.50625"), Decimal("11.01"))

    def test_invalid_public_prices_fail_closed(self):
        for value in (-1, "NaN", "Infinity", "-Infinity", Decimal("sNaN"), None,
                      True, "", "RD$50", {}, []):
            with self.subTest(type=type(value).__name__):
                with self.assertRaises(ValueError):
                    self.policy.sale_price(value)

    def test_invalid_discount_percentages_fail_closed(self):
        for value in (-1, "NaN", "Infinity", 100, 101, None, True):
            with self.subTest(type=type(value).__name__):
                rules = fictional_rules()
                rules["discountPercent"] = value
                with self.assertRaises(ValueError):
                    pricing.PricingPolicy.from_dict(rules)

    def test_invalid_band_values_fail_closed(self):
        for field in ("maxCost", "markupPercent"):
            for value in (-1, "NaN", "Infinity", None, True):
                with self.subTest(field=field, type=type(value).__name__):
                    rules = fictional_rules()
                    rules["bands"][0][field] = value
                    with self.assertRaises(ValueError):
                        pricing.PricingPolicy.from_dict(rules)

    def test_duplicate_or_descending_band_limits_fail_closed(self):
        for maximum in ("100", "90"):
            rules = fictional_rules()
            rules["bands"][1]["maxCost"] = maximum
            with self.assertRaises(ValueError):
                pricing.PricingPolicy.from_dict(rules)

    def test_invalid_shapes_and_fallback_fail_closed(self):
        for data in (None, [], {}, {**fictional_rules(), "discountPercent": None},
                     {**fictional_rules(), "bands": []},
                     {**fictional_rules(), "bands": {}},
                     {**fictional_rules(), "bands": [{"maxCost": "100"}]},
                     {**fictional_rules(), "aboveMax": "cost"},
                     {**fictional_rules(), "unexpected": "value"}):
            with self.assertRaises(ValueError):
                pricing.PricingPolicy.from_dict(data)

    def test_policy_representation_does_not_disclose_inputs(self):
        self.assertEqual(repr(self.policy), "<PricingPolicy private>")


class SalePriceRoundingTests(unittest.TestCase):
    def setUp(self):
        rules = fictional_rules()
        rules["rounding"] = {"step": "100", "downThrough": "30"}
        self.policy = pricing.PricingPolicy.from_dict(rules)

    def test_final_hundreds_follow_inclusive_downward_threshold(self):
        # These amounts use the public-price fallback, which must also round.
        cases = {
            "1825": "1800.00",
            "1830": "1800.00",
            "1830.01": "1900.00",
            "1885": "1900.00",
            "1899.99": "1900.00",
            "1900": "1900.00",
            "1930": "1900.00",
            "1930.01": "2000.00",
        }
        for public, expected in cases.items():
            with self.subTest(public=public):
                self.assertEqual(self.policy.sale_price(Decimal(public)), Decimal(expected))

    def test_sale_price_rounds_to_cents_before_step_threshold(self):
        self.assertEqual(self.policy.sale_price("1830.0049"), Decimal("1800.00"))
        self.assertEqual(self.policy.sale_price("1830.005"), Decimal("1900.00"))

    def test_cost_band_is_chosen_before_final_price_rounding(self):
        # Cost 100.00 uses the first band's 110.00 sale price; cost 100.01
        # uses the second band's 130.01, then rounds beyond the 30 threshold.
        self.assertEqual(self.policy.sale_price("125"), Decimal("100.00"))
        self.assertEqual(self.policy.sale_price("125.0125"), Decimal("200.00"))

    def test_markup_is_applied_before_rounding_instead_of_rounding_the_public_price(self):
        # Public 250 becomes a 260.00 sale price before rounding to 300.00.
        self.assertEqual(self.policy.sale_price("250"), Decimal("300.00"))

    def test_zero_input_is_preserved_but_positive_prices_cannot_become_free(self):
        self.assertEqual(self.policy.sale_price("0"), Decimal("0.00"))
        for public in ("12.50625", "0.0001"):
            with self.subTest(public=public):
                with self.assertRaisesRegex(ValueError, "zero sale price"):
                    self.policy.sale_price(public)

    def test_custom_integer_step_and_decimal_threshold_are_supported(self):
        rules = fictional_rules()
        rules["rounding"] = {"step": 50, "downThrough": "15.50"}
        policy = pricing.PricingPolicy.from_dict(rules)
        self.assertEqual(policy.sale_price("1815.50"), Decimal("1800.00"))
        self.assertEqual(policy.sale_price("1815.51"), Decimal("1850.00"))

    def test_rounding_is_independent_of_callers_decimal_context(self):
        with localcontext() as context:
            context.prec = 3
            context.rounding = ROUND_DOWN
            context.traps[Inexact] = True
            self.assertEqual(self.policy.sale_price("1830.005"), Decimal("1900.00"))
            self.assertEqual(self.policy.sale_price("125.0125"), Decimal("200.00"))

    def test_large_public_fallback_amounts_round_exactly(self):
        self.assertEqual(self.policy.sale_price("98765432109876543230.01"),
                         Decimal("98765432109876543300.00"))

    def test_large_step_has_enough_decimal_precision(self):
        rules = fictional_rules()
        rules["rounding"] = {"step": "1E100", "downThrough": 0}
        policy = pricing.PricingPolicy.from_dict(rules)
        self.assertEqual(policy.sale_price("900"), Decimal("1E100"))

    def test_invalid_rounding_configuration_fails_without_disclosing_values(self):
        invalid = (
            None, [], {}, {"step": 100}, {"downThrough": 30},
            {"step": 100, "downThrough": 30, "secret": "do-not-log"},
            {"step": 0, "downThrough": 0},
            {"step": "0.5", "downThrough": 0},
            {"step": "100.5", "downThrough": 30},
            {"step": 100, "downThrough": 100},
            {"step": 100, "downThrough": "100.01"},
        )
        for field in ("step", "downThrough"):
            for value in (-1, "NaN", "Infinity", None, True, "do-not-log"):
                invalid += ({"step": 100, "downThrough": 30, field: value},)
        for rounding in invalid:
            with self.subTest(rounding=rounding):
                rules = fictional_rules()
                rules["rounding"] = rounding
                with self.assertRaises(ValueError) as error:
                    pricing.PricingPolicy.from_dict(rules)
                self.assertNotIn("do-not-log", str(error.exception))

    def test_policy_representation_stays_private_with_rounding(self):
        self.assertEqual(repr(self.policy), "<PricingPolicy private>")


class PrivateConfigurationTests(unittest.TestCase):
    def test_environment_json_supports_exact_decimal_values(self):
        encoded = json.dumps(fictional_rules()).replace('"20"', "20.0")
        policy = pricing.PricingPolicy.from_env({"OMEGA_PRICING_RULES": encoded})
        self.assertEqual(policy.sale_price(Decimal("125")), Decimal("110.00"))

    def test_external_file_is_read_without_creating_repository_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "private-rules.json"
            path.write_text(json.dumps(fictional_rules()), encoding="utf-8")
            policy = pricing.PricingPolicy.from_env({}, file_path=path)
            self.assertEqual(policy.sale_price(Decimal("250")), Decimal("260.00"))

    def test_absent_empty_or_conflicting_sources_fail_closed(self):
        for environment in ({}, {"OMEGA_PRICING_RULES": ""}, {"OMEGA_PRICING_RULES": " "}):
            with self.assertRaises(ValueError):
                pricing.PricingPolicy.from_env(environment)
        with self.assertRaises(ValueError):
            pricing.PricingPolicy.from_env(
                {"OMEGA_PRICING_RULES": json.dumps(fictional_rules())}, file_path="unused")

    def test_invalid_json_and_duplicate_keys_fail_closed_without_values_in_errors(self):
        for encoded in ('{"sensitive": "hidden"', 'NaN', '{"bands": [], "bands": []}',
                        '{"discountPercent": Infinity}', '[]'):
            with self.assertRaises(ValueError) as error:
                pricing.PricingPolicy.from_env({"OMEGA_PRICING_RULES": encoded})
            self.assertNotIn("hidden", str(error.exception))
            self.assertNotIn(encoded, str(error.exception))

    def test_missing_file_path_is_not_disclosed(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "confidential-do-not-log.json"
            with self.assertRaises(ValueError) as error:
                pricing.PricingPolicy.from_env({}, file_path=missing)
            self.assertNotIn(str(missing), str(error.exception))

    def test_optional_rounding_reads_exact_numeric_values_from_private_json(self):
        rules = fictional_rules()
        rules["rounding"] = {"step": 100, "downThrough": 30}
        policy = pricing.PricingPolicy.from_env({"OMEGA_PRICING_RULES": json.dumps(rules)})
        self.assertEqual(policy.sale_price("1830"), Decimal("1800.00"))
        self.assertEqual(policy.sale_price("1830.01"), Decimal("1900.00"))


if __name__ == "__main__":
    unittest.main()
