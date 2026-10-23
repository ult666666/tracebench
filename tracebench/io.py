"""Strict bounded JSON readers and schema validation. No provider connections."""

from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
import unicodedata

MAX_LINE_BYTES = 1_048_576
MAX_ROWS = 100_000


class InputError(ValueError):
    """Malformed, ambiguous, or incompatible evaluation input."""


def fields(value, required, optional=(), where="record"):
    if not isinstance(value, dict):
        raise InputError(f"{where}: expected an object")
    missing = set(required) - value.keys()
    unknown = value.keys() - set(required) - set(optional)
    if missing:
        raise InputError(f"{where}: missing fields {sorted(missing)}")
    if unknown:
        raise InputError(f"{where}: unknown fields {sorted(unknown)}")


def valid_id(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise InputError("id: expected a nonempty string of at most 200 characters")
    if any(unicodedata.category(c) in {"Cc", "Cs"} for c in value):
        raise InputError("id: control characters and surrogates are forbidden")


def _number(text):
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise InputError("invalid JSON number") from exc
    if not number.is_finite() or len(number.as_tuple().digits) > 100 or abs(number.adjusted()) > 100:
        raise InputError("number must be finite with at most 100 digits and exponent magnitude 100")
    return number


def _integer(text):
    if len(text.lstrip("-")) > 100:
        raise InputError("integer exceeds 100 digits")
    return int(text)


def _constant(text):
    raise InputError(f"non-finite JSON value {text} is forbidden")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"duplicate object key {key!r}")
        result[key] = value
    return result


def validate_json(value, depth=0, max_depth=64):
    """Validate API values as well as parsed values; limit nesting to 64."""
    if depth > max_depth:
        raise InputError(f"JSON nesting exceeds {max_depth} levels")
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, str):
        if any(0xD800 <= ord(c) <= 0xDFFF for c in value):
            raise InputError("unpaired Unicode surrogate is forbidden")
    elif isinstance(value, (int, float, Decimal)):
        _number(str(value))
    elif isinstance(value, list):
        for item in value:
            validate_json(item, depth + 1, max_depth)
    elif isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise InputError("JSON object keys must be strings")
            validate_json(key, depth + 1, max_depth)
            validate_json(item, depth + 1, max_depth)
    else:
        raise InputError(f"unsupported JSON value type {type(value).__name__}")


def strict_json(text, max_depth=64):
    try:
        value = json.loads(text, parse_float=_number, parse_int=_integer,
                           parse_constant=_constant, object_pairs_hook=_pairs)
        validate_json(value, max_depth=max_depth)
        return value
    except (json.JSONDecodeError, UnicodeError, RecursionError, ValueError) as exc:
        if isinstance(exc, InputError):
            raise
        raise InputError(f"invalid JSON: {exc}") from exc


def validate_case(row):
    fields(row, {"id", "input", "checks"}, {"description"}, "case")
    validate_json(row)
    valid_id(row["id"])
    if "description" in row and not isinstance(row["description"], str):
        raise InputError("case description must be a string")
    if not isinstance(row["checks"], list) or not 1 <= len(row["checks"]) <= 100:
        raise InputError("case checks must contain 1 to 100 checks")
    for check in row["checks"]:
        fields(check, {"type", "expected"}, where="check")
        if check["type"] not in ("exact", "contains", "json_subset"):
            raise InputError("check type must be exact, contains, or json_subset")
        if check["type"] in ("exact", "contains") and not isinstance(check["expected"], str):
            raise InputError("exact/contains expected value must be a string")
        if check["type"] == "contains" and not check["expected"]:
            raise InputError("contains expected value cannot be empty")


def validate_output(row):
    fields(row, {"id", "output"}, {"metrics"}, "output")
    validate_json(row)
    valid_id(row["id"])
    metrics = row.get("metrics", {})
    fields(metrics, set(), {"latency_ms", "input_tokens", "output_tokens"}, "metrics")
    if "latency_ms" in metrics:
        latency = metrics["latency_ms"]
        if isinstance(latency, bool) or not isinstance(latency, (int, float, Decimal)) or latency < 0:
            raise InputError("latency_ms must be a finite nonnegative number in milliseconds")
    if ("input_tokens" in metrics) != ("output_tokens" in metrics):
        raise InputError("input_tokens and output_tokens must be supplied together")
    for key in ("input_tokens", "output_tokens"):
        if key in metrics and (type(metrics[key]) is not int or metrics[key] < 0):
            raise InputError(f"{key} must be a nonnegative integer")


def _load_jsonl(path, validator):
    records = {}
    try:
        with Path(path).open("rb") as stream:
            line_no = 0
            while True:
                raw = stream.readline(MAX_LINE_BYTES + 1)
                if not raw:
                    break
                line_no += 1
                if line_no > MAX_ROWS:
                    raise InputError(f"record count exceeds {MAX_ROWS}")
                try:
                    if len(raw) > MAX_LINE_BYTES:
                        raise InputError(f"row exceeds {MAX_LINE_BYTES} bytes including newline")
                    if not raw.strip():
                        raise InputError("blank rows are forbidden")
                    row = strict_json(raw.decode("utf-8"))
                    validator(row)
                    if row["id"] in records:
                        raise InputError(f"duplicate id {row['id']!r}")
                    records[row["id"]] = row
                except (InputError, UnicodeError) as exc:
                    raise InputError(f"{path}:{line_no}: {exc}") from exc
    except OSError as exc:
        raise InputError(f"cannot read {path}: {exc.strerror}") from exc
    if not records:
        raise InputError(f"{path}: no records")
    return records


def load_cases(path):
    """Read cases keyed by ID, preserving case-file order."""
    return _load_jsonl(path, validate_case)


def load_outputs(path):
    """Read candidate outputs keyed by ID; metrics are optional observations."""
    return _load_jsonl(path, validate_output)


def load_json(path, max_bytes=16_777_216):
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise InputError(f"{path}: JSON document exceeds {max_bytes} bytes")
        return strict_json(raw.decode("utf-8"), max_depth=128)
    except (OSError, UnicodeError) as exc:
        raise InputError(f"cannot read {path}: {exc}") from exc


def validate_pricing(pricing, normalized=False):
    fields(pricing, {"currency", "input_per_million", "output_per_million"}, where="pricing")
    if not isinstance(pricing["currency"], str) or not re.fullmatch(r"[A-Z]{3}", pricing["currency"]):
        raise InputError("currency must be a three-letter uppercase code supplied by the user")
    result = {"currency": pricing["currency"]}
    for key in ("input_per_million", "output_per_million"):
        value = pricing[key]
        if not isinstance(value, str) and not (normalized and isinstance(value, Decimal)):
            raise InputError(f"{key} must be an explicit decimal string")
        number = _number(str(value))
        if number < 0:
            raise InputError(f"{key} must be nonnegative")
        result[key] = number
    return result


def load_pricing(path):
    """Load explicit per-million-token prices; return Decimal rates."""
    return validate_pricing(load_json(path, MAX_LINE_BYTES))
