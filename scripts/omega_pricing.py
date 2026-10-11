"""Private, configurable sale-price calculation for the Omega synchronizer.

Supply rules through OMEGA_PRICING_RULES or an external configuration file.
Only sale_price() belongs in a public catalog; policy inputs and purchase costs
must never be copied into catalog metadata or logs.
"""

from decimal import Context, Decimal, DecimalException, InvalidOperation, ROUND_HALF_UP, localcontext
import json
import os
from pathlib import Path


CENT = Decimal("0.01")
HUNDRED = Decimal("100")


def _decimal(value, field):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError(f"Invalid {field}.")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"Invalid {field}.") from None
    if not number.is_finite() or number < 0:
        raise ValueError(f"Invalid {field}.")
    return number


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate pricing configuration field.")
        result[key] = value
    return result


def _invalid_constant(_value):
    raise ValueError("Invalid pricing configuration number.")


class PricingPolicy:
    """A policy that keeps its private inputs out of its representation."""

    __slots__ = ("_discount", "_bands", "_rounding", "_precision")

    def __init__(self, discount, bands, rounding=None):
        # Callers use from_dict() or from_env() to validate private configuration.
        self._discount = discount
        self._bands = tuple(bands)
        self._rounding = rounding
        numbers = [discount] + [value for band in bands for value in band]
        self._precision = (sum(len(number.as_tuple().digits) for number in numbers)
                           + max(max(0, markup.adjusted()) for _, markup in bands))
        if rounding is not None:
            self._precision += (sum(len(number.as_tuple().digits) for number in rounding)
                                + max(max(0, number.adjusted()) for number in rounding))

    def __repr__(self):
        return "<PricingPolicy private>"

    @property
    def rounding_enabled(self):
        return self._rounding is not None

    @classmethod
    def from_dict(cls, data):
        """Validate ordered maxCost/markupPercent bands and a public-price fallback."""
        required = {"discountPercent", "bands", "aboveMax"}
        if (not isinstance(data, dict) or not required.issubset(data)
                or set(data) - required - {"rounding"}):
            raise ValueError("Invalid pricing configuration fields.")
        if data["aboveMax"] != "public":
            raise ValueError("Invalid aboveMax behavior.")
        discount = _decimal(data["discountPercent"], "discount percentage")
        if discount >= HUNDRED:
            raise ValueError("Invalid discount percentage.")
        raw_bands = data["bands"]
        if not isinstance(raw_bands, list) or not raw_bands:
            raise ValueError("Pricing bands must be a nonempty list.")
        bands = []
        for band in raw_bands:
            if not isinstance(band, dict) or set(band) != {"maxCost", "markupPercent"}:
                raise ValueError("Invalid pricing band fields.")
            maximum = _decimal(band["maxCost"], "band maximum")
            markup = _decimal(band["markupPercent"], "markup percentage")
            if bands and maximum <= bands[-1][0]:
                raise ValueError("Pricing band maxima must be strictly increasing.")
            bands.append((maximum, markup))
        rounding = None
        if "rounding" in data:
            raw_rounding = data["rounding"]
            if not isinstance(raw_rounding, dict) or set(raw_rounding) != {"step", "downThrough"}:
                raise ValueError("Invalid price rounding fields.")
            step = _decimal(raw_rounding["step"], "rounding step")
            down_through = _decimal(raw_rounding["downThrough"], "rounding threshold")
            if step < 1 or step != step.to_integral_value() or down_through >= step:
                raise ValueError("Invalid price rounding rule.")
            rounding = (step, down_through)
        return cls(discount, bands, rounding)

    @classmethod
    def from_env(cls, environ=None, file_path=None):
        """Read private JSON from the environment or an explicit external file.

        Missing or conflicting sources fail closed. File paths and JSON values
        are deliberately omitted from errors, which may appear in CI logs.
        """
        environment = os.environ if environ is None else environ
        encoded = environment.get("OMEGA_PRICING_RULES")
        if encoded and file_path is not None:
            raise ValueError("Provide only one private pricing configuration source.")
        if file_path is not None:
            try:
                encoded = Path(file_path).read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                raise ValueError("Cannot read private pricing configuration.") from None
        if not isinstance(encoded, str) or not encoded.strip():
            raise ValueError("Private pricing configuration is required.")
        try:
            data = json.loads(encoded, parse_float=Decimal, parse_int=Decimal,
                              parse_constant=_invalid_constant, object_pairs_hook=_json_object)
        except (ValueError, TypeError):
            raise ValueError("Invalid private pricing JSON.") from None
        return cls.from_dict(data)

    def sale_price(self, public_price):
        """Return the final public sale price, optionally rounded to a configured step.

        The discounted purchase cost is rounded to cents before band selection.
        Above the last band, use the supplier's public price instead of the cost.
        Optional step rounding runs last, after the sale price rounds to cents.
        """
        public = _decimal(public_price, "public price")
        try:
            with localcontext(Context(rounding=ROUND_HALF_UP)) as context:
                # Avoid dependence on a caller's Decimal precision or rounding.
                context.prec = max(28, self._precision + len(public.as_tuple().digits)
                                   + max(0, public.adjusted()) + 10)
                cost = (public * (Decimal(1) - self._discount / HUNDRED)).quantize(
                    CENT, rounding=ROUND_HALF_UP)
                for maximum, markup in self._bands:
                    if cost <= maximum:
                        sale = (cost * (Decimal(1) + markup / HUNDRED)).quantize(
                            CENT, rounding=ROUND_HALF_UP)
                        break
                else:
                    sale = public.quantize(CENT, rounding=ROUND_HALF_UP)
                if self._rounding is None:
                    return sale
                step, down_through = self._rounding
                remainder = sale % step
                rounded = sale - remainder
                if remainder > down_through:
                    rounded += step
                if public > 0 and rounded == 0:
                    raise ValueError("Price rounding cannot produce a zero sale price.")
                return rounded.quantize(CENT, rounding=ROUND_HALF_UP)
        except (DecimalException, OverflowError):
            raise ValueError("Cannot calculate sale price.") from None
